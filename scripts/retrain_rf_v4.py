#!/usr/bin/env python3
"""
RF 파이프라인 v4 — 피처 개선 (가속도 + 자세 높이)
===================================================
v3 대비 변경사항:
  - 제거: area_mean, area_std, delta_area_mean, width_mean, width_std (ablation에서 최하위)
  - 추가: delta_y_accel_max (하강 가속도), final_height_ratio (최종 자세 높이 비율)
  - 총 13개 피처 (v3: 16개)

사용법:
    PYTHONUNBUFFERED=1 python3 scripts/retrain_rf_v4.py 2>/dev/null | tee /tmp/retrain_rf_v4_log.txt
    PYTHONUNBUFFERED=1 python3 scripts/retrain_rf_v4.py --skip-extract 2>/dev/null | tee /tmp/retrain_rf_v4_log.txt
"""

import argparse
import json
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
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, recall_score, precision_score, accuracy_score

import functools
print = functools.partial(print, flush=True)

# ── 설정 ──────────────────────────────────────────────────
PROJECT_ROOT = Path('/opt/app/project/main')
DATASET_ROOT = Path('/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상')
RF_YOLO_MODEL = 'yolov8n.pt'
RF_TARGET_FPS = 2
RF_CONF_THRES = 0.25
RF_PERSON_CLASS = 0
RF_YOLO_IMGSZ = 640

# v5 피처: n_frames → detection_rate (영상 길이 편향 제거)
FEATURE_COLUMNS = [
    'detection_rate',          # v5: n_frames/total_sampled → 영상 길이 무관 검출률
    'center_y_mean', 'center_y_std',
    'height_mean', 'height_std',
    'aspect_ratio_mean', 'aspect_ratio_std',
    'delta_y_mean', 'delta_y_max',
    'delta_height_mean', 'delta_width_mean',
    'delta_y_accel_max',       # v4: 하강 가속도 최대값
    'final_height_ratio',      # v4: 최종 자세 높이 비율
]

OUTPUT_DIR = PROJECT_ROOT / 'storage/training/fall-detection/rf-pipeline'
HITL_MODEL_PATH = OUTPUT_DIR / 'rf_hitl_model.pkl'
FEATURE_CACHE_PATH = OUTPUT_DIR / 'feature_cache_v5.json'

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


