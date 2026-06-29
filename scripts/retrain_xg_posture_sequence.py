#!/usr/bin/env python3
import datetime
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = '/opt/app/project/main'
MODULE_PATH = os.path.join(PROJECT_ROOT, 'src', 'model', 'struct', 'video_analysis.py')
REPORT_DIR = Path(PROJECT_ROOT) / 'outputs' / 'model_optimization'
REPORT_PATH = REPORT_DIR / 'xg_posture_sequence_training_report.json'
PROGRESS_PATH = REPORT_DIR / 'xg_posture_sequence_training_progress.log'


CLASSES = ['stand', 'walk', 'run', 'sit', 'lie']
LOWER_OCCLUSION_MODES = ['waist', 'thigh', 'knee']
VERTICAL_OCCLUSION_MODES = ['left', 'right']
RANDOM_LOWER_OCCLUSION_MODES = ['random_mild', 'random_moderate', 'random_severe']
RANDOM_VERTICAL_OCCLUSION_MODES = [
    'left_mild', 'left_moderate', 'left_severe',
    'right_mild', 'right_moderate', 'right_severe',
]
LOWER_BODY_KP = {11, 12, 13, 14, 15, 16}
LOWER_DISTAL_KP = {13, 14, 15, 16}
ANKLE_KP = {15, 16}
LEFT_BODY_KP = {5, 7, 9, 11, 13, 15}
RIGHT_BODY_KP = {6, 8, 10, 12, 14, 16}
LOWER_OCCLUSION_BOUNDARIES = {
    'mild': (0.70, 0.84),
    'moderate': (0.55, 0.70),
    'severe': (0.42, 0.58),
}
VERTICAL_OCCLUSION_EXTENTS = {
    'mild': (0.18, 0.30),
    'moderate': (0.30, 0.45),
    'severe': (0.45, 0.58),
}


class _Fs:
    def abspath(self):
        return PROJECT_ROOT


class _Project:
    def fs(self):
        return _Fs()


class _Wiz:
    project = _Project()


