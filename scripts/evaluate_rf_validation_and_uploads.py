#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

PROJECT_ROOT = Path('/opt/app/project/main')
DATASET_ROOT = Path('/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/영상')
MODEL_PATH = PROJECT_ROOT / 'storage/training/fall-detection/rf-pipeline/rf_hitl_model.pkl'
SUMMARY_PATH = PROJECT_ROOT / 'storage/training/fall-detection/rf-pipeline/training_summary.json'
FEATURE_CACHE_PATH = PROJECT_ROOT / 'storage/training/fall-detection/rf-pipeline/feature_cache_v3.json'
REPORT_DIR = PROJECT_ROOT / 'storage/training/fall-detection/evaluation'
UPLOAD_DIR = Path('/opt/app/_appdata/data/uploads/fall-detection-prototype')
REPORT_DIR.mkdir(parents=True, exist_ok=True)

RF_V3_FEATURE_COLUMNS = [
    'n_frames',
    'center_y_mean', 'center_y_std',
    'height_mean', 'height_std',
    'width_mean', 'width_std',
    'area_mean', 'area_std',
    'aspect_ratio_mean', 'aspect_ratio_std',
    'delta_y_mean', 'delta_y_max',
    'delta_height_mean', 'delta_width_mean', 'delta_area_mean',
]


def collect_videos(base_dir, subdirs, seed=42):
    import random
    rng = random.Random(seed)
    vids = []
    for subdir in subdirs:
        full = base_dir / subdir
        if not full.is_dir():
            continue
        for p in full.rglob('*.mp4'):
            vids.append(str(p))
    rng.shuffle(vids)
    return vids


def infer_upload_label(name: str):
    upper = name.upper()
    if '_FY_' in upper or '_BY_' in upper or '_SY_' in upper or re.search(r'(^|[_-])Y([_-]|$)', upper):
        return 1
    if '_N_' in upper or re.search(r'(^|[_-])N([_-]|$)', upper):
        return 0
    return None


def load_validation_split(n_train=450, n_val=100, seed=42):
    fall_all = collect_videos(DATASET_ROOT, ['Y/FY', 'Y/BY', 'Y/SY'], seed)
    nonfall_all = collect_videos(DATASET_ROOT, ['N/N'], seed)
    fall_val = fall_all[n_train:n_train + n_val]
    nonfall_val = nonfall_all[n_train:n_train + n_val]
    return fall_val, nonfall_val


def load_feature_df():
    with open(FEATURE_CACHE_PATH, 'r', encoding='utf-8') as f:
        all_feats = json.load(f)
    df = pd.DataFrame(all_feats)
    return df


def build_val_df(df_all, fall_val, nonfall_val):
    val_videos = set(os.path.basename(v) for v in (fall_val + nonfall_val))
    df_val = df_all[df_all['video'].isin(val_videos)].copy()
    X_val = df_val[RF_V3_FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0).values
    y_val = df_val['label'].astype(int).values
    vids = df_val['video'].tolist()
    return df_val, X_val, y_val, vids


def metrics_for_threshold(y_true, y_prob, thr):
    y_pred = (y_prob >= thr).astype(int)
    return {
        'threshold': round(float(thr), 4),
        'accuracy': round(float(accuracy_score(y_true, y_pred)), 4),
        'precision': round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        'recall': round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        'f1': round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        'TP': int(np.sum((y_true == 1) & (y_pred == 1))),
        'TN': int(np.sum((y_true == 0) & (y_pred == 0))),
        'FP': int(np.sum((y_true == 0) & (y_pred == 1))),
        'FN': int(np.sum((y_true == 1) & (y_pred == 0))),
    }


def choose_threshold(sweep, recall_target=0.95):
    eligible = [r for r in sweep if r['recall'] >= recall_target]
    if eligible:
        eligible.sort(key=lambda r: (r['accuracy'], r['f1'], r['precision'], -abs(r['threshold'] - 0.37)), reverse=True)
        return eligible[0]
    sweep = sorted(sweep, key=lambda r: (r['recall'], r['f1'], r['accuracy']), reverse=True)
    return sweep[0]


def list_fp_fn(y_true, y_prob, vids, thr):
    y_pred = (y_prob >= thr).astype(int)
    fps, fns = [], []
    for video, yt, yp, prob in zip(vids, y_true, y_pred, y_prob):
        item = {'video': video, 'true_label': int(yt), 'pred_label': int(yp), 'score': round(float(prob), 4)}
        if yt == 0 and yp == 1:
            fps.append(item)
        elif yt == 1 and yp == 0:
            fns.append(item)
    fps.sort(key=lambda x: x['score'], reverse=True)
    fns.sort(key=lambda x: x['score'])
    return fps, fns


def evaluate_uploads(model, threshold):
    import cv2
    uploads = sorted([p for p in UPLOAD_DIR.glob('*.mp4')])
    # dedupe by filename stem tail after first UUID-ish prefix
    results = []
    for p in uploads:
        name = p.name
        label = infer_upload_label(name)
        results.append({'file': name, 'path': str(p), 'label': label})
    # keep all files, but group in summary
    return results


def main():
    model = joblib.load(MODEL_PATH)
    with open(SUMMARY_PATH, 'r', encoding='utf-8') as f:
        summary = json.load(f)
    current_threshold = float((summary.get('best_config') or {}).get('threshold', 0.37))

    df_all = load_feature_df()
    fall_val, nonfall_val = load_validation_split()
    df_val, X_val, y_val, vids = build_val_df(df_all, fall_val, nonfall_val)

    proba = model.predict_proba(X_val)
    classes = list(model.classes_)
    pos_idx = classes.index(1)
    y_prob = proba[:, pos_idx]

    sweep = [metrics_for_threshold(y_val, y_prob, thr) for thr in np.arange(0.30, 0.451, 0.01)]
    best = choose_threshold(sweep, recall_target=0.95)
    current = next((r for r in sweep if abs(r['threshold'] - current_threshold) < 1e-9), None)
    if current is None:
        current = metrics_for_threshold(y_val, y_prob, current_threshold)

    current_fp, current_fn = list_fp_fn(y_val, y_prob, vids, current_threshold)
    best_fp, best_fn = list_fp_fn(y_val, y_prob, vids, best['threshold'])

    uploads = evaluate_uploads(model, current_threshold)

    report = {
        'model_path': str(MODEL_PATH),
        'summary_path': str(SUMMARY_PATH),
        'current_threshold': current_threshold,
        'validation_sample_size': int(len(y_val)),
        'validation_distribution': {
            'Y': int(np.sum(y_val == 1)),
            'N': int(np.sum(y_val == 0)),
        },
        'threshold_sweep': sweep,
        'current_metrics': current,
        'recommended_threshold': best,
        'current_false_positives': current_fp,
        'current_false_negatives': current_fn,
        'recommended_false_positives': best_fp,
        'recommended_false_negatives': best_fn,
        'uploads_all': uploads,
    }

    out_json = REPORT_DIR / 'rf_validation_eval_20260414.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print('saved', out_json)
    print('current', current)
    print('recommended', best)
    print('current_fp', len(current_fp), 'current_fn', len(current_fn))
    print('recommended_fp', len(best_fp), 'recommended_fn', len(best_fn))


if __name__ == '__main__':
    main()
