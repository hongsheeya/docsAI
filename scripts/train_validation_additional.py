#!/usr/bin/env python3
"""
FN-0025/0026: Validation additional training pipeline.
Processes batch manifests → extract person bboxes → extract features → train classifiers.

Supports two training targets:
  1. XGBoost fall classifier (person-feature-runtime)
  2. YOLO classification (trained-yolo-runtime)

Usage:
    cd /opt/app/project/main
    # batch-001 only (100 videos)
    python scripts/train_validation_additional.py --batch batch-001

    # both batches (200 videos)
    python scripts/train_validation_additional.py --batch batch-001 batch-002

    # skip bbox extraction if already done
    python scripts/train_validation_additional.py --batch batch-001 --skip-bbox

    # XGBoost only (skip YOLO)
    python scripts/train_validation_additional.py --batch batch-001 --xgb-only
"""

import argparse
import csv
import json
import math
import os
import pickle
import random
import shutil
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path('/opt/app')
PROJECT_ROOT = ROOT / 'project' / 'main'
TRAINING_ROOT = PROJECT_ROOT / 'storage' / 'training' / 'fall-detection'
SAMPLE_ROOT = TRAINING_ROOT / 'validation-samples'
BBOX_ROOT = TRAINING_ROOT / 'validation-bbox'
FEATURE_ROOT = TRAINING_ROOT / 'validation-features'
CLASSIFIER_ROOT = TRAINING_ROOT / 'fall-classifier'
YOLO_WORK_ROOT = TRAINING_ROOT / 'yolo-validation'
MODEL_ROOT = TRAINING_ROOT / 'model'

# Existing training data
EXISTING_BBOX_ROOT = TRAINING_ROOT / 'person-bbox'
EXISTING_FEATURE_ROOT = TRAINING_ROOT / 'fall-features'

STATUS_PATH = MODEL_ROOT / 'training_status.json'
STATUS_MD_PATH = MODEL_ROOT / 'training_status.md'
BASELINE_PATH = MODEL_ROOT / 'baseline_model.json'

os.environ.setdefault('YOLO_CONFIG_DIR', str(TRAINING_ROOT / 'yolo-validation' / 'config'))

FEATURE_COLS = [
    "center_dy", "height_ratio", "aspect_change", "stillness",
    "floor_proximity", "area_change", "vert_horiz_ratio",
    "max_down_speed", "avg_conf", "n_points",
]


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    ensure_dir(Path(path).parent)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_status(stage, message, **extra):
    status = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stage': stage,
        'message': message,
    }
    status.update(extra)
    write_json(STATUS_PATH, status)
    lines = [
        '# Validation 추가학습 현황',
        '',
        f'- 업데이트: {status["updated_at"]}',
        f'- 단계: {stage}',
        f'- 메시지: {message}',
    ]
    for k, v in extra.items():
        lines.append(f'- {k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}')
    ensure_dir(STATUS_MD_PATH.parent)
    STATUS_MD_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'[{status["updated_at"]}] {stage}: {message}')


def load_batch_entries(batch_names):
    """Load entries from batch manifests."""
    entries = []
    for bn in batch_names:
        path = SAMPLE_ROOT / f"{bn}.json"
        if not path.exists():
            print(f"ERROR: {path} not found")
            sys.exit(1)
        manifest = read_json(path)
        for e in manifest['entries']:
            e['batch'] = bn
        entries.extend(manifest['entries'])
        print(f"  Loaded {len(manifest['entries'])} entries from {bn}")
    return entries


# ============================================================
# Phase 1: Person BBox Extraction (adapted from extract_person_bbox.py)
# ============================================================