def log(message):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    line = f'[{stamp}] {message}'
    print(line, flush=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with PROGRESS_PATH.open('a', encoding='utf-8') as file:
        file.write(line + '\n')


def env_int(name, default):
    try:
        return int(os.environ.get(name, default) or default)
    except Exception:
        return int(default)


def env_float(name, default):
    try:
        return float(os.environ.get(name, default) or default)
    except Exception:
        return float(default)


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def stable_unit(*parts):
    raw = '|'.join(str(part) for part in parts).encode('utf-8', errors='ignore')
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def parse_modes(raw, default_modes, allowed_modes):
    values = [item.strip() for item in str(raw or '').split(',') if item.strip()]
    if not values:
        values = list(default_modes)
    allowed = set(allowed_modes)
    selected = [mode for mode in values if mode in allowed]
    return selected or list(default_modes)


def parse_class_weight_multipliers(class_names):
    raw = str(os.environ.get('POSTURE_CLASS_WEIGHT_MULTIPLIERS') or '').strip()
    multipliers = {name: 1.0 for name in class_names}
    if not raw:
        return multipliers
    for item in raw.split(','):
        if ':' not in item:
            continue
        name, value = item.split(':', 1)
        name = name.strip()
        if name not in multipliers:
            continue
        try:
            multipliers[name] = max(0.05, float(value.strip()))
        except Exception:
            continue
    return multipliers


def apply_class_weight_multipliers(weights, y, class_names, multipliers):
    import numpy as np

    adjusted = np.asarray(weights, dtype=float).copy()
    for idx, class_name in enumerate(class_names):
        multiplier = float(multipliers.get(class_name, 1.0) or 1.0)
        if abs(multiplier - 1.0) < 1e-9:
            continue
        adjusted[np.asarray(y) == idx] *= multiplier
    return adjusted


def load_video_analysis():
    spec = importlib.util.spec_from_file_location('project_video_analysis_sequence', MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load module: {MODULE_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.wiz = _Wiz()
    return module.VideoAnalysis(None)


def infer_group_id(row):
    explicit_group = row.get('group_id')
    if explicit_group is not None:
        explicit_group = str(explicit_group).strip()
        if explicit_group and explicit_group.lower() not in ('nan', 'none', 'null'):
            return explicit_group
    video = str(row.get('video', '') or '')
    source = str(row.get('source', '') or '')
    if video.startswith('aihub61occ:'):
        base = video.rsplit(':w', 1)[0]
        parts = base.split(':', 2)
        if len(parts) >= 3:
            return 'aihub61seq:' + parts[2]
        return base
    if video.startswith('aihub61vertocc:'):
        base = video.rsplit(':w', 1)[0]
        parts = base.split(':', 2)
        if len(parts) >= 3:
            return 'aihub61seq:' + parts[2]
        return base
    if video.startswith('aihub61seq:'):
        return video.rsplit(':w', 1)[0]
    if video.startswith('aihub62seq:'):
        return video.rsplit(':w', 1)[0]
    if video.startswith('aihub62raw:'):
        return video.rsplit(':w', 1)[0]
    if video.startswith('lowerocc:'):
        return video.rsplit(':w', 1)[0]
    if video.startswith('aihub61:'):
        rel = video.split(':', 1)[1]
        parts = [p for p in rel.split('/') if p]
        if len(parts) >= 2:
            return 'aihub61:' + '/'.join(parts[:2])
        return 'aihub61:' + (parts[0] if parts else 'unknown')
    name = os.path.basename(video)
    stem = re.sub(r'\.json$', '', name, flags=re.IGNORECASE)
    stem = re.sub(r'_person\(person\).*$', '', stem)
    match = re.match(r'^(IMG|VID)_(\d+)', stem)
    if match:
        prefix, number = match.group(1), int(match.group(2))
        return f'{source}:{prefix}:{number // 100:06d}'
    return f'{source}:{stem or video}'


def _frame_from_aihub61_json(va, data, name, frame_idx):
    image_meta = {}
    if isinstance(data.get('metadata'), dict):
        image_meta = dict(data.get('metadata') or {})
    elif isinstance(data.get('images'), list) and data.get('images'):
        image_meta = dict(data.get('images')[0] or {})
    width = float(image_meta.get('width', 0) or 0)
    height = float(image_meta.get('height', 0) or 0)
    if width <= 0 or height <= 0:
        return None

    best = None
    best_area = -1.0
    for ann in data.get('annotations', []) or []:
        coco = va._aihub61_convert_keypoints_to_coco17(ann.get('keypoints'), ann.get('invisible_keys', []))
        if len(coco) < 51:
            continue
        bbox = list(ann.get('bbox', []) or [])
        if len(bbox) < 4:
            bbox = va._aihub61_infer_bbox_from_keypoints(coco, width, height)
        if len(bbox) < 4:
            continue
        bx, by, bw, bh = [float(v or 0.0) for v in bbox[:4]]
        area = bw * bh
        if area > best_area:
            best_area = area
            best = (coco, bx, by, bw, bh)
    if best is None:
        return None

    coco, bx, by, bw, bh = best
    kps = []
    for idx in range(0, 51, 3):
        conf = float(coco[idx + 2] or 0.0) / 2.0
        kps.append({
            'x': float(coco[idx] or 0.0) / width,
            'y': float(coco[idx + 1] or 0.0) / height,
            'conf': conf,
        })
    return {
        'frame_idx': frame_idx,
        'time_sec': frame_idx / 30.0,
        'bbox': {
            'cx': (bx + bw / 2.0) / width,
            'cy': (by + bh / 2.0) / height,
            'w': bw / width,
            'h': bh / height,
            'aspect_ratio': (bw / width) / ((bh / height) + 1e-9),
            'area': (bw / width) * (bh / height),
            'conf': 1.0,
        },
        'keypoints': kps,
    }


def _iter_aihub61_clip_jsons(source_path):
    source_path = str(source_path or '')
    if os.path.isfile(source_path) and source_path.endswith('.zip'):
        try:
            archive = zipfile.ZipFile(source_path)
        except zipfile.BadZipFile as exc:
            log(f'aihub61 zip skip source={source_path} reason=bad_zip:{str(exc)[:140]}')
            return
        except Exception as exc:
            log(f'aihub61 zip skip source={source_path} reason={type(exc).__name__}:{str(exc)[:140]}')
            return
        with archive:
            by_clip = defaultdict(list)
            for name in archive.namelist():
                if not name.endswith('.json') or '/._' in name or os.path.basename(name).startswith('._'):
                    continue
                by_clip[os.path.dirname(name)].append(name)
            if not by_clip:
                log(f'aihub61 zip skip source={source_path} reason=no_json_labels')
            for clip_id in sorted(by_clip):
                frames = []
                for name in sorted(by_clip[clip_id]):
                    try:
                        data = json.loads(archive.read(name).decode('utf-8'))
                    except Exception:
                        continue
                    frames.append((name, data))
                if frames:
                    yield clip_id, frames
        return

    if os.path.isdir(source_path):
        for root, _dirs, files in os.walk(source_path):
            json_names = [
                name for name in files
                if name.endswith('.json') and not name.startswith('._')
            ]
            if not json_names:
                continue
            clip_id = os.path.relpath(root, source_path).replace(os.sep, '/')
            frames = []
            for name in sorted(json_names):
                path = os.path.join(root, name)
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                except Exception:
                    continue
                rel_name = os.path.relpath(path, source_path).replace(os.sep, '/')
                frames.append((rel_name, data))
            if frames:
                yield clip_id, frames


def _valid_local_zip_header_at(file, offset, file_size):
    if offset < 0 or offset + 30 > file_size:
        return False
    here = file.tell()
    try:
        file.seek(offset)
        if file.read(4) != b'PK\x03\x04':
            return False
        header = file.read(26)
        if len(header) < 26:
            return False
        import struct

        _version, _flag, method, _mtime, _mdate, _crc, _csize, _usize, name_len, extra_len = struct.unpack('<HHHHHIIIHH', header)
        if method not in {0, 8} or name_len <= 0 or name_len > 4096:
            return False
        if offset + 30 + name_len + extra_len > file_size:
            return False
        raw_name = file.read(name_len)
        return bool(raw_name and b'\x00' not in raw_name)
    finally:
        file.seek(here)


def _find_next_local_zip_header(file, start_offset, file_size):
    chunk_size = 1024 * 1024
    overlap = b''
    pos = start_offset
    while pos < file_size:
        file.seek(pos)
        chunk = file.read(min(chunk_size, file_size - pos))
        if not chunk:
            break
        data = overlap + chunk
        search_from = 0
        while True:
            idx = data.find(b'PK\x03\x04', search_from)
            if idx < 0:
                break
            candidate = pos - len(overlap) + idx
            if candidate > start_offset and _valid_local_zip_header_at(file, candidate, file_size):
                return candidate
            search_from = idx + 1
        if len(chunk) < chunk_size:
            break
        overlap = data[-3:]
        pos += len(chunk)
    return None


def _local_zip_ply_index(source_path):
    import struct

    members = []
    source_path = str(source_path or '')
    try:
        size = os.path.getsize(source_path)
        with open(source_path, 'rb') as file:
            while file.tell() + 30 <= size:
                sig = file.read(4)
                if sig != b'PK\x03\x04':
                    break
                header = file.read(26)
                if len(header) < 26:
                    break
                _version, flag, method, _mtime, _mdate, _crc, csize, usize, name_len, extra_len = struct.unpack('<HHHHHIIIHH', header)
                raw_name = file.read(name_len)
                file.seek(extra_len, os.SEEK_CUR)
                data_offset = file.tell()
                try:
                    name = raw_name.decode('utf-8' if flag & 0x800 else 'cp437', errors='replace')
                except Exception:
                    name = raw_name.decode('utf-8', errors='replace')
                if csize > 0:
                    data_size = int(csize)
                    next_offset = data_offset + data_size
                elif method == 0 and name.endswith('/'):
                    data_size = 0
                    next_offset = data_offset
                else:
                    found_next = _find_next_local_zip_header(file, data_offset, size)
                    next_offset = found_next if found_next is not None else size
                    data_size = max(0, int(next_offset - data_offset))
                if name.lower().endswith('.ply') and method in {0, 8} and data_size > 0:
                    members.append({
                        'name': name,
                        'offset': data_offset,
                        'size': data_size,
                        'compressed': method == 8,
                    })
                if next_offset <= data_offset:
                    continue
                file.seek(next_offset, os.SEEK_SET)
    except Exception as exc:
        log(f'aihub61 local-zip scan skip source={source_path} reason={type(exc).__name__}:{str(exc)[:140]}')
    return members


def _ply_clip_key(name):
    directory = os.path.dirname(str(name or '')).replace('\\', '/')
    stem = re.sub(r'\.ply$', '', os.path.basename(str(name or '')), flags=re.IGNORECASE)
    stem = re.sub(r'_[0-9]+$', '', stem)
    return f'{directory}/{stem}'.strip('/') or stem or 'unknown'


def _evenly_spaced(items, limit):
    items = list(items or [])
    limit = int(limit or 0)
    if limit <= 0 or len(items) <= limit:
        return items
    if limit == 1:
        return [items[len(items) // 2]]
    indexes = sorted({round(i * (len(items) - 1) / (limit - 1)) for i in range(limit)})
    return [items[int(idx)] for idx in indexes]


def _ply_bounds_from_bytes(raw, max_points=None):
    max_points = int(max_points or env_int('POSTURE_AIHUB61_PLY_MAX_POINTS', 1200))
    try:
        text = raw.decode('utf-8', errors='ignore')
    except Exception:
        return None
    lines = text.splitlines()
    vertex_count = 0
    body_start = 0
    for idx, line in enumerate(lines[:80]):
        if line.startswith('element vertex'):
            try:
                vertex_count = int(line.split()[-1])
            except Exception:
                vertex_count = 0
        if line.strip() == 'end_header':
            body_start = idx + 1
            break
    body = lines[body_start:]
    if not body:
        return None
    if vertex_count <= 0:
        vertex_count = len(body)
    stride = max(1, vertex_count // max(max_points, 1))
    xs, ys, zs = [], [], []
    for idx, line in enumerate(body[:vertex_count]):
        if idx % stride:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
        except Exception:
            continue
        xs.append(x)
        ys.append(y)
        zs.append(z)
    if len(xs) < 20 or len(ys) < 20 or len(zs) < 20:
        return None
    return {
        'x_min': min(xs), 'x_max': max(xs),
        'y_min': min(ys), 'y_max': max(ys),
        'z_min': min(zs), 'z_max': max(zs),
        'n_points': len(xs),
    }


def _pseudo_keypoints_from_bbox(cx, y_top, w, h, conf=0.68):
    def point(x, y):
        return {'x': max(0.0, min(1.0, x)), 'y': max(0.0, min(1.0, y)), 'conf': conf}

    left = cx - w * 0.24
    right = cx + w * 0.24
    hip_left = cx - w * 0.18
    hip_right = cx + w * 0.18
    knee_left = cx - w * 0.16
    knee_right = cx + w * 0.16
    ankle_left = cx - w * 0.14
    ankle_right = cx + w * 0.14
    y_shoulder = y_top + h * 0.22
    y_elbow = y_top + h * 0.36
    y_wrist = y_top + h * 0.48
    y_hip = y_top + h * 0.54
    y_knee = y_top + h * 0.75
    y_ankle = y_top + h * 0.96
    return [
        point(cx, y_top + h * 0.04),
        point(cx - w * 0.04, y_top + h * 0.03),
        point(cx + w * 0.04, y_top + h * 0.03),
        point(cx - w * 0.08, y_top + h * 0.05),
        point(cx + w * 0.08, y_top + h * 0.05),
        point(left, y_shoulder),
        point(right, y_shoulder),
        point(left - w * 0.08, y_elbow),
        point(right + w * 0.08, y_elbow),
        point(left - w * 0.10, y_wrist),
        point(right + w * 0.10, y_wrist),
        point(hip_left, y_hip),
        point(hip_right, y_hip),
        point(knee_left, y_knee),
        point(knee_right, y_knee),
        point(ankle_left, y_ankle),
        point(ankle_right, y_ankle),
    ]


def _resample_ply_stats(stats_rows, target_frames):
    stats_rows = list(stats_rows or [])
    target_frames = int(target_frames or 0)
    if len(stats_rows) < 2 or target_frames <= len(stats_rows):
        return stats_rows

    fields = ['x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max', 'n_points']
    resampled = []
    for idx in range(target_frames):
        pos = idx * (len(stats_rows) - 1) / max(target_frames - 1, 1)
        left = int(math.floor(pos))
        right = min(left + 1, len(stats_rows) - 1)
        frac = pos - left
        row = {}
        for field in fields:
            start = float(stats_rows[left].get(field, 0.0) or 0.0)
            end = float(stats_rows[right].get(field, start) or start)
            row[field] = start + (end - start) * frac
        resampled.append(row)
    return resampled


def _frames_from_ply_bounds(stats_rows):
    if len(stats_rows) < 2:
        return []
    stats_rows = _resample_ply_stats(
        stats_rows,
        env_int('POSTURE_AIHUB61_PLY_RESAMPLED_FRAMES', 48),
    )
    x_range = max(row['x_max'] for row in stats_rows) - min(row['x_min'] for row in stats_rows)
    z_range = max(row['z_max'] for row in stats_rows) - min(row['z_min'] for row in stats_rows)
    axis = 'x' if x_range >= z_range else 'z'
    a_min = min(row[f'{axis}_min'] for row in stats_rows)
    a_max = max(row[f'{axis}_max'] for row in stats_rows)
    y_min = min(row['y_min'] for row in stats_rows)
    y_max = max(row['y_max'] for row in stats_rows)
    a_span = max(1e-6, a_max - a_min)
    y_span = max(1e-6, y_max - y_min)
    frames = []
    for idx, row in enumerate(stats_rows):
        lo = row[f'{axis}_min']
        hi = row[f'{axis}_max']
        cx = ((lo + hi) / 2.0 - a_min) / a_span
        w = max(0.02, min(1.0, (hi - lo) / a_span))
        y_top = 1.0 - ((row['y_max'] - y_min) / y_span)
        y_bottom = 1.0 - ((row['y_min'] - y_min) / y_span)
        h = max(0.02, min(1.0, abs(y_bottom - y_top)))
        cy = max(0.0, min(1.0, (y_top + y_bottom) / 2.0))
        y_top = max(0.0, min(1.0, min(y_top, y_bottom)))
        bbox = {
            'cx': max(0.0, min(1.0, cx)),
            'cy': cy,
            'w': w,
            'h': h,
            'aspect_ratio': w / (h + 1e-9),
            'area': w * h,
            'conf': 0.72,
        }
        frames.append({
            'frame_idx': idx,
            'time_sec': idx / 10.0,
            'bbox': bbox,
            'keypoints': _pseudo_keypoints_from_bbox(bbox['cx'], y_top, w, h),
        })
    return frames


def _iter_aihub61_clip_ply_timeseries(source_path):
    source_path = str(source_path or '')
    frames_per_clip = max(8, env_int('POSTURE_AIHUB61_PLY_FRAMES_PER_CLIP', 14))
    grouped = defaultdict(list)
    zip_archive = None
    local_members = []

    if os.path.isfile(source_path) and zipfile.is_zipfile(source_path):
        try:
            zip_archive = zipfile.ZipFile(source_path)
            for name in zip_archive.namelist():
                if name.lower().endswith('.ply') and '/._' not in name and not os.path.basename(name).startswith('._'):
                    grouped[_ply_clip_key(name)].append({'name': name, 'source': 'zip'})
        except Exception as exc:
            log(f'aihub61 ply zip scan skip source={source_path} reason={type(exc).__name__}:{str(exc)[:140]}')
            zip_archive = None
    elif os.path.isfile(source_path):
        local_members = _local_zip_ply_index(source_path)
        for item in local_members:
            grouped[_ply_clip_key(item['name'])].append({**item, 'source': 'local'})
    elif os.path.isdir(source_path):
        for root, _dirs, files in os.walk(source_path):
            for file_name in files:
                if not file_name.lower().endswith('.ply') or file_name.startswith('._'):
                    continue
                path = os.path.join(root, file_name)
                rel = os.path.relpath(path, source_path).replace(os.sep, '/')
                grouped[_ply_clip_key(rel)].append({'name': rel, 'path': path, 'source': 'file'})

    if not grouped:
        return
    log(
        f'aihub61 ply fallback source={source_path} '
        f'clips={len(grouped)} frames_per_clip={frames_per_clip} '
        f'resampled_frames={env_int("POSTURE_AIHUB61_PLY_RESAMPLED_FRAMES", 48)} '
        f'local_members={len(local_members)}'
    )

    def read_member(item):
        if item['source'] == 'zip' and zip_archive is not None:
            return zip_archive.read(item['name'])
        if item['source'] == 'local':
            with open(source_path, 'rb') as file:
                file.seek(int(item['offset']))
                raw = file.read(int(item['size']))
            if item.get('compressed'):
                decompressor = zlib.decompressobj(-15)
                return decompressor.decompress(raw) + decompressor.flush()
            return raw
        with open(item['path'], 'rb') as file:
            return file.read()

    try:
        for clip_id in sorted(grouped):
            selected = _evenly_spaced(sorted(grouped[clip_id], key=lambda row: row['name']), frames_per_clip)
            stats_rows = []
            for item in selected:
                try:
                    stats = _ply_bounds_from_bytes(read_member(item))
                except Exception:
                    stats = None
                if stats is not None:
                    stats_rows.append(stats)
            timeseries = _frames_from_ply_bounds(stats_rows)
            if timeseries:
                yield clip_id, timeseries
    finally:
        if zip_archive is not None:
            zip_archive.close()


def _iter_aihub61_clip_timeseries(va, source_path):
    yielded = False
    for clip_id, frame_items in _iter_aihub61_clip_jsons(source_path):
        timeseries = []
        for frame_idx, (name, data) in enumerate(frame_items):
            frame = _frame_from_aihub61_json(va, data, name, frame_idx)
            if frame is not None:
                timeseries.append(frame)
        if timeseries:
            yielded = True
            yield clip_id, timeseries
    if yielded:
        return
    for clip_id, timeseries in _iter_aihub61_clip_ply_timeseries(source_path):
        yield clip_id, timeseries


def _motion_score(window):
    return (
        float(window.get('center_dx_abs_mean', 0.0) or 0.0)
        + float(window.get('speed_std', 0.0) or 0.0) * 3.0
        + float(window.get('pose_change_mean', 0.0) or 0.0) * 10.0
        + float(window.get('center_y_periodicity', 0.0) or 0.0) * 0.25
    )


def _steady_score(window):
    return (
        float(window.get('stillness', 0.0) or 0.0) * 2.0
        + float(window.get('post_descent_stillness', 0.0) or 0.0)
        + float(window.get('lower_body_visibility', 0.0) or 0.0) * 0.35
        - float(window.get('center_dx_abs_mean', 0.0) or 0.0) * 1.5
        - float(window.get('speed_std', 0.0) or 0.0) * 3.0
        - float(window.get('pose_change_mean', 0.0) or 0.0) * 6.0
    )


def _sit_score(window):
    knee_bend = max(0.0, min(180.0, float(window.get('pose_knee_bend_mean', 180.0) or 180.0)))
    return (
        float(window.get('bent_leg_ratio', 0.0) or 0.0) * 2.6
        + (1.0 - knee_bend / 180.0) * 1.3
        + float(window.get('floor_proximity', 0.0) or 0.0) * 0.45
        + float(window.get('stillness', 0.0) or 0.0) * 0.65
        - float(window.get('center_dx_abs_mean', 0.0) or 0.0) * 0.9
        - float(window.get('speed_std', 0.0) or 0.0) * 1.8
    )


def _lie_score(window):
    pose_height_min = max(0.0, min(1.0, float(window.get('pose_height_ratio_min', 1.0) or 1.0)))
    vert_horiz = max(0.0, float(window.get('vert_horiz_ratio', 0.0) or 0.0))
    return (
        float(window.get('pose_spread_mean', 0.0) or 0.0) * 3.0
        + float(window.get('pose_spread_max', 0.0) or 0.0) * 2.0
        + (1.0 - pose_height_min) * 1.4
        + float(window.get('floor_proximity', 0.0) or 0.0) * 0.8
        + float(window.get('stillness', 0.0) or 0.0) * 0.45
        - min(2.0, vert_horiz) * 0.18
        - float(window.get('center_dx_abs_mean', 0.0) or 0.0) * 0.5
    )


def select_sequence_windows(label, windows, windows_per_clip):
    ranked_motion = sorted(range(len(windows)), key=lambda idx: _motion_score(windows[idx]), reverse=True)
    ranked_steady = sorted(range(len(windows)), key=lambda idx: _steady_score(windows[idx]), reverse=True)
    anchors = [0, len(windows) // 2, len(windows) - 1]
    if label == 'stand':
        pools = [ranked_steady, anchors, ranked_motion[:1]]
    elif label in ('walk', 'run'):
        pools = [ranked_motion, anchors, ranked_steady[:2]]
    elif label == 'sit':
        ranked_sit = sorted(range(len(windows)), key=lambda idx: _sit_score(windows[idx]), reverse=True)
        pools = [ranked_sit, ranked_steady, anchors, ranked_motion[:1]]
    elif label == 'lie':
        ranked_lie = sorted(range(len(windows)), key=lambda idx: _lie_score(windows[idx]), reverse=True)
        pools = [ranked_lie, ranked_steady, anchors, ranked_motion[:1]]
    else:
        pools = [ranked_motion, anchors]

    selected = []
    while len(selected) < windows_per_clip and any(pools):
        for pool in pools:
            while pool and pool[0] in selected:
                pool.pop(0)
            if pool:
                selected.append(pool.pop(0))
                if len(selected) >= windows_per_clip:
                    break
        pools = [pool for pool in pools if pool]
    return selected[:windows_per_clip]


def load_hitl_posture_intake_rows(va, feature_cols, windows_per_clip=3):
    intake_root = Path(va._training_dir())
    rows = []
    counts = Counter()
    clip_counts = Counter()
    skipped = []
    used_files = []
    video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
    target_fps = max(2, env_int('POSTURE_HITL_TARGET_FPS', 6))
    if not intake_root.exists():
        return {
            'rows': rows,
            'counts': {},
            'clip_counts': {},
            'used_files': [],
            'skipped': [],
            'intake_root': str(intake_root),
        }

    for label in CLASSES:
        class_dir = intake_root / label
        if not class_dir.is_dir():
            continue
        for path in sorted(class_dir.iterdir()):
            if path.name.startswith('.') or path.suffix.lower() == '.json' or path.suffix.lower() not in video_exts:
                continue
            try:
                extracted = va._extract_unified_timeseries(
                    str(path),
                    input_source='file',
                    target_fps_override=target_fps,
                )
                windows = va._build_xg_feature_windows(
                    extracted.get('timeseries', []),
                    extracted.get('vid_meta', {}),
                    window_sec=1.5,
                    stride_sec=0.5,
                )
                if not windows:
                    skipped.append({'video': path.name, 'class': label, 'reason': 'no valid windows'})
                    continue
                selected = select_sequence_windows(label, windows, windows_per_clip)
                for win_idx in selected:
                    row = {
                        'video': f'hitl:{label}:{path.name}:w{win_idx}',
                        'group_id': f'hitl:{label}:{path.stem}',
                        'posture': label,
                        'source': 'hitl-posture-intake',
                    }
                    for col in feature_cols:
                        row[col] = float(windows[win_idx].get(col, 0.0) or 0.0)
                    rows.append(row)
                    counts[label] += 1
                clip_counts[label] += 1
                used_files.append(str(path))
            except Exception as exc:
                skipped.append({'video': path.name, 'class': label, 'reason': str(exc)})
    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'used_files': used_files,
        'skipped': skipped[:100],
        'intake_root': str(intake_root),
        'target_fps': target_fps,
        'windows_per_clip': windows_per_clip,
    }


def load_aihub61_sequence_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=4):
    limits = dict(class_clip_limits or {'walk': 180, 'run': 180, 'sit': 180, 'lie': 180})
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_sources = []
    for label, source_path in va._aihub61_label_zip_paths():
        if label not in limits or limits[label] <= 0:
            continue
        if clip_counts[label] >= limits[label]:
            continue
        used_sources.append(source_path)
        log(f'aihub61 sequence scan label={label} source={source_path}')
        for clip_id, timeseries in _iter_aihub61_clip_timeseries(va, source_path):
            if clip_counts[label] >= limits[label]:
                break
            scanned_clips[label] += 1
            if len(timeseries) < 8:
                continue
            windows = va._build_xg_feature_windows(
                timeseries,
                {'width': 1920, 'height': 1080, 'fps': 30.0},
                window_sec=1.5,
                stride_sec=0.75,
            )
            if not windows:
                continue
            selected = select_sequence_windows(label, windows, windows_per_clip)
            for seq_idx, win_idx in enumerate(selected):
                row = {
                    'video': f'aihub61seq:{clip_id}:w{win_idx}',
                    'posture': label,
                    'source': 'external-aihub61-sequence',
                }
                for col in feature_cols:
                    row[col] = float(windows[win_idx].get(col, 0.0) or 0.0)
                rows.append(row)
                counts[label] += 1
            clip_counts[label] += 1
        log(f'aihub61 sequence label={label} clips={clip_counts[label]} rows={counts[label]}')
    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'scanned_clips': dict(scanned_clips),
        'zip_files': used_sources,
    }


def _copy_frame(frame):
    return {
        'frame_idx': frame.get('frame_idx', 0),
        'time_sec': frame.get('time_sec', 0.0),
        'bbox': dict(frame.get('bbox') or {}),
        'keypoints': [dict(point or {}) for point in (frame.get('keypoints') or [])],
    }


def _apply_visible_bbox(frame, padding=0.035):
    points = [
        point for point in frame.get('keypoints', [])
        if float(point.get('conf', 0.0) or 0.0) > 0.05
        and 0.0 <= float(point.get('x', 0.0) or 0.0) <= 1.0
        and 0.0 <= float(point.get('y', 0.0) or 0.0) <= 1.0
    ]
    if len(points) < 2:
        return frame
    xs = [float(point.get('x', 0.0) or 0.0) for point in points]
    ys = [float(point.get('y', 0.0) or 0.0) for point in points]
    x1 = max(0.0, min(xs) - padding)
    y1 = max(0.0, min(ys) - padding)
    x2 = min(1.0, max(xs) + padding)
    y2 = min(1.0, max(ys) + padding)
    w = max(0.02, x2 - x1)
    h = max(0.02, y2 - y1)
    bbox = dict(frame.get('bbox') or {})
    bbox.update({
        'cx': x1 + w / 2.0,
        'cy': y1 + h / 2.0,
        'w': w,
        'h': h,
        'aspect_ratio': w / (h + 1e-9),
        'area': w * h,
        'conf': max(0.05, float(bbox.get('conf', 1.0) or 1.0) * 0.90),
    })
    frame['bbox'] = bbox
    return frame


def _lower_random_severity(mode):
    if 'mild' in mode:
        return 'mild'
    if 'severe' in mode:
        return 'severe'
    return 'moderate'


def _occlude_lower_body_frame(frame, mode, seed_tag=''):
    item = _copy_frame(frame)
    if mode.startswith('random_'):
        severity = _lower_random_severity(mode)
        lo, hi = LOWER_OCCLUSION_BOUNDARIES[severity]
        frame_idx = int(float(item.get('frame_idx', 0) or 0))
        clip_bucket = frame_idx // 8
        boundary = lo + (hi - lo) * stable_unit(seed_tag, mode, clip_bucket)
        soft_band = 0.08 if severity != 'severe' else 0.12
        for idx, point in enumerate(item.get('keypoints') or []):
            if idx not in LOWER_BODY_KP:
                continue
            y = float(point.get('y', 0.0) or 0.0)
            if y >= boundary:
                point['conf'] = 0.0
            elif y >= max(0.0, boundary - soft_band):
                fade = 0.20 + 0.35 * stable_unit(seed_tag, mode, frame_idx, idx)
                point['conf'] = float(point.get('conf', 0.0) or 0.0) * fade
        bbox = dict(item.get('bbox') or {})
        bbox['conf'] = max(0.05, float(bbox.get('conf', 1.0) or 1.0) * {'mild': 0.88, 'moderate': 0.78, 'severe': 0.64}[severity])
        item['bbox'] = bbox
        return _apply_visible_bbox(item, padding=0.025)
    if mode == 'waist':
        hidden = LOWER_BODY_KP
        softened = {}
    elif mode == 'thigh':
        hidden = LOWER_DISTAL_KP
        softened = {11: 0.45, 12: 0.45}
    else:
        hidden = ANKLE_KP
        softened = {13: 0.55, 14: 0.55}

    for idx, point in enumerate(item.get('keypoints') or []):
        if idx in hidden:
            point['conf'] = 0.0
        elif idx in softened:
            point['conf'] = float(point.get('conf', 0.0) or 0.0) * softened[idx]
    return _apply_visible_bbox(item)


def _occlude_lower_body_timeseries(timeseries, mode, seed_tag=''):
    return [_occlude_lower_body_frame(frame, mode, seed_tag=seed_tag) for frame in timeseries]


def _vertical_side_and_severity(mode):
    side = 'right' if str(mode).startswith('right') else 'left'
    if 'mild' in mode:
        severity = 'mild'
    elif 'severe' in mode:
        severity = 'severe'
    else:
        severity = 'moderate'
    return side, severity


def _occlude_vertical_body_frame(frame, mode, seed_tag=''):
    item = _copy_frame(frame)
    if mode in RANDOM_VERTICAL_OCCLUSION_MODES:
        side, severity = _vertical_side_and_severity(mode)
        lo, hi = VERTICAL_OCCLUSION_EXTENTS[severity]
        frame_idx = int(float(item.get('frame_idx', 0) or 0))
        clip_bucket = frame_idx // 8
        extent = lo + (hi - lo) * stable_unit(seed_tag, mode, clip_bucket)
        boundary = extent if side == 'left' else 1.0 - extent
        soft_band = 0.08 if severity != 'severe' else 0.12
        for idx, point in enumerate(item.get('keypoints') or []):
            x = float(point.get('x', 0.5) or 0.5)
            hidden = x <= boundary if side == 'left' else x >= boundary
            softened = (boundary < x <= boundary + soft_band) if side == 'left' else (boundary - soft_band <= x < boundary)
            if hidden:
                point['conf'] = 0.0
            elif softened:
                fade = 0.25 + 0.40 * stable_unit(seed_tag, mode, frame_idx, idx)
                point['conf'] = float(point.get('conf', 0.0) or 0.0) * fade
        bbox = dict(item.get('bbox') or {})
        bbox['conf'] = max(0.05, float(bbox.get('conf', 1.0) or 1.0) * {'mild': 0.86, 'moderate': 0.72, 'severe': 0.58}[severity])
        item['bbox'] = bbox
        return _apply_visible_bbox(item, padding=0.02)
    if mode == 'left':
        hidden = LEFT_BODY_KP
        softened = {6: 0.70, 8: 0.75, 10: 0.80, 12: 0.70, 14: 0.75, 16: 0.80}
    elif mode == 'right':
        hidden = RIGHT_BODY_KP
        softened = {5: 0.70, 7: 0.75, 9: 0.80, 11: 0.70, 13: 0.75, 15: 0.80}
    else:
        hidden = set()
        softened = {}
    for idx, point in enumerate(item.get('keypoints') or []):
        if idx in hidden:
            point['conf'] = 0.0
        elif idx in softened:
            point['conf'] = float(point.get('conf', 0.0) or 0.0) * softened[idx]
    return _apply_visible_bbox(item, padding=0.025)


def _occlude_vertical_body_timeseries(timeseries, mode, seed_tag=''):
    return [_occlude_vertical_body_frame(frame, mode, seed_tag=seed_tag) for frame in timeseries]


def load_aihub61_lower_occlusion_sequence_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=2, modes=None):
    limits = dict(class_clip_limits or {'walk': 48, 'run': 48, 'sit': 48, 'lie': 48})
    allowed_modes = LOWER_OCCLUSION_MODES + RANDOM_LOWER_OCCLUSION_MODES
    default_modes = parse_modes(
        os.environ.get('POSTURE_SYNTH_LOWER_OCCLUSION_MODES', 'waist,thigh,knee,random_mild,random_moderate,random_severe'),
        LOWER_OCCLUSION_MODES + RANDOM_LOWER_OCCLUSION_MODES,
        allowed_modes,
    )
    selected_modes = parse_modes(','.join(modes or []), default_modes, allowed_modes) if modes else default_modes
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_sources = []
    for label, source_path in va._aihub61_label_zip_paths():
        if label not in limits or limits[label] <= 0:
            continue
        if clip_counts[label] >= limits[label]:
            continue
        used_sources.append(source_path)
        log(f'aihub61 lower-occlusion scan label={label} source={source_path} modes={",".join(selected_modes)}')
        for clip_id, timeseries in _iter_aihub61_clip_timeseries(va, source_path):
            if clip_counts[label] >= limits[label]:
                break
            scanned_clips[label] += 1
            if len(timeseries) < 8:
                continue

            accepted = False
            for mode in selected_modes:
                occluded = _occlude_lower_body_timeseries(timeseries, mode, seed_tag=clip_id)
                windows = va._build_xg_feature_windows(
                    occluded,
                    {'width': 1920, 'height': 1080, 'fps': 30.0},
                    window_sec=1.5,
                    stride_sec=0.75,
                )
                if not windows:
                    continue
                selected = select_sequence_windows(label, windows, windows_per_clip)
                for seq_idx, win_idx in enumerate(selected):
                    row = {
                        'video': f'aihub61occ:{mode}:{clip_id}:w{win_idx}',
                        'posture': label,
                        'source': 'external-aihub61-lower-occlusion',
                        'augmentation': f'lower_body_{mode}_occlusion',
                    }
                    for col in feature_cols:
                        row[col] = float(windows[win_idx].get(col, 0.0) or 0.0)
                    rows.append(row)
                    counts[label] += 1
                accepted = accepted or bool(selected)
            if accepted:
                clip_counts[label] += 1
        log(f'aihub61 lower-occlusion label={label} clips={clip_counts[label]} rows={counts[label]}')
    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'scanned_clips': dict(scanned_clips),
        'zip_files': used_sources,
        'modes': selected_modes,
    }


def load_aihub61_vertical_occlusion_sequence_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=2, modes=None):
    limits = dict(class_clip_limits or {'walk': 36, 'run': 36, 'sit': 36, 'lie': 36})
    allowed_modes = VERTICAL_OCCLUSION_MODES + RANDOM_VERTICAL_OCCLUSION_MODES
    default_modes = parse_modes(
        os.environ.get('POSTURE_SYNTH_VERTICAL_OCCLUSION_MODES', 'left,right,left_mild,left_moderate,left_severe,right_mild,right_moderate,right_severe'),
        VERTICAL_OCCLUSION_MODES + RANDOM_VERTICAL_OCCLUSION_MODES,
        allowed_modes,
    )
    selected_modes = parse_modes(','.join(modes or []), default_modes, allowed_modes) if modes else default_modes
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_sources = []
    for label, source_path in va._aihub61_label_zip_paths():
        if label not in limits or limits[label] <= 0:
            continue
        if clip_counts[label] >= limits[label]:
            continue
        used_sources.append(source_path)
        log(f'aihub61 vertical-occlusion scan label={label} source={source_path} modes={",".join(selected_modes)}')
        for clip_id, timeseries in _iter_aihub61_clip_timeseries(va, source_path):
            if clip_counts[label] >= limits[label]:
                break
            scanned_clips[label] += 1
            if len(timeseries) < 8:
                continue

            accepted = False
            for mode in selected_modes:
                occluded = _occlude_vertical_body_timeseries(timeseries, mode, seed_tag=clip_id)
                windows = va._build_xg_feature_windows(
                    occluded,
                    {'width': 1920, 'height': 1080, 'fps': 30.0},
                    window_sec=1.5,
                    stride_sec=0.75,
                )
                if not windows:
                    continue
                selected = select_sequence_windows(label, windows, windows_per_clip)
                for seq_idx, win_idx in enumerate(selected):
                    row = {
                        'video': f'aihub61vertocc:{mode}:{clip_id}:w{win_idx}',
                        'posture': label,
                        'source': 'external-aihub61-vertical-occlusion',
                        'augmentation': f'vertical_body_{mode}_occlusion',
                    }
                    for col in feature_cols:
                        row[col] = float(windows[win_idx].get(col, 0.0) or 0.0)
                    rows.append(row)
                    counts[label] += 1
                accepted = accepted or bool(selected)
            if accepted:
                clip_counts[label] += 1
        log(f'aihub61 vertical-occlusion label={label} clips={clip_counts[label]} rows={counts[label]}')
    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'scanned_clips': dict(scanned_clips),
        'zip_files': used_sources,
        'modes': selected_modes,
    }


