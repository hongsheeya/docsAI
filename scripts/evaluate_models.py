#!/usr/bin/env python3
"""
FallAI 모델 평가 스크립트
========================
낙상사고 위험동작 영상 데이터셋에서 1000개 영상을 샘플링하여
RF 파이프라인과 Person-Feature(XGBoost) 파이프라인의 정확도 및 특성을 측정한다.

사용법:
    python3 scripts/evaluate_models.py [--n-fall 500] [--n-nonfall 500] [--output eval_result.json]

데이터셋 구조:
    .../영상/Y/FY/  (전방낙상 776개)
    .../영상/Y/BY/  (후방낙상 576개)
    .../영상/Y/SY/  (측방낙상 352개)
    .../영상/N/N/   (비낙상 568개)
"""

import argparse
import json
import os
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ── 환경 설정 ──────────────────────────────────────────────────
if '/opt/app/my_libs' not in sys.path:
    sys.path.insert(0, '/opt/app/my_libs')

import cv2
import numpy as np
import pandas as pd

# ── 설정 상수 ──────────────────────────────────────────────────
PROJECT_ROOT = Path('/opt/app/project/main')
DATASET_ROOT = Path('/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상')

# RF 파이프라인
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

# Person-Feature (XGBoost) 파이프라인
BASELINE_JSON = PROJECT_ROOT / 'storage/training/fall-detection/model/baseline_model.json'
PF_THRESHOLD = 0.5

# ── 유틸리티 ──────────────────────────────────────────────────
def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def resolve_path(raw):
    """Resolve /mnt/data/wiz/ ↔ /opt/app/ path mapping."""
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


def collect_videos(base_dir, label_dirs, n_per_label=None, seed=42):
    """Collect and sample video paths from label directories.
    
    Args:
        base_dir: Base dataset path (e.g. .../영상/)
        label_dirs: Dict mapping label (1=fall, 0=nonfall) to list of subdirs
        n_per_label: Max videos per label. None = all.
    
    Returns:
        List of (video_path, true_label, subcategory)
    """
    rng = random.Random(seed)
    all_videos = []
    for label, subdirs in label_dirs.items():
        label_videos = []
        for subdir in subdirs:
            full_path = os.path.join(str(base_dir), subdir)
            if not os.path.isdir(full_path):
                print(f"  [WARN] 디렉토리 없음: {full_path}")
                continue
            for root, dirs, files in os.walk(full_path):
                for f in files:
                    if f.lower().endswith('.mp4'):
                        label_videos.append((os.path.join(root, f), label, subdir))
        rng.shuffle(label_videos)
        if n_per_label is not None and len(label_videos) > n_per_label:
            label_videos = label_videos[:n_per_label]
        all_videos.extend(label_videos)
        print(f"  라벨 {label} ({', '.join(subdirs)}): {len(label_videos)}개 수집")
    rng.shuffle(all_videos)
    return all_videos


