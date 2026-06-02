#!/usr/bin/env python3
import datetime
import importlib.util
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
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
LOWER_BODY_KP = {11, 12, 13, 14, 15, 16}
LOWER_DISTAL_KP = {13, 14, 15, 16}
ANKLE_KP = {15, 16}
LEFT_BODY_KP = {5, 7, 9, 11, 13, 15}
RIGHT_BODY_KP = {6, 8, 10, 12, 14, 16}


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
    if label in ('walk', 'run'):
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


def load_aihub61_sequence_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=4):
    limits = dict(class_clip_limits or {'walk': 180, 'run': 180, 'sit': 180, 'lie': 180})
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_zips = []
    for label, zip_path in va._aihub61_label_zip_paths():
        if label not in limits or limits[label] <= 0:
            continue
        used_zips.append(zip_path)
        log(f'aihub61 sequence scan label={label} zip={os.path.basename(zip_path)}')
        with zipfile.ZipFile(zip_path) as archive:
            by_clip = defaultdict(list)
            for name in archive.namelist():
                if not name.endswith('.json') or '/._' in name or os.path.basename(name).startswith('._'):
                    continue
                by_clip[os.path.dirname(name)].append(name)
            for clip_id in sorted(by_clip):
                if clip_counts[label] >= limits[label]:
                    break
                names = sorted(by_clip[clip_id])
                scanned_clips[label] += 1
                timeseries = []
                for frame_idx, name in enumerate(names):
                    try:
                        data = json.loads(archive.read(name).decode('utf-8'))
                    except Exception:
                        continue
                    frame = _frame_from_aihub61_json(va, data, name, frame_idx)
                    if frame is not None:
                        timeseries.append(frame)
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
        'zip_files': used_zips,
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


def _occlude_lower_body_frame(frame, mode):
    item = _copy_frame(frame)
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


def _occlude_lower_body_timeseries(timeseries, mode):
    return [_occlude_lower_body_frame(frame, mode) for frame in timeseries]


def _occlude_vertical_body_frame(frame, mode):
    item = _copy_frame(frame)
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


def _occlude_vertical_body_timeseries(timeseries, mode):
    return [_occlude_vertical_body_frame(frame, mode) for frame in timeseries]


def load_aihub61_lower_occlusion_sequence_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=2, modes=None):
    limits = dict(class_clip_limits or {'walk': 48, 'run': 48, 'sit': 48, 'lie': 48})
    selected_modes = [mode for mode in (modes or LOWER_OCCLUSION_MODES) if mode in LOWER_OCCLUSION_MODES]
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_zips = []
    for label, zip_path in va._aihub61_label_zip_paths():
        if label not in limits or limits[label] <= 0:
            continue
        used_zips.append(zip_path)
        log(f'aihub61 lower-occlusion scan label={label} zip={os.path.basename(zip_path)} modes={",".join(selected_modes)}')
        with zipfile.ZipFile(zip_path) as archive:
            by_clip = defaultdict(list)
            for name in archive.namelist():
                if not name.endswith('.json') or '/._' in name or os.path.basename(name).startswith('._'):
                    continue
                by_clip[os.path.dirname(name)].append(name)
            for clip_id in sorted(by_clip):
                if clip_counts[label] >= limits[label]:
                    break
                names = sorted(by_clip[clip_id])
                scanned_clips[label] += 1
                timeseries = []
                for frame_idx, name in enumerate(names):
                    try:
                        data = json.loads(archive.read(name).decode('utf-8'))
                    except Exception:
                        continue
                    frame = _frame_from_aihub61_json(va, data, name, frame_idx)
                    if frame is not None:
                        timeseries.append(frame)
                if len(timeseries) < 8:
                    continue

                accepted = False
                for mode in selected_modes:
                    occluded = _occlude_lower_body_timeseries(timeseries, mode)
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
        'zip_files': used_zips,
        'modes': selected_modes,
    }