def build_static_lower_occlusion_rows(static_rows, feature_cols, class_limits=None):
    limits = dict(class_limits or {'stand': 180, 'walk': 60, 'sit': 120, 'lie': 120})
    counts = Counter()
    rows = []
    for row in static_rows:
        label = str(row.get('posture') or '').strip()
        if label not in limits or counts[label] >= limits[label]:
            continue
        out = dict(row)
        out['video'] = f"staticlowerocc:{counts[label]}:{row.get('video', '')}"
        out['source'] = 'external-static-lower-body-occlusion'
        out['augmentation'] = 'static_lower_body_occlusion'
        out['group_id'] = infer_group_id(row)
        for col in feature_cols:
            out[col] = float(out.get(col, 0.0) or 0.0)

        for col in [
            'lower_body_visibility', 'straight_leg_ratio', 'support_leg_ratio',
            'ankle_width', 'knee_width', 'foot_y_diff', 'ankle_hip_ratio',
            'knee_asymmetry', 'lower_upper_width_ratio',
        ]:
            if col in out:
                out[col] = 0.0
        for col in ['pose_knee_bend_mean', 'pose_knee_bend_min', 'pose_knee_support_mean', 'pose_knee_support_min']:
            if col in out:
                out[col] = 180.0
        if 'avg_conf' in out:
            out['avg_conf'] = max(0.08, min(1.0, float(out.get('avg_conf', 0.0) or 0.0) * 0.82))
        if 'occlusion_ratio' in out:
            out['occlusion_ratio'] = max(float(out.get('occlusion_ratio', 0.0) or 0.0), 0.45)

        if label == 'stand':
            if 'upright_geometry_score' in out:
                out['upright_geometry_score'] = max(float(out.get('upright_geometry_score', 0.0) or 0.0), 0.72)
            for col in ['lie_geometry_score', 'flatness_score', 'horizontal_pose_score', 'horizontal_flat_pose_score', 'low_flat_still_score']:
                if col in out:
                    out[col] = float(out.get(col, 0.0) or 0.0) * 0.35
        elif label == 'sit':
            if 'sit_geometry_score' in out:
                out['sit_geometry_score'] = max(float(out.get('sit_geometry_score', 0.0) or 0.0), 0.35)
            if 'stationary_bent_score' in out:
                out['stationary_bent_score'] = max(float(out.get('stationary_bent_score', 0.0) or 0.0), 0.25)
        elif label == 'lie':
            if 'lie_geometry_score' in out:
                out['lie_geometry_score'] = max(float(out.get('lie_geometry_score', 0.0) or 0.0), 0.30)
            if 'horizontal_pose_score' in out:
                out['horizontal_pose_score'] = max(float(out.get('horizontal_pose_score', 0.0) or 0.0), 0.18)

        rows.append(out)
        counts[label] += 1
    log(f'static lower-body occlusion rows loaded={len(rows)} counts={dict(counts)}')
    return {'rows': rows, 'counts': dict(counts)}


def build_static_vertical_occlusion_rows(static_rows, feature_cols, class_limits=None, modes=None):
    limits = dict(class_limits or {'stand': 140, 'walk': 60, 'sit': 100, 'lie': 100})
    allowed_modes = VERTICAL_OCCLUSION_MODES + RANDOM_VERTICAL_OCCLUSION_MODES
    default_modes = parse_modes(
        os.environ.get('POSTURE_SYNTH_STATIC_VERTICAL_OCCLUSION_MODES', 'left,right,left_mild,left_moderate,left_severe,right_mild,right_moderate,right_severe'),
        ['left', 'right', 'left_mild', 'left_moderate', 'left_severe', 'right_mild', 'right_moderate', 'right_severe'],
        allowed_modes,
    )
    selected_modes = parse_modes(','.join(modes or []), default_modes, allowed_modes) if modes else default_modes
    counts = Counter()
    rows = []
    width_cols = [
        'shoulder_width', 'hip_width', 'ankle_width', 'wrist_width', 'knee_width',
        'pose_spread_mean', 'pose_spread_max', 'full_skeleton_aspect',
        'lower_upper_width_ratio', 'width_height_volume_proxy', 'pose_width_variability',
        'torso_width_ratio', 'apparent_depth_score',
    ]
    confidence_cols = ['avg_conf', 'lower_body_visibility', 'support_stability_score']
    for row in static_rows:
        label = str(row.get('posture') or '').strip()
        if label not in limits or counts[label] >= limits[label]:
            continue
        mode = selected_modes[counts[label] % len(selected_modes)]
        out = dict(row)
        out['video'] = f"staticvertocc:{mode}:{counts[label]}:{row.get('video', '')}"
        out['source'] = 'external-static-vertical-body-occlusion'
        out['augmentation'] = f'static_vertical_body_{mode}_occlusion'
        out['group_id'] = infer_group_id(row)
        out['vertical_occlusion_mode'] = mode
        for col in feature_cols:
            out[col] = float(out.get(col, 0.0) or 0.0)

        for col in width_cols:
            if col in out:
                out[col] = float(out.get(col, 0.0) or 0.0) * 0.58
        for col in confidence_cols:
            if col in out:
                out[col] = max(0.08, float(out.get(col, 0.0) or 0.0) * 0.68)
        if 'occlusion_ratio' in out:
            out['occlusion_ratio'] = max(float(out.get('occlusion_ratio', 0.0) or 0.0), 0.38)
        if 'body_compactness' in out:
            out['body_compactness'] = min(1.0, float(out.get('body_compactness', 0.0) or 0.0) * 1.18)
        if 'limb_extension_ratio' in out:
            out['limb_extension_ratio'] = float(out.get('limb_extension_ratio', 0.0) or 0.0) * 0.72

        if label == 'stand':
            if 'upright_geometry_score' in out:
                out['upright_geometry_score'] = max(float(out.get('upright_geometry_score', 0.0) or 0.0), 0.62)
            for col in ['lie_geometry_score', 'flatness_score', 'horizontal_pose_score', 'horizontal_flat_pose_score', 'low_flat_still_score']:
                if col in out:
                    out[col] = float(out.get(col, 0.0) or 0.0) * 0.42
        elif label == 'sit':
            if 'sit_geometry_score' in out:
                out['sit_geometry_score'] = max(float(out.get('sit_geometry_score', 0.0) or 0.0), 0.30)
            if 'stationary_bent_score' in out:
                out['stationary_bent_score'] = max(float(out.get('stationary_bent_score', 0.0) or 0.0), 0.20)
        elif label == 'lie':
            if 'lie_geometry_score' in out:
                out['lie_geometry_score'] = max(float(out.get('lie_geometry_score', 0.0) or 0.0), 0.26)
            if 'horizontal_pose_score' in out:
                out['horizontal_pose_score'] = max(float(out.get('horizontal_pose_score', 0.0) or 0.0), 0.14)

        rows.append(out)
        counts[label] += 1
    log(f'static vertical-body occlusion rows loaded={len(rows)} counts={dict(counts)} modes={selected_modes}')
    return {'rows': rows, 'counts': dict(counts), 'modes': selected_modes}


def build_static_walk_motion_prior_rows(static_rows, feature_cols, class_limit=90):
    """Recover walk signal when 71461 only provides isolated action-labelled frames."""
    variants = [
        ('slow_walk_prior', 0.050, 0.14, 0.035, 0.32),
        ('normal_walk_prior', 0.075, 0.21, 0.052, 0.50),
        ('occluded_walk_prior', 0.042, 0.12, 0.030, 0.26),
    ]
    rows = []
    counts = Counter()
    limit = int(class_limit or 0)
    if limit <= 0:
        return {'rows': rows, 'counts': {}}
    for row in static_rows:
        label = str(row.get('posture') or '').strip()
        if label != 'walk':
            continue
        for variant, center_dx, center_span, speed_std, gait_score in variants:
            if counts['walk'] >= limit:
                break
            out = dict(row)
            out['video'] = f"staticwalkprior:{variant}:{counts['walk']}:{row.get('video', '')}"
            out['source'] = 'external-static-walk-motion-prior'
            out['augmentation'] = variant
            out['group_id'] = infer_group_id(row)
            for col in feature_cols:
                out[col] = float(out.get(col, 0.0) or 0.0)

            out['stillness'] = min(float(out.get('stillness', 1.0) or 1.0), 0.38)
            out['center_dx_abs_mean'] = max(float(out.get('center_dx_abs_mean', 0.0) or 0.0), center_dx)
            out['center_x_span'] = max(float(out.get('center_x_span', 0.0) or 0.0), center_span)
            out['speed_std'] = max(float(out.get('speed_std', 0.0) or 0.0), speed_std)
            out['upper_body_motion'] = max(float(out.get('upper_body_motion', 0.0) or 0.0), center_dx * 0.55)
            out['horizontal_motion_energy'] = max(float(out.get('horizontal_motion_energy', 0.0) or 0.0), center_span * 1.1)
            out['vertical_motion_energy'] = max(float(out.get('vertical_motion_energy', 0.0) or 0.0), speed_std * 0.55)
            out['total_motion_energy'] = max(float(out.get('total_motion_energy', 0.0) or 0.0), center_span * 1.25)
            out['gait_dynamic_score'] = max(float(out.get('gait_dynamic_score', 0.0) or 0.0), gait_score)
            out['run_stride_score'] = min(max(float(out.get('run_stride_score', 0.0) or 0.0), gait_score * 0.28), 0.18)
            out['dynamic_pose_ratio'] = max(float(out.get('dynamic_pose_ratio', 0.0) or 0.0), 0.34)
            out['step_period_est'] = max(float(out.get('step_period_est', 0.0) or 0.0), 0.42)
            out['knee_angle_cycle_strength'] = max(float(out.get('knee_angle_cycle_strength', 0.0) or 0.0), 0.24)
            out['pre_descent_stillness'] = min(float(out.get('pre_descent_stillness', 1.0) or 1.0), 0.40)
            out['post_descent_stillness'] = min(float(out.get('post_descent_stillness', 1.0) or 1.0), 0.42)
            if 'upright_geometry_score' in out:
                out['upright_geometry_score'] = max(float(out.get('upright_geometry_score', 0.0) or 0.0), 0.58)
            for col in ['lie_geometry_score', 'flatness_score', 'horizontal_pose_score', 'horizontal_flat_pose_score', 'low_flat_still_score']:
                if col in out:
                    out[col] = float(out.get(col, 0.0) or 0.0) * 0.35
            rows.append(out)
            counts['walk'] += 1
    log(f'static walk motion-prior rows loaded={len(rows)} counts={dict(counts)}')
    return {'rows': rows, 'counts': dict(counts)}


AIHUB62_ACTION_TO_LABEL = {
    '1': 'walk',
    '2': 'run',
    '3': 'sit',
}


def _aihub62_annotation_zip_paths():
    root = Path('/opt/app/datasets/action_behavior/aihub_62_person_action_video')
    if not root.exists():
        return []
    return sorted(str(path) for path in root.rglob('anno_2D_tar.zip'))


def _aihub62_action_label(data):
    images = data.get('images') or []
    if isinstance(images, list) and images:
        category = str((images[0] or {}).get('action_category', '') or '').strip()
        return AIHUB62_ACTION_TO_LABEL.get(category, '')
    return ''


def _aihub62_convert_keypoints_to_coco17(raw_keypoints):
    flat = list(raw_keypoints or [])
    if len(flat) < 48:
        return []
    points = []
    for idx in range(16):
        base = idx * 3
        try:
            x = float(flat[base] or 0.0)
            y = float(flat[base + 1] or 0.0)
            conf = float(flat[base + 2] or 0.0)
        except Exception:
            x, y, conf = 0.0, 0.0, 0.0
        points.append((x, y, conf))

    # AI-Hub 62 2D order: R ankle/knee/hip, L hip/knee/ankle,
    # pelvis, thorax, neck, head_top, R wrist/elbow/shoulder, L shoulder/elbow/wrist.
    mapping = {
        0: 9,   # nose proxy: head top
        5: 13,  # left shoulder
        6: 12,  # right shoulder
        7: 14,  # left elbow
        8: 11,  # right elbow
        9: 15,  # left wrist
        10: 10,  # right wrist
        11: 3,  # left hip
        12: 2,  # right hip
        13: 4,  # left knee
        14: 1,  # right knee
        15: 5,  # left ankle
        16: 0,  # right ankle
    }
    coco = []
    for coco_idx in range(17):
        src_idx = mapping.get(coco_idx)
        if src_idx is None or src_idx >= len(points):
            coco.extend([0.0, 0.0, 0.0])
            continue
        x, y, conf = points[src_idx]
        coco.extend([x, y, conf])
    return coco


