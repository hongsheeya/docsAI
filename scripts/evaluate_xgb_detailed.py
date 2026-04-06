#!/usr/bin/env python3
"""
FN-20260402-0010: XGBoost(Person-Feature) 파이프라인 정밀 평가
==============================================================
Y(낙상) 250개, N(비낙상) 250개 = 총 500개 영상을 XGBoost 파이프라인으로 분석.
100개마다(Y 50 + N 50) 중간 결과를 출력한다.

사용법:
    python3 scripts/evaluate_xgb_detailed.py [--n-per-label 250] [--batch-size 100] [--seed 42]
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

import numpy as np

# stdout unbuffered
import functools
print = functools.partial(print, flush=True)

# ── 설정 ──────────────────────────────────────────────────
PROJECT_ROOT = Path('/opt/app/project/main')
DATASET_ROOT = Path('/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상')

BASELINE_JSON = PROJECT_ROOT / 'storage/training/fall-detection/model/baseline_model.json'
PF_THRESHOLD = 0.5


def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def resolve_path(raw):
    raw = str(raw or '').strip()
    if not raw:
        return raw
    if os.path.exists(raw):
        return raw
    if raw.startswith('/mnt/data/wiz/'):
        alt = '/opt/app/' + raw[len('/mnt/data/wiz/'):]
        if os.path.exists(alt):
            return alt
    if raw.startswith('/opt/app/'):
        alt = '/mnt/data/wiz/' + raw[len('/opt/app/'):]
        if os.path.exists(alt):
            return alt
    return raw


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


class XGBInfer:
    """Person-Feature: YOLO + ByteTrack → 10 motion features → XGBoost"""

    def __init__(self):
        sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
        import yolo_fall_runtime as yfr
        self.yfr = yfr

        baseline = read_json(BASELINE_JSON, {}) or {}
        pd_info = baseline.get('person_detector', {}) or {}
        self.pd_weights = resolve_path(pd_info.get('weights', ''))

        fc_info = baseline.get('fall_classifier', {}) or {}
        fc_raw = fc_info.get('path', '')
        if fc_raw and not os.path.isabs(fc_raw):
            self.fc_path = str(PROJECT_ROOT / fc_raw)
        else:
            self.fc_path = resolve_path(fc_raw)

        if not os.path.exists(self.pd_weights):
            raise FileNotFoundError(f'Person detector 가중치 없음: {self.pd_weights}')
        if not os.path.exists(self.fc_path):
            raise FileNotFoundError(f'Fall classifier 모델 없음: {self.fc_path}')

        self.detector = yfr.get_cached_yolo(self.pd_weights)
        self.classifier = yfr.get_cached_classifier(self.fc_path)

        self.model_info = {
            'type': 'XGBoost (Person-Feature)',
            'person_detector': self.pd_weights,
            'fall_classifier': self.fc_path,
            'classifier_type': type(self.classifier).__name__,
            'threshold': PF_THRESHOLD,
            'cv_f1': fc_info.get('cv_f1', 0),
            'cv_auc': fc_info.get('cv_auc', 0),
        }
        print(f"  PF 모델: {self.fc_path}")
        print(f"  classifier={self.model_info['classifier_type']}, threshold={PF_THRESHOLD}")

    def infer(self, video_path):
        t0 = time.time()
        try:
            result = self.yfr._person_feature_infer(
                self.pd_weights, self.fc_path, str(video_path),
                threshold=PF_THRESHOLD, analysis_profile='fast'
            )
            score = float(result.get('fall_score', 0.0))
            fall_detected = 1 if result.get('fall_detected', False) else 0
            elapsed = round(time.time() - t0, 3)
            extra = {
                'tracks': result.get('tracks', 0),
                'windows': result.get('windows', 0),
                'processed_frames': result.get('processed_frames', 0),
            }
            return fall_detected, round(score, 4), elapsed, None, extra
        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            return 0, 0.0, elapsed, str(e), None


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

    print(f"\n{'─'*50}")
    print(f"  [{label}] 총 {total}건 | 오류 {errors}건")
    print(f"  정확도:    {acc:.4f} ({acc*100:.1f}%)")
    print(f"  Precision: {prec:.4f}  Recall: {rec:.4f}  F1: {f1:.4f}")
    print(f"  Y→Y(TP): {tp}  Y→N(FN): {fn}  N→Y(FP): {fp}  N→N(TN): {tn}")
    print(f"{'─'*50}")


def main():
    parser = argparse.ArgumentParser(description='XGBoost(Person-Feature) 파이프라인 정밀 평가')
    parser.add_argument('--n-per-label', type=int, default=250)
    parser.add_argument('--batch-size', type=int, default=100, help='중간 결과 출력 간격')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=str, default='')
    args = parser.parse_args()

    half_batch = args.batch_size // 2  # Y/N 각각의 배치 사이즈

    print("=" * 60)
    print("  XGBoost(Person-Feature) 파이프라인 정밀 평가")
    print(f"  Y {args.n_per_label}개 + N {args.n_per_label}개 = 총 {args.n_per_label * 2}개")
    print(f"  {args.batch_size}개마다(Y {half_batch} + N {half_batch}) 중간 결과 출력")
    print(f"  threshold={PF_THRESHOLD}")
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
    evaluator = XGBInfer()

    # 3. 평가
    print("\n[3/3] 평가 시작...")
    all_true, all_pred, all_scores = [], [], []
    error_count = 0
    results = []
    t_start = time.time()

    for idx, (vpath, true_label, subcat) in enumerate(batched):
        pred, score, elapsed, error, extra = evaluator.infer(vpath)
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
            'extra': extra,
        })

        done = idx + 1
        # 매 batch_size마다 중간결과 출력
        if done % args.batch_size == 0 or done == total:
            batch_label = f"중간 {done}/{total}" if done < total else f"최종 {done}/{total}"
            print_metrics(batch_label, all_true, all_pred, all_scores, error_count)

    total_time = round(time.time() - t_start, 1)
    print(f"\n총 소요 시간: {total_time}초")

    # 결과 저장
    output_path = args.output or str(PROJECT_ROOT / f'eval_xgb_detailed_{datetime.now().strftime("%Y%m%d-%H%M%S")}.json')
    tp, tn, fp, fn = confusion(all_true, all_pred)
    acc = (tp + tn) / len(all_true) if all_true else 0

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
        'pipeline': 'XGBoost (Person-Feature)',
        'threshold': PF_THRESHOLD,
        'model_info': evaluator.model_info,
        'sample_size': {'fall': sum(1 for t in all_true if t == 1), 'nonfall': sum(1 for t in all_true if t == 0)},
        'overall': {
            'accuracy': round(acc, 4),
            'TP': tp, 'TN': tn, 'FP': fp, 'FN': fn,
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