def extract_bboxes_for_video(model, video_path, label, scene_id, conf=0.3, imgsz=640, vid_stride=2):
    """Extract person bboxes with ByteTrack from a video. Uses vid_stride for speed."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    results = model.track(
        source=video_path,
        stream=True,
        persist=True,
        classes=[0],
        conf=conf,
        imgsz=imgsz,
        tracker="bytetrack.yaml",
        verbose=False,
        vid_stride=vid_stride,
    )

    frames_data = []
    t0 = time.time()

    for frame_idx, result in enumerate(results):
        actual_frame = frame_idx * vid_stride
        boxes = result.boxes
        frame_bboxes = []

        if boxes is not None and len(boxes) > 0:
            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf_val = float(boxes.conf[i])
                track_id = int(boxes.id[i]) if boxes.id is not None else -1
                frame_bboxes.append({
                    "track_id": track_id,
                    "x1": round(x1, 1), "y1": round(y1, 1),
                    "x2": round(x2, 1), "y2": round(y2, 1),
                    "confidence": round(conf_val, 4),
                })

        frames_data.append({
            "frame_idx": actual_frame,
            "timestamp": round(actual_frame / fps, 3) if fps > 0 else 0,
            "persons": frame_bboxes,
        })

    elapsed = time.time() - t0
    total_bboxes = sum(len(f["persons"]) for f in frames_data)
    frames_with_person = sum(1 for f in frames_data if len(f["persons"]) > 0)
    track_ids = set()
    for f in frames_data:
        for p in f["persons"]:
            if p["track_id"] >= 0:
                track_ids.add(p["track_id"])

    return {
        "video_name": f"{label}_{scene_id}",
        "filename": os.path.basename(video_path),
        "label": label,
        "video_meta": {
            "width": width, "height": height,
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "duration_sec": round(total_frames / fps, 2) if fps > 0 else 0,
        },
        "detection_config": {
            "imgsz": imgsz, "conf_threshold": conf, "tracker": "bytetrack",
            "vid_stride": vid_stride,
        },
        "summary": {
            "total_bboxes": total_bboxes,
            "frames_with_person": frames_with_person,
            "frames_processed": len(frames_data),
            "frames_total": total_frames,
            "unique_tracks": len(track_ids),
            "track_ids": sorted(track_ids),
            "processing_time_sec": round(elapsed, 2),
        },
        "frames": frames_data,
    }


def run_bbox_extraction(entries, conf=0.3, imgsz=640, vid_stride=2):
    """Extract person bboxes for all entries."""
    from ultralytics import YOLO

    ensure_dir(BBOX_ROOT)
    write_status('bbox-start', f'{len(entries)}개 영상 person bbox 추출 시작')

    # Check which are already done
    done = set()
    for fn in os.listdir(BBOX_ROOT):
        if fn.endswith('.json') and fn != 'manifest.json':
            done.add(fn.replace('.json', ''))

    todo = []
    for e in entries:
        key = f"{e['category']}_{e['scene_id']}"
        if key in done:
            print(f"  [SKIP] {key} — already extracted")
        else:
            todo.append(e)

    if not todo:
        print("  All bboxes already extracted!")
        return

    print(f"  Extracting bboxes for {len(todo)} videos (stride={vid_stride})...")
    model = YOLO("yolo11n.pt")

    summaries = []
    total_start = time.time()

    for i, entry in enumerate(todo, 1):
        scene_id = entry['scene_id']
        label = entry['category']
        video_path = entry['video_path']
        key = f"{label}_{scene_id}"

        print(f"\n  [{i}/{len(todo)}] {key}")
        result = extract_bboxes_for_video(
            model, video_path, label, scene_id,
            conf=conf, imgsz=imgsz, vid_stride=vid_stride,
        )
        if result is None:
            print(f"    FAILED: cannot open video")
            continue

        out_path = BBOX_ROOT / f"{key}.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
        size_kb = out_path.stat().st_size / 1024
        s = result['summary']
        print(f"    {s['total_bboxes']} bboxes, {s['unique_tracks']} tracks, "
              f"{s['frames_with_person']}/{s['frames_processed']} frames, "
              f"{s['processing_time_sec']:.1f}s  ({size_kb:.0f}KB)")

        summaries.append({
            'video_name': result['video_name'],
            'label': label,
            'total_bboxes': s['total_bboxes'],
            'unique_tracks': s['unique_tracks'],
            'processing_time_sec': s['processing_time_sec'],
        })

        # Status update every 10 videos
        if i % 10 == 0:
            elapsed = time.time() - total_start
            eta = elapsed / i * (len(todo) - i)
            write_status('bbox-progress', f'{i}/{len(todo)} 완료',
                         done=i, total=len(todo),
                         elapsed_sec=round(elapsed),
                         eta_sec=round(eta))

    total_elapsed = time.time() - total_start
    write_status('bbox-complete', f'{len(summaries)}개 영상 bbox 추출 완료',
                 total_time_sec=round(total_elapsed),
                 videos_processed=len(summaries))

    # Save manifest
    manifest = {
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_videos': len(summaries),
        'total_time_sec': round(total_elapsed, 2),
        'config': {'imgsz': imgsz, 'conf': conf, 'vid_stride': vid_stride},
        'videos': summaries,
    }
    write_json(BBOX_ROOT / 'manifest.json', manifest)


# ============================================================
# Phase 2: Feature Extraction (adapted from extract_fall_features.py)
# ============================================================

def build_track_sequences(vdata):
    tracks = {}
    video_w = vdata["video_meta"]["width"]
    video_h = vdata["video_meta"]["height"]

    for fdata in vdata["frames"]:
        fi = fdata["frame_idx"]
        for p in fdata["persons"]:
            tid = p["track_id"]
            if tid < 0:
                continue
            x1, y1, x2, y2 = p["x1"], p["y1"], p["x2"], p["y2"]
            cx = (x1 + x2) / 2.0 / video_w
            cy = (y1 + y2) / 2.0 / video_h
            w = (x2 - x1) / video_w
            h = (y2 - y1) / video_h
            conf = p["confidence"]
            if tid not in tracks:
                tracks[tid] = []
            tracks[tid].append((fi, cx, cy, w, h, conf))

    for tid in tracks:
        tracks[tid].sort(key=lambda x: x[0])
    return tracks


def compute_window_features(window_points, fps):
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
        dt = 1.0 / fps

    dy_total = cys[-1] - cys[0]
    center_dy = dy_total / dt

    h_start = hs[0] if hs[0] > 0.001 else 0.001
    height_ratio = (hs[-1] - hs[0]) / h_start

    def aspect(w, h):
        return w / h if h > 0.001 else 0
    aspect_change = aspect(ws[-1], hs[-1]) - aspect(ws[0], hs[0])

    movement_threshold = 0.005
    still_count = 0
    for i in range(1, n):
        dx = abs(cxs[i] - cxs[i - 1])
        dy = abs(cys[i] - cys[i - 1])
        if math.sqrt(dx**2 + dy**2) < movement_threshold:
            still_count += 1
    stillness = still_count / (n - 1) if n > 1 else 0

    floor_vals = [cy + h / 2 for cy, h in zip(cys, hs)]
    floor_proximity = max(floor_vals)

    area_start = ws[0] * hs[0] if ws[0] * hs[0] > 0.0001 else 0.0001
    area_end = ws[-1] * hs[-1]
    area_change = (area_end - area_start) / area_start

    dx_total = abs(cxs[-1] - cxs[0])
    dy_abs = abs(dy_total)
    vert_horiz_ratio = dy_abs / (dx_total + 1e-6)

    max_down_speed = 0
    for i in range(1, n):
        d_frame = frames[i] - frames[i - 1]
        if d_frame > 0:
            speed = (cys[i] - cys[i - 1]) / (d_frame / fps)
            max_down_speed = max(max_down_speed, speed)

    avg_conf = sum(confs) / n

    return {
        "center_dy": round(center_dy, 6),
        "height_ratio": round(height_ratio, 6),
        "aspect_change": round(aspect_change, 6),
        "stillness": round(stillness, 6),
        "floor_proximity": round(floor_proximity, 6),
        "area_change": round(area_change, 6),
        "vert_horiz_ratio": round(vert_horiz_ratio, 6),
        "max_down_speed": round(max_down_speed, 6),
        "avg_conf": round(avg_conf, 4),
        "n_points": n,
    }


def extract_features_from_bbox(vdata, window_sec=1.0, stride_sec=0.5):
    fps = vdata["video_meta"]["fps"]
    label = vdata["label"]
    vname = vdata["video_name"]
    tracks = build_track_sequences(vdata)

    if not tracks:
        return []

    window_frames = max(2, int(window_sec * fps))
    stride_frames = max(1, int(stride_sec * fps))
    features_list = []

    for tid, points in sorted(tracks.items()):
        if len(points) < 3:
            continue
        first_frame = points[0][0]
        last_frame = points[-1][0]
        win_start = first_frame

        while win_start + window_frames <= last_frame + 1:
            win_end = win_start + window_frames
            win_points = [p for p in points if win_start <= p[0] < win_end]
            feats = compute_window_features(win_points, fps)
            if feats is not None:
                feats["video"] = vname
                feats["label"] = label
                feats["track_id"] = tid
                feats["window_start"] = win_start
                feats["window_end"] = win_end
                features_list.append(feats)
            win_start += stride_frames

    return features_list


def run_feature_extraction(entries):
    """Extract features from all bbox files (validation + existing)."""
    ensure_dir(FEATURE_ROOT)
    write_status('feature-start', 'Feature 추출 시작')

    all_features = []
    processed = 0

    # Process validation bbox files
    entry_keys = {f"{e['category']}_{e['scene_id']}" for e in entries}
    for fn in sorted(os.listdir(BBOX_ROOT)):
        if fn == 'manifest.json' or not fn.endswith('.json'):
            continue
        key = fn.replace('.json', '')
        if key not in entry_keys:
            continue
        path = BBOX_ROOT / fn
        vdata = read_json(path)
        if vdata is None:
            continue
        features = extract_features_from_bbox(vdata)
        if features:
            all_features.extend(features)
            processed += 1

    val_count = len(all_features)
    print(f"  Validation features: {val_count} windows from {processed} videos")

    # Also load existing features (from original training data)
    existing_csv = EXISTING_FEATURE_ROOT / 'fall_features_all.csv'
    existing_count = 0
    if existing_csv.exists():
        with open(existing_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                feat = {}
                for col in FEATURE_COLS:
                    feat[col] = float(row[col])
                feat['video'] = row['video']
                feat['label'] = row['label']
                feat['track_id'] = int(row.get('track_id', 0))
                feat['window_start'] = int(row.get('window_start', 0))
                feat['window_end'] = int(row.get('window_end', 0))
                all_features.append(feat)
                existing_count += 1
        print(f"  Existing features: {existing_count} windows")

    # Save combined features
    feature_cols_full = [
        "video", "label", "track_id", "window_start", "window_end",
    ] + FEATURE_COLS

    combined_csv = FEATURE_ROOT / 'features_combined.csv'
    with open(combined_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=feature_cols_full)
        writer.writeheader()
        for feat in all_features:
            row = {c: feat.get(c, '') for c in feature_cols_full}
            writer.writerow(row)

    # Summary
    y_count = sum(1 for f in all_features if f['label'] == 'Y')
    n_count = sum(1 for f in all_features if f['label'] == 'N')
    unique_videos = len(set(f['video'] for f in all_features))

    summary = {
        'total_windows': len(all_features),
        'validation_windows': val_count,
        'existing_windows': existing_count,
        'y_windows': y_count,
        'n_windows': n_count,
        'unique_videos': unique_videos,
        'csv_path': str(combined_csv),
    }
    write_json(FEATURE_ROOT / 'feature_summary.json', summary)
    write_status('feature-complete', f'Feature 추출 완료: {len(all_features)} windows',
                 summary=summary)

    print(f"  Total: {len(all_features)} windows (Y={y_count}, N={n_count}) from {unique_videos} videos")
    return combined_csv, summary


# ============================================================
# Phase 3: XGBoost Classifier Training
# ============================================================

def train_xgboost(features_csv, output_label='validation'):
    """Train XGBoost fall classifier with expanded dataset."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedKFold, cross_validate
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score,
        f1_score, roc_auc_score, confusion_matrix,
    )

    try:
        from xgboost import XGBClassifier
        HAS_XGB = True
    except ImportError:
        HAS_XGB = False

    write_status('classifier-start', 'XGBoost 분류기 학습 시작')

    # Load data
    X, y, videos = [], [], []
    with open(features_csv, 'r') as f:
        for row in csv.DictReader(f):
            X.append([float(row[col]) for col in FEATURE_COLS])
            y.append(1 if row['label'] == 'Y' else 0)
            videos.append(row['video'])

    X = np.array(X)
    y = np.array(y)
    print(f"\n  Dataset: {X.shape[0]} samples, {X.shape[1]} features")
    print(f"  Y={np.sum(y==1)}, N={np.sum(y==0)}")

    # Build models
    models = {
        'LogisticRegression': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', LogisticRegression(max_iter=1000, random_state=42)),
        ]),
        'RandomForest': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)),
        ]),
    }
    if HAS_XGB:
        models['XGBoost'] = Pipeline([
            ('scaler', StandardScaler()),
            ('clf', XGBClassifier(max_depth=6, n_estimators=200, random_state=42,
                                  eval_metric='logloss', use_label_encoder=False)),
        ])

    # CV evaluation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_results = {}
    for name, pipeline in models.items():
        scoring = {'accuracy': 'accuracy', 'precision': 'precision',
                   'recall': 'recall', 'f1': 'f1', 'roc_auc': 'roc_auc'}
        cv = cross_validate(pipeline, X, y, cv=skf, scoring=scoring, return_train_score=True)
        metrics = {}
        for metric in scoring:
            test_vals = cv[f'test_{metric}']
            train_vals = cv[f'train_{metric}']
            metrics[metric] = {
                'mean': round(float(np.mean(test_vals)), 4),
                'std': round(float(np.std(test_vals)), 4),
                'per_fold': [round(float(v), 4) for v in test_vals],
                'train_mean': round(float(np.mean(train_vals)), 4),
                'train_std': round(float(np.std(train_vals)), 4),
                'train_per_fold': [round(float(v), 4) for v in train_vals],
            }
        cv_results[name] = metrics
        print(f"\n  [{name}]")
        print(f"    F1: {metrics['f1']['mean']:.4f} ± {metrics['f1']['std']:.4f}")
        print(f"    AUC: {metrics['roc_auc']['mean']:.4f} ± {metrics['roc_auc']['std']:.4f}")
        print(f"    Train F1: {metrics['f1']['train_mean']:.4f} | Val F1: {metrics['f1']['mean']:.4f} | Gap: {metrics['f1']['train_mean'] - metrics['f1']['mean']:.4f}")

    # Best model by F1
    best_name = max(cv_results, key=lambda k: cv_results[k]['f1']['mean'])
    print(f"\n  Best model: {best_name} (F1={cv_results[best_name]['f1']['mean']:.4f})")

    # Train on full data
    best_pipeline = models[best_name]
    best_pipeline.fit(X, y)

    # Feature importance
    clf = best_pipeline.named_steps['clf']
    importance = {}
    if hasattr(clf, 'feature_importances_'):
        imp = clf.feature_importances_
        for i in np.argsort(imp)[::-1][:5]:
            importance[FEATURE_COLS[i]] = round(float(imp[i]), 4)
    elif hasattr(clf, 'coef_'):
        coef = np.abs(clf.coef_[0])
        for i in np.argsort(coef)[::-1][:5]:
            importance[FEATURE_COLS[i]] = round(float(coef[i]), 4)

    # Full data metrics
    y_pred = best_pipeline.predict(X)
    y_proba = best_pipeline.predict_proba(X)[:, 1]
    cm = confusion_matrix(y, y_pred)

    # Save
    output_dir = ensure_dir(CLASSIFIER_ROOT)
    model_path = output_dir / 'best_model.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(best_pipeline, f)

    for name, pipeline in models.items():
        pipeline.fit(X, y)
        with open(output_dir / f'{name.lower()}_model.pkl', 'wb') as f:
            pickle.dump(pipeline, f)

    evaluation = {
        'best_model': best_name,
        'cv_folds': 5,
        'training_label': output_label,
        'dataset': {
            'total_samples': int(X.shape[0]),
            'features': int(X.shape[1]),
            'feature_names': FEATURE_COLS,
            'y_count': int(np.sum(y == 1)),
            'n_count': int(np.sum(y == 0)),
        },
        'cv_results': cv_results,
        'feature_importance': importance,
        'full_data_metrics': {
            'accuracy': round(float(accuracy_score(y, y_pred)), 4),
            'precision': round(float(precision_score(y, y_pred)), 4),
            'recall': round(float(recall_score(y, y_pred)), 4),
            'f1': round(float(f1_score(y, y_pred)), 4),
            'auc_roc': round(float(roc_auc_score(y, y_proba)), 4),
            'confusion_matrix': {
                'TN': int(cm[0][0]), 'FP': int(cm[0][1]),
                'FN': int(cm[1][0]), 'TP': int(cm[1][1]),
            },
        },
        'model_path': str(model_path),
    }
    write_json(output_dir / 'evaluation.json', evaluation)
    write_status('classifier-complete', f'XGBoost 학습 완료 (F1={cv_results[best_name]["f1"]["mean"]:.4f})',
                 evaluation_summary={
                     'best_model': best_name,
                     'f1': cv_results[best_name]['f1']['mean'],
                     'auc': cv_results[best_name]['roc_auc']['mean'],
                     'samples': int(X.shape[0]),
                 })

    return evaluation