def _frame_no_from_aihub62_image(image):
    img_path = str((image or {}).get('img_path', '') or '')
    match = re.search(r'_(\d+)\.(?:jpg|png)$', img_path, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _frames_from_aihub62_json(data):
    images = data.get('images') or []
    annotations = data.get('annotations') or []
    if not isinstance(images, list) or not isinstance(annotations, list) or not images:
        return []

    anns_by_img = defaultdict(list)
    for ann in annotations:
        anns_by_img[ann.get('img_no')].append(ann)

    frames = []
    for seq_idx, image in enumerate(images):
        try:
            width = float((image or {}).get('width', 0) or 0)
            height = float((image or {}).get('height', 0) or 0)
        except Exception:
            width, height = 0.0, 0.0
        if width <= 0 or height <= 0:
            continue

        best = None
        best_area = -1.0
        for ann in anns_by_img.get((image or {}).get('img_no'), []):
            bbox = list(ann.get('bbox') or [])
            if len(bbox) < 4:
                continue
            coco = _aihub62_convert_keypoints_to_coco17(ann.get('keypoints'))
            if len(coco) < 51:
                continue
            bx, by, bw, bh = [float(v or 0.0) for v in bbox[:4]]
            area = bw * bh
            if area > best_area:
                best_area = area
                best = (coco, bx, by, bw, bh)
        if best is None:
            continue

        coco, bx, by, bw, bh = best
        frame_no = _frame_no_from_aihub62_image(image)
        if frame_no is None:
            frame_no = seq_idx * 10
        keypoints = []
        for idx in range(0, 51, 3):
            keypoints.append({
                'x': float(coco[idx] or 0.0) / width,
                'y': float(coco[idx + 1] or 0.0) / height,
                'conf': max(0.0, min(1.0, float(coco[idx + 2] or 0.0) / 2.0)),
            })
        frames.append({
            'frame_idx': int(frame_no),
            'time_sec': float(frame_no) / 30.0,
            'bbox': {
                'cx': (bx + bw / 2.0) / width,
                'cy': (by + bh / 2.0) / height,
                'w': bw / width,
                'h': bh / height,
                'aspect_ratio': (bw / width) / ((bh / height) + 1e-9),
                'area': (bw / width) * (bh / height),
                'conf': 1.0,
            },
            'keypoints': keypoints,
        })
    frames.sort(key=lambda item: item.get('frame_idx', 0))
    return frames


def load_aihub62_sequence_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=2):
    limits = dict(class_clip_limits or {'walk': 120, 'run': 120, 'sit': 80})
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_zips = []
    for zip_path in _aihub62_annotation_zip_paths():
        used_zips.append(zip_path)
        log(f'aihub62 2d sequence scan zip={os.path.basename(zip_path)}')
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                name = info.filename
                base = os.path.basename(name)
                if not name.endswith('.json') or '/._' in name or base.startswith('._'):
                    continue
                try:
                    data = json.loads(archive.read(info).decode('utf-8'))
                except Exception:
                    continue
                label = _aihub62_action_label(data)
                if not label or label not in limits or clip_counts[label] >= int(limits[label] or 0):
                    continue
                scanned_clips[label] += 1
                frames = _frames_from_aihub62_json(data)
                if len(frames) < 8:
                    continue
                windows = va._build_xg_feature_windows(
                    frames,
                    {'width': 1920, 'height': 1080, 'fps': 3.0},
                    window_sec=1.5,
                    stride_sec=0.75,
                )
                if not windows:
                    continue
                selected = select_sequence_windows(label, windows, windows_per_clip)
                clip_id = name.rsplit('_2D.json', 1)[0]
                for win_idx in selected:
                    row = {
                        'video': f'aihub62seq:{clip_id}:w{win_idx}',
                        'posture': label,
                        'source': 'external-aihub62-2d-sequence',
                    }
                    for col in feature_cols:
                        row[col] = float(windows[win_idx].get(col, 0.0) or 0.0)
                    rows.append(row)
                    counts[label] += 1
                clip_counts[label] += 1
                if all(clip_counts[c] >= int(limits.get(c, 0) or 0) for c in limits):
                    break
    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'scanned_clips': dict(scanned_clips),
        'zip_files': used_zips,
    }


AIHUB62_RAW_VIDEO_TARS = {
    'walk': ('49912', 'video_action_1.tar'),
    'run': ('49913', 'video_action_2.tar'),
    'sit': ('49914', 'video_action_3.tar'),
}


def _aihub62_raw_video_tar_paths():
    root = Path('/opt/app/datasets/action_behavior/aihub_62_person_action_video/target_action_20260521')
    paths = {}
    for label, (file_key, tar_name) in AIHUB62_RAW_VIDEO_TARS.items():
        path = root / f'file_{file_key}' / '16.사람동작영상' / 'video' / tar_name
        if path.exists():
            paths[label] = str(path)
    return paths


def _aihub62_raw_clip_key(name):
    base = os.path.basename(str(name or ''))
    stem = re.sub(r'\.mp4$', '', base, flags=re.IGNORECASE)
    stem = re.sub(r'-C\d+$', '', stem, flags=re.IGNORECASE)
    return stem or base or 'unknown'


def _safe_tmp_video_name(label, clip_key, index):
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', f'{label}_{clip_key}_{index}')
    return safe[:120] + '.mp4'


def _aihub62_process_raw_video_stream(va, feature_cols, label, clip_key, stream, tempdir, index, windows_per_clip):
    tmp_path = Path(tempdir) / _safe_tmp_video_name(label, clip_key, index)
    try:
        with tmp_path.open('wb') as output:
            shutil.copyfileobj(stream, output)
        if tmp_path.stat().st_size <= 0:
            return []
        extracted = va._extract_unified_timeseries(
            str(tmp_path),
            input_source='upload',
            target_fps_override=float(os.environ.get('POSTURE_AIHUB62_RAW_FPS', '4') or 4),
            max_frames_override=int(os.environ.get('POSTURE_AIHUB62_RAW_MAX_FRAMES', '24') or 24),
        )
        windows = va._build_xg_feature_windows(
            extracted.get('timeseries') or [],
            extracted.get('vid_meta') or {'width': 1920, 'height': 1080, 'fps': 30.0},
            window_sec=1.5,
            stride_sec=0.75,
        )
        if not windows:
            return []
        selected = select_sequence_windows(label, windows, windows_per_clip)
        rows = []
        for win_idx in selected:
            row = {
                'video': f'aihub62raw:{label}:{clip_key}:w{win_idx}',
                'posture': label,
                'source': 'external-aihub62-raw-video',
            }
            for col in feature_cols:
                row[col] = float(windows[win_idx].get(col, 0.0) or 0.0)
            rows.append(row)
        return rows
    except Exception as exc:
        log(f'aihub62 raw skip label={label} clip={clip_key} reason={type(exc).__name__}:{str(exc)[:140]}')
        return []
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def load_aihub62_raw_video_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=2):
    limits = dict(class_clip_limits or {'walk': 12, 'run': 12, 'sit': 12})
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_tars = []

    tar_paths = _aihub62_raw_video_tar_paths()
    with tempfile.TemporaryDirectory(prefix='aihub62raw_') as tempdir:
        for label, tar_path in tar_paths.items():
            limit = int(limits.get(label, 0) or 0)
            if limit <= 0:
                continue
            used_tars.append(tar_path)
            seen_clip_keys = set()
            log(f'aihub62 raw video scan label={label} tar={os.path.basename(tar_path)} limit={limit}')

            def process_member(video_stream, video_name):
                if clip_counts[label] >= limit:
                    return False
                clip_key = _aihub62_raw_clip_key(video_name)
                if clip_key in seen_clip_keys:
                    return True
                seen_clip_keys.add(clip_key)
                scanned_clips[label] += 1
                new_rows = _aihub62_process_raw_video_stream(
                    va,
                    feature_cols,
                    label,
                    clip_key,
                    video_stream,
                    tempdir,
                    scanned_clips[label],
                    windows_per_clip,
                )
                if new_rows:
                    rows.extend(new_rows)
                    counts[label] += len(new_rows)
                    clip_counts[label] += 1
                    log(f'aihub62 raw accepted label={label} clip={clip_key} rows={len(new_rows)} total_clips={clip_counts[label]}')
                return clip_counts[label] < limit

            try:
                with tarfile.open(tar_path, mode='r:*') as outer:
                    for member in outer:
                        if clip_counts[label] >= limit:
                            break
                        if not member.isfile():
                            continue
                        member_name = member.name or ''
                        if member_name.lower().endswith('.mp4'):
                            stream = outer.extractfile(member)
                            if stream is None:
                                continue
                            with stream:
                                if not process_member(stream, member_name):
                                    break
                        elif member_name.lower().endswith('.tar'):
                            stream = outer.extractfile(member)
                            if stream is None:
                                continue
                            with stream:
                                try:
                                    nested = tarfile.open(fileobj=stream, mode='r|*')
                                except tarfile.TarError:
                                    continue
                                with nested:
                                    for nested_member in nested:
                                        if clip_counts[label] >= limit:
                                            break
                                        if not nested_member.isfile() or not str(nested_member.name).lower().endswith('.mp4'):
                                            continue
                                        nested_stream = nested.extractfile(nested_member)
                                        if nested_stream is None:
                                            continue
                                        with nested_stream:
                                            if not process_member(nested_stream, nested_member.name):
                                                break
            except tarfile.TarError as exc:
                log(f'aihub62 raw tar skip label={label} path={tar_path} reason={exc}')
                continue

    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'scanned_clips': dict(scanned_clips),
        'tar_files': used_tars,
    }


def load_lower_body_occlusion_rows(va, feature_cols, manifest_path=None, class_clip_limits=None, windows_per_clip=2):
    manifest = Path(manifest_path or os.environ.get(
        'POSTURE_LOWER_OCCLUSION_MANIFEST',
        '/opt/app/datasets/fall_classification/lower_body_occlusion_augments/manifest.jsonl',
    ))
    limits = dict(class_clip_limits or {'stand': 80, 'walk': 80, 'run': 80, 'sit': 80, 'lie': 80})
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    skipped = []
    if not manifest.is_file():
        return {
            'rows': rows,
            'counts': {},
            'clip_counts': {},
            'scanned_clips': {},
            'manifest_path': str(manifest),
            'skipped': [{'reason': 'manifest_not_found', 'path': str(manifest)}],
        }

    log(f'lower-body occlusion manifest scan path={manifest}')
    for line_idx, line in enumerate(manifest.read_text(encoding='utf-8').splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception as exc:
            skipped.append({'line': line_idx + 1, 'reason': f'json:{exc}'})
            continue

        label = str(item.get('label') or item.get('posture') or '').strip()
        if label not in limits or limits[label] <= 0 or clip_counts[label] >= limits[label]:
            continue
        video_path = Path(str(item.get('output') or item.get('path') or item.get('video') or ''))
        scanned_clips[label] += 1
        if not video_path.is_file():
            skipped.append({'line': line_idx + 1, 'label': label, 'reason': 'video_not_found', 'path': str(video_path)})
            continue

        try:
            extracted = va._extract_unified_timeseries(
                str(video_path),
                input_source='upload',
                target_fps_override=float(os.environ.get('POSTURE_LOWER_OCCLUSION_FPS', '4') or 4),
                max_frames_override=int(os.environ.get('POSTURE_LOWER_OCCLUSION_MAX_FRAMES', '24') or 24),
            )
            windows = va._build_xg_feature_windows(
                extracted.get('timeseries') or [],
                extracted.get('vid_meta') or {'width': 1920, 'height': 1080, 'fps': 30.0},
                window_sec=1.5,
                stride_sec=0.75,
            )
            if not windows:
                skipped.append({'line': line_idx + 1, 'label': label, 'reason': 'no_windows', 'path': str(video_path)})
                continue
            selected = select_sequence_windows(label, windows, windows_per_clip)
            group = str(item.get('group') or video_path.stem)
            for win_idx in selected:
                row = {
                    'video': f'lowerocc:{label}:{group}:w{win_idx}',
                    'posture': label,
                    'source': 'external-lower-body-occlusion',
                    'augmentation': 'lower_body_occlusion',
                }
                for col in feature_cols:
                    row[col] = float(windows[win_idx].get(col, 0.0) or 0.0)
                rows.append(row)
                counts[label] += 1
            clip_counts[label] += 1
        except Exception as exc:
            skipped.append({'line': line_idx + 1, 'label': label, 'reason': f'{type(exc).__name__}:{str(exc)[:140]}', 'path': str(video_path)})

    log(f"lower-body occlusion rows loaded={len(rows)} counts={dict(counts)} clip_counts={dict(clip_counts)} skipped={len(skipped)}")
    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'scanned_clips': dict(scanned_clips),
        'manifest_path': str(manifest),
        'skipped': skipped[:100],
    }


def _iter_video_files(root, labels, limit_per_label):
    exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    root = Path(root)
    for label in labels:
        label_dir = root / label
        if not label_dir.is_dir():
            continue
        count = 0
        for path in sorted(label_dir.iterdir()):
            if path.suffix.lower() not in exts:
                continue
            yield label, path
            count += 1
            if limit_per_label > 0 and count >= limit_per_label:
                break


def _predict_posture_windows(model_bundle, windows, feature_cols, min_conf):
    import numpy as np

    if not windows:
        return []
    model = model_bundle.get('model') if isinstance(model_bundle, dict) else model_bundle
    model_cols = list((model_bundle or {}).get('feature_cols') or feature_cols) if isinstance(model_bundle, dict) else list(feature_cols)
    classes = list((model_bundle or {}).get('classes') or CLASSES) if isinstance(model_bundle, dict) else list(CLASSES)
    if model is None or not hasattr(model, 'predict_proba'):
        return []
    X = []
    for window in windows:
        X.append([float(window.get(col, 0.0) or 0.0) for col in model_cols])
    try:
        probs = model.predict_proba(np.asarray(X, dtype=float))
    except Exception:
        return []
    out = []
    for idx, row in enumerate(np.asarray(probs)):
        pred_i = int(row.argmax())
        if pred_i < 0 or pred_i >= len(classes):
            continue
        label = str(classes[pred_i])
        conf = float(row[pred_i])
        if label in CLASSES and conf >= min_conf:
            out.append({'window_idx': idx, 'label': label, 'confidence': conf})
    return out


def load_rf_intake_pseudo_occlusion_rows(va, feature_cols, class_limits=None, windows_per_clip=2):
    """Emergency recovery path: self-train occlusion hard cases from registered RF videos.

    These rows are explicitly marked as pseudo-labelled because the RF intake only has
    Y/N labels. We keep only windows that the active XG-Posture model predicts with
    high confidence, then apply lower-body and side occlusion to the same time-series.
    """
    root = Path(os.environ.get('POSTURE_RF_INTAKE_ROOT', '/mnt/data/wiz/storage/training/fall-detection/intake'))
    labels = [item.strip() for item in os.environ.get('POSTURE_RF_INTAKE_SOURCE_LABELS', 'N,Y').split(',') if item.strip()]
    limit_per_label = env_int('POSTURE_RF_INTAKE_SOURCE_LIMIT', 80)
    pseudo_conf = float(os.environ.get('POSTURE_RF_INTAKE_PSEUDO_CONF', '0.88') or 0.88)
    fps = float(os.environ.get('POSTURE_RF_INTAKE_FPS', '4') or 4)
    max_frames = env_int('POSTURE_RF_INTAKE_MAX_FRAMES', 28)
    limits = dict(class_limits or {c: env_int('POSTURE_RF_INTAKE_PSEUDO_CLASS_LIMIT', 160) for c in CLASSES})
    lower_modes = parse_modes(
        os.environ.get('POSTURE_RF_INTAKE_LOWER_MODES', 'random_mild,random_moderate,random_severe'),
        RANDOM_LOWER_OCCLUSION_MODES,
        LOWER_OCCLUSION_MODES + RANDOM_LOWER_OCCLUSION_MODES,
    )
    vertical_modes = parse_modes(
        os.environ.get('POSTURE_RF_INTAKE_VERTICAL_MODES', 'left_mild,left_moderate,left_severe,right_mild,right_moderate,right_severe'),
        RANDOM_VERTICAL_OCCLUSION_MODES,
        VERTICAL_OCCLUSION_MODES + RANDOM_VERTICAL_OCCLUSION_MODES,
    )

    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned = Counter()
    skipped = []
    attempted = Counter()
    try:
        posture_model = va._get_xg_posture_model()
    except Exception as exc:
        return {
            'rows': rows,
            'counts': {},
            'clip_counts': {},
            'scanned_clips': {},
            'skipped': [{'reason': f'posture_model_unavailable:{type(exc).__name__}:{str(exc)[:120]}'}],
            'source_root': str(root),
            'modes': {'lower': lower_modes, 'vertical': vertical_modes},
        }

    log(
        'rf-intake pseudo occlusion source '
        f'root={root} labels={labels} source_limit={limit_per_label} '
        f'class_limits={limits} pseudo_conf={pseudo_conf} fps={fps} max_frames={max_frames}'
    )
    for yn_label, video_path in _iter_video_files(root, labels, limit_per_label):
        if all(counts.get(c, 0) >= limits.get(c, 0) for c in CLASSES):
            break
        attempted[yn_label] += 1
        total_attempted = sum(attempted.values())
        if total_attempted == 1 or total_attempted % 20 == 0:
            log(
                'rf-intake pseudo occlusion progress '
                f'attempted={dict(attempted)} accepted_clips={dict(clip_counts)} '
                f'rows={len(rows)} class_counts={dict(counts)} current={video_path.name}'
            )
        try:
            extracted = va._extract_unified_timeseries(
                str(video_path),
                input_source='upload',
                target_fps_override=fps,
                max_frames_override=max_frames,
            )
            timeseries = extracted.get('timeseries') or []
            vid_meta = extracted.get('vid_meta') or {'width': 1920, 'height': 1080, 'fps': 30.0}
            if len(timeseries) < 8:
                skipped.append({'path': str(video_path), 'reason': 'short_timeseries'})
                continue
            base_windows = va._build_xg_feature_windows(timeseries, vid_meta, window_sec=1.5, stride_sec=0.75)
            pseudo_windows = _predict_posture_windows(posture_model, base_windows, feature_cols, pseudo_conf)
            if not pseudo_windows:
                skipped.append({'path': str(video_path), 'reason': 'no_high_conf_pseudo_windows'})
                continue
            scanned[yn_label] += 1

            accepted_for_video = False
            lower_cache = {}
            vertical_cache = {}
            for item in pseudo_windows:
                label = item['label']
                if counts[label] >= limits.get(label, 0):
                    continue
                win_idx = int(item['window_idx'])
                group = f'rfintake-pseudo:{video_path.stem}:w{win_idx}'
                if os.environ.get('POSTURE_RF_INTAKE_INCLUDE_BASE', '1') == '1':
                    row = {
                        'video': f'rfintakepseudo:{yn_label}:{video_path.stem}:w{win_idx}',
                        'posture': label,
                        'source': 'rf-intake-pseudo-posture',
                        'augmentation': 'none_pseudo_base',
                        'group_id': group,
                        'pseudo_label_confidence': float(item['confidence']),
                    }
                    for col in feature_cols:
                        row[col] = float(base_windows[win_idx].get(col, 0.0) or 0.0)
                    rows.append(row)

                for mode in lower_modes:
                    if mode not in lower_cache:
                        occluded = _occlude_lower_body_timeseries(timeseries, mode, seed_tag=video_path.stem)
                        lower_cache[mode] = va._build_xg_feature_windows(occluded, vid_meta, window_sec=1.5, stride_sec=0.75)
                    occ_windows = lower_cache.get(mode) or []
                    if win_idx >= len(occ_windows):
                        continue
                    row = {
                        'video': f'rfintakepseudoocc:{mode}:{yn_label}:{video_path.stem}:w{win_idx}',
                        'posture': label,
                        'source': 'rf-intake-pseudo-lower-occlusion',
                        'augmentation': f'pseudo_lower_body_{mode}_occlusion',
                        'group_id': group,
                        'pseudo_label_confidence': float(item['confidence']),
                    }
                    for col in feature_cols:
                        row[col] = float(occ_windows[win_idx].get(col, 0.0) or 0.0)
                    rows.append(row)
                    counts[label] += 1
                    accepted_for_video = True
                    if counts[label] >= limits.get(label, 0):
                        break

                if counts[label] >= limits.get(label, 0):
                    continue
                for mode in vertical_modes:
                    if mode not in vertical_cache:
                        occluded = _occlude_vertical_body_timeseries(timeseries, mode, seed_tag=video_path.stem)
                        vertical_cache[mode] = va._build_xg_feature_windows(occluded, vid_meta, window_sec=1.5, stride_sec=0.75)
                    occ_windows = vertical_cache.get(mode) or []
                    if win_idx >= len(occ_windows):
                        continue
                    row = {
                        'video': f'rfintakepseudovertocc:{mode}:{yn_label}:{video_path.stem}:w{win_idx}',
                        'posture': label,
                        'source': 'rf-intake-pseudo-vertical-occlusion',
                        'augmentation': f'pseudo_vertical_body_{mode}_occlusion',
                        'group_id': group,
                        'pseudo_label_confidence': float(item['confidence']),
                    }
                    for col in feature_cols:
                        row[col] = float(occ_windows[win_idx].get(col, 0.0) or 0.0)
                    rows.append(row)
                    counts[label] += 1
                    accepted_for_video = True
                    if counts[label] >= limits.get(label, 0):
                        break
            if accepted_for_video:
                clip_counts[yn_label] += 1
                if sum(clip_counts.values()) == 1 or sum(clip_counts.values()) % 10 == 0:
                    log(
                        'rf-intake pseudo occlusion accepted '
                        f'accepted_clips={dict(clip_counts)} rows={len(rows)} '
                        f'class_counts={dict(counts)}'
                    )
        except Exception as exc:
            skipped.append({'path': str(video_path), 'reason': f'{type(exc).__name__}:{str(exc)[:140]}'})

    log(f"rf-intake pseudo occlusion rows loaded={len(rows)} counts={dict(counts)} clip_counts={dict(clip_counts)} skipped={len(skipped)}")
    return {
        'rows': rows,
        'counts': dict(counts),
        'clip_counts': dict(clip_counts),
        'scanned_clips': dict(scanned),
        'skipped': skipped[:100],
        'source_root': str(root),
        'pseudo_confidence_min': pseudo_conf,
        'modes': {'lower': lower_modes, 'vertical': vertical_modes},
    }


