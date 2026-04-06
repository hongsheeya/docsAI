#!/usr/bin/env python3
"""
FN-20260402-0009: RF 파이프라인 정밀 평가
==========================================
Y(낙상) 250개, N(비낙상) 250개 = 총 500개 영상을 RF 파이프라인으로 분석.
100개마다(Y 50 + N 50) 중간 결과를 출력한다.

사용법:
    python3 scripts/evaluate_rf_detailed.py [--n-per-label 250] [--batch-size 100] [--seed 42]
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

if '/opt/app/my_libs' not in sys.path:
    sys.path.insert(0, '/opt/app/my_libs')

import cv2
import numpy as np
import pandas as pd

# stdout unbuffered
import functools
print = functools.partial(print, flush=True)

# ── 설정 ──────────────────────────────────────────────────
PROJECT_ROOT = Path('/opt/app/project/main')
DATASET_ROOT = Path('/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상')

RF_SERVER_MODEL = '/opt/app/rf_model_server.pkl'
RF_HITL_MODEL = str(PROJECT_ROOT / 'storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl')
RF_YOLO_MODEL = 'yolov8n.pt'
RF_TARGET_FPS = 2
RF_CONF_THRES = 0.25
RF_PERSON_CLASS = 0
RF_YOLO_IMGSZ = 640
RF_THRESHOLD = 0.5
RF_FEATURE_COLUMNS = [
    'n_frames', 'center_y_mean', 'center_y_std',
    'height_mean', 'height_std', 'width_mean', 'width_std',
    'area_mean', 'area_std', 'aspect_ratio_mean', 'aspect_ratio_std',
    'delta_y_mean', 'delta_y_max',
    'delta_height_mean', 'delta_width_mean', 'delta_area_mean',
]


def collect_label_videos(base_dir, subdirs, n_per_label, seed):
    """라벨별 영상 수집 및 샘플링"""
    rng = random.Random(seed)
    videos = []
    for subdir in subdirs:
        full_path = os.path.join(str(base_dir), subdir)
        if not os.path.isdir(full_path):
            print(f"  [WARN] 디렉토리 없음: {full_path}")
            continue
        for root, dirs, files in os.walk(full_path):
            for f in files:
                if f.lower().endswith('.mp4'):
                    videos.append((os.path.join(root, f), subdir))
    rng.shuffle(videos)
    if len(videos) > n_per_label:
        videos = videos[:n_per_label]
    return videos


class RFInfer:
    def __init__(self):
        import joblib
        from ultralytics import YOLO

        model_path = RF_HITL_MODEL if os.path.isfile(RF_HITL_MODEL) else RF_SERVER_MODEL
        self.model_path = model_path
        self.rf_model = joblib.load(model_path)
        self.yolo = YOLO(RF_YOLO_MODEL)
        try:
            import torch
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        except ImportError:
            self.device = 'cpu'

        clf = self.rf_model.named_steps['clf'] if hasattr(self.rf_model, 'named_steps') and 'clf' in self.rf_model.named_steps else self.rf_model
        self.model_info = {
            'type': 'RandomForest',
            'model_path': model_path,
            'n_estimators': getattr(clf, 'n_estimators', 0),
            'threshold': RF_THRESHOLD,
        }
        print(f"  RF 모델: {model_path}")
        print(f"  n_estimators={self.model_info['n_estimators']}, threshold={RF_THRESHOLD}")

    def infer(self, video_path):
        t0 = time.time()
        try:
            feat_df = self._extract(video_path)
            score = 0.0
            if hasattr(self.rf_model, 'predict_proba'):
                proba = self.rf_model.predict_proba(feat_df)[0]
                classes = list(self.rf_model.classes_)
                prob_map = {int(c): float(p) for c, p in zip(classes, proba)}
                score = prob_map.get(1, 0.0)
            else:
                pred = int(self.rf_model.predict(feat_df)[0])
                score = float(pred)
            fall_detected = 1 if score >= RF_THRESHOLD else 0
            return fall_detected, round(score, 4), round(time.time() - t0, 3), None
        except Exception as e:
            return 0, 0.0, round(time.time() - t0, 3), str(e)

    def _extract(self, video_path):
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise Exception(f'열기 실패: {video_path}')
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
        if len(frames) == 0:
            raise Exception('프레임 없음')

        imgs = [f for _, f in frames]
        idxs = [i for i, _ in frames]
        results = self.yolo.predict(source=imgs, conf=RF_CONF_THRES, verbose=False, imgsz=RF_YOLO_IMGSZ, device=self.device)

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
                    best = {'frame_idx': idxs[i], 'width': w, 'height': h, 'center_x': (x1+x2)/2, 'center_y': (y1+y2)/2, 'area': area}
            if best: det_rows.append(best)

        if len(det_rows) < 2:
            raise Exception(f'검출 부족 ({len(det_rows)})')

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
        }
        feat_df = pd.DataFrame([feat]).replace([np.inf, -np.inf], np.nan).fillna(0.0)[RF_FEATURE_COLUMNS]
        return feat_df


def confusion(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    return tp, tn, fp, fn


def print_metrics(label, y_true, y_pred, y_scores, errors):
    tp, tn, fp, fn = confusion(y_true, y_pred)
    total = tp + tn + fp + fn
    acc = (tp + tn) / total if total > 0 else 0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

    # 오탐(FP)의 평균 위험 점수
    fp_scores = [s for t, p, s in zip(y_true, y_pred, y_scores) if t == 0 and p == 1]
    fp_avg_score = sum(fp_scores) / len(fp_scores) if fp_scores else 0

    print(f"\n{'─'*50}")
    print(f"  [{label}] 총 {total}건 | 오류 {errors}건")
    print(f"  정확도:    {acc:.4f} ({acc*100:.1f}%)")
    print(f"  Precision: {prec:.4f}  Recall: {rec:.4f}  F1: {f1:.4f}")
    print(f"  Y→Y(TP): {tp}  Y→N(FN): {fn}  N→Y(FP): {fp}  N→N(TN): {tn}")
    print(f"  오탐(FP) 평균 위험점수: {fp_avg_score:.4f}")
    print(f"{'─'*50}")


def main():
    parser = argparse.ArgumentParser(description='RF 파이프라인 정밀 평가')
    parser.add_argument('--n-per-label', type=int, default=250)
    parser.add_argument('--batch-size', type=int, default=100, help='중간 결과 출력 간격')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=str, default='')
    args = parser.parse_args()

    half_batch = args.batch_size // 2  # Y/N 각각의 배치 사이즈

    print("=" * 60)
    print("  RF 파이프라인 정밀 평가")
    print(f"  Y {args.n_per_label}개 + N {args.n_per_label}개 = 총 {args.n_per_label * 2}개")
    print(f"  {args.batch_size}개마다(Y {half_batch} + N {half_batch}) 중간 결과 출력")
    print(f"  threshold={RF_THRESHOLD}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 영상 수집
    print("\n[1/3] 영상 수집...")
    fall_videos = collect_label_videos(DATASET_ROOT, ['Y/FY', 'Y/BY', 'Y/SY'], args.n_per_label, args.seed)
    nonfall_videos = collect_label_videos(DATASET_ROOT, ['N/N'], args.n_per_label, args.seed)
    print(f"  Fall(Y): {len(fall_videos)}개, NonFall(N): {len(nonfall_videos)}개")

    # 교차 배치 구성: Y half_batch개 + N half_batch개씩 번갈아
    batched = []
    fi, ni = 0, 0
    while fi < len(fall_videos) or ni < len(nonfall_videos):
        chunk = []
        for _ in range(half_batch):
            if fi < len(fall_videos):
                vp, sc = fall_videos[fi]
                chunk.append((vp, 1, sc))
                fi += 1
        for _ in range(half_batch):
            if ni < len(nonfall_videos):
                vp, sc = nonfall_videos[ni]
                chunk.append((vp, 0, sc))
                ni += 1
        batched.extend(chunk)

    total = len(batched)
    print(f"  실제 평가 대상: {total}개")

    # 2. 모델 로드
    print("\n[2/3] 모델 로드...")
    evaluator = RFInfer()

    # 3. 평가
    print("\n[3/3] 평가 시작...")
    all_true, all_pred, all_scores = [], [], []
    error_count = 0
    results = []
    t_start = time.time()

    for idx, (vpath, true_label, subcat) in enumerate(batched):
        pred, score, elapsed, error = evaluator.infer(vpath)
        all_true.append(true_label)
        all_pred.append(pred)
        all_scores.append(score)
        if error:
            error_count += 1
        results.append({
            'video': os.path.basename(vpath),
            'true_label': true_label,
            'pred_label': pred,
            'score': score,
            'elapsed': elapsed,
            'subcat': subcat,
            'error': error,
        })

        done = idx + 1
        # 매 batch_size마다 중간결과 출력
        if done % args.batch_size == 0 or done == total:
            batch_label = f"중간 {done}/{total}" if done < total else f"최종 {done}/{total}"
            print_metrics(batch_label, all_true, all_pred, all_scores, error_count)

    total_time = round(time.time() - t_start, 1)
    print(f"\n총 소요 시간: {total_time}초")

    # 결과 저장
    output_path = args.output or str(PROJECT_ROOT / f'eval_rf_detailed_{datetime.now().strftime("%Y%m%d-%H%M%S")}.json')
    tp, tn, fp, fn = confusion(all_true, all_pred)
    acc = (tp + tn) / len(all_true) if all_true else 0
    fp_scores = [s for t, p, s in zip(all_true, all_pred, all_scores) if t == 0 and p == 1]

    # 오탐(FP) / 미탐(FN) 상세 목록
    fp_list = [r for r in results if r['true_label'] == 0 and r['pred_label'] == 1]
    fn_list = [r for r in results if r['true_label'] == 1 and r['pred_label'] == 0]

    if fp_list:
        print(f"\n{'='*50}")
        print(f"  오탐(FP) 상세 — {len(fp_list)}건")
        print(f"{'='*50}")
        for r in fp_list:
            print(f"  {r['video']:40s} score={r['score']:.4f}  subcat={r['subcat']}")

    if fn_list:
        print(f"\n{'='*50}")
        print(f"  미탐(FN) 상세 — {len(fn_list)}건")
        print(f"{'='*50}")
        for r in fn_list:
            print(f"  {r['video']:40s} score={r['score']:.4f}  subcat={r['subcat']}")

    save_data = {
        'pipeline': 'RF Pipeline',
        'threshold': RF_THRESHOLD,
        'model_info': evaluator.model_info,
        'sample_size': {'fall': sum(1 for t in all_true if t == 1), 'nonfall': sum(1 for t in all_true if t == 0)},
        'overall': {
            'accuracy': round(acc, 4),
            'TP': tp, 'TN': tn, 'FP': fp, 'FN': fn,
            'fp_avg_risk_score': round(sum(fp_scores) / len(fp_scores), 4) if fp_scores else 0,
        },
        'errors': error_count,
        'total_time_sec': total_time,
        'date': datetime.now().isoformat(),
        'false_positives': fp_list,
        'false_negatives': fn_list,
        'all_results': results,
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"  결과 저장: {output_path}")


if __name__ == '__main__':
    main()
