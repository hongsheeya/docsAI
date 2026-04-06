#!/usr/bin/env python3
import argparse
import json
import math
import os
import pickle
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if '/opt/app/my_libs' not in sys.path:
    sys.path.insert(0, '/opt/app/my_libs')

import cv2
import joblib
import numpy as np
from ultralytics import YOLO

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
BASELINE_MODEL_REL_PATH = Path('storage/training/fall-detection/model/baseline_model.json')
TRAINING_SUMMARY_REL_PATH = Path('storage/training/fall-detection/model/training_summary.json')
VALIDATION_REPORT_REL_PATH = Path('storage/training/fall-detection/model/validation_report.json')

_PERSON_DETECTOR_CACHE = {'path': None, 'mtime': None, 'model': None}
_CLASSIFIER_CACHE = {'path': None, 'mtime': None, 'model': None}


def read_json(path: Path, default=None):
    try:
        with path.open('r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path


def _get_mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def get_cached_yolo(weights_path: str) -> YOLO:
    mtime = _get_mtime(weights_path)
    if (
        _PERSON_DETECTOR_CACHE['model'] is None
        or _PERSON_DETECTOR_CACHE['path'] != weights_path
        or _PERSON_DETECTOR_CACHE['mtime'] != mtime
    ):
        _PERSON_DETECTOR_CACHE['model'] = YOLO(weights_path)
        _PERSON_DETECTOR_CACHE['path'] = weights_path
        _PERSON_DETECTOR_CACHE['mtime'] = mtime
    return _PERSON_DETECTOR_CACHE['model']


def get_cached_classifier(classifier_path: str):
    mtime = _get_mtime(classifier_path)
    if (
        _CLASSIFIER_CACHE['model'] is None
        or _CLASSIFIER_CACHE['path'] != classifier_path
        or _CLASSIFIER_CACHE['mtime'] != mtime
    ):
        _CLASSIFIER_CACHE['model'] = joblib.load(classifier_path)
        _CLASSIFIER_CACHE['path'] = classifier_path
        _CLASSIFIER_CACHE['mtime'] = mtime
    return _CLASSIFIER_CACHE['model']


def _resolve_unicode_dir(parent: str, target_name: str) -> Optional[str]:
    """Resolve directory name with Unicode NFC/NFD normalization.

    Some filesystems store Korean directory names in NFD (decomposed) form while
    user input is typically NFC (composed). This helper looks up the actual on-disk
    entry that matches after NFC normalisation.
    """
    target_nfc = unicodedata.normalize('NFC', target_name)
    if not os.path.isdir(parent):
        return None
    for entry in os.listdir(parent):
        if unicodedata.normalize('NFC', entry) == target_nfc:
            return os.path.join(parent, entry)
    return None


def resolve_existing_path(path: str) -> str:
    raw = str(path or '').strip()
    if not raw:
        return raw
    candidates = [raw]
    if raw.startswith('/mnt/data/wiz/'):
        candidates.append('/opt/app/' + raw[len('/mnt/data/wiz/'):])
    if raw.startswith('/opt/app/'):
        candidates.append('/mnt/data/wiz/' + raw[len('/opt/app/'):])
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    # Fallback: walk path segments with Unicode normalization
    for candidate in candidates:
        resolved = _resolve_unicode_segments(candidate)
        if resolved and os.path.exists(resolved):
            return resolved
    return raw


def _resolve_unicode_segments(path: str) -> Optional[str]:
    """Walk a path from root, resolving each segment via NFC-normalised lookup."""
    parts = Path(path).parts
    if not parts:
        return None
    current = parts[0]  # root '/'
    for segment in parts[1:]:
        direct = os.path.join(current, segment)
        if os.path.exists(direct):
            current = direct
            continue
        found = _resolve_unicode_dir(current, segment)
        if found is None:
            return None
        current = found
    return current


def get_runtime_context(project_root: Path) -> Dict:
    baseline = read_json(project_root / BASELINE_MODEL_REL_PATH, default={}) or {}
    summary = read_json(project_root / TRAINING_SUMMARY_REL_PATH, default={}) or {}
    weights = resolve_existing_path(baseline.get('weights', ''))
    if not weights or os.path.exists(weights) is False:
        raise FileNotFoundError('학습된 weights 파일을 찾을 수 없습니다.')
    return {
        'baseline': baseline,
        'summary': summary,
        'weights': weights,
        'class_names': baseline.get('class_names', []) or ['fall', 'normal'],
        'model_name': baseline.get('model', 'yolo11n-cls.pt'),
    }


def build_model(project_root: Path) -> Tuple[YOLO, Dict]:
    context = get_runtime_context(project_root)
    model = YOLO(context['weights'])
    return model, context


def video_meta(video_path: str) -> Dict:
    cap = cv2.VideoCapture(video_path)
    if cap.isOpened() is False:
        raise RuntimeError('영상을 열 수 없습니다.')
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if fps <= 0:
        fps = 30.0
    duration = frame_count / fps if frame_count > 0 else 0.0
    return {
        'fps': round(fps, 4),
        'frame_count': frame_count,
        'duration_sec': round(duration, 4),
        'width': width,
        'height': height,
    }


def sample_frame_indices(frame_count: int, sample_count: int) -> List[int]:
    if frame_count <= 0:
        return [0]
    wanted = max(1, min(sample_count, frame_count))
    if wanted == 1:
        return [max(0, frame_count // 2)]
    indices = set()
    for idx in range(wanted):
        position = int(round((frame_count - 1) * (idx / (wanted - 1))))
        indices.add(max(0, min(frame_count - 1, position)))
    return sorted(indices)


def crop_candidates(frame):
    h, w = frame.shape[:2]
    crops = [frame]

    def add_crop(x1_ratio, y1_ratio, x2_ratio, y2_ratio):
        x1 = max(0, min(w - 1, int(round(w * x1_ratio))))
        y1 = max(0, min(h - 1, int(round(h * y1_ratio))))
        x2 = max(x1 + 1, min(w, int(round(w * x2_ratio))))
        y2 = max(y1 + 1, min(h, int(round(h * y2_ratio))))
        candidate = frame[y1:y2, x1:x2]
        if candidate.size > 0:
            crops.append(candidate)

    add_crop(0.15, 0.10, 0.85, 0.95)
    return crops[:2]


def _probs_to_list(probs) -> List[float]:
    data = getattr(probs, 'data', None)
    if data is None:
        return []
    if hasattr(data, 'detach'):
        data = data.detach()
    if hasattr(data, 'cpu'):
        data = data.cpu()
    if hasattr(data, 'tolist'):
        return [float(x) for x in data.tolist()]
    return [float(x) for x in data]


def _class_map(names) -> Dict[str, int]:
    mapping = {}
    if isinstance(names, dict):
        iterable = names.items()
    else:
        iterable = enumerate(names or [])
    for idx, label in iterable:
        mapping[str(label).lower()] = int(idx)
    return mapping


def infer_frame(model: YOLO, frame, imgsz: int) -> Dict:
    candidates = crop_candidates(frame)
    results = model.predict(source=candidates, verbose=False, imgsz=imgsz, device='cpu')
    best = None
    for crop_index, result in enumerate(results):
        class_map = _class_map(getattr(result, 'names', getattr(model, 'names', {})))
        probs = _probs_to_list(getattr(result, 'probs', None))
        if not probs:
            continue
        fall_idx = class_map.get('fall', 0)
        normal_idx = class_map.get('normal', 1 if len(probs) > 1 else 0)
        fall_score = float(probs[fall_idx]) if fall_idx < len(probs) else 0.0
        normal_score = float(probs[normal_idx]) if normal_idx < len(probs) else max(0.0, 1.0 - fall_score)
        payload = {
            'fall_score': round(fall_score, 6),
            'normal_score': round(normal_score, 6),
            'top1_index': int(getattr(result.probs, 'top1', 0)),
            'top1_confidence': round(float(getattr(result.probs, 'top1conf', 0.0) or 0.0), 6),
            'crop_index': crop_index,
        }
        if best is None or payload['fall_score'] > best['fall_score']:
            best = payload
    if best is None:
        raise RuntimeError('프레임 추론 결과를 얻지 못했습니다.')
    return best


def _downscale_frame(frame, max_dim: int = 640):
    """Pre-downscale large frames (e.g. 4K) to reduce crop/predict overhead."""
    h, w = frame.shape[:2]
    if max(h, w) <= max_dim:
        return frame
    scale = max_dim / max(h, w)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def infer_video(model: YOLO, context: Dict, video_path: str, threshold: float, sample_count: int, imgsz: int) -> Dict:
    import time as _time
    t_start = _time.monotonic()

    meta = video_meta(video_path)
    cap = cv2.VideoCapture(video_path)
    if cap.isOpened() is False:
        raise RuntimeError('영상을 열 수 없습니다.')
    frame_indices = sample_frame_indices(meta['frame_count'], sample_count)
    frame_results = []
    for frame_index in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if ok is False or frame is None:
            continue
        frame = _downscale_frame(frame, max_dim=640)
        frame_prediction = infer_frame(model, frame, imgsz)
        frame_prediction['frame_index'] = int(frame_index)
        frame_prediction['time_sec'] = round(frame_index / meta['fps'], 4) if meta['fps'] > 0 else 0.0
        frame_results.append(frame_prediction)
    cap.release()
    if not frame_results:
        raise RuntimeError('영상에서 추론 가능한 프레임을 확보하지 못했습니다.')

    sorted_frames = sorted(frame_results, key=lambda item: item.get('fall_score', 0.0), reverse=True)
    max_score = float(sorted_frames[0].get('fall_score', 0.0))
    top_scores = [float(item.get('fall_score', 0.0)) for item in sorted_frames[:min(3, len(sorted_frames))]]
    top_mean = sum(top_scores) / len(top_scores)
    positive_ratio = sum(1 for item in frame_results if float(item.get('fall_score', 0.0)) >= threshold) / len(frame_results)
    final_score = max_score * 0.65 + top_mean * 0.25 + positive_ratio * 0.10
    final_score = round(max(0.0, min(0.999999, final_score)), 6)
    best_event = sorted_frames[0]
    elapsed = round(_time.monotonic() - t_start, 3)
    return {
        'status': 'ok',
        'runtime': 'trained-yolo-runtime',
        'threshold': threshold,
        'sample_count': len(frame_results),
        'fall_score': final_score,
        'fall_detected': final_score >= threshold,
        'positive_frame_ratio': round(positive_ratio, 6),
        'event_time_sec': round(float(best_event.get('time_sec', 0.0) or 0.0), 4),
        'elapsed_sec': elapsed,
        'top_frames': sorted_frames[:5],
        'video': {
            'path': str(video_path),
            **meta,
        },
        'model': {
            'name': context.get('model_name', ''),
            'weights': context.get('weights', ''),
            'class_names': context.get('class_names', []),
        },
    }


def metric_div(num: float, den: float) -> float:
    return round((num / den) if den else 0.0, 6)


def evaluate_dataset(model: YOLO, context: Dict, dataset_root: Path, threshold: float, sample_count: int, imgsz: int) -> Dict:
    items = []
    error_items = []
    confusion = {'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0}
    per_label = {'Y': 0, 'N': 0}
    for label in ['Y', 'N']:
        label_dir = dataset_root / label
        # Try direct path first, then Unicode-normalised lookup
        if not label_dir.exists():
            resolved = _resolve_unicode_dir(str(dataset_root), label)
            if resolved:
                label_dir = Path(resolved)
            else:
                continue
        for path in sorted(label_dir.iterdir()):
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            actual_fall = label == 'Y'
            try:
                prediction = infer_video(model, context, str(path), threshold=threshold, sample_count=sample_count, imgsz=imgsz)
            except Exception as exc:
                error_items.append({'file': path.name, 'label': label, 'error': str(exc)})
                continue
            predicted_fall = bool(prediction.get('fall_detected', False))
            if actual_fall and predicted_fall:
                confusion['tp'] += 1
            elif (actual_fall is False) and (predicted_fall is False):
                confusion['tn'] += 1
            elif (actual_fall is False) and predicted_fall:
                confusion['fp'] += 1
            else:
                confusion['fn'] += 1
            per_label[label] += 1
            items.append({
                'file': path.name,
                'label': label,
                'predicted_label': 'Y' if predicted_fall else 'N',
                'fall_score': prediction.get('fall_score', 0.0),
                'event_time_sec': prediction.get('event_time_sec', 0.0),
            })
    total = len(items)
    accuracy = metric_div(confusion['tp'] + confusion['tn'], total)
    precision = metric_div(confusion['tp'], confusion['tp'] + confusion['fp'])
    recall = metric_div(confusion['tp'], confusion['tp'] + confusion['fn'])
    f1 = metric_div(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    report = {
        'created_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'dataset_root': str(dataset_root),
        'runtime': 'trained-yolo-runtime',
        'threshold': threshold,
        'sample_count': total,
        'label_count': per_label,
        'metrics': {
            'accuracy': round(accuracy, 6),
            'precision': round(precision, 6),
            'recall': round(recall, 6),
            'f1': round(f1, 6),
            **confusion,
        },
        'errors': [item for item in items if item['label'] != item['predicted_label']][:10],
        'skipped': error_items,
        'items': items,
        'model': {
            'name': context.get('model_name', ''),
            'weights': context.get('weights', ''),
        },
    }
    return report


def command_infer(args):
    project_root = Path(args.project_root).resolve()
    if args.mode == 'person-feature':
        result = command_infer_person_feature(project_root, args)
        print(json.dumps(result, ensure_ascii=False))
        return
    model, context = build_model(project_root)
    result = infer_video(model, context, resolve_existing_path(args.video), threshold=args.threshold, sample_count=args.sample_count, imgsz=args.imgsz)
    print(json.dumps(result, ensure_ascii=False))


def command_evaluate(args):
    project_root = Path(args.project_root).resolve()
    dataset_root = Path(resolve_existing_path(args.dataset_root)).resolve()
    model, context = build_model(project_root)
    report = evaluate_dataset(model, context, dataset_root, threshold=args.threshold, sample_count=args.sample_count, imgsz=args.imgsz)
    output = Path(args.output) if args.output else (project_root / VALIDATION_REPORT_REL_PATH)
    write_json(output, report)
    print(json.dumps(report, ensure_ascii=False))


# ──────────────────────────────────────────────────────────────────
# Person-Feature Inference Pipeline
# ──────────────────────────────────────────────────────────────────

FEATURE_COLS = [
    'center_dy', 'height_ratio', 'aspect_change', 'stillness',
    'floor_proximity', 'area_change', 'vert_horiz_ratio',
    'max_down_speed', 'avg_conf', 'n_points',
]


def _person_feature_profile(meta, analysis_profile='fast'):
    fps = float(meta.get('fps', 30.0) or 30.0)
    duration = float(meta.get('duration_sec', 0.0) or 0.0)
    if analysis_profile == 'fast':
        target_processed_fps = 8.0 if fps >= 24 else 6.0
        vid_stride = max(1, int(round(fps / target_processed_fps)))
        max_duration_sec = min(max(duration, 0.0), 6.0) if duration > 0 else 6.0
        return {
            'profile': 'fast',
            'vid_stride': vid_stride,
            'track_imgsz': 320,
            'track_conf': 0.35,
            'track_iou': 0.5,
            'window_sec': 0.75,
            'stride_sec': 0.35,
            'max_duration_sec': max(3.0, max_duration_sec),
            'presence_check_frames': 4,
            'presence_conf': 0.30,
        }
    return {
        'profile': 'balanced',
        'vid_stride': 3,  # FN-0017: was 1 → 3 to reduce frame count ~3x for performance
        'track_imgsz': 352,
        'track_conf': 0.30,
        'track_iou': 0.5,
        'window_sec': 1.0,
        'stride_sec': 0.5,
        'max_duration_sec': duration if duration > 0 else 0.0,
        'presence_check_frames': 4,
        'presence_conf': 0.25,
    }


def _quick_person_presence_check(detector, video_path, meta, profile):
    frame_count = int(meta.get('frame_count', 0) or 0)
    indices = sample_frame_indices(frame_count, int(profile.get('presence_check_frames', 4) or 4))
    cap = cv2.VideoCapture(video_path)
    if cap.isOpened() is False:
        raise RuntimeError('영상을 열 수 없습니다.')
    try:
        for frame_index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if ok is False or frame is None:
                continue
            results = detector.predict(
                source=frame,
                verbose=False,
                imgsz=int(profile.get('track_imgsz', 320) or 320),
                conf=float(profile.get('presence_conf', 0.3) or 0.3),
                device='cpu',
                classes=[0],
            )
            for result in results:
                boxes = getattr(result, 'boxes', None)
                if boxes is not None and len(boxes) > 0:
                    return True
    finally:
        cap.release()
    return False


def _summarize_track(points, fps):
    if len(points) < 3:
        return {}
    points = sorted(points, key=lambda item: item[0])
    frames = [p[0] for p in points]
    cxs = [p[1] for p in points]
    cys = [p[2] for p in points]
    ws = [p[3] for p in points]
    hs = [p[4] for p in points]
    speeds = []
    for i in range(1, len(points)):
        d_frame = max(1, frames[i] - frames[i - 1])
        dt = d_frame / fps if fps > 0 else 1.0
        dx = cxs[i] - cxs[i - 1]
        dy = cys[i] - cys[i - 1]
        speeds.append(math.sqrt(dx ** 2 + dy ** 2) / max(dt, 1e-6))
    avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
    max_speed = max(speeds) if speeds else 0.0
    avg_aspect_ratio = 0.0
    valid_ratios = [w / h for w, h in zip(ws, hs) if h > 1e-6]
    if valid_ratios:
        avg_aspect_ratio = sum(valid_ratios) / len(valid_ratios)
    stillness = _compute_window_features(points, fps).get('stillness', 0.0)
    return {
        'duration_sec': round((frames[-1] - frames[0]) / fps, 3) if fps > 0 else 0.0,
        'avg_speed': round(avg_speed, 6),
        'max_speed': round(max_speed, 6),
        'avg_aspect_ratio': round(avg_aspect_ratio, 6),
        'final_aspect_ratio': round((ws[-1] / hs[-1]) if hs[-1] > 1e-6 else 0.0, 6),
        'final_floor_proximity': round(cys[-1] + hs[-1] / 2.0, 6),
        'max_floor_proximity': round(max(cy + h / 2.0 for cy, h in zip(cys, hs)), 6),
        'height_ratio_total': round((hs[-1] - hs[0]) / max(hs[0], 1e-6), 6),
        'stillness': round(stillness, 6),
        'points': len(points),
    }


def _compute_window_features(window_points, fps):
    """Compute motion features for a window of tracking points.
    Each point: (frame_idx, cx, cy, w, h, conf) in normalized coords.
    """
    if len(window_points) < 3:
        return None
    frames = [p[0] for p in window_points]
    cxs = [p[1] for p in window_points]
    cys = [p[2] for p in window_points]
    ws = [p[3] for p in window_points]
    hs = [p[4] for p in window_points]
    confs = [p[5] for p in window_points]
    n = len(window_points)
    dt = (frames[-1] - frames[0]) / fps if fps > 0 else 1.0
    if dt <= 0:
        dt = 1.0 / fps if fps > 0 else 1.0

    dy_total = cys[-1] - cys[0]
    center_dy = dy_total / dt
    h_start = hs[0] if hs[0] > 0.001 else 0.001
    height_ratio = (hs[-1] - hs[0]) / h_start
    ar_start = ws[0] / hs[0] if hs[0] > 0.001 else 0
    ar_end = ws[-1] / hs[-1] if hs[-1] > 0.001 else 0
    aspect_change = ar_end - ar_start
    movement_threshold = 0.005
    still_count = 0
    for i in range(1, n):
        dx = abs(cxs[i] - cxs[i - 1])
        dy = abs(cys[i] - cys[i - 1])
        if math.sqrt(dx ** 2 + dy ** 2) < movement_threshold:
            still_count += 1
    stillness = still_count / (n - 1) if n > 1 else 0
    floor_vals = [cy + h / 2 for cy, h in zip(cys, hs)]
    floor_proximity = max(floor_vals)
    area_start = ws[0] * hs[0] if ws[0] * hs[0] > 0.0001 else 0.0001
    area_end = ws[-1] * hs[-1]
    area_change = (area_end - area_start) / area_start
    dx_total = abs(cxs[-1] - cxs[0])
    vert_horiz_ratio = abs(dy_total) / (dx_total + 1e-6)
    max_down_speed = 0
    for i in range(1, n):
        d_frame = frames[i] - frames[i - 1]
        if d_frame > 0:
            speed = (cys[i] - cys[i - 1]) / (d_frame / fps) if fps > 0 else 0
            max_down_speed = max(max_down_speed, speed)
    avg_conf = sum(confs) / n

    return {
        'center_dy': round(center_dy, 6),
        'height_ratio': round(height_ratio, 6),
        'aspect_change': round(aspect_change, 6),
        'stillness': round(stillness, 6),
        'floor_proximity': round(floor_proximity, 6),
        'area_change': round(area_change, 6),
        'vert_horiz_ratio': round(vert_horiz_ratio, 6),
        'max_down_speed': round(max_down_speed, 6),
        'avg_conf': round(avg_conf, 4),
        'n_points': n,
    }


def _person_feature_infer(person_detector_path, classifier_path, video_path, threshold=0.5, analysis_profile='fast'):
    """Run person detection + tracking → feature extraction → XGBoost classification."""
    import time as _time
    t_start = _time.monotonic()
    _perf = {}

    # Video meta
    meta = video_meta(video_path)
    fps = meta['fps']
    video_w = meta['width']
    video_h = meta['height']
    profile = _person_feature_profile(meta, analysis_profile)

    # Load person detector
    _t = _time.monotonic()
    detector = get_cached_yolo(person_detector_path)
    _perf['model_load'] = round(_time.monotonic() - _t, 3)

    if _quick_person_presence_check(detector, video_path, meta, profile) is False:
        elapsed = round(_time.monotonic() - t_start, 3)
        _perf['total'] = elapsed
        return {
            'status': 'ok',
            'runtime': 'person-feature-runtime',
            'profile': profile['profile'],
            'profile_config': profile,
            'fall_score': 0.0,
            'fall_detected': False,
            'fall_probability': 0.0,
            'summary': '초기 프리체크에서 사람을 검출하지 못했습니다.',
            'tracks': 0,
            'windows': 0,
            'processed_frames': 0,
            'elapsed_sec': elapsed,
            'perf': _perf,
            'video': {'path': str(video_path), **meta},
            'feature_importance': {},
            'top_features': {},
        }

    # Load XGBoost classifier
    classifier = get_cached_classifier(classifier_path)

    # Run tracking on entire video
    _t = _time.monotonic()
    track_data = {}  # track_id -> list of (frame_idx, cx, cy, w, h, conf)
    # FN-0012: Collect detection_frames for visualization
    detection_frames = []
    frame_idx = 0
    processed_frames = 0
    vid_stride = int(profile.get('vid_stride', 1) or 1)
    track_imgsz = int(profile.get('track_imgsz', 320) or 320)
    max_duration_sec = float(profile.get('max_duration_sec', 0.0) or 0.0)
    max_source_frame = int(max_duration_sec * fps) if max_duration_sec > 0 and fps > 0 else 0
    for result in detector.track(source=video_path, stream=True, persist=True, classes=[0],
                                  conf=float(profile.get('track_conf', 0.3) or 0.3),
                                  iou=float(profile.get('track_iou', 0.5) or 0.5),
                                  tracker='bytetrack.yaml', imgsz=track_imgsz,
                                  verbose=False, device='cpu', vid_stride=vid_stride):
        if max_source_frame > 0 and frame_idx > max_source_frame:
            break
        processed_frames += 1
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            frame_idx += vid_stride
            continue
        # FN-0012: Build detection_frames entry with original-resolution coords
        frame_dets = []
        for i in range(len(boxes)):
            track_id_tensor = boxes.id
            if track_id_tensor is None:
                continue
            tid = int(track_id_tensor[i].item())
            if tid < 0:
                continue
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            conf = float(boxes.conf[i].item())
            cx = (x1 + x2) / 2.0 / video_w
            cy = (y1 + y2) / 2.0 / video_h
            w = (x2 - x1) / video_w
            h = (y2 - y1) / video_h
            if tid not in track_data:
                track_data[tid] = []
            track_data[tid].append((frame_idx, cx, cy, w, h, conf))
            # FN-0012: Collect original-resolution bbox for visualization
            frame_dets.append({
                'x1': round(x1, 1), 'y1': round(y1, 1),
                'x2': round(x2, 1), 'y2': round(y2, 1),
                'conf': round(conf, 3),
                'track_id': tid,
            })
        if len(frame_dets) > 0:
            detection_frames.append({
                'frame_idx': frame_idx,
                'time_sec': round(frame_idx / fps, 2) if fps > 0 else 0,
                'detections': frame_dets,
            })
        frame_idx += vid_stride

    _perf['yolo_tracking'] = round(_time.monotonic() - _t, 3)

    if not track_data:
        elapsed = round(_time.monotonic() - t_start, 3)
        _perf['total'] = elapsed
        return {
            'status': 'ok',
            'runtime': 'person-feature-runtime',
            'fall_score': 0.0,
            'fall_detected': False,
            'fall_probability': 0.0,
            'summary': '영상에서 사람을 검출하지 못했습니다.',
            'tracks': 0,
            'windows': 0,
            'processed_frames': processed_frames,
            'profile': profile['profile'],
            'profile_config': profile,
            'elapsed_sec': elapsed,
            'perf': _perf,
            'video': {'path': str(video_path), **meta},
            'feature_importance': {},
            'top_features': {},
        }

    # Sliding windows
    _t = _time.monotonic()
    window_frames = int(fps * float(profile.get('window_sec', 1.0) or 1.0))
    stride_frames = int(fps * float(profile.get('stride_sec', 0.5) or 0.5))
    if window_frames < 2:
        window_frames = 2
    if stride_frames < 1:
        stride_frames = 1

    all_features = []
    window_details = []

    for tid, points in sorted(track_data.items()):
        if len(points) < 3:
            continue
        points.sort(key=lambda x: x[0])
        first_frame = points[0][0]
        last_frame = points[-1][0]
        win_start = first_frame
        while win_start + window_frames <= last_frame + 1:
            win_end = win_start + window_frames
            win_points = [p for p in points if win_start <= p[0] < win_end]
            feats = _compute_window_features(win_points, fps)
            if feats is not None:
                all_features.append([feats[col] for col in FEATURE_COLS])
                window_details.append({
                    'track_id': tid,
                    'window_start': win_start,
                    'window_end': win_end,
                    'time_sec': round(win_start / fps, 3) if fps > 0 else 0,
                    'features': feats,
                })
            win_start += stride_frames

    _perf['feature_extract'] = round(_time.monotonic() - _t, 3)
    elapsed = round(_time.monotonic() - t_start, 3)

    if not all_features:
        _perf['total'] = elapsed
        return {
            'status': 'ok',
            'runtime': 'person-feature-runtime',
            'fall_score': 0.0,
            'fall_detected': False,
            'fall_probability': 0.0,
            'summary': '추적된 사람의 이동 패턴이 부족하여 판단할 수 없습니다.',
            'tracks': len(track_data),
            'windows': 0,
            'processed_frames': processed_frames,
            'profile': profile['profile'],
            'profile_config': profile,
            'elapsed_sec': elapsed,
            'perf': _perf,
            'video': {'path': str(video_path), **meta},
            'feature_importance': {},
            'top_features': {},
        }

    # Classify each window
    _t = _time.monotonic()
    X = np.array(all_features)
    proba = classifier.predict_proba(X)[:, 1]  # P(fall)
    predictions = classifier.predict(X)

    # Aggregate: max probability + ratio of fall-positive windows
    max_prob = float(np.max(proba))
    mean_prob = float(np.mean(proba))
    fall_ratio = float(np.sum(predictions == 1)) / len(predictions)
    # FN-0029: Enhanced final score with floor_proximity and height_ratio boost
    # Base combination: max_prob 45% + mean_prob 25% + fall_ratio 15%
    # + floor_proximity bonus 10% + height_ratio bonus 5%
    peak_idx_for_score = int(np.argmax(proba))
    peak_feats_for_score = window_details[peak_idx_for_score]['features']
    _fp = float(peak_feats_for_score.get('floor_proximity', 0.0) or 0.0)
    _hr = float(peak_feats_for_score.get('height_ratio', 0.0) or 0.0)
    # floor_proximity: higher → closer to ground → stronger fall signal
    _fp_boost = min(1.0, max(0.0, (_fp - 0.5) / 0.5)) if _fp > 0.5 else 0.0
    # height_ratio: more negative → stronger height decrease → stronger fall signal
    _hr_boost = min(1.0, max(0.0, (-_hr - 0.05) / 0.25)) if _hr < -0.05 else 0.0
    final_score = max_prob * 0.45 + mean_prob * 0.25 + fall_ratio * 0.15 + _fp_boost * 0.10 + _hr_boost * 0.05
    final_score = round(max(0.0, min(0.999999, final_score)), 6)
    fall_detected = final_score >= threshold

    # Find peak event time
    peak_idx = int(np.argmax(proba))
    peak_window = window_details[peak_idx]
    event_time = peak_window['time_sec']

    # Top windows by probability
    sorted_indices = np.argsort(proba)[::-1][:5]
    top_windows = []
    for idx in sorted_indices:
        w = window_details[int(idx)]
        top_windows.append({
            'track_id': w['track_id'],
            'time_sec': w['time_sec'],
            'fall_probability': round(float(proba[int(idx)]), 4),
            'features': w['features'],
        })

    # Feature descriptions for analysis_basis
    peak_feats = peak_window['features']
    top_features = {
        'max_down_speed': round(peak_feats.get('max_down_speed', 0), 4),
        'center_dy': round(peak_feats.get('center_dy', 0), 4),
        'aspect_change': round(peak_feats.get('aspect_change', 0), 4),
        'floor_proximity': round(peak_feats.get('floor_proximity', 0), 4),
        'height_ratio': round(peak_feats.get('height_ratio', 0), 4),
        'stillness': round(peak_feats.get('stillness', 0), 4),
    }
    motion_gate = {
        'max_down_speed': float(peak_feats.get('max_down_speed', 0.0) or 0.0) >= 0.15,
        'center_dy': float(peak_feats.get('center_dy', 0.0) or 0.0) >= 0.03,
        'pose_change': (
            float(peak_feats.get('height_ratio', 0.0) or 0.0) <= -0.05
            or float(peak_feats.get('aspect_change', 0.0) or 0.0) >= 0.05
            or float(peak_feats.get('floor_proximity', 0.0) or 0.0) >= 0.78
        ),
    }
    # FN-0029: If floor_proximity is very high (>0.85) and height decreased,
    # pass motion gate even if speed/dy are borderline
    _fp_val = float(peak_feats.get('floor_proximity', 0.0) or 0.0)
    _hr_val = float(peak_feats.get('height_ratio', 0.0) or 0.0)
    _mds_val = float(peak_feats.get('max_down_speed', 0.0) or 0.0)
    _floor_height_override = _fp_val >= 0.85 and _hr_val <= -0.08
    # FN-0031: Additional override — high floor_proximity + high down speed
    # covers cases where center_dy is low but person clearly fell (e.g., quick drop near ground)
    _floor_speed_override = _fp_val >= 0.75 and _mds_val >= 0.3
    # FN-0031: majority vote — pass if 2 of 3 conditions met (instead of all 3)
    _gate_pass_count = sum(1 for v in motion_gate.values() if v)
    _majority_pass = _gate_pass_count >= 2
    motion_gate_passed = _majority_pass or _floor_height_override or _floor_speed_override
    if motion_gate_passed is False:
        final_score = min(final_score, max_prob * 0.35, mean_prob * 0.45, 0.35)
        fall_detected = False
    final_score = round(max(0.0, min(0.999999, final_score)), 6)
    if motion_gate_passed:
        fall_detected = final_score >= threshold
    longest_track = max(track_data.items(), key=lambda item: len(item[1]))
    track_summary = _summarize_track(longest_track[1], fps)

    _perf['xgboost_predict'] = round(_time.monotonic() - _t, 3)
    elapsed = round(_time.monotonic() - t_start, 3)
    _perf['total'] = elapsed

    return {
        'status': 'ok',
        'runtime': 'person-feature-runtime',
        'profile': profile['profile'],
        'profile_config': profile,
        'threshold': threshold,
        'fall_score': final_score,
        'fall_detected': fall_detected,
        'fall_probability': round(max_prob, 4),
        'mean_probability': round(mean_prob, 4),
        'fall_window_ratio': round(fall_ratio, 4),
        'event_time_sec': event_time,
        'elapsed_sec': elapsed,
        'perf': _perf,
        'processed_frames': processed_frames,
        'tracks': len(track_data),
        'windows': len(all_features),
        'top_windows': top_windows,
        'top_features': top_features,
        'motion_gate': {
            'passed': motion_gate_passed,
            'checks': motion_gate,
        },
        'track_summary': track_summary,
        'detection_frames': detection_frames,  # FN-0012: bbox visualization data
        'video': {'path': str(video_path), **meta},
        'model': {
            'person_detector': str(person_detector_path),
            'fall_classifier': str(classifier_path),
        },
    }


def command_infer_person_feature(project_root, args):
    """Person-detect → tracking → feature extraction → XGBoost classification."""
    baseline = read_json(project_root / BASELINE_MODEL_REL_PATH, default={}) or {}

    pd_info = baseline.get('person_detector', {}) or {}
    pd_weights = resolve_existing_path(pd_info.get('weights', ''))
    if not pd_weights or not os.path.exists(pd_weights):
        raise FileNotFoundError('Person detector weights를 찾을 수 없습니다.')

    fc_info = baseline.get('fall_classifier', {}) or {}
    fc_path_raw = fc_info.get('path', '')
    # Resolve relative path against project root
    if fc_path_raw and not os.path.isabs(fc_path_raw):
        fc_path = str(project_root / fc_path_raw)
    else:
        fc_path = resolve_existing_path(fc_path_raw)
    if not fc_path or not os.path.exists(fc_path):
        raise FileNotFoundError('Fall classifier 모델을 찾을 수 없습니다.')

    video_path = resolve_existing_path(args.video)
    return _person_feature_infer(pd_weights, fc_path, video_path, threshold=args.threshold, analysis_profile=getattr(args, 'profile', 'fast'))


# ──────────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(description='YOLO fall runtime helpers')
    subparsers = parser.add_subparsers(dest='command', required=True)

    infer_parser = subparsers.add_parser('infer', help='Infer fall score from video')
    infer_parser.add_argument('--project-root', required=True)
    infer_parser.add_argument('--video', required=True)
    infer_parser.add_argument('--threshold', type=float, default=0.5)
    infer_parser.add_argument('--sample-count', type=int, default=12)
    infer_parser.add_argument('--imgsz', type=int, default=224)
    infer_parser.add_argument('--profile', choices=['fast', 'balanced'], default='fast')
    infer_parser.add_argument('--mode', choices=['yolo-cls', 'person-feature'], default='yolo-cls',
                              help='Inference mode: yolo-cls (YOLO classification) or person-feature (person detect + XGBoost)')
    infer_parser.set_defaults(func=command_infer)

    eval_parser = subparsers.add_parser('evaluate', help='Evaluate fall model on labeled dataset')
    eval_parser.add_argument('--project-root', required=True)
    eval_parser.add_argument('--dataset-root', required=True)
    eval_parser.add_argument('--output', default='')
    eval_parser.add_argument('--threshold', type=float, default=0.5)
    eval_parser.add_argument('--sample-count', type=int, default=12)
    eval_parser.add_argument('--imgsz', type=int, default=224)
    eval_parser.set_defaults(func=command_evaluate)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