def candidate_models(n_classes):
    from xgboost import XGBClassifier
    models = {
        'xgb_regularized': XGBClassifier(
            n_estimators=220, max_depth=3, learning_rate=0.045,
            objective='multi:softprob', num_class=n_classes,
            eval_metric='mlogloss', random_state=42, n_jobs=2,
            min_child_weight=5, subsample=0.88, colsample_bytree=0.82,
            reg_alpha=0.14, reg_lambda=2.2,
        ),
        'xgb_shallow': XGBClassifier(
            n_estimators=260, max_depth=2, learning_rate=0.042,
            objective='multi:softprob', num_class=n_classes,
            eval_metric='mlogloss', random_state=7, n_jobs=2,
            min_child_weight=4, subsample=0.90, colsample_bytree=0.88,
            reg_alpha=0.10, reg_lambda=1.8,
        ),
        'xgb_sit_lie_tuned': XGBClassifier(
            n_estimators=320, max_depth=3, learning_rate=0.035,
            objective='multi:softprob', num_class=n_classes,
            eval_metric='mlogloss', random_state=53, n_jobs=2,
            min_child_weight=3, subsample=0.92, colsample_bytree=0.76,
            reg_alpha=0.18, reg_lambda=2.8,
        ),
        'xgb_motion_interactions': XGBClassifier(
            n_estimators=260, max_depth=4, learning_rate=0.032,
            objective='multi:softprob', num_class=n_classes,
            eval_metric='mlogloss', random_state=137, n_jobs=2,
            min_child_weight=4, subsample=0.86, colsample_bytree=0.68,
            reg_alpha=0.20, reg_lambda=3.0,
        ),
    }
    if os.environ.get('POSTURE_INCLUDE_HGB') == '1':
        from sklearn.ensemble import HistGradientBoostingClassifier
        models['hgb_l2'] = HistGradientBoostingClassifier(
            max_iter=140, learning_rate=0.045, l2_regularization=0.08,
            max_leaf_nodes=23, random_state=42,
        )
        models['hgb_conservative'] = HistGradientBoostingClassifier(
            max_iter=180, learning_rate=0.035, l2_regularization=0.16,
            max_leaf_nodes=19, min_samples_leaf=24, random_state=77,
        )
    if os.environ.get('POSTURE_INCLUDE_TREE_ENSEMBLES') == '1':
        from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
        models['extra_trees_balanced'] = ExtraTreesClassifier(
            n_estimators=260, max_depth=None, min_samples_leaf=2,
            max_features=0.72, class_weight='balanced', random_state=42,
            n_jobs=2,
        )
        models['extra_trees_motion_breakthrough'] = ExtraTreesClassifier(
            n_estimators=360, max_depth=None, min_samples_leaf=1,
            max_features=0.58, class_weight='balanced', random_state=137,
            n_jobs=2,
        )
        models['extra_trees_boundary_stable'] = ExtraTreesClassifier(
            n_estimators=320, max_depth=None, min_samples_leaf=3,
            max_features=0.64, class_weight='balanced', random_state=173,
            n_jobs=2,
        )
        models['rf_balanced'] = RandomForestClassifier(
            n_estimators=260, max_depth=None, min_samples_leaf=2,
            max_features='sqrt', class_weight='balanced_subsample',
            random_state=91, n_jobs=2,
        )
    model_filter = [
        item.strip() for item in os.environ.get('POSTURE_MODEL_FILTER', '').split(',')
        if item.strip()
    ]
    if model_filter:
        models = {
            name: model for name, model in models.items()
            if any(token in name for token in model_filter)
        }
    return models


def expand_proba_to_class_count(proba, class_labels, n_classes, n_rows=None):
    import numpy as np

    arr = np.asarray(proba, dtype=float)
    if arr.ndim == 1:
        rows = int(n_rows or len(arr))
        arr = arr.reshape(rows, -1)
    if arr.ndim != 2:
        rows = int(n_rows or arr.shape[0])
        arr = arr.reshape(rows, -1)
    if arr.shape[1] == int(n_classes):
        return arr

    rows = int(n_rows or arr.shape[0])
    full = np.zeros((rows, int(n_classes)), dtype=float)
    for col_idx, class_idx in enumerate(list(class_labels)[:arr.shape[1]]):
        try:
            class_idx = int(class_idx)
        except Exception:
            continue
        if 0 <= class_idx < int(n_classes):
            full[:, class_idx] = arr[:, col_idx]
    return full


def expand_proba_to_all_classes(proba, class_labels, n_rows=None):
    return expand_proba_to_class_count(proba, class_labels, len(CLASSES), n_rows=n_rows)


def feature_sets(all_cols):
    temporal = {
        'center_dy', 'center_dx_abs_mean', 'center_x_span', 'max_down_speed',
        'center_x_net_displacement', 'center_y_net_displacement',
        'center_x_direction_change_ratio', 'center_y_direction_change_ratio',
        'center_path_efficiency', 'height_change_abs_mean', 'height_change_std',
        'pose_height_delta', 'torso_tilt_delta', 'knee_bend_delta',
        'lower_body_visibility_min', 'lower_body_visibility_std',
        'pose_descent_mean', 'pose_descent_max', 'pose_change_mean', 'pose_change_max',
        'descent_duration', 'oscillation_count', 'speed_std', 'post_descent_stillness',
        'time_to_max_down_speed', 'time_from_peak_to_stillness', 'pre_descent_stillness',
        'post_peak_recovery_ratio', 'step_period_est', 'knee_angle_cycle_strength',
        'center_y_periodicity', 'tilt_change_duration', 'spread_after_descent',
        'floor_proximity_slope', 'height_drop_persistence', 'collapse_impulse',
        'post_floor_stability', 'slow_descent_ratio',
    }
    source_sensitive = {'avg_conf', 'lower_body_visibility', 'floor_contact_ratio'}
    fall_specific = {'collapse_impulse', 'height_drop_persistence', 'slow_descent_ratio', 'tilt_height_collapse'}
    pose3d_proxy = {
        'torso_width_ratio', 'lower_upper_width_ratio', 'apparent_depth_score',
        'horizontal_flat_pose_score', 'low_flat_still_score',
        'sit_lie_depth_contrast', 'width_height_volume_proxy',
        'pose_width_variability', 'pose_height_variability', 'apparent_depth_motion',
    }
    lower_body_unstable = {
        'ankle_width', 'knee_width', 'foot_y_diff', 'ankle_hip_ratio',
        'knee_asymmetry', 'lower_upper_width_ratio',
    }
    occlusion_core = {
        'lower_body_visibility', 'upper_body_motion', 'shoulder_width',
        'lower_body_visibility_min', 'lower_body_visibility_std',
        'hip_width', 'wrist_width', 'shoulder_hip_ratio', 'wrist_shoulder_ratio',
        'elbow_bend_mean', 'arm_extension_ratio', 'body_compactness',
        'upper_body_temporal_motion', 'upper_motion_energy',
        'upper_center_x_span', 'upper_center_dx_abs_mean',
        'upper_center_y_std', 'upper_center_dy_abs_mean',
        'shoulder_center_x_span', 'shoulder_center_dx_abs_mean',
        'shoulder_center_y_std', 'occluded_upper_motion_score',
        'pose_tilt_mean', 'pose_tilt_max', 'pose_height_ratio_mean',
        'pose_height_ratio_min', 'upright_geometry_score', 'sit_geometry_score',
        'lie_geometry_score', 'flatness_score', 'horizontal_pose_score',
        'low_height_floor_score', 'floor_height_ratio', 'lie_stand_separation_score',
        'torso_width_ratio', 'apparent_depth_score', 'horizontal_flat_pose_score',
        'low_flat_still_score', 'sit_lie_depth_contrast', 'width_height_volume_proxy',
    }
    posture_geometry = {
        'pose_tilt_mean', 'pose_tilt_max', 'pose_height_ratio_mean', 'pose_height_ratio_min',
        'pose_knee_bend_mean', 'pose_knee_bend_min', 'pose_knee_support_mean',
        'pose_knee_support_min', 'straight_leg_ratio', 'support_leg_ratio',
        'pose_height_delta', 'torso_tilt_delta', 'knee_bend_delta',
        'lower_body_visibility_min', 'lower_body_visibility_std',
        'bent_leg_ratio', 'pose_spread_mean', 'pose_spread_max', 'shoulder_width',
        'hip_width', 'ankle_width', 'wrist_width', 'knee_width', 'foot_y_diff',
        'shoulder_hip_ratio', 'ankle_hip_ratio', 'wrist_shoulder_ratio',
        'limb_extension_ratio', 'body_compactness', 'knee_asymmetry',
        'elbow_bend_mean', 'arm_extension_ratio', 'full_skeleton_aspect',
        'full_skeleton_height', 'upper_body_aspect', 'lower_body_aspect',
        'upper_lower_height_ratio', 'upper_lower_center_gap', 'upper_lower_width_ratio',
        'torso_verticality', 'leg_verticality', 'lower_body_extension',
    }
    behavior_scores = {
        'horizontal_motion_energy', 'vertical_motion_energy', 'total_motion_energy',
        'upper_motion_energy', 'body_translation_signal', 'weak_body_translation_signal',
        'walk_displacement_signal', 'gait_translation_consistency',
        'occluded_upper_motion_score', 'upright_motion_conflict_score',
        'sit_lie_transition_score',
        'gait_dynamic_score', 'run_stride_score', 'sit_geometry_score',
        'lie_geometry_score', 'upright_geometry_score', 'knee_bend_intensity',
        'stationary_bent_score', 'flatness_score', 'support_stability_score',
        'pose_compactness_score', 'dynamic_pose_ratio', 'low_height_floor_score',
        'floor_height_ratio', 'horizontal_pose_score', 'lie_stand_separation_score',
        'standing_skeleton_score', 'lying_skeleton_score', 'sitting_skeleton_score',
    }
    upper_body_motion = {
        'upper_body_motion', 'upper_body_temporal_motion', 'upper_motion_energy',
        'upper_center_x_span', 'upper_center_dx_abs_mean',
        'upper_center_y_std', 'upper_center_dy_abs_mean',
        'shoulder_center_x_span', 'shoulder_center_dx_abs_mean',
        'shoulder_center_y_std', 'shoulder_width', 'wrist_width',
        'shoulder_hip_ratio', 'wrist_shoulder_ratio', 'elbow_bend_mean',
        'arm_extension_ratio', 'torso_verticality', 'torso_tilt_delta',
        'torso_tilt_std', 'body_translation_signal', 'weak_body_translation_signal',
        'walk_displacement_signal', 'occluded_upper_motion_score',
    }
    motion_breakthrough = (
        temporal
        | behavior_scores
        | upper_body_motion
        | posture_geometry
        | {
            'height_ratio', 'aspect_change', 'stillness', 'floor_proximity',
            'area_change', 'vert_horiz_ratio', 'avg_conf',
        }
    )
    all_cols = [c for c in all_cols if c != 'n_points']
    return {
        'full': all_cols,
        'all_runtime_64': all_cols,
        'geometry_motion': [c for c in all_cols if c in motion_breakthrough],
        'motion_breakthrough': [c for c in all_cols if c in motion_breakthrough],
        'legacy_runtime_82': [c for c in all_cols if c not in pose3d_proxy],
        'occlusion_aware': [
            c for c in all_cols
            if c not in {'avg_conf', 'floor_contact_ratio'} | lower_body_unstable
            or c in occlusion_core
        ],
        'drop_source_sensitive': [c for c in all_cols if c not in source_sensitive],
        'behavior_focused': [c for c in all_cols if c not in source_sensitive | fall_specific],
        'behavior_no_lower_noise': [
            c for c in all_cols
            if c not in source_sensitive | fall_specific | lower_body_unstable
        ],
        'sit_lie_geometry_focus': [
            c for c in all_cols
            if c in posture_geometry
            or c in behavior_scores
            or c in temporal
            or c in {'height_ratio', 'aspect_change', 'stillness', 'floor_proximity', 'area_change', 'vert_horiz_ratio'}
        ],
        'upper_body_motion_focus': [
            c for c in all_cols
            if c in temporal
            or c in behavior_scores
            or c in upper_body_motion
            or c in {
                'shoulder_width', 'wrist_width', 'shoulder_hip_ratio', 'wrist_shoulder_ratio',
                'elbow_bend_mean', 'arm_extension_ratio', 'upper_body_aspect',
                'torso_verticality', 'upper_body_motion', 'body_compactness',
                'pose_tilt_mean', 'pose_tilt_max', 'pose_spread_mean', 'pose_spread_max',
                'height_ratio', 'aspect_change', 'stillness', 'floor_proximity',
                'center_dx_abs_mean', 'center_x_span', 'max_down_speed',
            }
        ],
        'temporal_pose_core': [
            c for c in all_cols
            if c in temporal
            or c in {
                'height_ratio', 'floor_proximity', 'vert_horiz_ratio',
                'pose_tilt_mean', 'pose_tilt_max', 'pose_height_ratio_mean', 'pose_height_ratio_min',
                'pose_knee_bend_mean', 'pose_knee_bend_min', 'pose_knee_support_mean',
                'pose_knee_support_min', 'straight_leg_ratio', 'support_leg_ratio',
                'bent_leg_ratio', 'pose_spread_mean', 'pose_spread_max',
                'shoulder_width', 'hip_width', 'ankle_width', 'wrist_width', 'knee_width',
                'foot_y_diff', 'shoulder_hip_ratio', 'ankle_hip_ratio', 'wrist_shoulder_ratio',
                'limb_extension_ratio', 'body_compactness', 'knee_asymmetry',
                'elbow_bend_mean', 'arm_extension_ratio', 'upper_body_motion',
            }
        ],
    }


def _class_index(class_names, name):
    try:
        return list(class_names).index(name)
    except ValueError:
        return None