# ── 특징 추출 ────────────────────────────────────────────
def extract_single(video_path, yolo, device):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0: fps = 30.0
    vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(int(round(fps / RF_TARGET_FPS)), 1)

    _resize = None
    if vw > 1280 or vh > 720:
        if vw > vh:
            _resize = (640, int(vh * 640 / max(vw, 1)))
        else:
            _resize = (int(vw * 360 / max(vh, 1)), 360)

    frames = []
    if total > 0 and step > 1:
        targets = set(range(0, total, step))
        idx = 0
        mx = max(targets) if targets else 0
        while idx <= mx:
            ret = cap.grab()
            if not ret: break
            if idx in targets:
                ret2, frame = cap.retrieve()
                if ret2:
                    if _resize: frame = cv2.resize(frame, _resize)
                    frames.append((idx, frame))
            idx += 1
    else:
        idx = 0
        while True:
            ret = cap.grab()
            if not ret: break
            if idx % step == 0:
                ret2, frame = cap.retrieve()
                if ret2:
                    if _resize: frame = cv2.resize(frame, _resize)
                    frames.append((idx, frame))
            idx += 1
    cap.release()
    if len(frames) < 3:
        return None

    imgs = [f for _, f in frames]
    idxs = [i for i, _ in frames]
    results = yolo.predict(source=imgs, conf=RF_CONF_THRES, verbose=False, imgsz=RF_YOLO_IMGSZ, device=device)

    det_rows = []
    for i, r in enumerate(results):
        boxes = r.boxes
        if boxes is None or len(boxes) == 0: continue
        best, best_area = None, -1
        for b in boxes:
            if int(b.cls.item()) != RF_PERSON_CLASS: continue
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            w, h = x2 - x1, y2 - y1
            area = w * h
            if area > best_area:
                best_area = area
                best = {'frame_idx': idxs[i], 'width': w, 'height': h,
                        'center_x': (x1+x2)/2, 'center_y': (y1+y2)/2, 'area': area}
        if best: det_rows.append(best)

    if len(det_rows) < 2:
        return None

    df = pd.DataFrame(det_rows).sort_values('frame_idx').reset_index(drop=True)
    g = df.copy()
    g['aspect_ratio'] = g['width'] / (g['height'] + 1e-6)
    g['delta_y_raw'] = g['center_y'].diff()
    g['delta_y'] = g['delta_y_raw'].clip(lower=0)
    g['delta_height'] = g['height'].diff().abs()
    g['delta_width'] = g['width'].diff().abs()

    # v4 NEW: 하강 가속도 (delta_y의 2차 도함수)
    g['delta_y_accel'] = g['delta_y'].diff()
    delta_y_accel_max = float(g['delta_y_accel'].max() or 0)

    # v4 NEW: 최종 자세 높이 비율 (마지막 3프레임 높이 / 전체 평균 높이)
    n_tail = min(3, len(g))
    final_height = float(g['height'].tail(n_tail).mean())
    height_mean = float(g['height'].mean())
    final_height_ratio = final_height / (height_mean + 1e-6)

    total_sampled = max(len(frames), 1)
    feat = {
        'detection_rate': float(len(g)) / total_sampled,  # v5: 검출률 (영상 길이 무관)
        'n_frames': float(len(g)),            # 보조: short-clip 참조용
        'total_sampled_frames': float(total_sampled),  # 보조: 정규화 분모
        'center_y_mean': float(g['center_y'].mean()),
        'center_y_std': float(g['center_y'].std() or 0),
        'height_mean': height_mean,
        'height_std': float(g['height'].std() or 0),
        'aspect_ratio_mean': float(g['aspect_ratio'].mean()),
        'aspect_ratio_std': float(g['aspect_ratio'].std() or 0),
        'delta_y_mean': float(g['delta_y'].mean() or 0),
        'delta_y_max': float(g['delta_y'].max() or 0),
        'delta_height_mean': float(g['delta_height'].mean() or 0),
        'delta_width_mean': float(g['delta_width'].mean() or 0),
        'delta_y_accel_max': delta_y_accel_max,
        'final_height_ratio': final_height_ratio,
        'video': os.path.basename(video_path),
    }
    return feat


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
            print(f"    [{lab}] {processed}/{len(video_paths)} 완료 | "
                  f"성공 {len(results)} 오류 {errors} | "
                  f"{elapsed:.0f}초 경과 | 속도 {rate:.1f}개/초 | ETA {eta:.0f}초")
    return results, errors


# ── 학습 + 평가 ───────────────────────────────────────────
def train_evaluate_sweep(X_train, y_train, X_val, y_val, n_estimators, max_depth,
                         min_samples_leaf, class_weight, thresholds):
    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight=class_weight,
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    proba = clf.predict_proba(X_val)
    classes = list(clf.classes_)
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
    return clf, results


def find_best_configs(all_results, recall_targets=[0.95, 0.93, 0.90]):
    bests = {}
    for target in recall_targets:
        candidates = [r for r in all_results if r.get('recall', 0) >= target]
        if not candidates:
            continue
        candidates.sort(key=lambda x: (x['accuracy'], x['f1']), reverse=True)
        bests[f'recall>={target}'] = candidates[0]
    return bests


