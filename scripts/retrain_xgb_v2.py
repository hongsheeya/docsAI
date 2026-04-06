#!/usr/bin/env python3
"""
XGBoost v2 — 2000건 대규모 학습 (Person-Feature Pipeline)
==========================================================
기존 train_fall_classifier.py의 CSV 기반 학습을 대체.
영상에서 직접 YOLO ByteTrack → 슬라이딩 윈도우 피처 추출 → XGBoost 학습.

변경사항 (v1 대비):
  - 학습 데이터 대폭 확대 (기존 ~200건 → 최대 2000건)
  - HP Grid Search + Threshold Sweep
  - 100건마다 진행 상황 보고
  - Recall + Precision 동시 최적화 (F1 기반)

사용법:
    PYTHONUNBUFFERED=1 python3 scripts/retrain_xgb_v2.py 2>/dev/null | tee /tmp/retrain_xgb_v2_log.txt
    PYTHONUNBUFFERED=1 python3 scripts/retrain_xgb_v2.py --skip-extract 2>/dev/null | tee /tmp/retrain_xgb_v2_log.txt
"""

import argparse
import json
import math
import os
import random
import sys
import time
import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'
from datetime import datetime
from pathlib import Path

if '/opt/app/my_libs' not in sys.path:
    sys.path.insert(0, '/opt/app/my_libs')

import cv2
import numpy as np
import joblib

import functools
print = functools.partial(print, flush=True)

PROGRESS_FILE = '/tmp/retrain_xgb_v2_progress.txt'

def log(msg):
    """콘솔 + 진행 파일 동시 기록."""
    print(msg)
    with open(PROGRESS_FILE, 'a') as f:
        f.write(msg + '\n')

# ── 설정 ──────────────────────────────────────────────────
PROJECT_ROOT = Path('/opt/app/project/main')
DATASET_ROOT = Path('/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상')
YOLO_MODEL = 'yolov8n.pt'

# XGBoost person-feature 피처 (yolo_fall_runtime.py와 동일)
FEATURE_COLS = [
    'center_dy', 'height_ratio', 'aspect_change', 'stillness',
    'floor_proximity', 'area_change', 'vert_horiz_ratio',
    'max_down_speed', 'avg_conf', 'n_points',
]

OUTPUT_DIR = PROJECT_ROOT / 'storage/training/fall-detection/fall-classifier'
FEATURE_CACHE_PATH = OUTPUT_DIR / 'feature_cache_xgb_v2.json'


# ── 슬라이딩 윈도우 피처 계산 (yolo_fall_runtime.py와 동일) ──
def compute_window_features(window_points, fps):
    """window_points: list of (frame_idx, cx, cy, w, h, conf) in normalized coords."""
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


# ── 영상 수집 ────────────────────────────────────────────
def collect_videos(base_dir, subdirs, seed):
    rng = random.Random(seed)
    vids = []
    for subdir in subdirs:
        full = os.path.join(str(base_dir), subdir)
        if not os.path.isdir(full):
            continue
        for root, _, files in os.walk(full):
            for f in files:
                if f.lower().endswith('.mp4'):
                    vids.append(os.path.join(root, f))
    rng.shuffle(vids)
    return vids