def sequence_group_policy(pred, avg_probs, feature_avg, class_names=None):
    class_names = list(class_names or CLASSES)
    stand_i = _class_index(class_names, 'stand')
    sit_i = _class_index(class_names, 'sit')
    lie_i = _class_index(class_names, 'lie')
    if lie_i is None:
        return pred
    if pred not in {idx for idx in (stand_i, sit_i) if idx is not None}:
        return pred

    def prob(name):
        idx = _class_index(class_names, name)
        if idx is None or idx >= len(avg_probs):
            return 0.0
        return float(avg_probs[idx])

    lie_prob = prob('lie')
    stand_prob = prob('stand')
    sit_prob = prob('sit')
    walk_prob = prob('walk')
    run_prob = prob('run')
    low_motion = (
        float(feature_avg.get('center_dx_abs_mean', 0.0)) <= 0.055
        and float(feature_avg.get('speed_std', 0.0)) <= 0.035
    )
    lie_geometry = (
        float(feature_avg.get('lie_geometry_score', 0.0)) >= 0.08
        or float(feature_avg.get('flatness_score', 0.0)) >= 0.02
        or float(feature_avg.get('pose_spread_max', 0.0)) >= 0.30
        or float(feature_avg.get('low_height_floor_score', 0.0)) >= 0.35
        or float(feature_avg.get('horizontal_pose_score', 0.0)) >= 0.16
        or float(feature_avg.get('lie_stand_separation_score', 0.0)) >= 0.36
        or float(feature_avg.get('horizontal_flat_pose_score', 0.0)) >= 0.22
        or float(feature_avg.get('low_flat_still_score', 0.0)) >= 0.20
        or float(feature_avg.get('sit_lie_depth_contrast', 0.0)) >= 0.05
        or float(feature_avg.get('width_height_volume_proxy', 0.0)) >= 1.15
    )
    not_upright = (
        float(feature_avg.get('upright_geometry_score', 0.0)) <= 0.58
        or float(feature_avg.get('vert_horiz_ratio', 0.0)) <= 1.20
    )
    no_gait = (
        walk_prob < env_float('POSTURE_POLICY_MAX_WALK_PROB', 0.22)
        and run_prob < env_float('POSTURE_POLICY_MAX_RUN_PROB', 0.18)
    )
    close_lie_probability = lie_prob >= max(stand_prob, sit_prob) - env_float('POSTURE_POLICY_LIE_CLOSE_MARGIN', 0.16)
    if (
        lie_prob >= env_float('POSTURE_POLICY_LIE_PROB_MIN', 0.12)
        and close_lie_probability
        and lie_geometry
        and not_upright
        and low_motion
        and no_gait
    ):
        return lie_i
    return pred


def sequence_group_metrics(df, y, groups, proba, class_names=None):
    import numpy as np
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

    class_names = list(class_names or CLASSES)
    labels = list(range(len(class_names)))
    feature_names = [
        'center_dx_abs_mean', 'speed_std', 'vert_horiz_ratio',
        'lie_geometry_score', 'flatness_score', 'upright_geometry_score',
        'pose_spread_max', 'low_height_floor_score', 'horizontal_pose_score',
        'lie_stand_separation_score', 'apparent_depth_score',
        'horizontal_flat_pose_score', 'low_flat_still_score',
        'sit_lie_depth_contrast', 'width_height_volume_proxy',
    ]
    by_group = defaultdict(list)
    for idx, group_id in enumerate(groups):
        by_group[group_id].append(idx)

    y_true = []
    y_pred = []
    adjusted = 0
    for indexes in by_group.values():
        indexes = np.asarray(indexes, dtype=int)
        true_label = int(np.bincount(y[indexes]).argmax())
        avg_probs = proba[indexes].mean(axis=0)
        pred = int(avg_probs.argmax())
        feature_avg = {}
        for name in feature_names:
            if name in df.columns:
                feature_avg[name] = float(df.iloc[indexes][name].astype(float).mean())
            else:
                feature_avg[name] = 0.0
        policy_pred = sequence_group_policy(pred, avg_probs, feature_avg, class_names=class_names)
        adjusted += int(policy_pred != pred)
        y_true.append(true_label)
        y_pred.append(policy_pred)

    report = classification_report(y_true, y_pred, labels=labels, target_names=class_names, output_dict=True, zero_division=0)
    return {
        'accuracy': round(float(accuracy_score(y_true, y_pred)), 4),
        'f1_macro': round(float(f1_score(y_true, y_pred, labels=labels, average='macro', zero_division=0)), 4),
        'class_recall': {c: round(float(report[c]['recall']), 4) for c in class_names},
        'class_precision': {c: round(float(report[c]['precision']), 4) for c in class_names},
        'class_f1': {c: round(float(report[c]['f1-score']), 4) for c in class_names},
        'confusion_matrix': confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        'groups': int(len(y_true)),
        'policy_adjusted_groups': int(adjusted),
    }


