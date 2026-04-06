#!/usr/bin/env python3
"""
RF 파이프라인 최적화 재학습
===========================
1. 대규모 데이터셋에서 YOLO 특징 추출 (학습/검증 분리)
2. class_weight sweep으로 Recall 최적화
3. threshold sweep으로 최적 분류 경계점 탐색
4. 최적 모델 저장 및 검증 결과 리포트

사용법:
    python3 scripts/retrain_rf_optimized.py [--n-train 400] [--n-val 100] [--seed 42]
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
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report, f1_score, recall_score, precision_score

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

FEATURE_COLUMNS = [
    'n_frames', 'center_y_mean', 'center_y_std',
    'height_mean', 'height_std', 'width_mean', 'width_std',
    'area_mean', 'area_std', 'aspect_ratio_mean', 'aspect_ratio_std',
    'delta_y_mean', 'delta_y_max',
    'delta_height_mean', 'delta_width_mean', 'delta_area_mean',
]

OUTPUT_DIR = PROJECT_ROOT / 'storage/training/fall-detection/rf-pipeline'
HITL_MODEL_PATH = OUTPUT_DIR / 'rf_hitl_model.pkl'


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


def extract_features_batch(video_paths, yolo, device):
    """배치로 특징 추출"""
    all_feats = []
    errors = 0
    for i, vp in enumerate(video_paths):
        if (i + 1) % 20 == 0:
            print(f"    특징 추출 {i+1}/{len(video_paths)}...")
        try:
            feat = extract_single(vp, yolo, device)
            if feat is not None:
                all_feats.append(feat)
            else:
                errors += 1
        except Exception:
            errors += 1
    return all_feats, errors


def extract_single(video_path, yolo, device):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0: fps = 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
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
    g['area'] = g['width'] * g['height']
    g['aspect_ratio'] = g['width'] / (g['height'] + 1e-6)
    g['delta_y_raw'] = g['center_y'].diff()
    g['delta_y'] = g['delta_y_raw'].clip(lower=0)
    g['delta_height'] = g['height'].diff().abs()
    g['delta_width'] = g['width'].diff().abs()
    g['delta_area'] = g['area'].diff().abs()

    feat = {
        'n_frames': len(g), 'center_y_mean': g['center_y'].mean(), 'center_y_std': g['center_y'].std(),
        'height_mean': g['height'].mean(), 'height_std': g['height'].std(),
        'width_mean': g['width'].mean(), 'width_std': g['width'].std(),
        'area_mean': g['area'].mean(), 'area_std': g['area'].std(),
        'aspect_ratio_mean': g['aspect_ratio'].mean(), 'aspect_ratio_std': g['aspect_ratio'].std(),
        'delta_y_mean': g['delta_y'].mean(), 'delta_y_max': g['delta_y'].max(),
        'delta_height_mean': g['delta_height'].mean(), 'delta_width_mean': g['delta_width'].mean(),
        'delta_area_mean': g['delta_area'].mean(),
        'video': os.path.basename(video_path),
    }
    return feat


def train_and_evaluate(X_train, y_train, X_val, y_val, n_estimators, class_weight, thresholds):
    """특정 설정으로 RF 학습 → threshold sweep"""
    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        class_weight=class_weight,
        max_depth=None,
        min_samples_split=2,
        min_samples_leaf=1,
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    # 검증 세트 확률 예측
    proba = clf.predict_proba(X_val)
    classes = list(clf.classes_)
    fall_idx = classes.index(1)
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


def main():
    parser = argparse.ArgumentParser(description='RF 최적화 재학습')
    parser.add_argument('--n-train', type=int, default=400, help='학습용 Y/N 각 개수')
    parser.add_argument('--n-val', type=int, default=100, help='검증용 Y/N 각 개수')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    print("=" * 60)
    print("  RF 파이프라인 최적화 재학습")
    print(f"  학습: Y/N 각 {args.n_train}개 | 검증: Y/N 각 {args.n_val}개")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 영상 수집 (학습/검증 분리)
    print("\n[1/4] 영상 수집...")
    rng = random.Random(args.seed)

    fall_all = collect_videos(DATASET_ROOT, ['Y/FY', 'Y/BY', 'Y/SY'], None, args.seed)
    nonfall_all = collect_videos(DATASET_ROOT, ['N/N'], None, args.seed)
    rng.shuffle(fall_all)
    rng.shuffle(nonfall_all)

    n_train = args.n_train
    n_val = args.n_val

    fall_train = fall_all[:n_train]
    fall_val = fall_all[n_train:n_train + n_val]
    nonfall_train = nonfall_all[:n_train]
    nonfall_val = nonfall_all[n_train:n_train + n_val]

    print(f"  학습: Fall {len(fall_train)}개 + NonFall {len(nonfall_train)}개")
    print(f"  검증: Fall {len(fall_val)}개 + NonFall {len(nonfall_val)}개")

    # 2. YOLO 로드 + 특징 추출
    print("\n[2/4] YOLO 로드 및 특징 추출...")
    from ultralytics import YOLO
    yolo = YOLO(RF_YOLO_MODEL)
    try:
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    except ImportError:
        device = 'cpu'
    print(f"  Device: {device}")

    print("  학습 Fall 특징 추출...")
    train_fall_feats, err1 = extract_features_batch(fall_train, yolo, device)
    print(f"    → {len(train_fall_feats)}건 (오류 {err1})")

    print("  학습 NonFall 특징 추출...")
    train_nonfall_feats, err2 = extract_features_batch(nonfall_train, yolo, device)
    print(f"    → {len(train_nonfall_feats)}건 (오류 {err2})")

    print("  검증 Fall 특징 추출...")
    val_fall_feats, err3 = extract_features_batch(fall_val, yolo, device)
    print(f"    → {len(val_fall_feats)}건 (오류 {err3})")

    print("  검증 NonFall 특징 추출...")
    val_nonfall_feats, err4 = extract_features_batch(nonfall_val, yolo, device)
    print(f"    → {len(val_nonfall_feats)}건 (오류 {err4})")

    # DataFrame 구성
    for f in train_fall_feats: f['label'] = 1
    for f in train_nonfall_feats: f['label'] = 0
    for f in val_fall_feats: f['label'] = 1
    for f in val_nonfall_feats: f['label'] = 0

    df_train = pd.DataFrame(train_fall_feats + train_nonfall_feats)
    df_val = pd.DataFrame(val_fall_feats + val_nonfall_feats)

    X_train = df_train[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    y_train = df_train['label'].values
    X_val = df_val[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    y_val = df_val['label'].values

    print(f"\n  학습 데이터: {len(X_train)}건 (Y:{sum(y_train==1)} N:{sum(y_train==0)})")
    print(f"  검증 데이터: {len(X_val)}건 (Y:{sum(y_val==1)} N:{sum(y_val==0)})")

    # 3. Grid Search: class_weight × threshold
    print("\n[3/4] class_weight × threshold 최적화...")
    thresholds = [round(t * 0.05, 2) for t in range(3, 12)]  # 0.15 ~ 0.55
    weight_configs = [
        ('balanced', 'balanced'),
        ('1:1', {0: 1, 1: 1}),
        ('1:2', {0: 1, 1: 2}),
        ('1:3', {0: 1, 1: 3}),
        ('1:4', {0: 1, 1: 4}),
        ('1:5', {0: 1, 1: 5}),
    ]
    n_estimators_list = [200, 300]

    all_results = []
    best_config = None
    best_recall_f1_score = -1  # recall ≥ 0.85 조건에서 F1 최대화

    for n_est in n_estimators_list:
        for wname, wval in weight_configs:
            print(f"\n  n_est={n_est}, weight={wname}")
            clf, sweep = train_and_evaluate(X_train, y_train, X_val, y_val, n_est, wval, thresholds)

            for r in sweep:
                r['n_estimators'] = n_est
                r['class_weight'] = wname
                all_results.append(r)

                # Recall ≥ 0.85 조건에서 F1 최대화 (Recall 우선)
                score = r['recall'] * 0.6 + r['f1'] * 0.4  # Recall 가중
                if r['recall'] >= 0.80 and score > best_recall_f1_score:
                    best_recall_f1_score = score
                    best_config = {
                        'clf': clf,
                        'n_estimators': n_est,
                        'class_weight': wname,
                        'class_weight_val': wval,
                        'threshold': r['threshold'],
                        'metrics': r,
                    }

                # 상위 결과만 출력
                if r['recall'] >= 0.80:
                    print(f"    thr={r['threshold']:.2f} → acc={r['accuracy']:.3f} prec={r['precision']:.3f} "
                          f"rec={r['recall']:.3f} f1={r['f1']:.3f} | TP={r['TP']} FN={r['FN']} FP={r['FP']} TN={r['TN']}")

    # Recall 0.80 미달 시 가장 높은 recall 선택
    if best_config is None:
        print("\n  [!] Recall ≥ 0.80 조건 미충족 — 최고 Recall 선택")
        best_r = max(all_results, key=lambda x: x['recall'])
        # 해당 config로 다시 학습
        for n_est in n_estimators_list:
            for wname, wval in weight_configs:
                clf, sweep = train_and_evaluate(X_train, y_train, X_val, y_val, n_est, wval, thresholds)
                for r in sweep:
                    if r['threshold'] == best_r['threshold'] and n_est == best_r['n_estimators'] and wname == best_r['class_weight']:
                        best_config = {
                            'clf': clf, 'n_estimators': n_est, 'class_weight': wname,
                            'class_weight_val': wval, 'threshold': r['threshold'], 'metrics': r,
                        }
                        break

    # 4. 최적 모델 저장
    print("\n[4/4] 최적 모델 저장...")
    m = best_config['metrics']
    print(f"  ★ 최적 설정:")
    print(f"    n_estimators: {best_config['n_estimators']}")
    print(f"    class_weight: {best_config['class_weight']}")
    print(f"    threshold:    {best_config['threshold']}")
    print(f"    Accuracy:     {m['accuracy']}")
    print(f"    Precision:    {m['precision']}")
    print(f"    Recall:       {m['recall']}")
    print(f"    F1:           {m['f1']}")
    print(f"    TP={m['TP']} FN={m['FN']} FP={m['FP']} TN={m['TN']}")

    # 모델 저장 (기존 백업 후)
    backup_path = str(HITL_MODEL_PATH) + f'.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}'
    if os.path.exists(HITL_MODEL_PATH):
        os.rename(HITL_MODEL_PATH, backup_path)
        print(f"  기존 모델 백업: {backup_path}")

    joblib.dump(best_config['clf'], HITL_MODEL_PATH)
    print(f"  새 모델 저장: {HITL_MODEL_PATH}")

    # 학습 요약 저장
    summary = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'training_samples': len(X_train),
        'validation_samples': len(X_val),
        'class_distribution_train': {'Y': int(sum(y_train == 1)), 'N': int(sum(y_train == 0))},
        'class_distribution_val': {'Y': int(sum(y_val == 1)), 'N': int(sum(y_val == 0))},
        'features': FEATURE_COLUMNS,
        'best_config': {
            'n_estimators': best_config['n_estimators'],
            'class_weight': best_config['class_weight'],
            'threshold': best_config['threshold'],
        },
        'best_metrics': m,
        'source': 'retrain_rf_optimized.py',
        'ready': True,
        'model_path': str(HITL_MODEL_PATH),
        'n_estimators': best_config['n_estimators'],
        'optimal_threshold': best_config['threshold'],
    }
    summary_path = OUTPUT_DIR / 'training_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  학습 요약: {summary_path}")

    # 전체 grid 결과 저장
    grid_path = OUTPUT_DIR / f'grid_search_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(grid_path, 'w', encoding='utf-8') as f:
        json.dump({'grid_results': all_results, 'best': summary['best_config'], 'best_metrics': m}, f, ensure_ascii=False, indent=2)
    print(f"  Grid 결과: {grid_path}")

    # video_analysis.py threshold 업데이트 안내
    print(f"\n  ⚠️ threshold 적용:")
    print(f"    src/model/struct/video_analysis.py → self.fall_decision_threshold = {best_config['threshold']}")
    print(f"    scripts/evaluate_models.py → RF_THRESHOLD = {best_config['threshold']}")

    print(f"\n{'='*60}")
    print(f"  재학습 완료!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