# ── 메인 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='RF v5 — 검출률 정규화 (n_frames → detection_rate)')
    parser.add_argument('--n-train', type=int, default=400, help='학습 Y/N 각 개수')
    parser.add_argument('--n-val', type=int, default=100, help='검증 Y/N 각 개수')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--skip-extract', action='store_true', help='캐시된 특징 사용')
    parser.add_argument('--recall-target', type=float, default=0.95, help='최소 recall 목표')
    args = parser.parse_args()

    n_total = (args.n_train + args.n_val) * 2
    print("=" * 70)
    print("  RF 파이프라인 v5 — 검출률 정규화 (n_frames → detection_rate)")
    print(f"  총 {n_total}개 영상 | 학습 Y/N 각 {args.n_train} | 검증 Y/N 각 {args.n_val}")
    print(f"  피처 수: {len(FEATURE_COLUMNS)}개 (v4 → v5: {len(FEATURE_COLUMNS)}개)")
    print(f"  교체: n_frames → detection_rate (영상 길이 편향 제거)")
    print(f"  유지: delta_y_accel_max, final_height_ratio")
    print(f"  최소 Recall 목표: {args.recall_target}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ── Phase 1: 영상 수집 ──
    print("\n[Phase 1] 영상 수집...")
    fall_all = collect_videos(DATASET_ROOT, ['Y/FY', 'Y/BY', 'Y/SY'], args.seed)
    nonfall_all = collect_videos(DATASET_ROOT, ['N/N'], args.seed)
    print(f"  사용 가능: Fall {len(fall_all)}개, NonFall {len(nonfall_all)}개")

    fall_train = fall_all[:args.n_train]
    fall_val = fall_all[args.n_train:args.n_train + args.n_val]
    nonfall_train = nonfall_all[:args.n_train]
    nonfall_val = nonfall_all[args.n_train:args.n_train + args.n_val]

    print(f"  학습: Fall {len(fall_train)} + NonFall {len(nonfall_train)} = {len(fall_train)+len(nonfall_train)}")
    print(f"  검증: Fall {len(fall_val)} + NonFall {len(nonfall_val)} = {len(fall_val)+len(nonfall_val)}")

    # ── Phase 2: 특징 추출 ──
    all_feats = []

    if args.skip_extract and os.path.exists(FEATURE_CACHE_PATH):
        print(f"\n[Phase 2] 캐시된 특징 로드: {FEATURE_CACHE_PATH}")
        with open(FEATURE_CACHE_PATH, 'r') as f:
            all_feats = json.load(f)
        print(f"  로드 완료: {len(all_feats)}건")
    else:
        print("\n[Phase 2] YOLO 로드 및 특징 추출...")
        from ultralytics import YOLO
        yolo = YOLO(RF_YOLO_MODEL)
        try:
            import torch
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        except ImportError:
            device = 'cpu'
        print(f"  Device: {device}")

        total_videos = len(fall_train) + len(nonfall_train) + len(fall_val) + len(nonfall_val)
        global_t0 = time.time()

        print(f"\n  === 특징 추출 시작 (총 {total_videos}개) ===")

        print(f"\n  [학습 Fall] {len(fall_train)}개...")
        train_fall_feats, err1 = extract_features_with_progress(fall_train, yolo, device, label=1, report_every=50)
        elapsed = time.time() - global_t0
        print(f"  ✓ 학습 Fall 완료 | {elapsed:.0f}초")

        print(f"\n  [학습 NonFall] {len(nonfall_train)}개...")
        train_nonfall_feats, err2 = extract_features_with_progress(nonfall_train, yolo, device, label=0, report_every=50)
        elapsed = time.time() - global_t0
        print(f"  ✓ 학습 NonFall 완료 | {elapsed:.0f}초")

        print(f"\n  [검증 Fall] {len(fall_val)}개...")
        val_fall_feats, err3 = extract_features_with_progress(fall_val, yolo, device, label=1, report_every=50)
        elapsed = time.time() - global_t0
        print(f"  ✓ 검증 Fall 완료 | {elapsed:.0f}초")

        print(f"\n  [검증 NonFall] {len(nonfall_val)}개...")
        val_nonfall_feats, err4 = extract_features_with_progress(nonfall_val, yolo, device, label=0, report_every=50)
        elapsed = time.time() - global_t0
        print(f"  ✓ 검증 NonFall 완료 | {elapsed:.0f}초")

        all_feats = train_fall_feats + train_nonfall_feats + val_fall_feats + val_nonfall_feats
        print(f"\n  총 추출 특징: {len(all_feats)}건 (오류: {err1+err2+err3+err4}건)")

        # 캐시 저장
        with open(FEATURE_CACHE_PATH, 'w') as f:
            json.dump(all_feats, f, ensure_ascii=False)
        print(f"  캐시 저장: {FEATURE_CACHE_PATH}")

        del yolo
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # ── Phase 3: 데이터 준비 ──
    print("\n[Phase 3] 데이터 준비...")
    df_all = pd.DataFrame(all_feats)

    # 피처 검증
    missing = [c for c in FEATURE_COLUMNS if c not in df_all.columns]
    if missing:
        print(f"  [오류] 누락된 피처: {missing}")
        print(f"  사용 가능한 컬럼: {list(df_all.columns)}")
        return

    train_videos = set(os.path.basename(v) for v in fall_train + nonfall_train)
    val_videos = set(os.path.basename(v) for v in fall_val + nonfall_val)

    df_train = df_all[df_all['video'].isin(train_videos)].copy()
    df_val = df_all[df_all['video'].isin(val_videos)].copy()

    if len(df_val) < 10:
        print("  [경고] 비디오 이름 매칭 실패, 순서 기반 분리 사용")
        feat_with_label = all_feats
        train_feats = [f for f in feat_with_label if f.get('label') == 1][:args.n_train] + \
                      [f for f in feat_with_label if f.get('label') == 0][:args.n_train]
        val_feats = [f for f in feat_with_label if f.get('label') == 1][args.n_train:args.n_train+args.n_val] + \
                    [f for f in feat_with_label if f.get('label') == 0][args.n_train:args.n_train+args.n_val]
        df_train = pd.DataFrame(train_feats)
        df_val = pd.DataFrame(val_feats)

    X_train = df_train[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    y_train = df_train['label'].astype(int).values
    X_val = df_val[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    y_val = df_val['label'].astype(int).values

    print(f"  학습: {len(X_train)}건 (Y:{sum(y_train==1)} N:{sum(y_train==0)})")
    print(f"  검증: {len(X_val)}건 (Y:{sum(y_val==1)} N:{sum(y_val==0)})")

    # 주요 피처 통계 미리보기
    print(f"\n  === 주요 피처 통계 ===")
    for col in ['detection_rate', 'delta_y_accel_max', 'final_height_ratio']:
        vals_fall = df_train.loc[df_train['label'] == 1, col]
        vals_nonfall = df_train.loc[df_train['label'] == 0, col]
        print(f"  {col}:")
        print(f"    Fall:    mean={vals_fall.mean():.3f} std={vals_fall.std():.3f} median={vals_fall.median():.3f}")
        print(f"    NonFall: mean={vals_nonfall.mean():.3f} std={vals_nonfall.std():.3f} median={vals_nonfall.median():.3f}")

    # ── Phase 4: 점진적 학습 ──
    print("\n[Phase 4] 점진적 학습 + 메트릭 보고...")
    thresholds = [round(t * 0.01, 2) for t in range(20, 56)]

    hp_configs = [
        ('balanced-300-None-1', 300, None, 1, 'balanced', 'balanced'),
        ('1:1-300-None-1', 300, None, 1, '1:1', {0: 1, 1: 1}),
        ('balanced-200-None-1', 200, None, 1, 'balanced', 'balanced'),
        ('balanced-500-None-1', 500, None, 1, 'balanced', 'balanced'),
        ('balanced-300-20-1', 300, 20, 1, 'balanced', 'balanced'),
        ('balanced-300-15-1', 300, 15, 1, 'balanced', 'balanced'),
        ('balanced-300-None-2', 300, None, 2, 'balanced', 'balanced'),
        ('balanced-300-None-3', 300, None, 3, 'balanced', 'balanced'),
        ('balanced-300-20-2', 300, 20, 2, 'balanced', 'balanced'),
        ('1:1-300-20-1', 300, 20, 1, '1:1', {0: 1, 1: 1}),
        ('1:2-300-None-1', 300, None, 1, '1:2', {0: 1, 1: 2}),
        ('1:3-300-None-1', 300, None, 1, '1:3', {0: 1, 1: 3}),
    ]

    incremental_stages = []
    step_size = 50
    n_steps = args.n_train // step_size

    for stage_idx in range(1, n_steps + 1):
        n_per_class = stage_idx * step_size
        n_total_train = n_per_class * 2

        mask_y = (y_train == 1)
        mask_n = (y_train == 0)
        idx_y = np.where(mask_y)[0][:n_per_class]
        idx_n = np.where(mask_n)[0][:n_per_class]
        idx_sub = np.concatenate([idx_y, idx_n])
        np.random.shuffle(idx_sub)

        X_sub = X_train[idx_sub]
        y_sub = y_train[idx_sub]

        stage_t0 = time.time()
        print(f"\n  === Stage {stage_idx}/{n_steps}: 학습 {n_total_train}개 (Y:{len(idx_y)} N:{len(idx_n)}) ===")

        stage_all_results = []
        best_stage = None
        best_stage_score = -1

        for hp in hp_configs:
            hp_name, n_est, max_d, min_leaf, cw_name, cw_val = hp
            try:
                clf, sweep = train_evaluate_sweep(
                    X_sub, y_sub, X_val, y_val,
                    n_estimators=n_est, max_depth=max_d,
                    min_samples_leaf=min_leaf, class_weight=cw_val,
                    thresholds=thresholds
                )
            except Exception as e:
                print(f"    [오류] {hp_name}: {e}")
                continue

            for r in sweep:
                r['hp_name'] = hp_name
                r['n_estimators'] = n_est
                r['max_depth'] = max_d
                r['min_samples_leaf'] = min_leaf
                r['class_weight'] = cw_name
                r['train_size'] = n_total_train
                stage_all_results.append(r)

                if r['recall'] >= args.recall_target:
                    score = r['accuracy'] * 0.5 + r['f1'] * 0.5
                    if score > best_stage_score:
                        best_stage_score = score
                        best_stage = {**r, 'clf': clf}

        stage_elapsed = time.time() - stage_t0

        if best_stage:
            bs = best_stage
            print(f"  ★ Best (recall>={args.recall_target}): "
                  f"thr={bs['threshold']:.2f} | acc={bs['accuracy']:.3f} prec={bs['precision']:.3f} "
                  f"rec={bs['recall']:.3f} f1={bs['f1']:.3f} | "
                  f"{bs['hp_name']} | {stage_elapsed:.1f}초")
        else:
            if stage_all_results:
                max_rec = max(stage_all_results, key=lambda x: x['recall'])
                print(f"  [!] Recall 목표 미달 | 최고 recall={max_rec['recall']:.3f} at thr={max_rec['threshold']:.2f}")

        stage_bests = find_best_configs(stage_all_results, [0.99, 0.97, 0.95, 0.93, 0.90])
        for key, cfg in stage_bests.items():
            print(f"    {key}: thr={cfg['threshold']:.2f} acc={cfg['accuracy']:.3f} "
                  f"prec={cfg['precision']:.3f} rec={cfg['recall']:.3f} f1={cfg['f1']:.3f} "
                  f"| {cfg.get('hp_name','')}")

        incremental_stages.append({
            'stage': stage_idx,
            'train_size': n_total_train,
            'best': {k: v for k, v in (best_stage or {}).items() if k != 'clf'} if best_stage else None,
            'targets': {k: v for k, v in stage_bests.items()},
            'elapsed_sec': round(stage_elapsed, 1),
        })

    # ── Phase 5: 최종 모델 저장 ──
    print("\n" + "=" * 70)
    print("  [Phase 5] 최종 최적 모델 선택")
    print("=" * 70)

    last_stage = incremental_stages[-1] if incremental_stages else None

    final_best = last_stage['best'] if last_stage and last_stage.get('best') else {}
    final_n_est = final_best.get('n_estimators', 300)
    final_max_d = final_best.get('max_depth', None)
    final_min_leaf = final_best.get('min_samples_leaf', 1)
    final_cw_name = final_best.get('class_weight', 'balanced')
    final_threshold = final_best.get('threshold', 0.42)

    cw_map = {
        'balanced': 'balanced', '1:1': {0: 1, 1: 1}, '1:2': {0: 1, 1: 2},
        '1:3': {0: 1, 1: 3}, '1:4': {0: 1, 1: 4}, '1:5': {0: 1, 1: 5},
    }
    final_cw_val = cw_map.get(final_cw_name, 'balanced')

    print(f"\n  최종 모델 학습 (전체 학습 데이터)...")
    final_clf = RandomForestClassifier(
        n_estimators=final_n_est,
        max_depth=final_max_d,
        min_samples_leaf=final_min_leaf,
        class_weight=final_cw_val,
        random_state=42,
        n_jobs=-1,
    )
    final_clf.fit(X_train, y_train)

    # 최종 검증
    final_proba = final_clf.predict_proba(X_val)
    final_classes = list(final_clf.classes_)
    final_fall_idx = final_classes.index(1) if 1 in final_classes else 0
    final_scores = final_proba[:, final_fall_idx]
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

    print(f"\n  ★ 최종 모델 검증 결과:")
    print(f"    하이퍼파라미터: n_est={final_n_est}, max_depth={final_max_d}, "
          f"min_samples_leaf={final_min_leaf}, class_weight={final_cw_name}")
    print(f"    Threshold:  {final_threshold}")
    print(f"    Accuracy:   {final_acc:.4f}")
    print(f"    Precision:  {final_prec:.4f}")
    print(f"    Recall:     {final_rec:.4f}")
    print(f"    F1:         {final_f1:.4f}")
    print(f"    TP={tp} FN={fn} FP={fp} TN={tn}")

    # 피처 중요도 출력
    importances = final_clf.feature_importances_
    feat_imp = sorted(zip(FEATURE_COLUMNS, importances), key=lambda x: x[1], reverse=True)
    print(f"\n  === 피처 중요도 ===")
    for col, imp in feat_imp:
        marker = " ★v5" if col == 'detection_rate' else ""
        print(f"    {col:>25}: {imp:.4f}{marker}")

    # 이전 모델과 비교
    prev_summary_path = OUTPUT_DIR / 'training_summary.json'
    if os.path.exists(prev_summary_path):
        with open(prev_summary_path, 'r') as f:
            prev = json.load(f)
        prev_m = prev.get('best_metrics', {})
        print(f"\n  === v3 모델 대비 변화 ===")
        for metric in ['accuracy', 'precision', 'recall', 'f1']:
            old_val = prev_m.get(metric, 0)
            new_val = {'accuracy': final_acc, 'precision': final_prec, 'recall': final_rec, 'f1': final_f1}[metric]
            diff = new_val - old_val
            arrow = '↑' if diff > 0 else ('↓' if diff < 0 else '=')
            print(f"    {metric:>10}: {old_val:.4f} → {new_val:.4f} ({arrow}{abs(diff):.4f})")
        old_thr = prev.get('best_config', {}).get('threshold', 0)
        print(f"    {'threshold':>10}: {old_thr} → {final_threshold}")
        old_features = prev.get('features', [])
        print(f"    {'features':>10}: {len(old_features)}개 → {len(FEATURE_COLUMNS)}개")

    # 모델 저장
    backup_path = str(HITL_MODEL_PATH) + f'.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}'
    if os.path.exists(HITL_MODEL_PATH):
        os.rename(HITL_MODEL_PATH, backup_path)
        print(f"\n  기존 모델 백업: {backup_path}")

    joblib.dump(final_clf, HITL_MODEL_PATH)
    print(f"  새 모델 저장: {HITL_MODEL_PATH}")

    # 학습 요약 저장
    summary = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'training_samples': len(X_train),
        'validation_samples': len(X_val),
        'class_distribution_train': {'Y': int(sum(y_train == 1)), 'N': int(sum(y_train == 0))},
        'class_distribution_val': {'Y': int(sum(y_val == 1)), 'N': int(sum(y_val == 0))},
        'features': FEATURE_COLUMNS,
        'feature_importances': {col: round(float(imp), 4) for col, imp in feat_imp},
        'best_config': {
            'n_estimators': final_n_est,
            'max_depth': final_max_d,
            'min_samples_leaf': final_min_leaf,
            'class_weight': final_cw_name,
            'threshold': final_threshold,
        },
        'best_metrics': {
            'accuracy': round(final_acc, 4),
            'precision': round(final_prec, 4),
            'recall': round(final_rec, 4),
            'f1': round(final_f1, 4),
            'TP': tp, 'TN': tn, 'FP': fp, 'FN': fn,
        },
        'incremental_learning_curve': incremental_stages,
        'source': 'retrain_rf_v4.py',
        'version': 'v5',
        'changes': {
            'replaced': {'n_frames': 'detection_rate'},
            'reason': '영상 길이 편향 제거: n_frames → detection_rate (n_frames/total_sampled_frames)',
        },
        'ready': True,
        'model_path': str(HITL_MODEL_PATH),
        'n_estimators': final_n_est,
        'optimal_threshold': final_threshold,
    }
    with open(prev_summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  학습 요약: {prev_summary_path}")

    grid_path = OUTPUT_DIR / f'grid_search_v5_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(grid_path, 'w', encoding='utf-8') as f:
        json.dump({
            'stages': incremental_stages,
            'final_config': summary['best_config'],
            'final_metrics': summary['best_metrics'],
            'features': FEATURE_COLUMNS,
            'feature_importances': summary['feature_importances'],
        }, f, ensure_ascii=False, indent=2)
    print(f"  Grid 결과: {grid_path}")

    print(f"\n  ⚠️ threshold 적용 필요:")
    print(f"    src/model/struct/video_analysis.py → self.fall_decision_threshold = {final_threshold}")

    print(f"\n{'='*70}")
    print(f"  RF v5 학습 완료!")
    print(f"  총 소요: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
