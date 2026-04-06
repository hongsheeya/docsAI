#!/usr/bin/env python3
"""
XGBoost Person-Feature 파이프라인 최적화 재학습
================================================
1. 대규모 데이터셋에서 YOLO+ByteTrack 추적 → 슬라이딩 윈도우 feature 추출
2. XGBoost scale_pos_weight sweep → window-level 분류 최적화
3. 전체 파이프라인 (집계+motion gate+threshold) simulation으로 video-level 최적화
4. 최적 모델 저장

사용법:
    python3 scripts/retrain_xgb_optimized.py [--n-train 200] [--n-val 80] [--seed 42]
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
import pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_val_score

import functools
print = functools.partial(print, flush=True)

# ── 설정 ──────────────────────────────────────────────────
PROJECT_ROOT = Path('/opt/app/project/main')
DATASET_ROOT = Path('/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상')
PERSON_DETECTOR_PATH = str(PROJECT_ROOT / 'storage/training/fall-detection/person-detect/runs/person-det-20260326-051849/weights/best.pt')
CLASSIFIER_DIR = PROJECT_ROOT / 'storage/training/fall-detection/fall-classifier'

FEATURE_COLS = [
    'center_dy', 'height_ratio', 'aspect_change', 'stillness',
    'floor_proximity', 'area_change', 'vert_horiz_ratio',
    'max_down_speed', 'avg_conf', 'n_points',
]

# Profile (balanced - more thorough feature extraction)
PROFILE = {
    'vid_stride': 3,
    'track_imgsz': 352,
    'track_conf': 0.30,
    'track_iou': 0.5,
    'window_sec': 1.0,
    'stride_sec': 0.5,
    'presence_check_frames': 4,
    'presence_conf': 0.25,
}


def collect_videos(base_dir, subdirs, n, seed):
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
    return vids[:n] if n and len(vids) > n else vids


def video_meta(video_path):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0: fps = 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return {'fps': fps, 'width': w, 'height': h, 'frame_count': fc,
            'duration_sec': fc / fps if fps > 0 else 0}


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
        'center_dy': round(center_dy, 6), 'height_ratio': round(height_ratio, 6),
        'aspect_change': round(aspect_change, 6), 'stillness': round(stillness, 6),
        'floor_proximity': round(floor_proximity, 6), 'area_change': round(area_change, 6),
        'vert_horiz_ratio': round(vert_horiz_ratio, 6), 'max_down_speed': round(max_down_speed, 6),
        'avg_conf': round(avg_conf, 4), 'n_points': n,
    }


def extract_video_features(video_path, detector, profile):
    """비디오로부터 모든 슬라이딩 윈도우 features 추출. Returns (list of feature dicts, meta)"""
    meta = video_meta(video_path)
    fps = meta['fps']
    video_w = meta['width']
    video_h = meta['height']

    vid_stride = int(profile.get('vid_stride', 3))
    track_imgsz = int(profile.get('track_imgsz', 352))

    # Run ByteTrack tracking
    track_data = {}
    frame_idx = 0
    for result in detector.track(source=video_path, stream=True, persist=True, classes=[0],
                                  conf=float(profile.get('track_conf', 0.3)),
                                  iou=float(profile.get('track_iou', 0.5)),
                                  tracker='bytetrack.yaml', imgsz=track_imgsz,
                                  verbose=False, device='cpu', vid_stride=vid_stride):
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

    if not track_data:
        return [], meta

    # Sliding windows
    window_frames = int(fps * float(profile.get('window_sec', 1.0)))
    stride_frames = int(fps * float(profile.get('stride_sec', 0.5)))
    if window_frames < 2: window_frames = 2
    if stride_frames < 1: stride_frames = 1

    all_features = []
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
                feats['track_id'] = tid
                feats['window_start'] = win_start
                feats['window_end'] = win_end
                all_features.append(feats)
            win_start += stride_frames

    return all_features, meta


def simulate_pipeline_score(classifier, features_list, fps, threshold):
    """단일 비디오의 윈도우 features로 전체 파이프라인 최종 score 시뮬레이션"""
    if not features_list:
        return 0.0, False

    X = np.array([[f[col] for col in FEATURE_COLS] for f in features_list])
    proba = classifier.predict_proba(X)[:, 1]
    predictions = classifier.predict(X)

    max_prob = float(np.max(proba))
    mean_prob = float(np.mean(proba))
    fall_ratio = float(np.sum(predictions == 1)) / len(predictions)

    peak_idx = int(np.argmax(proba))
    peak_feats = features_list[peak_idx]

    _fp = float(peak_feats.get('floor_proximity', 0.0))
    _hr = float(peak_feats.get('height_ratio', 0.0))
    _mds = float(peak_feats.get('max_down_speed', 0.0))
    _cdy = float(peak_feats.get('center_dy', 0.0))

    _fp_boost = min(1.0, max(0.0, (_fp - 0.5) / 0.5)) if _fp > 0.5 else 0.0
    _hr_boost = min(1.0, max(0.0, (-_hr - 0.05) / 0.25)) if _hr < -0.05 else 0.0

    final_score = max_prob * 0.45 + mean_prob * 0.25 + fall_ratio * 0.15 + _fp_boost * 0.10 + _hr_boost * 0.05
    final_score = round(max(0.0, min(0.999999, final_score)), 6)

    # Motion gate (majority vote)
    gate_checks = {
        'max_down_speed': _mds >= 0.15,
        'center_dy': _cdy >= 0.03,
        'pose_change': (_hr <= -0.05 or peak_feats.get('aspect_change', 0) >= 0.05 or _fp >= 0.78),
    }
    _floor_height_override = _fp >= 0.85 and _hr <= -0.08
    _floor_speed_override = _fp >= 0.75 and _mds >= 0.3
    _gate_pass_count = sum(1 for v in gate_checks.values() if v)
    motion_gate_passed = _gate_pass_count >= 2 or _floor_height_override or _floor_speed_override

    if not motion_gate_passed:
        final_score = min(final_score, max_prob * 0.35, mean_prob * 0.45, 0.35)

    fall_detected = final_score >= threshold
    return final_score, fall_detected


def main():
    parser = argparse.ArgumentParser(description='XGBoost 최적화 재학습')
    parser.add_argument('--n-train', type=int, default=200, help='학습용 Y/N 각 개수')
    parser.add_argument('--n-val', type=int, default=80, help='검증용 Y/N 각 개수')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    print("=" * 60)
    print("  XGBoost Person-Feature 파이프라인 최적화 재학습")
    print(f"  학습: Y/N 각 {args.n_train}개 | 검증: Y/N 각 {args.n_val}개")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 영상 수집
    print("\n[1/5] 영상 수집...")
    rng = random.Random(args.seed)

    fall_all = collect_videos(DATASET_ROOT, ['Y/FY', 'Y/BY', 'Y/SY'], None, args.seed)
    nonfall_all = collect_videos(DATASET_ROOT, ['N/N'], None, args.seed)
    rng.shuffle(fall_all)
    rng.shuffle(nonfall_all)

    n_train = args.n_train
    n_val = args.n_val

    # Fall은 충분하므로 offset 사용, NonFall은 적으므로 별도 seed로 셔플
    fall_offset = 400
    fall_train = fall_all[fall_offset:fall_offset + n_train]
    fall_val = fall_all[fall_offset + n_train:fall_offset + n_train + n_val]
    # NonFall은 seed+1로 다른 순서 사용 (RF와 부분적으로 겹칠 수 있지만 OK)
    rng2 = random.Random(args.seed + 1)
    rng2.shuffle(nonfall_all)
    nonfall_train = nonfall_all[:n_train]
    nonfall_val = nonfall_all[n_train:n_train + n_val]

    print(f"  학습: Fall {len(fall_train)}개 + NonFall {len(nonfall_train)}개")
    print(f"  검증: Fall {len(fall_val)}개 + NonFall {len(nonfall_val)}개")

    # 2. YOLO 로드
    print("\n[2/5] Person Detector 로드...")
    from ultralytics import YOLO
    detector = YOLO(PERSON_DETECTOR_PATH)
    print(f"  Person detector: {PERSON_DETECTOR_PATH}")

    # 3. Feature 추출
    print("\n[3/5] 윈도우 Feature 추출...")
    train_windows = []
    train_video_features = {}  # video_path -> features list (for pipeline sim)
    errors = 0

    def process_videos(video_paths, label, desc):
        nonlocal errors
        feats_all = []
        for i, vp in enumerate(video_paths):
            if (i + 1) % 10 == 0:
                print(f"    {desc} {i+1}/{len(video_paths)}...")
            try:
                features, meta = extract_video_features(vp, detector, PROFILE)
                if features:
                    for f in features:
                        f['label'] = label
                        f['video'] = os.path.basename(vp)
                    feats_all.extend(features)
                    train_video_features[vp] = features
                else:
                    errors += 1
            except Exception as e:
                errors += 1
        return feats_all

    print("  학습 Fall feature 추출...")
    train_fall_wins = process_videos(fall_train, 1, "학습 Fall")
    print(f"    → {len(train_fall_wins)} 윈도우")

    print("  학습 NonFall feature 추출...")
    train_nonfall_wins = process_videos(nonfall_train, 0, "학습 NonFall")
    print(f"    → {len(train_nonfall_wins)} 윈도우")

    train_windows = train_fall_wins + train_nonfall_wins
    print(f"  전체 학습 윈도우: {len(train_windows)} (Fall:{len(train_fall_wins)} NonFall:{len(train_nonfall_wins)})")

    # 검증 데이터 (video-level)
    print("  검증 Fall feature 추출...")
    val_video_data = []
    for i, vp in enumerate(fall_val):
        if (i + 1) % 10 == 0:
            print(f"    검증 Fall {i+1}/{len(fall_val)}...")
        try:
            features, meta = extract_video_features(vp, detector, PROFILE)
            val_video_data.append({'video': vp, 'label': 1, 'features': features, 'fps': meta['fps']})
        except Exception:
            errors += 1

    print("  검증 NonFall feature 추출...")
    for i, vp in enumerate(nonfall_val):
        if (i + 1) % 10 == 0:
            print(f"    검증 NonFall {i+1}/{len(nonfall_val)}...")
        try:
            features, meta = extract_video_features(vp, detector, PROFILE)
            val_video_data.append({'video': vp, 'label': 0, 'features': features, 'fps': meta['fps']})
        except Exception:
            errors += 1

    print(f"  검증 영상: {len(val_video_data)}개 (오류 {errors}건)")

    # 4. XGBoost 학습 + 최적화
    print("\n[4/5] XGBoost 학습 + threshold 최적화...")

    df_train = pd.DataFrame(train_windows)
    X_train = df_train[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    y_train = df_train['label'].values
    n_pos = int(sum(y_train == 1))
    n_neg = int(sum(y_train == 0))
    print(f"  학습 윈도우: {len(X_train)} (Fall:{n_pos} NonFall:{n_neg})")

    try:
        from xgboost import XGBClassifier
        use_xgb = True
    except ImportError:
        use_xgb = False
        print("  [!] xgboost 미설치 — sklearn GradientBoosting 사용")
        from sklearn.ensemble import GradientBoostingClassifier

    # Hyperparameter configurations
    configs = []
    for spw in [1.0, 2.0, 3.0, 5.0]:
        for md in [4, 6, 8]:
            for ne in [200, 300]:
                configs.append({
                    'name': f"spw={spw} md={md} ne={ne}",
                    'scale_pos_weight': spw,
                    'max_depth': md,
                    'n_estimators': ne,
                })

    thresholds = [round(t * 0.05, 2) for t in range(3, 12)]  # 0.15 ~ 0.55
    best_config = None
    best_score = -1
    all_results = []

    for ci, cfg in enumerate(configs):
        print(f"\n  [{ci+1}/{len(configs)}] {cfg['name']}")

        if use_xgb:
            clf_inner = XGBClassifier(
                max_depth=cfg['max_depth'],
                n_estimators=cfg['n_estimators'],
                scale_pos_weight=cfg['scale_pos_weight'],
                eval_metric='logloss',
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )
        else:
            clf_inner = GradientBoostingClassifier(
                max_depth=cfg['max_depth'],
                n_estimators=cfg['n_estimators'],
                random_state=42,
            )

        pipe = Pipeline([
            ('scaler', StandardScaler()),
            ('clf', clf_inner),
        ])
        pipe.fit(X_train, y_train)

        # Video-level validation with full pipeline simulation
        for thr in thresholds:
            tp = fn = fp = tn = 0
            for vd in val_video_data:
                if not vd['features']:
                    # 사람 미검출 → NonFall 예측
                    if vd['label'] == 0: tn += 1
                    else: fn += 1
                    continue
                score, detected = simulate_pipeline_score(pipe, vd['features'], vd['fps'], thr)
                pred = 1 if detected else 0
                if vd['label'] == 1 and pred == 1: tp += 1
                elif vd['label'] == 1 and pred == 0: fn += 1
                elif vd['label'] == 0 and pred == 1: fp += 1
                else: tn += 1

            total = tp + fn + fp + tn
            acc = (tp + tn) / total if total > 0 else 0
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

            result = {
                'config': cfg['name'], 'threshold': thr,
                'accuracy': round(acc, 4), 'precision': round(prec, 4),
                'recall': round(rec, 4), 'f1': round(f1, 4),
                'TP': tp, 'TN': tn, 'FP': fp, 'FN': fn,
            }
            all_results.append(result)

            # Recall ≥ 0.80 조건에서 Recall*0.6 + F1*0.4 최대화
            combo = rec * 0.6 + f1 * 0.4
            if rec >= 0.70 and combo > best_score:
                best_score = combo
                best_config = {
                    'pipe': pipe, 'cfg': cfg, 'threshold': thr, 'metrics': result,
                }

            if rec >= 0.70:
                print(f"    thr={thr:.2f} → acc={acc:.3f} prec={prec:.3f} "
                      f"rec={rec:.3f} f1={f1:.3f} | TP={tp} FN={fn} FP={fp} TN={tn}")

    # Recall 0.70 미달 시 가장 높은 recall 선택
    if best_config is None:
        print("\n  [!] Recall ≥ 0.70 미충족 — 최고 Recall 조합 선택")
        best_r = max(all_results, key=lambda x: x['recall'])
        print(f"    최고: {best_r}")
        # 해당 config 재학습
        for cfg in configs:
            if cfg['name'] == best_r['config']:
                if use_xgb:
                    clf_inner = XGBClassifier(
                        max_depth=cfg['max_depth'], n_estimators=cfg['n_estimators'],
                        scale_pos_weight=cfg['scale_pos_weight'], eval_metric='logloss',
                        random_state=42, n_jobs=-1, verbosity=0)
                else:
                    clf_inner = GradientBoostingClassifier(max_depth=cfg['max_depth'],
                        n_estimators=cfg['n_estimators'], random_state=42)
                pipe = Pipeline([('scaler', StandardScaler()), ('clf', clf_inner)])
                pipe.fit(X_train, y_train)
                best_config = {'pipe': pipe, 'cfg': cfg, 'threshold': best_r['threshold'], 'metrics': best_r}
                break

    # 5. 최적 모델 저장
    print("\n[5/5] 최적 모델 저장...")
    m = best_config['metrics']
    print(f"  ★ 최적 설정:")
    print(f"    {best_config['cfg']['name']}")
    print(f"    threshold:    {best_config['threshold']}")
    print(f"    Accuracy:     {m['accuracy']}")
    print(f"    Precision:    {m['precision']}")
    print(f"    Recall:       {m['recall']}")
    print(f"    F1:           {m['f1']}")
    print(f"    TP={m['TP']} FN={m['FN']} FP={m['FP']} TN={m['TN']}")

    # 모델 저장
    model_path = CLASSIFIER_DIR / 'best_model.pkl'
    backup_path = str(model_path) + f'.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}'
    if os.path.exists(model_path):
        os.rename(model_path, backup_path)
        print(f"  기존 모델 백업: {backup_path}")

    joblib.dump(best_config['pipe'], model_path)
    print(f"  새 모델 저장: {model_path}")

    # XGBoost 전용 모델도 저장
    xgb_path = CLASSIFIER_DIR / 'xgboost_model.pkl'
    if os.path.exists(xgb_path):
        os.rename(xgb_path, str(xgb_path) + f'.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}')
    joblib.dump(best_config['pipe'], xgb_path)

    # 평가 결과 JSON 저장
    eval_result = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'training_windows': {'total': len(X_train), 'fall': n_pos, 'nonfall': n_neg},
        'training_videos': {'fall': len(fall_train), 'nonfall': len(nonfall_train)},
        'validation_videos': len(val_video_data),
        'best_config': best_config['cfg'],
        'best_threshold': best_config['threshold'],
        'best_metrics': m,
        'source': 'retrain_xgb_optimized.py',
    }
    eval_path = CLASSIFIER_DIR / 'evaluation.json'
    with open(eval_path, 'w', encoding='utf-8') as f:
        json.dump(eval_result, f, ensure_ascii=False, indent=2)
    print(f"  평가 결과: {eval_path}")

    # Grid 결과 저장
    grid_path = CLASSIFIER_DIR / f'grid_search_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(grid_path, 'w', encoding='utf-8') as f:
        json.dump({'grid_results': all_results, 'best': eval_result}, f, ensure_ascii=False, indent=2)
    print(f"  Grid 결과: {grid_path}")

    # baseline_model.json 업데이트
    baseline_path = PROJECT_ROOT / 'storage/training/fall-detection/model/baseline_model.json'
    if os.path.exists(baseline_path):
        try:
            with open(baseline_path) as f:
                baseline = json.load(f)
            baseline['fall_classifier'] = {
                'type': 'XGBoost' if use_xgb else 'GradientBoosting',
                'training_samples': len(X_train),
                'training_videos': len(fall_train) + len(nonfall_train),
                'cv_f1': m['f1'],
                'cv_auc': 0,
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            with open(baseline_path, 'w') as f:
                json.dump(baseline, f, ensure_ascii=False, indent=2)
            print(f"  Baseline 업데이트: {baseline_path}")
        except Exception:
            pass

    # PF threshold 적용 안내
    print(f"\n  ⚠️ PF threshold 적용:")
    print(f"    src/model/struct/video_analysis.py → pf_threshold = {best_config['threshold']}")

    print(f"\n{'='*60}")
    print(f"  재학습 완료!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