# ============================================================
# Phase 4: YOLO Classification Training
# ============================================================

def prepare_yolo_dataset(entries, frames_per_video=20, imgsz=224, train_ratio=0.8, seed=42):
    """Extract frames from sampled videos and build YOLO classification dataset."""
    write_status('yolo-prepare', 'YOLO 분류 데이터셋 준비')

    dataset_root = ensure_dir(YOLO_WORK_ROOT / 'dataset')
    if dataset_root.exists():
        shutil.rmtree(dataset_root)

    rng = random.Random(seed)

    # Group by (category, prefix) for video-level split
    grouped = defaultdict(list)
    for e in entries:
        prefix = e['scene_id'].split('_')[0]
        grouped[(e['category'], prefix)].append(e)

    all_frames = []

    for (cat, prefix), group_entries in sorted(grouped.items()):
        class_name = 'fall' if cat == 'Y' else 'normal'
        for entry in group_entries:
            video_path = entry['video_path']
            if not os.path.exists(video_path):
                continue
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                continue
            fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            n = min(frames_per_video, fc)
            indices = sorted(set(int(i * fc / n) for i in range(n)))

            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret:
                    continue
                h, w = frame.shape[:2]
                scale = imgsz / min(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                y_start = (new_h - imgsz) // 2
                x_start = (new_w - imgsz) // 2
                cropped = resized[y_start:y_start + imgsz, x_start:x_start + imgsz]

                all_frames.append({
                    'image': cropped,
                    'class_name': class_name,
                    'category': cat,
                    'video': entry['scene_id'],
                    'prefix': prefix,
                    'frame_idx': idx,
                })
            cap.release()

    print(f"  Extracted {len(all_frames)} frames")

    # Split by prefix to prevent data leakage
    class_prefixes = defaultdict(list)
    for f in all_frames:
        key = (f['class_name'], f['prefix'])
        if key not in class_prefixes:
            class_prefixes[key] = []
        class_prefixes[key].append(f)

    train_frames, val_frames = [], []
    for key, frames in class_prefixes.items():
        rng.shuffle(frames)
    
    # Split by unique prefix
    unique_keys = list(class_prefixes.keys())
    for cls_name in ['fall', 'normal']:
        keys = [k for k in unique_keys if k[0] == cls_name]
        rng.shuffle(keys)
        n_train = max(1, int(len(keys) * train_ratio))
        for k in keys[:n_train]:
            train_frames.extend(class_prefixes[k])
        for k in keys[n_train:]:
            val_frames.extend(class_prefixes[k])

    rng.shuffle(train_frames)
    rng.shuffle(val_frames)

    # Save frames as JPEG
    for split, frames in [('train', train_frames), ('val', val_frames)]:
        for idx, f in enumerate(frames, 1):
            target_dir = ensure_dir(dataset_root / split / f['class_name'])
            fname = f"{f['video']}__f{f['frame_idx']:04d}_{idx:04d}.jpg"
            cv2.imwrite(str(target_dir / fname), f['image'], [cv2.IMWRITE_JPEG_QUALITY, 95])

    class_dist = Counter(f['class_name'] for f in all_frames)
    manifest = {
        'prepared_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'Validation',
        'total_frames': len(all_frames),
        'train_count': len(train_frames),
        'validation_count': len(val_frames),
        'class_distribution': dict(class_dist),
        'classes': sorted(class_dist.keys()),
        'frames_per_video': frames_per_video,
        'train_ratio': train_ratio,
    }
    write_json(YOLO_WORK_ROOT / 'dataset_manifest.json', manifest)
    write_status('yolo-prepare-complete', f'YOLO 데이터셋 준비 완료: {len(all_frames)} frames',
                 manifest=manifest)
    return manifest


def run_yolo_training(entries, epochs=20, imgsz=224, batch=16, seed=42, frames_per_video=20):
    """Train YOLO classification model from validation video frames."""
    from ultralytics import YOLO

    manifest = prepare_yolo_dataset(entries, frames_per_video=frames_per_video,
                                     imgsz=imgsz, seed=seed)

    dataset_root = YOLO_WORK_ROOT / 'dataset'
    runs_root = ensure_dir(YOLO_WORK_ROOT / 'runs')
    run_name = f"val-yolo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    model_name = 'yolo11n-cls.pt'
    try:
        model = YOLO(model_name)
    except Exception:
        model_name = 'yolov8n-cls.pt'
        model = YOLO(model_name)

    write_status('yolo-train-start', f'YOLO 학습 시작 (epochs={epochs})')

    results = model.train(
        data=str(dataset_root),
        project=str(runs_root),
        name=run_name,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        seed=seed,
        device='cpu',
        workers=0,
        pretrained=True,
        plots=False,
        verbose=True,
        exist_ok=False,
        label_smoothing=0.1,
        flipud=0.3,
        fliplr=0.5,
        erasing=0.2,
        dropout=0.2,
    )

    save_dir = Path(getattr(results, 'save_dir', runs_root / run_name))
    best_path = save_dir / 'weights' / 'best.pt'
    last_path = save_dir / 'weights' / 'last.pt'
    results_csv = save_dir / 'results.csv'

    # Parse results
    def safe_float(v):
        try:
            return float(v)
        except:
            return 0.0

    rows = []
    if results_csv.exists():
        with open(results_csv, 'r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
    last_row = rows[-1] if rows else {}
    top1 = safe_float(last_row.get('metrics/accuracy_top1') or last_row.get('metrics/accuracy_top1(B)'))
    top5 = safe_float(last_row.get('metrics/accuracy_top5') or last_row.get('metrics/accuracy_top5(B)'))
    train_loss = safe_float(last_row.get('train/loss'))
    val_loss = safe_float(last_row.get('val/loss'))

    # Track all epoch metrics for overfitting analysis
    epoch_metrics = []
    for row in rows:
        epoch_metrics.append({
            'epoch': int(row.get('epoch', 0)) if row.get('epoch', '').strip() else len(epoch_metrics),
            'train_loss': safe_float(row.get('train/loss')),
            'val_loss': safe_float(row.get('val/loss')),
            'top1': safe_float(row.get('metrics/accuracy_top1') or row.get('metrics/accuracy_top1(B)')),
            'top5': safe_float(row.get('metrics/accuracy_top5') or row.get('metrics/accuracy_top5(B)')),
        })

    yolo_summary = {
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'model_name': model_name,
        'run_name': run_name,
        'best_weights': str(best_path if best_path.exists() else last_path),
        'save_dir': str(save_dir),
        'dataset': manifest,
        'final_metrics': {
            'top1': top1, 'top5': top5,
            'train_loss': train_loss, 'val_loss': val_loss,
        },
        'epoch_metrics': epoch_metrics,
        'arguments': {
            'epochs': epochs, 'imgsz': imgsz, 'batch': batch, 'seed': seed,
        },
    }
    write_json(YOLO_WORK_ROOT / 'training_summary.json', yolo_summary)
    write_status('yolo-complete', f'YOLO 학습 완료 (top1={top1:.4f})',
                 summary={'top1': top1, 'top5': top5, 'train_loss': train_loss, 'val_loss': val_loss})

    return yolo_summary


# ============================================================
# Phase 5: Update baseline model
# ============================================================

def update_baseline(xgb_eval, yolo_summary=None):
    """Update baseline_model.json with new classifier."""
    baseline = read_json(BASELINE_PATH, {})

    baseline['fall_classifier'] = {
        'type': xgb_eval['best_model'],
        'path': 'storage/training/fall-detection/fall-classifier/best_model.pkl',
        'cv_f1': xgb_eval['cv_results'][xgb_eval['best_model']]['f1']['mean'],
        'cv_auc': xgb_eval['cv_results'][xgb_eval['best_model']]['roc_auc']['mean'],
        'features': FEATURE_COLS,
        'training_source': 'validation-additional',
        'dataset_size': xgb_eval['dataset']['total_samples'],
    }
    baseline['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if yolo_summary:
        baseline['weights'] = yolo_summary['best_weights']
        baseline['save_dir'] = yolo_summary['save_dir']
        baseline['source_dataset'] = 'Validation'

    write_json(BASELINE_PATH, baseline)
    print(f"\n  Baseline model updated: {BASELINE_PATH}")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Validation additional training pipeline')
    parser.add_argument('--batch', nargs='+', required=True, help='Batch names (e.g. batch-001 batch-002)')
    parser.add_argument('--skip-bbox', action='store_true', help='Skip bbox extraction')
    parser.add_argument('--xgb-only', action='store_true', help='Train XGBoost only (skip YOLO)')
    parser.add_argument('--yolo-only', action='store_true', help='Train YOLO only (skip XGBoost)')
    parser.add_argument('--skip-train', action='store_true', help='Extract only, no training')
    parser.add_argument('--vid-stride', type=int, default=2, help='Video frame stride for bbox extraction')
    parser.add_argument('--epochs', type=int, default=20, help='YOLO training epochs')
    parser.add_argument('--update-baseline', action='store_true', help='Update baseline_model.json')
    args = parser.parse_args()

    print("=" * 60)
    print("Validation 추가학습 파이프라인")
    print(f"  배치: {args.batch}")
    print("=" * 60)

    # Load entries
    entries = load_batch_entries(args.batch)
    print(f"\n  총 {len(entries)}건 로드")
    cats = Counter(e['category'] for e in entries)
    print(f"  분포: {dict(cats)}")

    # Phase 1: BBox extraction
    if not args.skip_bbox and not args.yolo_only:
        print(f"\n{'='*60}")
        print("Phase 1: Person BBox 추출")
        print(f"{'='*60}")
        run_bbox_extraction(entries, vid_stride=args.vid_stride)

    # Phase 2: Feature extraction
    if not args.yolo_only:
        print(f"\n{'='*60}")
        print("Phase 2: Feature 추출")
        print(f"{'='*60}")
        features_csv, feat_summary = run_feature_extraction(entries)

    # Phase 3: XGBoost training
    xgb_eval = None
    if not args.skip_train and not args.yolo_only:
        print(f"\n{'='*60}")
        print("Phase 3: XGBoost 분류기 학습")
        print(f"{'='*60}")
        label = '+'.join(args.batch)
        xgb_eval = train_xgboost(features_csv, output_label=label)

    # Phase 4: YOLO training
    yolo_summary = None
    if not args.skip_train and not args.xgb_only:
        print(f"\n{'='*60}")
        print("Phase 4: YOLO 분류 학습")
        print(f"{'='*60}")
        yolo_summary = run_yolo_training(entries, epochs=args.epochs)

    # Phase 5: Update baseline
    if args.update_baseline and xgb_eval:
        print(f"\n{'='*60}")
        print("Phase 5: Baseline 모델 업데이트")
        print(f"{'='*60}")
        update_baseline(xgb_eval, yolo_summary)

    print(f"\n{'='*60}")
    print("COMPLETE: 추가학습 파이프라인 완료")
    if xgb_eval:
        best = xgb_eval['best_model']
        print(f"  XGBoost F1: {xgb_eval['cv_results'][best]['f1']['mean']:.4f}")
        print(f"  XGBoost AUC: {xgb_eval['cv_results'][best]['roc_auc']['mean']:.4f}")
    if yolo_summary:
        print(f"  YOLO top1: {yolo_summary['final_metrics']['top1']:.4f}")
    print(f"{'='*60}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        write_status('failed', f'추가학습 오류: {e}', error=str(e))
        raise