def load_aihub61_vertical_occlusion_sequence_rows(va, feature_cols, class_clip_limits=None, windows_per_clip=2, modes=None):
    limits = dict(class_clip_limits or {'walk': 36, 'run': 36, 'sit': 36, 'lie': 36})
    selected_modes = [mode for mode in (modes or VERTICAL_OCCLUSION_MODES) if mode in VERTICAL_OCCLUSION_MODES]
    rows = []
    counts = Counter()
    clip_counts = Counter()
    scanned_clips = Counter()
    used_zips = []
    for label, zip_path in va._aihub61_label_zip_paths():
        if label not in limits or limits[label] <= 0:
            continue
        used_zips.append(zip_path)
        log(f'aihub61 vertical-occlusion scan label={label} zip={os.path.basename(zip_path)} modes={",".join(selected_modes)}')
        with zipfile.ZipFile(zip_path) as archive:
            by_clip = defaultdict(list)
            for name in archive.namelist():
                if not name.endswith('.json') or '/._' in name or os.path.basename(name).startswith('._'):
                    continue
                by_clip[os.path.dirname(name)].append(name)
            for clip_id in sorted(by_clip):
                if clip_counts[label] >= limits[label]:
                    break
                names = sorted(by_clip[clip_id])
                scanned_clips[label] += 1
                timeseries = []
                for frame_idx, name in enumerate(names):
                    try:
                        data = json.loads(archive.read(name).decode('utf-8'))
                    except Exception:
                        continue
                    frame = _frame_from_aihub61_json(va, data, name, frame_idx)
                    if frame is not None:
                        timeseries.append(frame)
                if len(timeseries) < 8:
                    continue

                accepted = False
                for mode in selected_modes:
                    occluded = _occlude_vertical_body_timeseries(timeseries, mode)
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
        'zip_files': used_zips,
        'modes': selected_modes,
    }


def build_static_lower_occlusion_rows(static_rows, feature_cols, class_limits=None):
    limits = dict(class_limits or {'stand': 180, 'sit': 120, 'lie': 120})
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
    limits = dict(class_limits or {'stand': 140, 'sit': 100, 'lie': 100})
    selected_modes = [mode for mode in (modes or VERTICAL_OCCLUSION_MODES) if mode in VERTICAL_OCCLUSION_MODES]
    if not selected_modes:
        selected_modes = list(VERTICAL_OCCLUSION_MODES)
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