# ── 단일 영상 특징 추출 (ByteTrack → 슬라이딩 윈도우 → 피처) ──
def extract_single(video_path, yolo, device, window_sec=1.0, stride_sec=0.5, vid_stride=6, track_imgsz=352):
    """Run YOLO+ByteTrack tracking and extract sliding-window features from a single video."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0:
        fps = 30.0
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    cap.release()

    if video_w <= 0 or video_h <= 0:
        return None

    # Run YOLO tracking
    track_data = {}  # track_id -> list of (frame_idx, cx, cy, w, h, conf)
    frame_idx = 0
    try:
        for result in yolo.track(source=str(video_path), stream=True, persist=True, classes=[0],
                                  conf=0.30, iou=0.5,
                                  tracker='bytetrack.yaml', imgsz=track_imgsz,
                                  verbose=False, device=device, vid_stride=vid_stride):
            boxes = result.boxes
            if boxes is not None and len(boxes) > 0:
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
            frame_idx += vid_stride
    except Exception:
        return None

    if not track_data:
        return None

    # Sliding window feature extraction
    window_frames = int(fps * window_sec)
    stride_frames = int(fps * stride_sec)
    if window_frames < 2:
        window_frames = 2
    if stride_frames < 1:
        stride_frames = 1

    all_feats = []
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
            feats = compute_window_features(win_points, fps)
            if feats is not None:
                all_feats.append(feats)
            win_start += stride_frames

    if not all_feats:
        return None

    return {
        'video': os.path.basename(video_path),
        'windows': all_feats,
        'n_windows': len(all_feats),
        'n_tracks': len(track_data),
    }


def extract_features_with_progress(video_paths, yolo, device, label, report_every=100):
    results = []
    errors = 0
    t0 = time.time()
    for i, vp in enumerate(video_paths):
        try:
            feat = extract_single(vp, yolo, device)
            if feat is not None:
                feat['label'] = label
                results.append(feat)
            else:
                errors += 1
        except Exception:
            errors += 1

        processed = i + 1
        if processed % report_every == 0 or processed == len(video_paths):
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(video_paths) - processed) / rate if rate > 0 else 0
            lab = "Fall" if label == 1 else "NonFall"
            total_windows = sum(r['n_windows'] for r in results)
            log(f"    [{lab}] {processed}/{len(video_paths)} 완료 | "
                  f"성공 {len(results)} 오류 {errors} | 윈도우 {total_windows}개 | "
                  f"{elapsed:.0f}초 경과 | 속도 {rate:.1f}개/초 | ETA {eta:.0f}초")
    return results, errors


# ── 학습 + 평가 ───────────────────────────────────────────
def train_evaluate_sweep(X_train, y_train, X_val, y_val, hp, thresholds):
    from xgboost import XGBClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('clf', XGBClassifier(
            max_depth=hp['max_depth'],
            n_estimators=hp['n_estimators'],
            learning_rate=hp['learning_rate'],
            scale_pos_weight=hp['scale_pos_weight'],
            min_child_weight=hp['min_child_weight'],
            subsample=hp['subsample'],
            colsample_bytree=hp['colsample_bytree'],
            random_state=42,
            eval_metric='logloss',
            use_label_encoder=False,
            n_jobs=-1,
        )),
    ])
    pipeline.fit(X_train, y_train)

    proba = pipeline.predict_proba(X_val)
    classes = list(pipeline.named_steps['clf'].classes_)
    fall_idx = classes.index(1) if 1 in classes else 0
    scores = proba[:, fall_idx]

    results = []
    for thr in thresholds:
        preds = (scores >= thr).astype(int)
        tp = int(((y_val == 1) & (preds == 1)).sum())
        tn = int(((y_val == 0) & (preds == 0)).sum())
        fp = int(((y_val == 0) & (preds == 1)).sum())
        fn = int(((y_val == 1) & (preds == 0)).sum())
        total = tp + tn + fp + fn
        acc = (tp + tn) / total if total > 0 else 0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        results.append({
            'threshold': round(thr, 3),
            'accuracy': round(acc, 4),
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'f1': round(f1, 4),
            'TP': tp, 'TN': tn, 'FP': fp, 'FN': fn,
        })
    return pipeline, results


# ── 메인 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='XGBoost v2 — 2000건 대규모 학습')
    parser.add_argument('--n-fall-train', type=int, default=800, help='Fall 학습 영상 수')
    parser.add_argument('--n-fall-val', type=int, default=200, help='Fall 검증 영상 수')
    parser.add_argument('--n-nonfall-train', type=int, default=400, help='NonFall 학습 영상 수')
    parser.add_argument('--n-nonfall-val', type=int, default=100, help='NonFall 검증 영상 수')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--skip-extract', action='store_true', help='캐시된 특징 사용')
    parser.add_argument('--recall-target', type=float, default=0.93, help='최소 recall 목표')
    args = parser.parse_args()

    n_total = args.n_fall_train + args.n_fall_val + args.n_nonfall_train + args.n_nonfall_val
    log("=" * 70)
    log("  XGBoost v2 — 2000건 대규모 학습 (Person-Feature Pipeline)")
    log(f"  총 {n_total}개 영상 | Fall 학습 {args.n_fall_train} + 검증 {args.n_fall_val}")
    log(f"  NonFall 학습 {args.n_nonfall_train} + 검증 {args.n_nonfall_val}")
    log(f"  피처 수: {len(FEATURE_COLS)}개")
    log(f"  최소 Recall 목표: {args.recall_target}")
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)

    # ── Phase 1: 영상 수집 ──
    log("\n[Phase 1] 영상 수집...")
    fall_all = collect_videos(DATASET_ROOT, ['Y/FY', 'Y/BY', 'Y/SY'], args.seed)
    nonfall_all = collect_videos(DATASET_ROOT, ['N/N'], args.seed)
    log(f"  사용 가능: Fall {len(fall_all)}개, NonFall {len(nonfall_all)}개")

    fall_train = fall_all[:args.n_fall_train]
    fall_val = fall_all[args.n_fall_train:args.n_fall_train + args.n_fall_val]
    nonfall_train = nonfall_all[:args.n_nonfall_train]
    nonfall_val = nonfall_all[args.n_nonfall_train:args.n_nonfall_train + args.n_nonfall_val]

    log(f"  학습: Fall {len(fall_train)} + NonFall {len(nonfall_train)} = {len(fall_train)+len(nonfall_train)}")
    log(f"  검증: Fall {len(fall_val)} + NonFall {len(nonfall_val)} = {len(fall_val)+len(nonfall_val)}")

    # ── Phase 2: 특징 추출 ──
    all_results = {}

    if args.skip_extract and os.path.exists(FEATURE_CACHE_PATH):
        log(f"\n[Phase 2] 캐시된 특징 로드: {FEATURE_CACHE_PATH}")
        with open(FEATURE_CACHE_PATH, 'r') as f:
            all_results = json.load(f)
        total_windows = sum(r['n_windows'] for r in all_results.get('train_fall', []) +
                           all_results.get('train_nonfall', []) +
                           all_results.get('val_fall', []) +
                           all_results.get('val_nonfall', []))
        total_vids = sum(len(all_results.get(k, [])) for k in ['train_fall', 'train_nonfall', 'val_fall', 'val_nonfall'])
        log(f"  로드 완료: {total_vids}건, 윈도우 {total_windows}개")
    else:
        log("\n[Phase 2] YOLO 로드 및 ByteTrack 특징 추출...")
        from ultralytics import YOLO
        yolo = YOLO(YOLO_MODEL)
        try:
            import torch
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        except ImportError:
            device = 'cpu'
        log(f"  Device: {device}")

        global_t0 = time.time()
        log(f"\n  === 특징 추출 시작 (총 {n_total}개, 100건마다 보고) ===")

        log(f"\n  [학습 Fall] {len(fall_train)}개...")
        train_fall_feats, err1 = extract_features_with_progress(fall_train, yolo, device, label=1, report_every=100)
        elapsed = time.time() - global_t0
        log(f"  ✓ 학습 Fall 완료 | {elapsed:.0f}초")

        log(f"\n  [학습 NonFall] {len(nonfall_train)}개...")
        train_nonfall_feats, err2 = extract_features_with_progress(nonfall_train, yolo, device, label=0, report_every=100)
        elapsed = time.time() - global_t0
        log(f"  ✓ 학습 NonFall 완료 | {elapsed:.0f}초")

        log(f"\n  [검증 Fall] {len(fall_val)}개...")
        val_fall_feats, err3 = extract_features_with_progress(fall_val, yolo, device, label=1, report_every=100)
        elapsed = time.time() - global_t0
        log(f"  ✓ 검증 Fall 완료 | {elapsed:.0f}초")

        log(f"\n  [검증 NonFall] {len(nonfall_val)}개...")
        val_nonfall_feats, err4 = extract_features_with_progress(nonfall_val, yolo, device, label=0, report_every=100)
        elapsed = time.time() - global_t0
        log(f"  ✓ 검증 NonFall 완료 | {elapsed:.0f}초")

        all_results = {
            'train_fall': train_fall_feats,
            'train_nonfall': train_nonfall_feats,
            'val_fall': val_fall_feats,
            'val_nonfall': val_nonfall_feats,
        }
        total_errors = err1 + err2 + err3 + err4
        total_windows = sum(r['n_windows'] for r in train_fall_feats + train_nonfall_feats + val_fall_feats + val_nonfall_feats)
        log(f"\n  총 영상: {len(train_fall_feats)+len(train_nonfall_feats)+len(val_fall_feats)+len(val_nonfall_feats)}건 "
              f"(오류: {total_errors}건)")
        log(f"  총 윈도우: {total_windows}개")

        # 캐시 저장
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(FEATURE_CACHE_PATH, 'w') as f:
            json.dump(all_results, f, ensure_ascii=False)
        log(f"  캐시 저장: {FEATURE_CACHE_PATH}")

        del yolo
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # ── Phase 3: 데이터 준비 (영상 → 윈도우 레벨) ──
    log("\n[Phase 3] 데이터 준비 (윈도우 레벨)...")

    def flatten_to_windows(video_feats_list):
        """각 영상의 윈도우 피처들을 (X, y) 형태로 flat하게 변환."""
        X_rows = []
        y_rows = []
        for vf in video_feats_list:
            label = vf['label']
            for wf in vf['windows']:
                row = [float(wf.get(col, 0.0) or 0.0) for col in FEATURE_COLS]
                X_rows.append(row)
                y_rows.append(label)
        return np.array(X_rows), np.array(y_rows)

    X_train, y_train = flatten_to_windows(
        all_results.get('train_fall', []) + all_results.get('train_nonfall', [])
    )
    X_val, y_val = flatten_to_windows(
        all_results.get('val_fall', []) + all_results.get('val_nonfall', [])
    )

    # inf/nan 제거
    X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
    X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)

    n_train_fall = int(np.sum(y_train == 1))
    n_train_nonfall = int(np.sum(y_train == 0))
    n_val_fall = int(np.sum(y_val == 1))
    n_val_nonfall = int(np.sum(y_val == 0))

    log(f"  학습 윈도우: {len(X_train)}개 (Fall:{n_train_fall} NonFall:{n_train_nonfall})")
    log(f"  검증 윈도우: {len(X_val)}개 (Fall:{n_val_fall} NonFall:{n_val_nonfall})")

    # 클래스 불균형 비율 (scale_pos_weight 기준)
    base_spw = n_train_nonfall / max(n_train_fall, 1)
    log(f"  클래스 불균형 비율 (N/Y): {base_spw:.2f}")

    # 피처 통계 미리보기
    log(f"\n  === 주요 피처 통계 ===")
    for col_idx, col in enumerate(FEATURE_COLS[:5]):
        vals_fall = X_train[y_train == 1, col_idx]
        vals_nonfall = X_train[y_train == 0, col_idx]
        if len(vals_fall) > 0 and len(vals_nonfall) > 0:
            log(f"  {col}:")
            log(f"    Fall:    mean={vals_fall.mean():.4f} std={vals_fall.std():.4f}")
            log(f"    NonFall: mean={vals_nonfall.mean():.4f} std={vals_nonfall.std():.4f}")

    # ── Phase 4: HP Grid Search ──
    log("\n[Phase 4] HP Grid Search + Threshold Sweep...")
    thresholds = [round(t * 0.01, 2) for t in range(25, 76)]

    hp_configs = [
        # name, max_depth, n_estimators, learning_rate, scale_pos_weight, min_child_weight, subsample, colsample
        {'name': 'base-6-200-0.1', 'max_depth': 6, 'n_estimators': 200, 'learning_rate': 0.1,
         'scale_pos_weight': 1.0, 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
        {'name': 'base-6-300-0.1', 'max_depth': 6, 'n_estimators': 300, 'learning_rate': 0.1,
         'scale_pos_weight': 1.0, 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
        {'name': 'deep-8-300-0.05', 'max_depth': 8, 'n_estimators': 300, 'learning_rate': 0.05,
         'scale_pos_weight': 1.0, 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
        {'name': 'deep-8-500-0.05', 'max_depth': 8, 'n_estimators': 500, 'learning_rate': 0.05,
         'scale_pos_weight': 1.0, 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
        {'name': 'spw-6-300-0.1', 'max_depth': 6, 'n_estimators': 300, 'learning_rate': 0.1,
         'scale_pos_weight': max(base_spw, 1.0), 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
        {'name': 'spw2-6-300-0.1', 'max_depth': 6, 'n_estimators': 300, 'learning_rate': 0.1,
         'scale_pos_weight': 2.0, 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
        {'name': 'spw3-6-300-0.1', 'max_depth': 6, 'n_estimators': 300, 'learning_rate': 0.1,
         'scale_pos_weight': 3.0, 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
        {'name': 'reg-6-300-0.05', 'max_depth': 6, 'n_estimators': 300, 'learning_rate': 0.05,
         'scale_pos_weight': 1.0, 'min_child_weight': 3, 'subsample': 0.7, 'colsample_bytree': 0.7},
        {'name': 'reg-8-500-0.03', 'max_depth': 8, 'n_estimators': 500, 'learning_rate': 0.03,
         'scale_pos_weight': 1.0, 'min_child_weight': 3, 'subsample': 0.7, 'colsample_bytree': 0.7},
        {'name': 'spw-8-500-0.05', 'max_depth': 8, 'n_estimators': 500, 'learning_rate': 0.05,
         'scale_pos_weight': 2.0, 'min_child_weight': 1, 'subsample': 0.8, 'colsample_bytree': 0.8},
    ]

    all_sweep_results = []
    best_overall = None
    best_overall_score = -1

    for hp_idx, hp in enumerate(hp_configs):
        hp_t0 = time.time()
        hp_name = hp['name']
        log(f"\n  [{hp_idx+1}/{len(hp_configs)}] {hp_name} ...")
        try:
            pipeline, sweep = train_evaluate_sweep(X_train, y_train, X_val, y_val, hp, thresholds)
        except Exception as e:
            log(f"오류: {e}")
            continue

        for r in sweep:
            r['hp_name'] = hp_name
            r['hp'] = {k: v for k, v in hp.items() if k != 'name'}
            all_sweep_results.append(r)

            if r['recall'] >= args.recall_target and r['precision'] >= 0.70:
                # F1 기반 종합 점수 (Recall + Precision 동시 최적화)
                score = r['f1']
                if score > best_overall_score:
                    best_overall_score = score
                    best_overall = {**r, 'pipeline': pipeline}

        # 해당 HP에서의 최고 F1
        hp_best = max(sweep, key=lambda x: x['f1'])
        hp_elapsed = time.time() - hp_t0
        log(f"best_f1={hp_best['f1']:.3f} (thr={hp_best['threshold']:.2f} "
              f"prec={hp_best['precision']:.3f} rec={hp_best['recall']:.3f}) | {hp_elapsed:.1f}초")

    # Recall 목표별 최적
    log(f"\n  === Recall 목표별 최적 구성 ===")
    for target in [0.97, 0.95, 0.93, 0.90, 0.85]:
        candidates = [r for r in all_sweep_results if r['recall'] >= target]
        if not candidates:
            log(f"    recall>={target}: 달성 불가")
            continue
        best_c = max(candidates, key=lambda x: x['f1'])
        log(f"    recall>={target}: thr={best_c['threshold']:.2f} acc={best_c['accuracy']:.3f} "
              f"prec={best_c['precision']:.3f} rec={best_c['recall']:.3f} f1={best_c['f1']:.3f} "
              f"| {best_c.get('hp_name','')}")

    # ── Phase 5: 최종 모델 학습 + 저장 ──
    log("\n" + "=" * 70)
    log("  [Phase 5] 최종 최적 모델")
    log("=" * 70)

    if best_overall is None:
        # recall 목표 미달 시 F1 최적으로 폴백
        log("  [경고] Recall 목표 미달, F1 최적 구성 사용")
        best_overall_r = max(all_sweep_results, key=lambda x: x['f1'])
        # 해당 HP로 재학습
        final_hp_name = best_overall_r['hp_name']
        final_hp = best_overall_r['hp']
    else:
        final_hp_name = best_overall['hp_name']
        final_hp = best_overall['hp']

    # 전체 학습 데이터로 최종 모델 학습
    from xgboost import XGBClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    final_pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('clf', XGBClassifier(
            max_depth=final_hp['max_depth'],
            n_estimators=final_hp['n_estimators'],
            learning_rate=final_hp['learning_rate'],
            scale_pos_weight=final_hp['scale_pos_weight'],
            min_child_weight=final_hp['min_child_weight'],
            subsample=final_hp['subsample'],
            colsample_bytree=final_hp['colsample_bytree'],
            random_state=42,
            eval_metric='logloss',
            use_label_encoder=False,
            n_jobs=-1,
        )),
    ])
    final_pipeline.fit(X_train, y_train)

    # 최종 검증
    final_proba = final_pipeline.predict_proba(X_val)
    final_classes = list(final_pipeline.named_steps['clf'].classes_)
    final_fall_idx = final_classes.index(1) if 1 in final_classes else 0
    final_scores = final_proba[:, final_fall_idx]

    # best threshold 적용
    if best_overall:
        final_threshold = best_overall['threshold']
    else:
        final_threshold = best_overall_r['threshold']

    final_preds = (final_scores >= final_threshold).astype(int)
    tp = int(((y_val == 1) & (final_preds == 1)).sum())
    tn = int(((y_val == 0) & (final_preds == 0)).sum())
    fp = int(((y_val == 0) & (final_preds == 1)).sum())
    fn = int(((y_val == 1) & (final_preds == 0)).sum())
    total = tp + tn + fp + fn
    final_acc = (tp + tn) / total if total > 0 else 0
    final_prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    final_rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    final_f1 = 2 * final_prec * final_rec / (final_prec + final_rec) if (final_prec + final_rec) > 0 else 0

    log(f"\n  ★ 최종 모델 검증 결과:")
    log(f"    HP: {final_hp_name}")
    log(f"    max_depth={final_hp['max_depth']}, n_estimators={final_hp['n_estimators']}, "
          f"lr={final_hp['learning_rate']}, spw={final_hp['scale_pos_weight']}")
    log(f"    Threshold:  {final_threshold}")
    log(f"    Accuracy:   {final_acc:.4f}")
    log(f"    Precision:  {final_prec:.4f}")
    log(f"    Recall:     {final_rec:.4f}")
    log(f"    F1:         {final_f1:.4f}")
    log(f"    TP={tp} FN={fn} FP={fp} TN={tn}")

    # 피처 중요도
    clf = final_pipeline.named_steps['clf']
    importances = clf.feature_importances_
    feat_imp = sorted(zip(FEATURE_COLS, importances), key=lambda x: x[1], reverse=True)
    log(f"\n  === 피처 중요도 ===")
    for col, imp in feat_imp:
        log(f"    {col:>25}: {imp:.4f}")

    # 모델 저장
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model_path = OUTPUT_DIR / 'best_model.pkl'
    backup_path = str(model_path) + f'.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}'
    if os.path.exists(model_path):
        os.rename(model_path, backup_path)
        log(f"\n  기존 모델 백업: {backup_path}")

    joblib.dump(final_pipeline, model_path)
    log(f"  새 모델 저장: {model_path}")

    # 학습 요약 저장
    summary = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'training_videos': {
            'fall_train': len(all_results.get('train_fall', [])),
            'nonfall_train': len(all_results.get('train_nonfall', [])),
            'fall_val': len(all_results.get('val_fall', [])),
            'nonfall_val': len(all_results.get('val_nonfall', [])),
        },
        'training_windows': int(len(X_train)),
        'validation_windows': int(len(X_val)),
        'class_distribution_train': {'Fall': n_train_fall, 'NonFall': n_train_nonfall},
        'class_distribution_val': {'Fall': n_val_fall, 'NonFall': n_val_nonfall},
        'features': FEATURE_COLS,
        'feature_importances': {col: round(float(imp), 4) for col, imp in feat_imp},
        'best_config': {
            'hp_name': final_hp_name,
            **final_hp,
            'threshold': final_threshold,
        },
        'best_metrics': {
            'accuracy': round(final_acc, 4),
            'precision': round(final_prec, 4),
            'recall': round(final_rec, 4),
            'f1': round(final_f1, 4),
            'TP': tp, 'TN': tn, 'FP': fp, 'FN': fn,
        },
        'source': 'retrain_xgb_v2.py',
        'version': 'v2',
        'model_path': str(model_path),
        'ready': True,
    }

    eval_path = OUTPUT_DIR / 'evaluation_v2.json'
    with open(eval_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log(f"  학습 요약: {eval_path}")

    log(f"\n{'='*70}")
    log(f"  XGBoost v2 학습 완료!")
    log(f"  총 소요: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"{'='*70}")


if __name__ == '__main__':
    main()