# ── RF 파이프라인 추론 ────────────────────────────────────────
class RFEvaluator:
    """RF 파이프라인: YOLOv8n 사람 검출 → 16 통계 특성 → RandomForest 분류"""
    
    def __init__(self):
        import joblib
        from ultralytics import YOLO
        
        # 모델 로드
        model_path = RF_HITL_MODEL if os.path.isfile(RF_HITL_MODEL) else RF_SERVER_MODEL
        self.model_path = model_path
        self.rf_model = joblib.load(model_path)
        self.yolo = YOLO(RF_YOLO_MODEL)
        self.device = self._detect_device()
        
        # 모델 메타
        clf = self.rf_model.named_steps['clf'] if hasattr(self.rf_model, 'named_steps') and 'clf' in self.rf_model.named_steps else self.rf_model
        self.model_info = {
            'type': 'RandomForest',
            'model_path': model_path,
            'n_estimators': getattr(clf, 'n_estimators', 0),
            'max_depth': getattr(clf, 'max_depth', None),
            'n_features': getattr(clf, 'n_features_in_', len(RF_FEATURE_COLUMNS)),
            'threshold': RF_THRESHOLD,
        }
        print(f"  RF 모델 로드: {model_path}")
        print(f"    n_estimators={self.model_info['n_estimators']}, threshold={RF_THRESHOLD}")
    
    def _detect_device(self):
        try:
            import torch
            if torch.cuda.is_available():
                return 'cuda'
        except ImportError:
            pass
        return 'cpu'
    
    def infer(self, video_path):
        """단일 영상 RF 추론. Returns (predicted_label, score, elapsed_sec, error)"""
        t0 = time.time()
        try:
            feat, feat_df = self._extract_features(video_path)
            pred = int(self.rf_model.predict(feat_df)[0])
            fall_prob = None
            if hasattr(self.rf_model, 'predict_proba'):
                proba = self.rf_model.predict_proba(feat_df)[0]
                classes = list(self.rf_model.classes_)
                prob_map = {int(c): float(p) for c, p in zip(classes, proba)}
                fall_prob = prob_map.get(1, 0.0)
            
            score = fall_prob if fall_prob is not None else float(pred)
            fall_detected = 1 if score >= RF_THRESHOLD else 0
            elapsed = round(time.time() - t0, 3)
            return fall_detected, score, elapsed, None, feat
        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            return 0, 0.0, elapsed, str(e), None
    
    def _extract_features(self, video_path):
        """16 통계 특성 추출"""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise Exception(f'영상 열기 실패: {video_path}')
        
        orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if orig_fps <= 0:
            orig_fps = 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        
        step = max(int(round(orig_fps / RF_TARGET_FPS)), 1)
        frames = []
        _resize_to = None
        if vid_w > 1280 or vid_h > 720:
            if vid_w > vid_h:
                _resize_to = (640, int(vid_h * 640 / max(vid_w, 1)))
            else:
                _resize_to = (int(vid_w * 360 / max(vid_h, 1)), 360)
        
        if total_frames > 0 and step > 1:
            target_indices = set(range(0, total_frames, step))
            frame_idx = 0
            max_idx = max(target_indices) if target_indices else 0
            while frame_idx <= max_idx:
                ret = cap.grab()
                if not ret:
                    break
                if frame_idx in target_indices:
                    ret2, frame = cap.retrieve()
                    if ret2:
                        if _resize_to:
                            frame = cv2.resize(frame, _resize_to)
                        frames.append((frame_idx, frame))
                frame_idx += 1
        else:
            frame_idx = 0
            while True:
                ret = cap.grab()
                if not ret:
                    break
                if frame_idx % step == 0:
                    ret2, frame = cap.retrieve()
                    if ret2:
                        if _resize_to:
                            frame = cv2.resize(frame, _resize_to)
                        frames.append((frame_idx, frame))
                frame_idx += 1
        cap.release()
        
        if len(frames) == 0:
            raise Exception('프레임 추출 실패')
        
        # YOLO 추론
        frame_images = [f for _, f in frames]
        frame_indices = [i for i, _ in frames]
        batch_results = self.yolo.predict(
            source=frame_images, conf=RF_CONF_THRES, verbose=False,
            imgsz=RF_YOLO_IMGSZ, device=self.device
        )
        
        det_rows = []
        for i, r in enumerate(batch_results):
            boxes = r.boxes
            if boxes is None or len(boxes) == 0:
                continue
            best_row = None
            best_area = -1
            for b in boxes:
                cls_id = int(b.cls.item())
                if cls_id != RF_PERSON_CLASS:
                    continue
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                w, h = x2 - x1, y2 - y1
                area = w * h
                if area > best_area:
                    best_area = area
                    best_row = {
                        'frame_idx': frame_indices[i],
                        'width': w, 'height': h,
                        'center_x': (x1 + x2) / 2,
                        'center_y': (y1 + y2) / 2,
                        'area': area,
                    }
            if best_row:
                det_rows.append(best_row)
        
        if len(det_rows) < 2:
            raise Exception(f'사람 검출 부족 ({len(det_rows)} 프레임)')
        
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
            'n_frames': len(g),
            'center_y_mean': g['center_y'].mean(),
            'center_y_std': g['center_y'].std(),
            'height_mean': g['height'].mean(),
            'height_std': g['height'].std(),
            'width_mean': g['width'].mean(),
            'width_std': g['width'].std(),
            'area_mean': g['area'].mean(),
            'area_std': g['area'].std(),
            'aspect_ratio_mean': g['aspect_ratio'].mean(),
            'aspect_ratio_std': g['aspect_ratio'].std(),
            'delta_y_mean': g['delta_y'].mean(),
            'delta_y_max': g['delta_y'].max(),
            'delta_height_mean': g['delta_height'].mean(),
            'delta_width_mean': g['delta_width'].mean(),
            'delta_area_mean': g['delta_area'].mean(),
        }
        
        feat_df = pd.DataFrame([feat])
        feat_df = feat_df.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        feat_df = feat_df[RF_FEATURE_COLUMNS]
        
        return feat, feat_df