def sync_action_behavior_summary(xg_summary):
    class_dist = {c: int((xg_summary.get('class_distribution') or {}).get(c, 0) or 0) for c in CLASSES}
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    feature_count = int(xg_summary.get('feature_count') or len(xg_summary.get('features') or []))
    model_name = f'behavior-posture-sequence-grouped-feature{feature_count}-v4'
    validation = xg_summary.get('sequence_group_cv') or xg_summary.get('group_cv') or {}
    train = xg_summary.get('train_metrics') or {}
    summary = {
        'created_at': now,
        'updated_at': now,
        'model': model_name,
        'model_type': 'behavior-posture-5class',
        'ready_by_rules': False,
        'ready': True,
        'partial_ready': False,
        'multiclass_ready': True,
        'coverage_status': 'full-5class-sequence-group-split',
        'dataset': {
            'sample_count': int(xg_summary.get('n_windows') or sum(class_dist.values())),
            'train_count': int(xg_summary.get('training_samples') or sum(class_dist.values())),
            'validation_count': 0,
            'class_distribution': class_dist,
            'train_ratio': 1.0,
            'validation_ratio': 0.0,
            'split_strategy': 'StratifiedGroupKFold by inferred person/video/clip group',
            'label_note': 'AI-Hub 61/62 연속 프레임 window feature와 AI-Hub 71461 정적 pose 라벨을 결합했습니다.',
        },
        'class_distribution': class_dist,
        'class_order': CLASSES,
        'active_classes': list(xg_summary.get('active_classes') or CLASSES),
        'missing_classes': [c for c in CLASSES if class_dist.get(c, 0) <= 0],
        'train_metrics': {
            'accuracy': train.get('accuracy'),
            'macro_f1': train.get('f1_macro'),
            'per_class_recall': train.get('class_recall') or {},
        },
        'validation_metrics': {
            'accuracy': validation.get('accuracy'),
            'macro_f1': validation.get('f1_macro'),
            'per_class_recall': validation.get('class_recall') or {},
            'per_class_precision': validation.get('class_precision') or {},
            'folds': validation.get('folds'),
            'split_strategy': 'StratifiedGroupKFold',
            'note': '같은 영상/사람/clip 묶음이 train과 validation에 동시에 들어가지 않도록 group split으로 검증했습니다.',
        },
        'confusion_matrix': xg_summary.get('confusion_matrix'),
        'feature_count': feature_count,
        'n_features': feature_count,
        'features': xg_summary.get('features') or [],
        'feature_importance': xg_summary.get('feature_importance') or {},
        'runtime_source': 'rf-dual xg-posture layer',
        'source': 'AI-Hub 61 sequence labels + AI-Hub 62 2D action labels + AI-Hub 71461 pose labels',
        'xg_posture_model_path': xg_summary.get('model_path'),
        'xg_posture_summary_path': '/opt/app/storage/training/fall-detection/xg-posture/training_summary.json',
    }
    behavior_model = {
        'model': model_name,
        'updated_at': now,
        'class_order': CLASSES,
        'active_classes': summary['active_classes'],
        'missing_classes': summary['missing_classes'],
        'ready': True,
        'partial_ready': False,
        'multiclass_ready': True,
        'source': summary['source'],
        'runtime_source': summary['runtime_source'],
        'feature_count': feature_count,
        'xg_posture_model_path': xg_summary.get('model_path'),
        'xg_posture_summary_path': summary['xg_posture_summary_path'],
        'validation_metrics': summary['validation_metrics'],
        'notes': [
            '낙상 최종 판정은 RF-Dual RF binary 레이어가 담당합니다.',
            '행동분류는 XG-Posture가 stand/walk/run/sit/lie 5-class를 병렬 설명 레이어로 제공합니다.',
            '이번 버전은 AI-Hub 61/62 연속 프레임 sequence feature를 포함해 walk/run/sit 신호를 보강했습니다.',
        ],
    }
    for root in [
        Path('/opt/app/storage/training/action-behavior/model'),
        Path('/opt/app/project/main/storage/training/action-behavior/model'),
    ]:
        root.mkdir(parents=True, exist_ok=True)
        (root / 'training_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        (root / 'behavior_model.json').write_text(json.dumps(behavior_model, ensure_ascii=False, indent=2), encoding='utf-8')


def sync_xg_posture_project_assets():
    persistent_root = Path('/opt/app/storage/training/fall-detection/xg-posture')
    project_root = Path('/opt/app/project/main/storage/training/fall-detection/xg-posture')
    project_root.mkdir(parents=True, exist_ok=True)
    for name in ['xg_posture_model.pkl', 'training_summary.json']:
        src = persistent_root / name
        dst = project_root / name
        if src.exists():
            try:
                if src.resolve() == dst.resolve():
                    continue
            except FileNotFoundError:
                pass
            shutil.copy2(src, dst)


def main():
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
    from sklearn.utils.class_weight import compute_sample_weight

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text('', encoding='utf-8')
    va = load_video_analysis()
    all_feature_cols = [c for c in va._XG_FEATURE_COLUMNS if c != 'n_points']

    log('load AI-Hub 71461 static rows for stand/sit/lie boundary coverage')
    va._EXTERNAL_POSE_CLASS_LIMITS = {
        'stand': env_int('POSTURE_STATIC_STAND_LIMIT', 500),
        'walk': env_int('POSTURE_STATIC_WALK_LIMIT', 120),
        'sit': env_int('POSTURE_STATIC_SIT_LIMIT', 300),
        'lie': env_int('POSTURE_STATIC_LIE_LIMIT', 300),
    }
    va._AIHUB61_POSE_CLASS_TARGETS = {
        'walk': env_int('POSTURE_STATIC_AIHUB61_WALK_TARGET', 0),
        'run': env_int('POSTURE_STATIC_AIHUB61_RUN_TARGET', 0),
        'sit': env_int('POSTURE_STATIC_AIHUB61_SIT_TARGET', 0),
        'lie': env_int('POSTURE_STATIC_AIHUB61_LIE_TARGET', 0),
    }
    static_external = va._load_external_pose_training_rows(all_feature_cols)
    static_rows = list(static_external.get('rows') or [])
    log(f"static rows loaded={len(static_rows)} counts={static_external.get('counts', {})}")

    static_walk_motion_external = {'rows': [], 'counts': {}}
    if os.environ.get('POSTURE_INCLUDE_STATIC_WALK_MOTION_PRIOR', '1') == '1':
        walk_prior_limit = env_int('POSTURE_STATIC_WALK_MOTION_PRIOR_LIMIT', 90)
        static_walk_motion_external = build_static_walk_motion_prior_rows(
            static_rows,
            all_feature_cols,
            class_limit=walk_prior_limit,
        )
    static_walk_motion_rows = list(static_walk_motion_external.get('rows') or [])
    static_rows_for_occlusion = static_rows + static_walk_motion_rows

    static_occ_external = {'rows': [], 'counts': {}}
    if os.environ.get('POSTURE_INCLUDE_SYNTH_LOWER_OCCLUSION', '0') == '1':
        static_occ_limit = int(os.environ.get('POSTURE_SYNTH_STATIC_OCC_LIMIT', '160') or 160)
        log(f'build static lower-body occlusion rows limit_per_class={static_occ_limit}')
        static_occ_external = build_static_lower_occlusion_rows(
            static_rows_for_occlusion,
            all_feature_cols,
            class_limits={
                'stand': env_int('POSTURE_SYNTH_STATIC_OCC_STAND_LIMIT', static_occ_limit),
                'walk': env_int('POSTURE_SYNTH_STATIC_OCC_WALK_LIMIT', static_occ_limit),
                'sit': env_int('POSTURE_SYNTH_STATIC_OCC_SIT_LIMIT', static_occ_limit),
                'lie': env_int('POSTURE_SYNTH_STATIC_OCC_LIE_LIMIT', static_occ_limit),
            },
        )
    static_occ_rows = list(static_occ_external.get('rows') or [])

    static_vertical_occ_external = {'rows': [], 'counts': {}, 'modes': []}
    if os.environ.get('POSTURE_INCLUDE_SYNTH_VERTICAL_OCCLUSION', '0') == '1':
        static_vertical_limit = int(os.environ.get('POSTURE_SYNTH_STATIC_VERTICAL_OCC_LIMIT', '120') or 120)
        log(f'build static vertical-body occlusion rows limit_per_class={static_vertical_limit}')
        static_vertical_occ_external = build_static_vertical_occlusion_rows(
            static_rows_for_occlusion,
            all_feature_cols,
            class_limits={
                'stand': env_int('POSTURE_SYNTH_STATIC_VERTICAL_OCC_STAND_LIMIT', static_vertical_limit),
                'walk': env_int('POSTURE_SYNTH_STATIC_VERTICAL_OCC_WALK_LIMIT', static_vertical_limit),
                'sit': env_int('POSTURE_SYNTH_STATIC_VERTICAL_OCC_SIT_LIMIT', static_vertical_limit),
                'lie': env_int('POSTURE_SYNTH_STATIC_VERTICAL_OCC_LIE_LIMIT', static_vertical_limit),
            },
        )
    static_vertical_occ_rows = list(static_vertical_occ_external.get('rows') or [])

    log('build AI-Hub 61 sequence window rows')
    aihub61_seq_limit = env_int('POSTURE_AIHUB61_SEQ_LIMIT', 180)
    seq_external = load_aihub61_sequence_rows(
        va,
        all_feature_cols,
        class_clip_limits={
            'walk': env_int('POSTURE_AIHUB61_SEQ_WALK_LIMIT', aihub61_seq_limit),
            'run': env_int('POSTURE_AIHUB61_SEQ_RUN_LIMIT', aihub61_seq_limit),
            'sit': env_int('POSTURE_AIHUB61_SEQ_SIT_LIMIT', aihub61_seq_limit),
            'lie': env_int('POSTURE_AIHUB61_SEQ_LIE_LIMIT', aihub61_seq_limit),
        },
        windows_per_clip=env_int('POSTURE_AIHUB61_WINDOWS_PER_CLIP', 4),
    )
    seq_rows = list(seq_external.get('rows') or [])
    log(f"sequence rows loaded={len(seq_rows)} counts={seq_external.get('counts', {})} clip_counts={seq_external.get('clip_counts', {})}")

    seq_occ_external = {'rows': [], 'counts': {}, 'clip_counts': {}, 'scanned_clips': {}, 'zip_files': [], 'modes': []}
    if os.environ.get('POSTURE_INCLUDE_SYNTH_LOWER_OCCLUSION', '0') == '1':
        seq_occ_limit = int(os.environ.get('POSTURE_SYNTH_SEQ_OCC_LIMIT', '48') or 48)
        log(f'build AI-Hub 61 synthetic lower-body occlusion sequence rows limit_per_class={seq_occ_limit}')
        seq_occ_external = load_aihub61_lower_occlusion_sequence_rows(
            va,
            all_feature_cols,
            class_clip_limits={
                'walk': env_int('POSTURE_SYNTH_SEQ_OCC_WALK_LIMIT', seq_occ_limit),
                'run': env_int('POSTURE_SYNTH_SEQ_OCC_RUN_LIMIT', seq_occ_limit),
                'sit': env_int('POSTURE_SYNTH_SEQ_OCC_SIT_LIMIT', seq_occ_limit),
                'lie': env_int('POSTURE_SYNTH_SEQ_OCC_LIE_LIMIT', seq_occ_limit),
            },
            windows_per_clip=env_int('POSTURE_SYNTH_SEQ_OCC_WINDOWS_PER_CLIP', 2),
        )
    seq_occ_rows = list(seq_occ_external.get('rows') or [])
    log(f"synthetic lower-body sequence rows loaded={len(seq_occ_rows)} counts={seq_occ_external.get('counts', {})} clip_counts={seq_occ_external.get('clip_counts', {})}")

    seq_vertical_occ_external = {'rows': [], 'counts': {}, 'clip_counts': {}, 'scanned_clips': {}, 'zip_files': [], 'modes': []}
    if os.environ.get('POSTURE_INCLUDE_SYNTH_VERTICAL_OCCLUSION', '0') == '1':
        seq_vertical_limit = int(os.environ.get('POSTURE_SYNTH_SEQ_VERTICAL_OCC_LIMIT', '36') or 36)
        log(f'build AI-Hub 61 synthetic vertical-body occlusion sequence rows limit_per_class={seq_vertical_limit}')
        seq_vertical_occ_external = load_aihub61_vertical_occlusion_sequence_rows(
            va,
            all_feature_cols,
            class_clip_limits={
                'walk': env_int('POSTURE_SYNTH_SEQ_VERTICAL_OCC_WALK_LIMIT', seq_vertical_limit),
                'run': env_int('POSTURE_SYNTH_SEQ_VERTICAL_OCC_RUN_LIMIT', seq_vertical_limit),
                'sit': env_int('POSTURE_SYNTH_SEQ_VERTICAL_OCC_SIT_LIMIT', seq_vertical_limit),
                'lie': env_int('POSTURE_SYNTH_SEQ_VERTICAL_OCC_LIE_LIMIT', seq_vertical_limit),
            },
            windows_per_clip=env_int('POSTURE_SYNTH_SEQ_VERTICAL_OCC_WINDOWS_PER_CLIP', 2),
        )
    seq_vertical_occ_rows = list(seq_vertical_occ_external.get('rows') or [])
    log(f"synthetic vertical-body sequence rows loaded={len(seq_vertical_occ_rows)} counts={seq_vertical_occ_external.get('counts', {})} clip_counts={seq_vertical_occ_external.get('clip_counts', {})}")

    log('build AI-Hub 62 2D sequence rows for direct walk/run/sit action coverage')
    aihub62_seq_limit = env_int('POSTURE_AIHUB62_SEQ_LIMIT', 120)
    seq62_external = load_aihub62_sequence_rows(
        va,
        all_feature_cols,
        class_clip_limits={
            'walk': env_int('POSTURE_AIHUB62_SEQ_WALK_LIMIT', aihub62_seq_limit),
            'run': env_int('POSTURE_AIHUB62_SEQ_RUN_LIMIT', aihub62_seq_limit),
            'sit': env_int('POSTURE_AIHUB62_SEQ_SIT_LIMIT', env_int('POSTURE_AIHUB62_SEQ_LIMIT', 80)),
        },
        windows_per_clip=env_int('POSTURE_AIHUB62_WINDOWS_PER_CLIP', 2),
    )
    seq62_rows = list(seq62_external.get('rows') or [])
    log(f"aihub62 rows loaded={len(seq62_rows)} counts={seq62_external.get('counts', {})} clip_counts={seq62_external.get('clip_counts', {})}")

    seq62_raw_external = {'rows': [], 'counts': {}, 'clip_counts': {}, 'scanned_clips': {}, 'tar_files': []}
    if os.environ.get('POSTURE_INCLUDE_AIHUB62_RAW', '0') == '1':
        raw_limit = int(os.environ.get('POSTURE_AIHUB62_RAW_LIMIT', '12') or 12)
        log(f'build AI-Hub 62 raw video YOLO-pose rows limit_per_class={raw_limit}')
        seq62_raw_external = load_aihub62_raw_video_rows(
            va,
            all_feature_cols,
            class_clip_limits={
                'walk': env_int('POSTURE_AIHUB62_RAW_WALK_LIMIT', raw_limit),
                'run': env_int('POSTURE_AIHUB62_RAW_RUN_LIMIT', raw_limit),
                'sit': env_int('POSTURE_AIHUB62_RAW_SIT_LIMIT', raw_limit),
            },
            windows_per_clip=env_int('POSTURE_AIHUB62_RAW_WINDOWS_PER_CLIP', 2),
        )
    seq62_raw_rows = list(seq62_raw_external.get('rows') or [])
    log(f"aihub62 raw rows loaded={len(seq62_raw_rows)} counts={seq62_raw_external.get('counts', {})} clip_counts={seq62_raw_external.get('clip_counts', {})}")

    lower_occ_external = {'rows': [], 'counts': {}, 'clip_counts': {}, 'scanned_clips': {}, 'manifest_path': '', 'skipped': []}
    if os.environ.get('POSTURE_INCLUDE_LOWER_OCCLUSION', '0') == '1':
        occ_limit = int(os.environ.get('POSTURE_LOWER_OCCLUSION_LIMIT', '80') or 80)
        log(f'build lower-body occlusion augmentation rows limit_per_class={occ_limit}')
        lower_occ_external = load_lower_body_occlusion_rows(
            va,
            all_feature_cols,
            class_clip_limits={
                c: env_int(f'POSTURE_LOWER_OCCLUSION_{c.upper()}_LIMIT', occ_limit)
                for c in CLASSES
            },
            windows_per_clip=env_int('POSTURE_LOWER_OCCLUSION_WINDOWS_PER_CLIP', 2),
        )
    lower_occ_rows = list(lower_occ_external.get('rows') or [])
    log(f"lower-body occlusion rows loaded={len(lower_occ_rows)} counts={lower_occ_external.get('counts', {})} clip_counts={lower_occ_external.get('clip_counts', {})}")

    rf_pseudo_occ_external = {'rows': [], 'counts': {}, 'clip_counts': {}, 'scanned_clips': {}, 'skipped': [], 'modes': {}}
    if os.environ.get('POSTURE_INCLUDE_RF_INTAKE_PSEUDO_OCCLUSION', '0') == '1':
        pseudo_limit = int(os.environ.get('POSTURE_RF_INTAKE_PSEUDO_CLASS_LIMIT', '160') or 160)
        log(f'build RF intake pseudo posture occlusion rows limit_per_class={pseudo_limit}')
        rf_pseudo_occ_external = load_rf_intake_pseudo_occlusion_rows(
            va,
            all_feature_cols,
            class_limits={
                c: env_int(f'POSTURE_RF_INTAKE_PSEUDO_{c.upper()}_LIMIT', pseudo_limit)
                for c in CLASSES
            },
            windows_per_clip=env_int('POSTURE_RF_INTAKE_PSEUDO_WINDOWS_PER_CLIP', 2),
        )
    rf_pseudo_occ_rows = list(rf_pseudo_occ_external.get('rows') or [])
    log(f"rf-intake pseudo occlusion rows loaded={len(rf_pseudo_occ_rows)} counts={rf_pseudo_occ_external.get('counts', {})} clip_counts={rf_pseudo_occ_external.get('clip_counts', {})}")

    log('load dashboard HITL posture intake rows')
    hitl_posture_intake = load_hitl_posture_intake_rows(
        va,
        all_feature_cols,
        windows_per_clip=env_int('POSTURE_HITL_WINDOWS_PER_CLIP', 3),
    )
    hitl_rows = list(hitl_posture_intake.get('rows') or [])
    log(f"hitl posture intake rows loaded={len(hitl_rows)} counts={hitl_posture_intake.get('counts', {})} clip_counts={hitl_posture_intake.get('clip_counts', {})}")

    rows = (
        static_rows
        + static_walk_motion_rows
        + static_occ_rows
        + static_vertical_occ_rows
        + seq_rows
        + seq_occ_rows
        + seq_vertical_occ_rows
        + seq62_rows
        + seq62_raw_rows
        + lower_occ_rows
        + rf_pseudo_occ_rows
        + hitl_rows
    )
    if not rows:
        log('no posture training rows were loaded; wait for AI-Hub 61/62/71461 or HITL/occlusion intake data before training')
        return 2
    df = pd.DataFrame(rows)
    if 'posture' not in df.columns:
        log(f"loaded posture rows are missing required 'posture' column; columns={list(df.columns)}")
        return 2
    df = df[df['posture'].isin(CLASSES)].copy()
    if df.empty:
        log(f'no valid posture rows remain after class filter; expected classes={CLASSES}')
        return 2
    loaded_class_dist = {c: int((df['posture'] == c).sum()) for c in CLASSES}
    requested_classes = [
        item.strip()
        for item in os.environ.get('POSTURE_ACTIVE_CLASSES', '').split(',')
        if item.strip()
    ]
    active_classes = [c for c in CLASSES if (not requested_classes or c in requested_classes)]
    if not active_classes:
        active_classes = list(CLASSES)
    dropped_classes = []
    if env_bool('POSTURE_ALLOW_MISSING_RUN', True) and 'run' in active_classes and loaded_class_dist.get('run', 0) <= 0:
        active_classes.remove('run')
        dropped_classes.append({
            'class': 'run',
            'reason': 'no run posture/action-labelled rows available; POSTURE_ALLOW_MISSING_RUN=1',
        })
    if env_bool('POSTURE_AUTO_DROP_EMPTY_CLASSES', False):
        remaining = []
        for cls in active_classes:
            if loaded_class_dist.get(cls, 0) > 0:
                remaining.append(cls)
            else:
                dropped_classes.append({
                    'class': cls,
                    'reason': 'no labelled rows available; POSTURE_AUTO_DROP_EMPTY_CLASSES=1',
                })
        active_classes = remaining
    if len(active_classes) < 2:
        log(f'not enough active posture classes for training active_classes={active_classes} loaded_class_dist={loaded_class_dist}')
        return 2
    if dropped_classes:
        log(f'active posture classes={active_classes}; dropped={dropped_classes}')
    df = df[df['posture'].isin(active_classes)].copy()
    if df.empty:
        log(f'no valid posture rows remain after active class filter; active_classes={active_classes}')
        return 2
    df['group_id'] = [infer_group_id(row) for row in df.to_dict('records')]
    class_dist = {c: int((df['posture'] == c).sum()) for c in active_classes}
    full_class_dist = {c: int((df['posture'] == c).sum()) for c in CLASSES}
    group_counts = df.groupby('posture')['group_id'].nunique().to_dict()
    source_counts = df.groupby(['posture', 'source']).size().to_dict()
    log(f'training table rows={len(df)} active_classes={active_classes} class_dist={class_dist} loaded_class_dist={loaded_class_dist} group_counts={group_counts}')

    class_to_int = {c: i for i, c in enumerate(active_classes)}
    y = df['posture'].map(class_to_int).to_numpy()
    groups = df['group_id'].to_numpy()
    class_weight_multipliers = parse_class_weight_multipliers(active_classes)
    log(f'class weight multipliers={class_weight_multipliers}')
    n_splits = min(5, min(group_counts.values()))
    if n_splits < 2:
        log(f'not enough groups per active class for StratifiedGroupKFold active_classes={active_classes} group_counts={group_counts}')
        return 2
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)

    trials = []
    best = None
    log('start feature-set and model comparison')
    requested_feature_sets = {
        item.strip() for item in os.environ.get('POSTURE_FEATURE_SET_FILTER', '').split(',')
        if item.strip()
    }
    for feature_set_name, cols in feature_sets(all_feature_cols).items():
        if requested_feature_sets and feature_set_name not in requested_feature_sets:
            continue
        cols = [c for c in cols if c in df.columns]
        X = df[cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
        weights = apply_class_weight_multipliers(
            compute_sample_weight(class_weight='balanced', y=y),
            y,
            active_classes,
            class_weight_multipliers,
        )
        models = candidate_models(len(active_classes))
        if not models:
            raise RuntimeError('No candidate models selected. Check POSTURE_MODEL_FILTER.')
        for model_name, model in models.items():
            log(f'evaluate feature_set={feature_set_name} model={model_name} n_features={len(cols)}')
            params = {'sample_weight': weights} if model_name.startswith('xgb') else None
            if params:
                oof_probs = cross_val_predict(model, X, y, cv=cv, groups=groups, params=params, method='predict_proba')
            else:
                oof_probs = cross_val_predict(model, X, y, cv=cv, groups=groups, method='predict_proba')
            oof_probs = expand_proba_to_class_count(oof_probs, sorted(np.unique(y)), len(active_classes), n_rows=len(y))
            y_oof = np.asarray(oof_probs).argmax(axis=1).flatten().astype(int)
            active_labels = list(range(len(active_classes)))
            report = classification_report(y, y_oof, labels=active_labels, target_names=active_classes, output_dict=True, zero_division=0)
            recalls = {c: round(float(report[c]['recall']), 4) for c in active_classes}
            precision = {c: round(float(report[c]['precision']), 4) for c in active_classes}
            f1s = {c: round(float(report[c]['f1-score']), 4) for c in active_classes}
            seq_metrics = sequence_group_metrics(df, y, groups, np.asarray(oof_probs), class_names=active_classes)
            trial = {
                'feature_set': feature_set_name,
                'model': model_name,
                'feature_count': len(cols),
                'accuracy': round(float(accuracy_score(y, y_oof)), 4),
                'f1_macro': round(float(f1_score(y, y_oof, labels=active_labels, average='macro', zero_division=0)), 4),
                'class_recall': recalls,
                'class_precision': precision,
                'class_f1': f1s,
                'confusion_matrix': confusion_matrix(y, y_oof, labels=active_labels).tolist(),
                'sequence_group_cv': seq_metrics,
                'features': cols,
                'active_classes': list(active_classes),
                'dropped_classes': list(dropped_classes),
                'class_weight_multipliers': dict(class_weight_multipliers),
            }
            boundary_members = [c for c in ('walk', 'run', 'sit', 'lie') if c in active_classes]
            boundary_score = sum(recalls.get(c, 0.0) for c in boundary_members) / max(1, len(boundary_members))
            min_recall = min(recalls.values()) if recalls else 0.0
            weak_terms = []
            if 'sit' in active_classes:
                weak_terms.append((recalls.get('sit', 0.0), 0.45))
            if 'lie' in active_classes:
                weak_terms.append((recalls.get('lie', 0.0), 0.20))
            if 'run' in active_classes:
                weak_terms.append((precision.get('run', 0.0), 0.20))
            if 'walk' in active_classes:
                weak_terms.append((recalls.get('walk', 0.0), 0.15))
            weak_weight = sum(weight for _score, weight in weak_terms) or 1.0
            weak_class_score = sum(score * weight for score, weight in weak_terms) / weak_weight
            composite_score = (
                seq_metrics['f1_macro'] * 0.35
                + seq_metrics['accuracy'] * 0.20
                + trial['f1_macro'] * 0.30
                + min_recall * 0.05
                + weak_class_score * 0.15
                + boundary_score * 0.05
            )
            sequence_target_met = seq_metrics['accuracy'] >= 0.9 and seq_metrics['f1_macro'] >= 0.9
            trial['_rank'] = (sequence_target_met, composite_score, seq_metrics['f1_macro'], trial['f1_macro'], min_recall, trial['accuracy'])
            trials.append(trial)
            log(f"{feature_set_name}/{model_name} window_f1={trial['f1_macro']} window_acc={trial['accuracy']} sequence_f1={seq_metrics['f1_macro']} sequence_acc={seq_metrics['accuracy']} recall={recalls}")
            if best is None or trial['_rank'] > best['_rank']:
                best = trial

    trials.sort(key=lambda item: item.get('_rank', ()), reverse=True)
    for trial in trials:
        trial.pop('_rank', None)
    best = trials[0]
    best_cols = best['features']
    best_name = best['model']

    def save_occlusion_aux_candidate(reason):
        if os.environ.get('POSTURE_SAVE_OCCLUSION_AUX', '0') != '1':
            return {'ready': False, 'reason': 'POSTURE_SAVE_OCCLUSION_AUX disabled'}
        occlusion_row_count = (
            len(static_occ_rows)
            + len(static_vertical_occ_rows)
            + len(seq_occ_rows)
            + len(seq_vertical_occ_rows)
            + len(lower_occ_rows)
            + len(rf_pseudo_occ_rows)
        )
        if occlusion_row_count <= 0:
            return {'ready': False, 'reason': 'no occlusion rows in this run'}
        trigger_policy = {
            'lower_body_visibility_lt': float(os.environ.get('POSTURE_OCC_AUX_LOWER_VIS_LT', '0.42') or 0.42),
            'avg_conf_lt': float(os.environ.get('POSTURE_OCC_AUX_AVG_CONF_LT', '0.38') or 0.38),
            'main_margin_lt': float(os.environ.get('POSTURE_OCC_AUX_MARGIN_LT', '0.07') or 0.07),
            'side_body_width_suspected': True,
        }

        log(f"fit body-occlusion auxiliary feature_set={best['feature_set']} model={best_name} rows={len(df)} occlusion_rows={occlusion_row_count}")
        X_aux = df[best_cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
        aux_weights = apply_class_weight_multipliers(
            compute_sample_weight(class_weight='balanced', y=y),
            y,
            active_classes,
            class_weight_multipliers,
        )
        aux_model = candidate_models(len(active_classes))[best_name]
        if best_name.startswith('xgb'):
            aux_model.fit(X_aux, y, sample_weight=aux_weights)
        else:
            aux_model.fit(X_aux, y)

        y_aux = np.asarray(aux_model.predict(X_aux)).flatten().astype(int)
        active_labels = list(range(len(active_classes)))
        aux_train_report = classification_report(y, y_aux, labels=active_labels, target_names=active_classes, output_dict=True, zero_division=0)
        aux_feature_importance = {}
        if hasattr(aux_model, 'feature_importances_'):
            aux_feature_importance = {
                col: round(float(imp), 4)
                for col, imp in zip(best_cols, aux_model.feature_importances_)
            }

        aux_summary = {
            'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'trained_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ready': True,
            'purpose': 'body occlusion auxiliary posture classifier',
            'runtime_policy': 'Use only when the active posture model is uncertain, keypoint confidence is low, lower-body visibility is low, or side/vertical body occlusion is suspected; do not replace the active model globally.',
            'reason': reason,
            'algorithm': best_name,
            'feature_set': best['feature_set'],
            'features': list(best_cols),
            'feature_count': len(best_cols),
            'classes': list(active_classes),
            'base_class_order': list(CLASSES),
            'active_classes': list(active_classes),
            'dropped_classes': list(dropped_classes),
            'n_classes': len(active_classes),
            'n_windows': int(len(df)),
            'occlusion_training_windows': int(occlusion_row_count),
            'class_distribution': class_dist,
            'loaded_class_distribution': loaded_class_dist,
            'full_class_distribution': full_class_dist,
            'group_distribution': {k: int(v) for k, v in group_counts.items()},
            'source_distribution': {str(k): int(v) for k, v in source_counts.items()},
            'group_cv': {
                'folds': n_splits,
                'strategy': 'StratifiedGroupKFold',
                'accuracy': best['accuracy'],
                'f1_macro': best['f1_macro'],
                'class_recall': best['class_recall'],
                'class_precision': best['class_precision'],
                'class_f1': best['class_f1'],
            },
            'sequence_group_cv': {
                'folds': n_splits,
                'strategy': 'StratifiedGroupKFold + group probability average + lie rescue policy',
                **(best.get('sequence_group_cv') or {}),
            },
            'confusion_matrix': {
                'labels': list(active_classes),
                'matrix': best['confusion_matrix'],
            },
            'train_metrics': {
                'accuracy': round(float(accuracy_score(y, y_aux)), 4),
                'f1_macro': round(float(f1_score(y, y_aux, labels=active_labels, average='macro', zero_division=0)), 4),
                'class_recall': {c: round(float(aux_train_report[c]['recall']), 4) for c in active_classes},
            },
            'feature_importance': aux_feature_importance,
            'trigger_policy': trigger_policy,
            'external_pose_dataset': {
                'static_walk_motion_prior_counts': static_walk_motion_external.get('counts', {}),
                'static_lower_occlusion_counts': static_occ_external.get('counts', {}),
                'static_vertical_occlusion_counts': static_vertical_occ_external.get('counts', {}),
                'static_vertical_occlusion_modes': static_vertical_occ_external.get('modes', []),
                'synthetic_lower_occlusion_counts': seq_occ_external.get('counts', {}),
                'synthetic_lower_occlusion_clip_counts': seq_occ_external.get('clip_counts', {}),
                'synthetic_lower_occlusion_modes': seq_occ_external.get('modes', []),
                'synthetic_vertical_occlusion_counts': seq_vertical_occ_external.get('counts', {}),
                'synthetic_vertical_occlusion_clip_counts': seq_vertical_occ_external.get('clip_counts', {}),
                'synthetic_vertical_occlusion_modes': seq_vertical_occ_external.get('modes', []),
                'lower_body_occlusion_counts': lower_occ_external.get('counts', {}),
                'lower_body_occlusion_clip_counts': lower_occ_external.get('clip_counts', {}),
                'rf_intake_pseudo_occlusion_counts': rf_pseudo_occ_external.get('counts', {}),
                'rf_intake_pseudo_occlusion_clip_counts': rf_pseudo_occ_external.get('clip_counts', {}),
                'rf_intake_pseudo_occlusion_scanned_clips': rf_pseudo_occ_external.get('scanned_clips', {}),
                'rf_intake_pseudo_occlusion_modes': rf_pseudo_occ_external.get('modes', {}),
                'rf_intake_pseudo_label_note': 'RF-Fall Y/N intake has no ground-truth posture class; these emergency rows use high-confidence active XG-Posture pseudo labels.',
            },
        }
        aux_model_data = {
            'model': aux_model,
            'classes': list(active_classes),
            'base_class_order': list(CLASSES),
            'feature_cols': list(best_cols),
            'auxiliary': True,
            'purpose': aux_summary['purpose'],
            'trigger_policy': trigger_policy,
        }

        persistent_dir = Path('/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux')
        project_dir = Path(PROJECT_ROOT) / 'storage' / 'training' / 'fall-detection' / 'xg-posture-occlusion-aux'
        persistent_dir.mkdir(parents=True, exist_ok=True)
        project_dir.mkdir(parents=True, exist_ok=True)
        model_path = persistent_dir / 'xg_posture_occlusion_aux_model.pkl'
        summary_path = persistent_dir / 'training_summary.json'

        def copy_if_distinct(src, dst):
            src = Path(src)
            dst = Path(dst)
            try:
                if dst.exists() and os.path.samefile(src, dst):
                    return
            except Exception:
                pass
            if os.path.abspath(src) == os.path.abspath(dst):
                return
            shutil.copy2(src, dst)

        def occlusion_aux_version_index(summary):
            if not isinstance(summary, dict):
                return 0
            raw = ' '.join(
                str(summary.get(key) or '')
                for key in ('model_version', 'version_badge', 'training_run_label', 'run_id')
            )
            found = re.findall(r'(?:^|\D)v?(\d+)(?:\D|$)', raw)
            if not found:
                return 0
            try:
                return max(int(value) for value in found)
            except Exception:
                return 0

        existing_aux = {}
        existing_aux_f1 = 0.0
        if summary_path.exists():
            try:
                existing_aux = json.loads(summary_path.read_text(encoding='utf-8'))
                existing_aux_f1 = float(((existing_aux.get('group_cv') or {}).get('f1_macro')) or 0.0)
            except Exception:
                existing_aux = {}
                existing_aux_f1 = 0.0
        next_version_index = max(1, occlusion_aux_version_index(existing_aux) + 1)
        next_version_badge = f'v{next_version_index}'
        candidate_run_id = datetime.datetime.now(datetime.timezone.utc).strftime('occlusion_aux_%Y%m%d%H%M%S')
        aux_summary.update({
            'model_family': 'xg-posture-occlusion-aux',
            'candidate_model_version': next_version_badge,
            'candidate_run_id': candidate_run_id,
        })
        min_save_f1 = float(os.environ.get('POSTURE_OCC_AUX_MIN_SAVE_F1', '0.0') or 0.0)
        should_skip_aux_save = (
            (existing_aux_f1 > 0.0 and best['f1_macro'] < existing_aux_f1)
            or (min_save_f1 > 0.0 and best['f1_macro'] < min_save_f1)
        )
        if should_skip_aux_save:
            aux_summary.update({
                'ready': False,
                'saved': False,
                'reason': (
                    f'skipped save: candidate f1_macro={best["f1_macro"]:.4f}, '
                    f'existing auxiliary f1_macro={existing_aux_f1:.4f}, '
                    f'min_save_f1={min_save_f1:.4f}'
                ),
                'existing_aux_f1_macro': existing_aux_f1,
                'min_save_f1': min_save_f1,
            })
            log(aux_summary['reason'])
            return aux_summary
        aux_summary.update({
            'model_version': next_version_badge,
            'version_badge': next_version_badge,
            'training_run_label': f'가림 보조 {next_version_badge}',
            'run_id': candidate_run_id,
        })
        aux_model_data.update({
            'model_version': next_version_badge,
            'version_badge': next_version_badge,
            'training_run_label': aux_summary['training_run_label'],
            'run_id': candidate_run_id,
        })
        fd, tmp_path = tempfile.mkstemp(suffix='.pkl.tmp', dir=str(persistent_dir))
        os.close(fd)
        try:
            joblib.dump(aux_model_data, tmp_path)
            os.replace(tmp_path, model_path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        summary_path.write_text(json.dumps(aux_summary, ensure_ascii=False, indent=2), encoding='utf-8')
        copy_if_distinct(model_path, project_dir / model_path.name)
        copy_if_distinct(summary_path, project_dir / summary_path.name)
        aux_summary['model_path'] = str(model_path)
        aux_summary['summary_path'] = str(summary_path)
        log(f"body occlusion auxiliary saved model={model_path} summary={summary_path}")
        return aux_summary

    previous_summary = va._xg_posture_summary()
    previous_f1 = float(
        ((previous_summary.get('group_cv') or {}).get('f1_macro'))
        or previous_summary.get('f1_macro')
        or previous_summary.get('macro_f1')
        or 0.0
    )
    previous_sequence = previous_summary.get('sequence_group_cv') or {}
    previous_sequence_f1 = float(previous_sequence.get('f1_macro') or previous_f1)
    previous_sit_recall = float((((previous_summary.get('group_cv') or {}).get('class_recall') or {}).get('sit')) or 0.0)
    previous_algorithm = str(previous_summary.get('algorithm') or '')
    best_sit_recall = float((best.get('class_recall') or {}).get('sit') or 0.0)
    xgb_policy_upgrade = (
        previous_algorithm and not previous_algorithm.startswith('xgb')
        and best_name.startswith('xgb')
        and best['f1_macro'] >= previous_f1 - 0.01
        and best_sit_recall >= previous_sit_recall + 0.015
    )
    apply_candidate = (
        previous_f1 <= 0.0
        or best['f1_macro'] >= previous_f1
        or (
            (best.get('sequence_group_cv') or {}).get('f1_macro', 0.0) >= max(0.9, previous_sequence_f1)
            and best['f1_macro'] >= previous_f1 - 0.02
        )
        or (best['f1_macro'] >= previous_f1 - 0.01 and best_sit_recall >= previous_sit_recall + 0.03)
        or xgb_policy_upgrade
    )
    if os.environ.get('POSTURE_DISABLE_ACTIVE_REPLACEMENT', '0') == '1':
        apply_candidate = False
    occlusion_aux_summary = save_occlusion_aux_candidate('candidate_selected_before_active_replacement_check')
    if not apply_candidate:
        report = {
            'applied': False,
            'reason': 'candidate did not beat the active macro F1 and did not improve sit recall enough to justify replacing the model',
            'active_f1_macro': previous_f1,
            'active_sit_recall': previous_sit_recall,
            'candidate_f1_macro': best['f1_macro'],
            'candidate_sit_recall': best_sit_recall,
            'best': best,
            'class_distribution': class_dist,
            'loaded_class_distribution': loaded_class_dist,
            'full_class_distribution': full_class_dist,
            'active_classes': list(active_classes),
            'dropped_classes': list(dropped_classes),
            'group_distribution': {k: int(v) for k, v in group_counts.items()},
            'source_distribution': {str(k): int(v) for k, v in source_counts.items()},
            'trials': trials,
            'occlusion_auxiliary': occlusion_aux_summary,
            'hitl_posture_intake': {
                'counts': hitl_posture_intake.get('counts', {}),
                'clip_counts': hitl_posture_intake.get('clip_counts', {}),
                'used_files': hitl_posture_intake.get('used_files', []),
                'skipped': hitl_posture_intake.get('skipped', []),
            },
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        sync_action_behavior_summary(previous_summary)
        sync_xg_posture_project_assets()
        log(f"candidate skipped active_f1={previous_f1} candidate_f1={best['f1_macro']} active_sit={previous_sit_recall} candidate_sit={best_sit_recall}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    log(f"fit final best feature_set={best['feature_set']} model={best_name} f1={best['f1_macro']}")
    X_final = df[best_cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    weights = apply_class_weight_multipliers(
        compute_sample_weight(class_weight='balanced', y=y),
        y,
        active_classes,
        class_weight_multipliers,
    )
    final_model = candidate_models(len(active_classes))[best_name]
    if best_name.startswith('xgb'):
        final_model.fit(X_final, y, sample_weight=weights)
    else:
        final_model.fit(X_final, y)

    y_train = np.asarray(final_model.predict(X_final)).flatten().astype(int)
    active_labels = list(range(len(active_classes)))
    train_report = classification_report(y, y_train, labels=active_labels, target_names=active_classes, output_dict=True, zero_division=0)
    train_metrics = {
        'accuracy': round(float(accuracy_score(y, y_train)), 4),
        'f1_macro': round(float(f1_score(y, y_train, labels=active_labels, average='macro', zero_division=0)), 4),
        'class_recall': {c: round(float(train_report[c]['recall']), 4) for c in active_classes},
    }
    feature_importance = {}
    if hasattr(final_model, 'feature_importances_'):
        feature_importance = {
            col: round(float(imp), 4)
            for col, imp in zip(best_cols, final_model.feature_importances_)
        }

    model_data = {
        'model': final_model,
        'classes': list(active_classes),
        'base_class_order': list(CLASSES),
        'feature_cols': list(best_cols),
        'group_split': {
            'strategy': 'StratifiedGroupKFold',
            'n_splits': n_splits,
            'group_source': 'inferred video/person/clip id',
        },
    }
    model_path = va._xg_posture_model_path()
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix='.pkl.tmp', dir=os.path.dirname(model_path))
    os.close(fd)
    try:
        joblib.dump(model_data, tmp_path)
        os.replace(tmp_path, model_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    summary = {
        'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'trained_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'model_type': f'xg-posture-sequence-grouped-{len(best_cols)}',
        'ready': True,
        'training_samples': int(len(df)),
        'class_distribution': class_dist,
        'loaded_class_distribution': loaded_class_dist,
        'full_class_distribution': full_class_dist,
        'group_distribution': {k: int(v) for k, v in group_counts.items()},
        'source_distribution': {str(k): int(v) for k, v in source_counts.items()},
        'features': list(best_cols),
        'feature_count': len(best_cols),
        'n_features': len(best_cols),
        'classes': list(active_classes),
        'base_class_order': list(CLASSES),
        'active_classes': list(active_classes),
        'dropped_classes': list(dropped_classes),
        'n_classes': len(active_classes),
        'n_windows': int(len(df)),
        'model_path': model_path,
        'algorithm': best_name,
        'feature_set': best['feature_set'],
        'class_balance_strategy': 'sequence windows + boundary-aware sampling + balanced sample weights + optional class multipliers',
        'class_weight_multipliers': dict(class_weight_multipliers),
        'group_cv': {
            'folds': n_splits,
            'strategy': 'StratifiedGroupKFold',
            'accuracy': best['accuracy'],
            'f1_macro': best['f1_macro'],
            'class_recall': best['class_recall'],
            'class_precision': best['class_precision'],
            'class_f1': best['class_f1'],
        },
        'sequence_group_cv': {
            'folds': n_splits,
            'strategy': 'StratifiedGroupKFold + group probability average + lie rescue policy',
            **(best.get('sequence_group_cv') or {}),
        },
        'cv': {
            'folds': n_splits,
            'strategy': 'StratifiedGroupKFold',
            'accuracy': best['accuracy'],
            'f1_macro': best['f1_macro'],
        },
        'confusion_matrix': {
            'labels': list(active_classes),
            'matrix': best['confusion_matrix'],
        },
        'train_metrics': train_metrics,
        'feature_importance': feature_importance,
        'candidate_trials': trials,
        'external_pose_dataset': {
            'static_counts': static_external.get('counts', {}),
            'static_walk_motion_prior_counts': static_walk_motion_external.get('counts', {}),
            'static_lower_occlusion_counts': static_occ_external.get('counts', {}),
            'static_vertical_occlusion_counts': static_vertical_occ_external.get('counts', {}),
            'static_vertical_occlusion_modes': static_vertical_occ_external.get('modes', []),
            'sequence_counts': seq_external.get('counts', {}),
            'sequence_clip_counts': seq_external.get('clip_counts', {}),
            'sequence_scanned_clips': seq_external.get('scanned_clips', {}),
            'used_sequence_zip_files': seq_external.get('zip_files', []),
            'synthetic_lower_occlusion_counts': seq_occ_external.get('counts', {}),
            'synthetic_lower_occlusion_clip_counts': seq_occ_external.get('clip_counts', {}),
            'synthetic_lower_occlusion_scanned_clips': seq_occ_external.get('scanned_clips', {}),
            'used_synthetic_lower_occlusion_zip_files': seq_occ_external.get('zip_files', []),
            'synthetic_lower_occlusion_modes': seq_occ_external.get('modes', []),
            'synthetic_vertical_occlusion_counts': seq_vertical_occ_external.get('counts', {}),
            'synthetic_vertical_occlusion_clip_counts': seq_vertical_occ_external.get('clip_counts', {}),
            'synthetic_vertical_occlusion_scanned_clips': seq_vertical_occ_external.get('scanned_clips', {}),
            'used_synthetic_vertical_occlusion_zip_files': seq_vertical_occ_external.get('zip_files', []),
            'synthetic_vertical_occlusion_modes': seq_vertical_occ_external.get('modes', []),
            'aihub62_sequence_counts': seq62_external.get('counts', {}),
            'aihub62_sequence_clip_counts': seq62_external.get('clip_counts', {}),
            'aihub62_sequence_scanned_clips': seq62_external.get('scanned_clips', {}),
            'used_aihub62_annotation_zip_files': seq62_external.get('zip_files', []),
            'aihub62_raw_video_counts': seq62_raw_external.get('counts', {}),
            'aihub62_raw_video_clip_counts': seq62_raw_external.get('clip_counts', {}),
            'aihub62_raw_video_scanned_clips': seq62_raw_external.get('scanned_clips', {}),
            'used_aihub62_raw_video_tar_files': seq62_raw_external.get('tar_files', []),
            'lower_body_occlusion_counts': lower_occ_external.get('counts', {}),
            'lower_body_occlusion_clip_counts': lower_occ_external.get('clip_counts', {}),
            'lower_body_occlusion_scanned_clips': lower_occ_external.get('scanned_clips', {}),
            'lower_body_occlusion_manifest': lower_occ_external.get('manifest_path', ''),
            'lower_body_occlusion_skipped': lower_occ_external.get('skipped', []),
            'rf_intake_pseudo_occlusion_counts': rf_pseudo_occ_external.get('counts', {}),
            'rf_intake_pseudo_occlusion_clip_counts': rf_pseudo_occ_external.get('clip_counts', {}),
            'rf_intake_pseudo_occlusion_scanned_clips': rf_pseudo_occ_external.get('scanned_clips', {}),
            'rf_intake_pseudo_occlusion_skipped': rf_pseudo_occ_external.get('skipped', []),
            'rf_intake_pseudo_occlusion_modes': rf_pseudo_occ_external.get('modes', {}),
            'rf_intake_pseudo_label_note': 'Emergency occlusion rows generated from registered RF-Fall videos using high-confidence active XG-Posture pseudo labels. Replace/validate with true posture labels when AI-Hub 61/62/71461 or HITL posture labels are available.',
            'hitl_posture_intake_counts': hitl_posture_intake.get('counts', {}),
            'hitl_posture_intake_clip_counts': hitl_posture_intake.get('clip_counts', {}),
            'hitl_posture_intake_root': hitl_posture_intake.get('intake_root', ''),
            'hitl_posture_intake_used_files': hitl_posture_intake.get('used_files', []),
            'hitl_posture_intake_skipped': hitl_posture_intake.get('skipped', []),
        },
        'diagnosis': {
            'previous_issue': 'single-frame training rows made temporal behavior features constant zero',
            'fix': 'AI-Hub 61 clip-level windows, AI-Hub 62 2D action windows, optional AI-Hub 62 raw-video YOLO windows, lower-body occlusion rows, and side/vertical occlusion rows now populate motion/velocity/pose-change features for walk/run/sit/lie',
            'weakness_reinforcement': 'sit/lie rows use posture-stable windows plus a transition window; lower-body and side/vertical occlusion rows target hidden-leg and wall/door-frame hard cases; sequence-level lie rescue uses floor/height and horizontal-pose evidence to reduce lie→sit/stand misses',
        },
        'runtime_sequence_policy': {
            'target': 'raise sequence-level behavior accuracy and macro F1 above 0.90 while keeping walk/run guards conservative',
            'lie_rescue_thresholds': {
                'lie_prob_min': 0.12,
                'lie_close_margin': 0.16,
                'max_center_dx': 0.055,
                'max_speed_std': 0.035,
                'max_walk_prob': 0.22,
                'max_run_prob': 0.18,
                'max_upright_geometry_score': 0.58,
            },
        },
    }
    va._write_json(va._xg_posture_summary_path(), summary)
    sync_action_behavior_summary(summary)
    sync_xg_posture_project_assets()
    report = {
        'applied': True,
        'summary_path': va._xg_posture_summary_path(),
        'model_path': model_path,
        'best': best,
        'class_distribution': class_dist,
        'loaded_class_distribution': loaded_class_dist,
        'full_class_distribution': full_class_dist,
        'active_classes': list(active_classes),
        'dropped_classes': list(dropped_classes),
        'group_distribution': {k: int(v) for k, v in group_counts.items()},
        'source_distribution': {str(k): int(v) for k, v in source_counts.items()},
        'trials': trials,
        'occlusion_auxiliary': occlusion_aux_summary,
        'hitl_posture_intake': {
            'counts': hitl_posture_intake.get('counts', {}),
            'clip_counts': hitl_posture_intake.get('clip_counts', {}),
            'used_files': hitl_posture_intake.get('used_files', []),
            'skipped': hitl_posture_intake.get('skipped', []),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f"complete best={best_name}/{best['feature_set']} grouped_macro_f1={best['f1_macro']} report={REPORT_PATH}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