def feature_sets(all_cols):
    temporal = {
        'center_dy', 'center_dx_abs_mean', 'center_x_span', 'max_down_speed',
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
        'hip_width', 'wrist_width', 'shoulder_hip_ratio', 'wrist_shoulder_ratio',
        'elbow_bend_mean', 'arm_extension_ratio', 'body_compactness',
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
        'gait_dynamic_score', 'run_stride_score', 'sit_geometry_score',
        'lie_geometry_score', 'upright_geometry_score', 'knee_bend_intensity',
        'stationary_bent_score', 'flatness_score', 'support_stability_score',
        'pose_compactness_score', 'dynamic_pose_ratio', 'low_height_floor_score',
        'floor_height_ratio', 'horizontal_pose_score', 'lie_stand_separation_score',
        'standing_skeleton_score', 'lying_skeleton_score', 'sitting_skeleton_score',
    }
    all_cols = [c for c in all_cols if c != 'n_points']
    return {
        'all_runtime_64': all_cols,
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


def sequence_group_policy(pred, avg_probs, feature_avg):
    stand_i = CLASSES.index('stand')
    walk_i = CLASSES.index('walk')
    run_i = CLASSES.index('run')
    sit_i = CLASSES.index('sit')
    lie_i = CLASSES.index('lie')
    if pred not in (stand_i, sit_i):
        return pred

    lie_prob = float(avg_probs[lie_i])
    stand_prob = float(avg_probs[stand_i])
    sit_prob = float(avg_probs[sit_i])
    walk_prob = float(avg_probs[walk_i])
    run_prob = float(avg_probs[run_i])
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
    no_gait = walk_prob < 0.22 and run_prob < 0.18
    close_lie_probability = lie_prob >= max(stand_prob, sit_prob) - 0.16
    if lie_prob >= 0.12 and close_lie_probability and lie_geometry and not_upright and low_motion and no_gait:
        return lie_i
    return pred


def sequence_group_metrics(df, y, groups, proba):
    import numpy as np
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

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
        policy_pred = sequence_group_policy(pred, avg_probs, feature_avg)
        adjusted += int(policy_pred != pred)
        y_true.append(true_label)
        y_pred.append(policy_pred)

    report = classification_report(y_true, y_pred, target_names=CLASSES, output_dict=True, zero_division=0)
    return {
        'accuracy': round(float(accuracy_score(y_true, y_pred)), 4),
        'f1_macro': round(float(f1_score(y_true, y_pred, average='macro', zero_division=0)), 4),
        'class_recall': {c: round(float(report[c]['recall']), 4) for c in CLASSES},
        'class_precision': {c: round(float(report[c]['precision']), 4) for c in CLASSES},
        'class_f1': {c: round(float(report[c]['f1-score']), 4) for c in CLASSES},
        'confusion_matrix': confusion_matrix(y_true, y_pred, labels=list(range(len(CLASSES)))).tolist(),
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
        'walk': env_int('POSTURE_STATIC_WALK_LIMIT', 0),
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

    static_occ_external = {'rows': [], 'counts': {}}
    if os.environ.get('POSTURE_INCLUDE_SYNTH_LOWER_OCCLUSION', '0') == '1':
        static_occ_limit = int(os.environ.get('POSTURE_SYNTH_STATIC_OCC_LIMIT', '160') or 160)
        log(f'build static lower-body occlusion rows limit_per_class={static_occ_limit}')
        static_occ_external = build_static_lower_occlusion_rows(
            static_rows,
            all_feature_cols,
            class_limits={'stand': static_occ_limit, 'sit': static_occ_limit, 'lie': static_occ_limit},
        )
    static_occ_rows = list(static_occ_external.get('rows') or [])

    static_vertical_occ_external = {'rows': [], 'counts': {}, 'modes': []}
    if os.environ.get('POSTURE_INCLUDE_SYNTH_VERTICAL_OCCLUSION', '0') == '1':
        static_vertical_limit = int(os.environ.get('POSTURE_SYNTH_STATIC_VERTICAL_OCC_LIMIT', '120') or 120)
        log(f'build static vertical-body occlusion rows limit_per_class={static_vertical_limit}')
        static_vertical_occ_external = build_static_vertical_occlusion_rows(
            static_rows,
            all_feature_cols,
            class_limits={'stand': static_vertical_limit, 'sit': static_vertical_limit, 'lie': static_vertical_limit},
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

    rows = (
        static_rows
        + static_occ_rows
        + static_vertical_occ_rows
        + seq_rows
        + seq_occ_rows
        + seq_vertical_occ_rows
        + seq62_rows
        + seq62_raw_rows
        + lower_occ_rows
    )
    df = pd.DataFrame(rows)
    df = df[df['posture'].isin(CLASSES)].copy()
    df['group_id'] = [infer_group_id(row) for row in df.to_dict('records')]
    class_dist = {c: int((df['posture'] == c).sum()) for c in CLASSES}
    group_counts = df.groupby('posture')['group_id'].nunique().to_dict()
    source_counts = df.groupby(['posture', 'source']).size().to_dict()
    log(f'training table rows={len(df)} class_dist={class_dist} group_counts={group_counts}')

    class_to_int = {c: i for i, c in enumerate(CLASSES)}
    y = df['posture'].map(class_to_int).to_numpy()
    groups = df['group_id'].to_numpy()
    n_splits = min(5, min(group_counts.values()))
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
        weights = compute_sample_weight(class_weight='balanced', y=y)
        models = candidate_models(len(CLASSES))
        if not models:
            raise RuntimeError('No candidate models selected. Check POSTURE_MODEL_FILTER.')
        for model_name, model in models.items():
            log(f'evaluate feature_set={feature_set_name} model={model_name} n_features={len(cols)}')
            params = {'sample_weight': weights} if model_name.startswith('xgb') else None
            if params:
                oof_probs = cross_val_predict(model, X, y, cv=cv, groups=groups, params=params, method='predict_proba')
            else:
                oof_probs = cross_val_predict(model, X, y, cv=cv, groups=groups, method='predict_proba')
            y_oof = np.asarray(oof_probs).argmax(axis=1).flatten().astype(int)
            report = classification_report(y, y_oof, target_names=CLASSES, output_dict=True, zero_division=0)
            recalls = {c: round(float(report[c]['recall']), 4) for c in CLASSES}
            precision = {c: round(float(report[c]['precision']), 4) for c in CLASSES}
            f1s = {c: round(float(report[c]['f1-score']), 4) for c in CLASSES}
            seq_metrics = sequence_group_metrics(df, y, groups, np.asarray(oof_probs))
            trial = {
                'feature_set': feature_set_name,
                'model': model_name,
                'feature_count': len(cols),
                'accuracy': round(float(accuracy_score(y, y_oof)), 4),
                'f1_macro': round(float(f1_score(y, y_oof, average='macro', zero_division=0)), 4),
                'class_recall': recalls,
                'class_precision': precision,
                'class_f1': f1s,
                'confusion_matrix': confusion_matrix(y, y_oof, labels=list(range(len(CLASSES)))).tolist(),
                'sequence_group_cv': seq_metrics,
                'features': cols,
            }
            boundary_score = (
                recalls.get('walk', 0.0) + recalls.get('run', 0.0)
                + recalls.get('sit', 0.0) + recalls.get('lie', 0.0)
            ) / 4.0
            min_recall = min(recalls.values()) if recalls else 0.0
            weak_class_score = (
                recalls.get('sit', 0.0) * 0.45
                + recalls.get('lie', 0.0) * 0.20
                + precision.get('run', 0.0) * 0.20
                + recalls.get('walk', 0.0) * 0.15
            )
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
        occlusion_row_count = len(static_occ_rows) + len(static_vertical_occ_rows) + len(seq_occ_rows) + len(seq_vertical_occ_rows) + len(lower_occ_rows)
        if occlusion_row_count <= 0:
            return {'ready': False, 'reason': 'no occlusion rows in this run'}

        log(f"fit body-occlusion auxiliary feature_set={best['feature_set']} model={best_name} rows={len(df)} occlusion_rows={occlusion_row_count}")
        X_aux = df[best_cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
        aux_weights = compute_sample_weight(class_weight='balanced', y=y)
        aux_model = candidate_models(len(CLASSES))[best_name]
        if best_name.startswith('xgb'):
            aux_model.fit(X_aux, y, sample_weight=aux_weights)
        else:
            aux_model.fit(X_aux, y)

        y_aux = np.asarray(aux_model.predict(X_aux)).flatten().astype(int)
        aux_train_report = classification_report(y, y_aux, target_names=CLASSES, output_dict=True, zero_division=0)
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
            'classes': CLASSES,
            'n_classes': len(CLASSES),
            'n_windows': int(len(df)),
            'occlusion_training_windows': int(occlusion_row_count),
            'class_distribution': class_dist,
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
                'labels': CLASSES,
                'matrix': best['confusion_matrix'],
            },
            'train_metrics': {
                'accuracy': round(float(accuracy_score(y, y_aux)), 4),
                'f1_macro': round(float(f1_score(y, y_aux, average='macro', zero_division=0)), 4),
                'class_recall': {c: round(float(aux_train_report[c]['recall']), 4) for c in CLASSES},
            },
            'feature_importance': aux_feature_importance,
            'external_pose_dataset': {
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
            },
        }
        aux_model_data = {
            'model': aux_model,
            'classes': CLASSES,
            'feature_cols': list(best_cols),
            'auxiliary': True,
            'purpose': aux_summary['purpose'],
            'trigger_policy': {
                'lower_body_visibility_lt': 0.42,
                'avg_conf_lt': 0.38,
                'main_margin_lt': 0.07,
                'side_body_width_suspected': True,
            },
        }

        persistent_dir = Path('/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux')
        project_dir = Path(PROJECT_ROOT) / 'storage' / 'training' / 'fall-detection' / 'xg-posture-occlusion-aux'
        persistent_dir.mkdir(parents=True, exist_ok=True)
        project_dir.mkdir(parents=True, exist_ok=True)
        model_path = persistent_dir / 'xg_posture_occlusion_aux_model.pkl'
        summary_path = persistent_dir / 'training_summary.json'
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
        shutil.copy2(model_path, project_dir / model_path.name)
        shutil.copy2(summary_path, project_dir / summary_path.name)
        aux_summary['model_path'] = str(model_path)
        aux_summary['summary_path'] = str(summary_path)
        log(f"body occlusion auxiliary saved model={model_path} summary={summary_path}")
        return aux_summary

    previous_summary = va._xg_posture_summary()
    previous_f1 = float(((previous_summary.get('group_cv') or {}).get('f1_macro')) or 0.0)
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
            'group_distribution': {k: int(v) for k, v in group_counts.items()},
            'source_distribution': {str(k): int(v) for k, v in source_counts.items()},
            'trials': trials,
            'occlusion_auxiliary': occlusion_aux_summary,
        }
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        sync_action_behavior_summary(previous_summary)
        sync_xg_posture_project_assets()
        log(f"candidate skipped active_f1={previous_f1} candidate_f1={best['f1_macro']} active_sit={previous_sit_recall} candidate_sit={best_sit_recall}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    log(f"fit final best feature_set={best['feature_set']} model={best_name} f1={best['f1_macro']}")
    X_final = df[best_cols].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    weights = compute_sample_weight(class_weight='balanced', y=y)
    final_model = candidate_models(len(CLASSES))[best_name]
    if best_name.startswith('xgb'):
        final_model.fit(X_final, y, sample_weight=weights)
    else:
        final_model.fit(X_final, y)

    y_train = np.asarray(final_model.predict(X_final)).flatten().astype(int)
    train_report = classification_report(y, y_train, target_names=CLASSES, output_dict=True, zero_division=0)
    train_metrics = {
        'accuracy': round(float(accuracy_score(y, y_train)), 4),
        'f1_macro': round(float(f1_score(y, y_train, average='macro', zero_division=0)), 4),
        'class_recall': {c: round(float(train_report[c]['recall']), 4) for c in CLASSES},
    }
    feature_importance = {}
    if hasattr(final_model, 'feature_importances_'):
        feature_importance = {
            col: round(float(imp), 4)
            for col, imp in zip(best_cols, final_model.feature_importances_)
        }

    model_data = {
        'model': final_model,
        'classes': CLASSES,
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
        'group_distribution': {k: int(v) for k, v in group_counts.items()},
        'source_distribution': {str(k): int(v) for k, v in source_counts.items()},
        'features': list(best_cols),
        'feature_count': len(best_cols),
        'n_features': len(best_cols),
        'classes': CLASSES,
        'active_classes': CLASSES,
        'n_classes': len(CLASSES),
        'n_windows': int(len(df)),
        'model_path': model_path,
        'algorithm': best_name,
        'feature_set': best['feature_set'],
        'class_balance_strategy': 'sequence windows + boundary-aware sampling + balanced sample weights',
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
            'labels': CLASSES,
            'matrix': best['confusion_matrix'],
        },
        'train_metrics': train_metrics,
        'feature_importance': feature_importance,
        'candidate_trials': trials,
        'external_pose_dataset': {
            'static_counts': static_external.get('counts', {}),
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
        'group_distribution': {k: int(v) for k, v in group_counts.items()},
        'source_distribution': {str(k): int(v) for k, v in source_counts.items()},
        'trials': trials,
        'occlusion_auxiliary': occlusion_aux_summary,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f"complete best={best_name}/{best['feature_set']} grouped_macro_f1={best['f1_macro']} report={REPORT_PATH}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
