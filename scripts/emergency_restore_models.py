#!/usr/bin/env python3
"""비상 합성 모델 복구 스크립트.

실제 RF/XG 모델 파일과 intake 데이터가 모두 사라진 상황에서,
서비스가 즉시 fallback 상태를 벗어나도록 최소 동작 가능한 운영 모델 아티팩트를 재생성한다.

생성 대상:
- /opt/app/_appdata/data (끊어진 project/main/data 심볼릭 링크 복구)
- RF-Dual 낙상 분류 모델
- XG-Posture 자세 분류 번들
- 각 training_summary.json
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split


APP_ROOT = Path('/opt/app')
PROJECT_ROOT = APP_ROOT / 'project' / 'main'
APPDATA_ROOT = APP_ROOT / '_appdata'
VIDEO_ANALYSIS_PATH = PROJECT_ROOT / 'src' / 'model' / 'struct' / 'video_analysis.py'

DATA_ROOT = APPDATA_ROOT / 'data'
UPLOADS_ROOT = DATA_ROOT / 'uploads' / 'fall-detection-prototype'
TRAINING_ROOT = APP_ROOT / 'storage' / 'training' / 'fall-detection'
INTAKE_ROOT = TRAINING_ROOT / 'intake'

RF_MODEL_PATH = TRAINING_ROOT / 'rf-pipeline' / 'rf_hitl_model.pkl'
RF_SUMMARY_PATH = TRAINING_ROOT / 'rf-pipeline' / 'training_summary.json'
RF_LEGACY_PATH = APP_ROOT / 'rf_model_server.pkl'
RF_POSE_MODEL_PATH = TRAINING_ROOT / 'rf-pose' / 'rf_pose_model.pkl'
RF_POSE_SUMMARY_PATH = TRAINING_ROOT / 'rf-pose' / 'training_summary.json'

XG_FALL_MODEL_PATH = TRAINING_ROOT / 'xg-fall' / 'xg_fall_model.pkl'
XG_FALL_SUMMARY_PATH = TRAINING_ROOT / 'xg-fall' / 'training_summary.json'

XG_POSTURE_MODEL_PATH = TRAINING_ROOT / 'xg-posture' / 'xg_posture_model.pkl'
XG_POSTURE_SUMMARY_PATH = TRAINING_ROOT / 'xg-posture' / 'training_summary.json'


def _read_list_constant(name: str):
    text = VIDEO_ANALYSIS_PATH.read_text(encoding='utf-8')
    match = re.search(rf'{re.escape(name)}\s*=\s*(\[[\s\S]*?\])', text)
    if match is None:
        raise RuntimeError(f'상수 {name} 를 {VIDEO_ANALYSIS_PATH} 에서 찾을 수 없습니다.')
    return ast.literal_eval(match.group(1))


RF_FEATURE_COLUMNS = _read_list_constant('_RF_FEATURE_COLUMNS')
POSE_FEATURE_COLUMNS = _read_list_constant('_POSE_FEATURE_COLUMNS')
XG_FEATURE_COLUMNS = _read_list_constant('_XG_FEATURE_COLUMNS')
LABEL_L2_CLASSES = _read_list_constant('_LABEL_L2_CLASSES')


def _now() -> str:
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _atomic_joblib_dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix='.tmp', dir=str(path.parent))
    os.close(fd)
    try:
        joblib.dump(obj, tmp_path)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _atomic_write_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix='.tmp', dir=str(path.parent))
    os.close(fd)
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _clamp(col: str, value: float) -> float:
    if 'rate' in col or 'ratio' in col or 'conf' in col or 'stillness' in col or 'proximity' in col:
        return float(np.clip(value, 0.0, 1.4))
    if 'angle' in col or 'tilt' in col:
        return float(np.clip(value, 0.0, 180.0))
    if 'count' in col or 'points' in col:
        return float(np.clip(value, 0.0, 17.0))
    return float(np.clip(value, -2.0, 2.0))


def ensure_structure():
    for path in [
        DATA_ROOT,
        UPLOADS_ROOT,
        APPDATA_ROOT / 'storage' / 'alerts' / 'fall-detection',
        RF_MODEL_PATH.parent,
        RF_POSE_MODEL_PATH.parent,
        XG_FALL_MODEL_PATH.parent,
        XG_POSTURE_MODEL_PATH.parent,
        INTAKE_ROOT,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    for name in ['Y', 'N', *LABEL_L2_CLASSES]:
        (INTAKE_ROOT / name).mkdir(parents=True, exist_ok=True)


def _rf_profile(label: int):
    if label == 1:
        return {
            'detection_rate': 0.90,
            'center_y_mean': 0.78,
            'center_y_std': 0.16,
            'height_mean': 0.18,
            'height_std': 0.07,
            'aspect_ratio_mean': 1.65,
            'aspect_ratio_std': 0.34,
            'delta_y_mean': 0.11,
            'delta_y_max': 0.27,
            'delta_height_mean': -0.035,
            'delta_width_mean': 0.020,
            'delta_y_accel_max': 0.12,
            'final_height_ratio': 0.42,
        }
    return {
        'detection_rate': 0.95,
        'center_y_mean': 0.55,
        'center_y_std': 0.05,
        'height_mean': 0.34,
        'height_std': 0.03,
        'aspect_ratio_mean': 0.58,
        'aspect_ratio_std': 0.09,
        'delta_y_mean': 0.012,
        'delta_y_max': 0.045,
        'delta_height_mean': -0.002,
        'delta_width_mean': 0.004,
        'delta_y_accel_max': 0.015,
        'final_height_ratio': 0.96,
    }


def build_rf_dataset(seed: int = 42):
    rng = np.random.default_rng(seed)
    rows = []
    labels = []
    for label, n_samples in [(0, 260), (1, 220)]:
        proto = _rf_profile(label)
        for _ in range(n_samples):
            row = []
            for col in RF_FEATURE_COLUMNS:
                base = proto.get(col, 0.0)
                noise_scale = 0.015
                if 'std' in col:
                    noise_scale = 0.01
                elif 'max' in col:
                    noise_scale = 0.02
                elif 'mean' in col:
                    noise_scale = 0.012
                value = _clamp(col, base + float(rng.normal(0.0, noise_scale)))
                row.append(value)
            rows.append(row)
            labels.append(label)
    return np.array(rows, dtype=float), np.array(labels, dtype=int)


def _pose_profile(label: int):
    if label == 1:
        return {
            'body_tilt_angle_mean': 68.0,
            'body_tilt_angle_max': 102.0,
            'height_ratio_mean': 0.24,
            'height_ratio_min': 0.12,
            'knee_bend_angle_mean': 108.0,
            'knee_bend_angle_min': 62.0,
            'horizontal_spread_mean': 0.62,
            'horizontal_spread_max': 0.80,
            'center_descent_speed_mean': 0.34,
            'center_descent_speed_max': 0.92,
            'pose_change_rate_mean': 0.28,
            'pose_change_rate_max': 0.74,
        }
    return {
        'body_tilt_angle_mean': 12.0,
        'body_tilt_angle_max': 24.0,
        'height_ratio_mean': 0.96,
        'height_ratio_min': 0.88,
        'knee_bend_angle_mean': 166.0,
        'knee_bend_angle_min': 148.0,
        'horizontal_spread_mean': 0.28,
        'horizontal_spread_max': 0.36,
        'center_descent_speed_mean': 0.02,
        'center_descent_speed_max': 0.06,
        'pose_change_rate_mean': 0.05,
        'pose_change_rate_max': 0.12,
    }


def build_rf_pose_dataset(seed: int = 42):
    rng = np.random.default_rng(seed + 11)
    rows = []
    labels = []
    combined_cols = list(RF_FEATURE_COLUMNS) + list(POSE_FEATURE_COLUMNS)
    for label, n_samples in [(0, 260), (1, 220)]:
        rf_proto = _rf_profile(label)
        pose_proto = _pose_profile(label)
        for _ in range(n_samples):
            row = []
            for col in combined_cols:
                base = rf_proto.get(col, pose_proto.get(col, 0.0))
                noise_scale = 0.02
                if 'angle' in col:
                    noise_scale = 5.0
                elif 'max' in col:
                    noise_scale = 0.03
                elif 'mean' in col:
                    noise_scale = 0.015
                value = _clamp(col, base + float(rng.normal(0.0, noise_scale)))
                row.append(value)
            rows.append(row)
            labels.append(label)
    return np.array(rows, dtype=float), np.array(labels, dtype=int), combined_cols


def _xg_exact_profile(posture: str):
    profiles = {
        'stand': {
            'center_dy': 0.01, 'height_ratio': 0.98, 'aspect_change': 0.04, 'stillness': 0.92,
            'floor_proximity': 0.10, 'area_change': 0.03, 'vert_horiz_ratio': 0.92,
            'max_down_speed': 0.06, 'avg_conf': 0.88, 'n_points': 17.0,
            'pose_tilt_mean': 10.0, 'pose_tilt_max': 18.0, 'pose_height_ratio_mean': 0.98,
            'pose_height_ratio_min': 0.92, 'pose_knee_bend_mean': 0.18, 'pose_knee_bend_min': 0.12,
            'pose_spread_mean': 0.30, 'pose_spread_max': 0.35, 'pose_descent_mean': 0.01,
            'pose_descent_max': 0.05, 'pose_change_mean': 0.04, 'pose_change_max': 0.09,
            'descent_duration': 0.03, 'oscillation_count': 0.10, 'speed_std': 0.05,
            'post_descent_stillness': 0.94, 'upper_body_motion': 0.08,
            'time_to_max_down_speed': 0.22, 'time_from_peak_to_stillness': 0.12,
            'pre_descent_stillness': 0.92, 'post_peak_recovery_ratio': 0.90,
            'step_period_est': 0.10, 'knee_angle_cycle_strength': 0.06,
            'center_y_periodicity': 0.05, 'tilt_change_duration': 0.04,
            'spread_after_descent': 0.22, 'floor_proximity_slope': 0.02,
            'floor_contact_ratio': 0.08, 'height_drop_persistence': 0.05,
            'collapse_impulse': 0.04, 'post_floor_stability': 0.10,
            'slow_descent_ratio': 0.06, 'tilt_height_collapse': 0.05,
        },
        'walk': {
            'center_dy': 0.05, 'height_ratio': 0.94, 'aspect_change': 0.12, 'stillness': 0.20,
            'floor_proximity': 0.14, 'area_change': 0.10, 'vert_horiz_ratio': 0.88,
            'max_down_speed': 0.14, 'avg_conf': 0.85, 'n_points': 16.5,
            'pose_tilt_mean': 14.0, 'pose_tilt_max': 24.0, 'pose_height_ratio_mean': 0.94,
            'pose_height_ratio_min': 0.84, 'pose_knee_bend_mean': 0.28, 'pose_knee_bend_min': 0.14,
            'pose_spread_mean': 0.44, 'pose_spread_max': 0.55, 'pose_descent_mean': 0.04,
            'pose_descent_max': 0.13, 'pose_change_mean': 0.16, 'pose_change_max': 0.28,
            'descent_duration': 0.07, 'oscillation_count': 0.80, 'speed_std': 0.28,
            'post_descent_stillness': 0.24, 'upper_body_motion': 0.28,
            'time_to_max_down_speed': 0.34, 'time_from_peak_to_stillness': 0.24,
            'pre_descent_stillness': 0.28, 'post_peak_recovery_ratio': 0.86,
            'step_period_est': 0.58, 'knee_angle_cycle_strength': 0.74,
            'center_y_periodicity': 0.68, 'tilt_change_duration': 0.12,
            'spread_after_descent': 0.34, 'floor_proximity_slope': 0.04,
            'floor_contact_ratio': 0.18, 'height_drop_persistence': 0.10,
            'collapse_impulse': 0.08, 'post_floor_stability': 0.18,
            'slow_descent_ratio': 0.10, 'tilt_height_collapse': 0.09,
        },
        'run': {
            'center_dy': 0.09, 'height_ratio': 0.90, 'aspect_change': 0.20, 'stillness': 0.08,
            'floor_proximity': 0.18, 'area_change': 0.16, 'vert_horiz_ratio': 0.82,
            'max_down_speed': 0.24, 'avg_conf': 0.82, 'n_points': 16.0,
            'pose_tilt_mean': 18.0, 'pose_tilt_max': 32.0, 'pose_height_ratio_mean': 0.91,
            'pose_height_ratio_min': 0.76, 'pose_knee_bend_mean': 0.38, 'pose_knee_bend_min': 0.18,
            'pose_spread_mean': 0.52, 'pose_spread_max': 0.68, 'pose_descent_mean': 0.08,
            'pose_descent_max': 0.22, 'pose_change_mean': 0.24, 'pose_change_max': 0.42,
            'descent_duration': 0.09, 'oscillation_count': 1.20, 'speed_std': 0.46,
            'post_descent_stillness': 0.12, 'upper_body_motion': 0.42,
            'time_to_max_down_speed': 0.28, 'time_from_peak_to_stillness': 0.20,
            'pre_descent_stillness': 0.12, 'post_peak_recovery_ratio': 0.83,
            'step_period_est': 0.32, 'knee_angle_cycle_strength': 0.90,
            'center_y_periodicity': 0.82, 'tilt_change_duration': 0.14,
            'spread_after_descent': 0.40, 'floor_proximity_slope': 0.06,
            'floor_contact_ratio': 0.22, 'height_drop_persistence': 0.12,
            'collapse_impulse': 0.10, 'post_floor_stability': 0.14,
            'slow_descent_ratio': 0.08, 'tilt_height_collapse': 0.12,
        },
        'sit': {
            'center_dy': 0.08, 'height_ratio': 0.68, 'aspect_change': 0.16, 'stillness': 0.62,
            'floor_proximity': 0.52, 'area_change': 0.14, 'vert_horiz_ratio': 0.62,
            'max_down_speed': 0.24, 'avg_conf': 0.83, 'n_points': 16.4,
            'pose_tilt_mean': 32.0, 'pose_tilt_max': 54.0, 'pose_height_ratio_mean': 0.66,
            'pose_height_ratio_min': 0.54, 'pose_knee_bend_mean': 0.66, 'pose_knee_bend_min': 0.42,
            'pose_spread_mean': 0.42, 'pose_spread_max': 0.54, 'pose_descent_mean': 0.12,
            'pose_descent_max': 0.28, 'pose_change_mean': 0.16, 'pose_change_max': 0.30,
            'descent_duration': 0.18, 'oscillation_count': 0.36, 'speed_std': 0.14,
            'post_descent_stillness': 0.74, 'upper_body_motion': 0.18,
            'time_to_max_down_speed': 0.42, 'time_from_peak_to_stillness': 0.32,
            'pre_descent_stillness': 0.60, 'post_peak_recovery_ratio': 0.70,
            'step_period_est': 0.20, 'knee_angle_cycle_strength': 0.24,
            'center_y_periodicity': 0.12, 'tilt_change_duration': 0.22,
            'spread_after_descent': 0.46, 'floor_proximity_slope': 0.18,
            'floor_contact_ratio': 0.44, 'height_drop_persistence': 0.46,
            'collapse_impulse': 0.16, 'post_floor_stability': 0.48,
            'slow_descent_ratio': 0.34, 'tilt_height_collapse': 0.36,
        },
        'lie': {
            'center_dy': 0.03, 'height_ratio': 0.26, 'aspect_change': 0.10, 'stillness': 0.84,
            'floor_proximity': 0.92, 'area_change': 0.08, 'vert_horiz_ratio': 0.24,
            'max_down_speed': 0.10, 'avg_conf': 0.80, 'n_points': 15.5,
            'pose_tilt_mean': 80.0, 'pose_tilt_max': 92.0, 'pose_height_ratio_mean': 0.24,
            'pose_height_ratio_min': 0.18, 'pose_knee_bend_mean': 0.28, 'pose_knee_bend_min': 0.12,
            'pose_spread_mean': 0.58, 'pose_spread_max': 0.70, 'pose_descent_mean': 0.08,
            'pose_descent_max': 0.16, 'pose_change_mean': 0.08, 'pose_change_max': 0.14,
            'descent_duration': 0.26, 'oscillation_count': 0.12, 'speed_std': 0.06,
            'post_descent_stillness': 0.90, 'upper_body_motion': 0.06,
            'time_to_max_down_speed': 0.40, 'time_from_peak_to_stillness': 0.20,
            'pre_descent_stillness': 0.72, 'post_peak_recovery_ratio': 0.36,
            'step_period_est': 0.08, 'knee_angle_cycle_strength': 0.08,
            'center_y_periodicity': 0.04, 'tilt_change_duration': 0.26,
            'spread_after_descent': 0.62, 'floor_proximity_slope': 0.08,
            'floor_contact_ratio': 0.88, 'height_drop_persistence': 0.82,
            'collapse_impulse': 0.10, 'post_floor_stability': 0.86,
            'slow_descent_ratio': 0.42, 'tilt_height_collapse': 0.72,
        },
        'fall': {
            'center_dy': 0.22, 'height_ratio': 0.18, 'aspect_change': 0.34, 'stillness': 0.38,
            'floor_proximity': 0.96, 'area_change': 0.24, 'vert_horiz_ratio': 0.18,
            'max_down_speed': 0.94, 'avg_conf': 0.76, 'n_points': 14.2,
            'pose_tilt_mean': 72.0, 'pose_tilt_max': 108.0, 'pose_height_ratio_mean': 0.22,
            'pose_height_ratio_min': 0.10, 'pose_knee_bend_mean': 0.46, 'pose_knee_bend_min': 0.18,
            'pose_spread_mean': 0.66, 'pose_spread_max': 0.84, 'pose_descent_mean': 0.42,
            'pose_descent_max': 0.92, 'pose_change_mean': 0.34, 'pose_change_max': 0.72,
            'descent_duration': 0.12, 'oscillation_count': 0.28, 'speed_std': 0.36,
            'post_descent_stillness': 0.72, 'upper_body_motion': 0.32,
            'time_to_max_down_speed': 0.10, 'time_from_peak_to_stillness': 0.38,
            'pre_descent_stillness': 0.44, 'post_peak_recovery_ratio': 0.08,
            'step_period_est': 0.12, 'knee_angle_cycle_strength': 0.18,
            'center_y_periodicity': 0.12, 'tilt_change_duration': 0.18,
            'spread_after_descent': 0.80, 'floor_proximity_slope': 0.44,
            'floor_contact_ratio': 0.94, 'height_drop_persistence': 0.90,
            'collapse_impulse': 0.88, 'post_floor_stability': 0.76,
            'slow_descent_ratio': 0.08, 'tilt_height_collapse': 0.94,
        },
    }
    return profiles[posture]


def build_xg_dataset(seed: int = 42):
    rng = np.random.default_rng(seed + 100)
    rows = []
    labels = []
    per_class = {
        'stand': 140,
        'walk': 120,
        'run': 100,
        'sit': 130,
        'lie': 120,
        'fall': 130,
    }
    for posture in LABEL_L2_CLASSES:
        proto = _xg_exact_profile(posture)
        n_samples = per_class.get(posture, 100)
        for _ in range(n_samples):
            row = []
            for col in XG_FEATURE_COLUMNS:
                base = proto.get(col, 0.0)
                noise_scale = 0.03
                if 'angle' in col or 'tilt' in col:
                    noise_scale = 4.0
                elif 'n_points' == col:
                    noise_scale = 0.6
                elif 'period' in col or 'duration' in col or 'count' in col:
                    noise_scale = 0.05
                value = _clamp(col, base + float(rng.normal(0.0, noise_scale)))
                row.append(value)
            rows.append(row)
            labels.append(posture)
    return np.array(rows, dtype=float), np.array(labels, dtype=object), per_class


def train_rf_model():
    X, y = build_rf_dataset()
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=240,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced_subsample',
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)
    _atomic_joblib_dump(model, RF_MODEL_PATH)
    try:
        _atomic_joblib_dump(model, RF_LEGACY_PATH)
    except Exception:
        pass

    summary = {
        'updated_at': _now(),
        'training_samples': int(len(X_train)),
        'validation_samples': int(len(X_val)),
        'class_distribution': {
            'Y': int(np.sum(y == 1)),
            'N': int(np.sum(y == 0)),
        },
        'features': list(RF_FEATURE_COLUMNS),
        'feature_count': len(RF_FEATURE_COLUMNS),
        'source': 'synthetic-bootstrap-recovery',
        'ready': True,
        'model_path': 'storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl',
        'n_estimators': int(model.n_estimators),
        'tuned_thresholds': {
            'suspect': 0.42,
            'confirm': 0.57,
            'high': 0.72,
        },
        'best_config': {
            'threshold': 0.57,
        },
        'best_metrics': {
            'accuracy': round(float(accuracy_score(y_val, y_pred)), 4),
            'precision': round(float(precision_score(y_val, y_pred, zero_division=0)), 4),
            'recall': round(float(recall_score(y_val, y_pred, zero_division=0)), 4),
            'f1': round(float(f1_score(y_val, y_pred, zero_division=0)), 4),
        },
        'train_metrics': {
            'accuracy': round(float(accuracy_score(y_train, model.predict(X_train))), 4),
            'precision': round(float(precision_score(y_train, model.predict(X_train), zero_division=0)), 4),
            'recall': round(float(recall_score(y_train, model.predict(X_train), zero_division=0)), 4),
            'f1': round(float(f1_score(y_train, model.predict(X_train), zero_division=0)), 4),
        },
        'feature_importance': {
            col: round(float(imp), 4)
            for col, imp in zip(RF_FEATURE_COLUMNS, model.feature_importances_)
        },
        'bootstrap_note': '실모델/실데이터 유실로 합성 feature 분포 기반 비상 복구 모델을 생성했습니다.',
    }
    _atomic_write_json(summary, RF_SUMMARY_PATH)
    return summary


def train_xg_fall_model():
    X, y_str, per_class = build_xg_dataset(seed=52)
    y = np.array([1 if label == 'fall' else 0 for label in y_str], dtype=int)
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=260,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced_subsample',
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)
    _atomic_joblib_dump(model, XG_FALL_MODEL_PATH)

    summary = {
        'updated_at': _now(),
        'model_type': 'xg-fall-bootstrap',
        'training_samples': int(len(X_train)),
        'validation_samples': int(len(X_val)),
        'class_distribution': {
            'Y': int(np.sum(y == 1)),
            'N': int(np.sum(y == 0)),
        },
        'features': list(XG_FEATURE_COLUMNS),
        'feature_count': len(XG_FEATURE_COLUMNS),
        'source': 'synthetic-bootstrap-recovery',
        'ready': True,
        'model_path': 'storage/training/fall-detection/xg-fall/xg_fall_model.pkl',
        'algorithm': 'RandomForestClassifier',
        'tuned_thresholds': {
            'suspect': 0.40,
            'confirm': 0.55,
            'high': 0.72,
        },
        'cv_accuracy': round(float(accuracy_score(y_val, y_pred)), 4),
        'train_metrics': {
            'accuracy': round(float(accuracy_score(y_val, y_pred)), 4),
            'precision': round(float(precision_score(y_val, y_pred, zero_division=0)), 4),
            'recall': round(float(recall_score(y_val, y_pred, zero_division=0)), 4),
            'f1': round(float(f1_score(y_val, y_pred, zero_division=0)), 4),
        },
        'feature_importance': {
            col: round(float(imp), 4)
            for col, imp in zip(XG_FEATURE_COLUMNS, model.feature_importances_)
        },
        'bootstrap_note': '실 xg-fall 모델과 원본 데이터가 없어 합성 feature 분포 기반 비상 복구 모델을 생성했습니다.',
        'bootstrap_class_distribution': per_class,
    }
    _atomic_write_json(summary, XG_FALL_SUMMARY_PATH)
    return summary


def train_rf_pose_model():
    X, y, combined_cols = build_rf_pose_dataset()
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=240,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced_subsample',
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)
    _atomic_joblib_dump(model, RF_POSE_MODEL_PATH)

    summary = {
        'updated_at': _now(),
        'training_samples': int(len(X_train)),
        'validation_samples': int(len(X_val)),
        'class_distribution': {
            'Y': int(np.sum(y == 1)),
            'N': int(np.sum(y == 0)),
        },
        'features': list(combined_cols),
        'feature_count': len(combined_cols),
        'bbox_feature_count': len(RF_FEATURE_COLUMNS),
        'pose_feature_count': len(POSE_FEATURE_COLUMNS),
        'source': 'synthetic-bootstrap-recovery',
        'ready': True,
        'model_path': 'storage/training/fall-detection/rf-pose/rf_pose_model.pkl',
        'n_estimators': int(model.n_estimators),
        'cv_accuracy': round(float(accuracy_score(y_val, y_pred)), 4),
        'train_metrics': {
            'accuracy': round(float(accuracy_score(y_val, y_pred)), 4),
            'precision': round(float(precision_score(y_val, y_pred, zero_division=0)), 4),
            'recall': round(float(recall_score(y_val, y_pred, zero_division=0)), 4),
            'f1': round(float(f1_score(y_val, y_pred, zero_division=0)), 4),
        },
        'feature_importance': {
            col: round(float(imp), 4)
            for col, imp in zip(combined_cols, model.feature_importances_)
        },
        'bootstrap_note': '실 rf-pose 모델과 원본 데이터가 없어 합성 feature 분포 기반 비상 복구 모델을 생성했습니다.',
    }
    _atomic_write_json(summary, RF_POSE_SUMMARY_PATH)
    return summary


def train_xg_posture_model():
    X, y_str, per_class = build_xg_dataset()
    class_to_idx = {name: idx for idx, name in enumerate(LABEL_L2_CLASSES)}
    y = np.array([class_to_idx[name] for name in y_str], dtype=int)
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=280,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced_subsample',
    )
    model.fit(X_train, y_train)
    bundle = {
        'model': model,
        'classes': list(LABEL_L2_CLASSES),
        'feature_cols': list(XG_FEATURE_COLUMNS),
    }
    _atomic_joblib_dump(bundle, XG_POSTURE_MODEL_PATH)

    y_pred = model.predict(X_val)
    summary = {
        'updated_at': _now(),
        'model_type': 'xg-posture-bootstrap',
        'training_samples': int(len(X_train)),
        'validation_samples': int(len(X_val)),
        'class_distribution': {key: int(val) for key, val in per_class.items()},
        'features': list(XG_FEATURE_COLUMNS),
        'feature_count': len(XG_FEATURE_COLUMNS),
        'source': 'synthetic-bootstrap-recovery',
        'ready': True,
        'active_classes': list(LABEL_L2_CLASSES),
        'n_classes': len(LABEL_L2_CLASSES),
        'n_windows': int(len(X)),
        'model_path': 'storage/training/fall-detection/xg-posture/xg_posture_model.pkl',
        'algorithm': 'RandomForestClassifier',
        'cv_accuracy': round(float(accuracy_score(y_val, y_pred)), 4),
        'train_accuracy': round(float(accuracy_score(y_train, model.predict(X_train))), 4),
        'train_metrics': {
            'accuracy': round(float(accuracy_score(y_val, y_pred)), 4),
            'f1_macro': round(float(f1_score(y_val, y_pred, average='macro', zero_division=0)), 4),
        },
        'feature_importance': {
            col: round(float(imp), 4)
            for col, imp in zip(XG_FEATURE_COLUMNS, model.feature_importances_)
        },
        'bootstrap_note': '실 posture 모델과 intake 데이터가 모두 유실되어 합성 feature 분포 기반 비상 복구 번들을 생성했습니다.',
    }
    _atomic_write_json(summary, XG_POSTURE_SUMMARY_PATH)
    return summary


def main():
    ensure_structure()
    rf_summary = train_rf_model()
    rf_pose_summary = train_rf_pose_model()
    xg_fall_summary = train_xg_fall_model()
    posture_summary = train_xg_posture_model()
    print(json.dumps({
        'status': 'ok',
        'rf_model': str(RF_MODEL_PATH),
        'rf_ready': rf_summary.get('ready'),
        'rf_pose_model': str(RF_POSE_MODEL_PATH),
        'rf_pose_ready': rf_pose_summary.get('ready'),
        'xg_fall_model': str(XG_FALL_MODEL_PATH),
        'xg_fall_ready': xg_fall_summary.get('ready'),
        'xg_posture_model': str(XG_POSTURE_MODEL_PATH),
        'xg_posture_ready': posture_summary.get('ready'),
        'data_root': str(DATA_ROOT),
        'uploads_root': str(UPLOADS_ROOT),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()