# ── Person-Feature (XGBoost) 파이프라인 추론 ──────────────────
class PFEvaluator:
    """Person-Feature: YOLOv8n 추적 → 10 모션 특성 → XGBoost 분류"""
    
    def __init__(self):
        # yolo_fall_runtime.py 모듈 로드
        sys.path.insert(0, str(PROJECT_ROOT / 'scripts'))
        import yolo_fall_runtime as yfr
        self.yfr = yfr
        
        # baseline 설정 로드
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
        
        # 모델 사전 로드
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
        print(f"  PF 모델 로드: {self.fc_path}")
        print(f"    classifier={self.model_info['classifier_type']}, threshold={PF_THRESHOLD}")
    
    def infer(self, video_path):
        """단일 영상 Person-Feature 추론."""
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
                'motion_gate_passed': (result.get('motion_gate', {}) or {}).get('passed', None),
            }
            return fall_detected, score, elapsed, None, extra
        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            return 0, 0.0, elapsed, str(e), None


# ── 메트릭 계산 ──────────────────────────────────────────────
def compute_metrics(y_true, y_pred, y_scores=None):
    """이진 분류 메트릭 계산"""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
    
    metrics = {
        'accuracy': round(accuracy, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1_score': round(f1, 4),
        'specificity': round(specificity, 4),
        'confusion_matrix': {
            'TP': tp, 'TN': tn, 'FP': fp, 'FN': fn,
        },
        'total': total,
    }
    
    # AUC (if scores available)
    if y_scores is not None and len(set(y_true)) > 1:
        try:
            from sklearn.metrics import roc_auc_score
            metrics['auc_roc'] = round(roc_auc_score(y_true, y_scores), 4)
        except Exception:
            pass
    
    return metrics


def compute_subcategory_metrics(results, subcategory_key='subcategory'):
    """서브카테고리별 메트릭 계산"""
    cats = {}
    for r in results:
        cat = r.get(subcategory_key, 'unknown')
        if cat not in cats:
            cats[cat] = {'y_true': [], 'y_pred': [], 'y_scores': []}
        cats[cat]['y_true'].append(r['true_label'])
        cats[cat]['y_pred'].append(r['pred_label'])
        cats[cat]['y_scores'].append(r['score'])
    
    cat_metrics = {}
    for cat, data in sorted(cats.items()):
        cat_metrics[cat] = compute_metrics(data['y_true'], data['y_pred'], data['y_scores'])
        cat_metrics[cat]['count'] = len(data['y_true'])
    return cat_metrics


# ── 메인 평가 루프 ────────────────────────────────────────────
def evaluate_pipeline(evaluator, videos, pipeline_name):
    """단일 파이프라인으로 모든 영상 평가"""
    results = []
    errors = []
    timings = []
    
    total = len(videos)
    print(f"\n{'='*60}")
    print(f"  {pipeline_name} 평가 시작 ({total}개 영상)")
    print(f"{'='*60}")
    
    for idx, (video_path, true_label, subcat) in enumerate(videos):
        pred, score, elapsed, error, extra = evaluator.infer(video_path)
        
        result = {
            'video': os.path.basename(video_path),
            'true_label': true_label,
            'pred_label': pred,
            'score': round(score, 4),
            'elapsed_sec': elapsed,
            'subcategory': subcat,
            'error': error,
        }
        if extra and isinstance(extra, dict):
            result['extra'] = extra
        
        results.append(result)
        timings.append(elapsed)
        
        if error:
            errors.append({'video': os.path.basename(video_path), 'error': error, 'subcat': subcat})
        
        # 진행률 출력 (매 50개마다)
        if (idx + 1) % 50 == 0 or idx == total - 1:
            done = idx + 1
            err_count = len(errors)
            avg_time = sum(timings) / len(timings) if timings else 0
            eta_sec = avg_time * (total - done)
            y_true_so_far = [r['true_label'] for r in results]
            y_pred_so_far = [r['pred_label'] for r in results]
            acc_so_far = sum(1 for t, p in zip(y_true_so_far, y_pred_so_far) if t == p) / len(y_true_so_far) if y_true_so_far else 0
            print(f"  [{done:4d}/{total}] acc={acc_so_far:.3f} | avg={avg_time:.2f}s | err={err_count} | ETA={eta_sec:.0f}s")
    
    # 최종 메트릭 계산
    y_true = [r['true_label'] for r in results]
    y_pred = [r['pred_label'] for r in results]
    y_scores = [r['score'] for r in results]
    
    overall = compute_metrics(y_true, y_pred, y_scores)
    subcat = compute_subcategory_metrics(results)
    
    timing_stats = {
        'mean_sec': round(np.mean(timings), 3),
        'median_sec': round(np.median(timings), 3),
        'p95_sec': round(np.percentile(timings, 95), 3),
        'min_sec': round(np.min(timings), 3),
        'max_sec': round(np.max(timings), 3),
        'total_sec': round(sum(timings), 1),
    }
    
    # Feature importance (RF만)
    feature_importance = {}
    if hasattr(evaluator, 'rf_model'):
        try:
            clf = evaluator.rf_model
            if hasattr(clf, 'named_steps') and 'clf' in clf.named_steps:
                clf = clf.named_steps['clf']
            if hasattr(clf, 'feature_importances_'):
                for col, imp in zip(RF_FEATURE_COLUMNS, clf.feature_importances_):
                    feature_importance[col] = round(float(imp), 4)
        except Exception:
            pass
    
    return {
        'pipeline': pipeline_name,
        'model_info': evaluator.model_info,
        'overall_metrics': overall,
        'subcategory_metrics': subcat,
        'timing': timing_stats,
        'feature_importance': feature_importance,
        'error_count': len(errors),
        'error_samples': errors[:20],
        'results': results,  # 전체 결과 (output에 포함)
    }


def print_report(eval_result):
    """평가 결과를 콘솔에 보기 좋게 출력"""
    name = eval_result['pipeline']
    m = eval_result['overall_metrics']
    t = eval_result['timing']
    cm = m['confusion_matrix']
    
    print(f"\n{'#'*60}")
    print(f"  {name} 최종 결과")
    print(f"{'#'*60}")
    print(f"  모델: {eval_result['model_info'].get('type', '?')}")
    print(f"  전체 정확도:  {m['accuracy']:.4f} ({m['accuracy']*100:.1f}%)")
    print(f"  Precision:   {m['precision']:.4f}")
    print(f"  Recall:      {m['recall']:.4f}")
    print(f"  F1 Score:    {m['f1_score']:.4f}")
    print(f"  Specificity: {m['specificity']:.4f}")
    if 'auc_roc' in m:
        print(f"  AUC-ROC:     {m['auc_roc']:.4f}")
    print(f"\n  혼동 행렬:")
    print(f"              Pred=Fall  Pred=Normal")
    print(f"  True=Fall     {cm['TP']:5d}      {cm['FN']:5d}")
    print(f"  True=Normal   {cm['FP']:5d}      {cm['TN']:5d}")
    print(f"\n  추론 시간 (초):")
    print(f"    평균: {t['mean_sec']:.3f}  /  중앙값: {t['median_sec']:.3f}  /  P95: {t['p95_sec']:.3f}")
    print(f"    최소: {t['min_sec']:.3f}  /  최대: {t['max_sec']:.3f}  /  총: {t['total_sec']:.1f}s")
    
    print(f"\n  서브카테고리별:")
    for cat, cm2 in eval_result['subcategory_metrics'].items():
        print(f"    {cat:6s}: acc={cm2['accuracy']:.3f}  prec={cm2['precision']:.3f}  rec={cm2['recall']:.3f}  f1={cm2['f1_score']:.3f}  n={cm2['count']}")
    
    if eval_result.get('feature_importance'):
        print(f"\n  Feature Importance (상위 10):")
        sorted_fi = sorted(eval_result['feature_importance'].items(), key=lambda x: x[1], reverse=True)
        for feat, imp in sorted_fi[:10]:
            bar = '█' * int(imp * 100)
            print(f"    {feat:22s}: {imp:.4f}  {bar}")
    
    if eval_result['error_count'] > 0:
        print(f"\n  오류: {eval_result['error_count']}건")
        for e in eval_result['error_samples'][:5]:
            print(f"    {e['video']}: {e['error'][:80]}")


def main():
    parser = argparse.ArgumentParser(description='FallAI 모델 평가')
    parser.add_argument('--n-fall', type=int, default=500, help='낙상(Y) 영상 수 (기본: 500)')
    parser.add_argument('--n-nonfall', type=int, default=500, help='비낙상(N) 영상 수 (기본: 500)')
    parser.add_argument('--seed', type=int, default=42, help='랜덤 시드')
    parser.add_argument('--output', type=str, default='', help='결과 JSON 파일 경로')
    parser.add_argument('--pipeline', type=str, default='both', choices=['rf', 'pf', 'both'],
                        help='평가할 파이프라인 (rf/pf/both)')
    parser.add_argument('--skip-detail', action='store_true', help='개별 결과 미저장')
    args = parser.parse_args()
    
    print("=" * 60)
    print("  FallAI 모델 정확도 평가")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 영상 수집 ──────────────────────────────────────────
    print("\n[1/4] 영상 수집 중...")
    label_dirs = {
        1: ['Y/FY', 'Y/BY', 'Y/SY'],  # fall
        0: ['N/N'],                      # non-fall
    }
    videos = collect_videos(
        DATASET_ROOT, label_dirs,
        n_per_label=None,  # 전부 수집 후 아래서 라벨별 샘플링
        seed=args.seed,
    )
    
    # 라벨별 샘플링
    fall_videos = [(v, l, s) for v, l, s in videos if l == 1]
    nonfall_videos = [(v, l, s) for v, l, s in videos if l == 0]
    
    rng = random.Random(args.seed)
    rng.shuffle(fall_videos)
    rng.shuffle(nonfall_videos)
    
    fall_sample = fall_videos[:args.n_fall]
    nonfall_sample = nonfall_videos[:args.n_nonfall]
    
    test_videos = fall_sample + nonfall_sample
    rng.shuffle(test_videos)
    
    n_fall = sum(1 for _, l, _ in test_videos if l == 1)
    n_nonfall = sum(1 for _, l, _ in test_videos if l == 0)
    print(f"  총 {len(test_videos)}개 (Fall={n_fall}, NonFall={n_nonfall})")
    
    # 2. 모델 로드 ──────────────────────────────────────────
    print("\n[2/4] 모델 로드 중...")
    evaluators = {}
    
    if args.pipeline in ('rf', 'both'):
        try:
            evaluators['RF Pipeline'] = RFEvaluator()
        except Exception as e:
            print(f"  [ERROR] RF 로드 실패: {e}")
    
    if args.pipeline in ('pf', 'both'):
        try:
            evaluators['Person-Feature (XGBoost)'] = PFEvaluator()
        except Exception as e:
            print(f"  [ERROR] PF 로드 실패: {e}")
    
    if not evaluators:
        print("  평가 가능한 모델 없음. 종료.")
        return
    
    # 3. 평가 실행 ──────────────────────────────────────────
    print("\n[3/4] 평가 실행 중...")
    all_results = {}
    total_start = time.time()
    
    for name, evaluator in evaluators.items():
        result = evaluate_pipeline(evaluator, test_videos, name)
        if args.skip_detail:
            result.pop('results', None)
        all_results[name] = result
        print_report(result)
    
    total_elapsed = round(time.time() - total_start, 1)
    
    # 4. 비교 요약 ──────────────────────────────────────────
    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print(f"  모델 비교 요약")
        print(f"{'='*60}")
        header = f"  {'모델':30s} {'정확도':>8s} {'Precision':>10s} {'Recall':>8s} {'F1':>8s} {'AUC':>8s} {'평균시간':>8s}"
        print(header)
        print(f"  {'-'*len(header)}")
        for name, r in all_results.items():
            m = r['overall_metrics']
            t = r['timing']
            auc = f"{m.get('auc_roc', 0):.4f}" if 'auc_roc' in m else 'N/A'
            print(f"  {name:30s} {m['accuracy']:>8.4f} {m['precision']:>10.4f} {m['recall']:>8.4f} {m['f1_score']:>8.4f} {auc:>8s} {t['mean_sec']:>7.3f}s")
    
    print(f"\n  총 소요 시간: {total_elapsed}초")
    
    # 5. 결과 저장 ──────────────────────────────────────────
    output_path = args.output
    if not output_path:
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        output_path = str(PROJECT_ROOT / f'eval_result_{ts}.json')
    
    # results 내 extra dict 정리 (JSON 직렬화)
    save_data = {
        'evaluation_date': datetime.now().isoformat(),
        'dataset': str(DATASET_ROOT),
        'sample_size': {'fall': n_fall, 'nonfall': n_nonfall, 'total': len(test_videos)},
        'seed': args.seed,
        'total_elapsed_sec': total_elapsed,
        'pipelines': {},
    }
    for name, r in all_results.items():
        save_r = dict(r)
        # Remove full per-video results from saved JSON to keep file manageable
        if 'results' in save_r:
            # Keep summary only
            save_r['per_video_count'] = len(save_r['results'])
            save_r.pop('results')
        save_data['pipelines'][name] = save_r
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  결과 저장: {output_path}")
    print("  완료.")


if __name__ == '__main__':
    main()
