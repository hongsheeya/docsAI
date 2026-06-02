#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path


PROJECT_ROOT = '/opt/app/project/main'
MODULE_PATH = os.path.join(PROJECT_ROOT, 'src', 'model', 'struct', 'video_analysis.py')
OUT_PATH = Path(PROJECT_ROOT) / 'outputs' / 'model_optimization' / 'xg_posture_feature_trials.json'
ROWS_CACHE_PATH = Path(PROJECT_ROOT) / 'outputs' / 'model_optimization' / 'xg_posture_feature_rows_cache.json'


class _Fs:
    def abspath(self):
        return PROJECT_ROOT


class _Project:
    def fs(self):
        return _Fs()


class _Wiz:
    project = _Project()


def load_video_analysis():
    spec = importlib.util.spec_from_file_location('project_video_analysis', MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load module: {MODULE_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.wiz = _Wiz()
    return module.VideoAnalysis(None)


def main():
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import ExtraTreesClassifier
    from sklearn.metrics import accuracy_score, f1_score, classification_report
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.utils.class_weight import compute_sample_weight

    try:
        from xgboost import XGBClassifier
        has_xgb = True
    except Exception:
        XGBClassifier = None
        has_xgb = False

    va = load_video_analysis()

    def unique(seq):
        seen = set()
        result = []
        for item in seq:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    base_cols = [c for c in va._XG_FEATURE_COLUMNS if c != 'n_points']
    candidate_cols = [
        c for c in [
            'center_dx_abs_mean',
            'center_x_span',
            'pose_knee_support_mean',
            'pose_knee_support_min',
            'lower_body_visibility',
            'straight_leg_ratio',
            'support_leg_ratio',
            'bent_leg_ratio',
            'shoulder_width',
            'hip_width',
            'ankle_width',
            'wrist_width',
            'knee_width',
            'foot_y_diff',
            'shoulder_hip_ratio',
            'ankle_hip_ratio',
            'wrist_shoulder_ratio',
            'limb_extension_ratio',
            'body_compactness',
            'knee_asymmetry',
            'elbow_bend_mean',
            'arm_extension_ratio',
        ]
    ]
    feature_sets = {
        'current_runtime_no_npoints': unique(base_cols),
        'runtime_existing_extra': unique(base_cols + candidate_cols[:8]),
        'geometry_extended': unique(base_cols + candidate_cols),
    }

    if ROWS_CACHE_PATH.exists():
        payload = json.loads(ROWS_CACHE_PATH.read_text(encoding='utf-8'))
        rows = payload.get('rows', [])
        external = payload.get('external', {})
    else:
        external = va._load_external_pose_training_rows(feature_sets['geometry_extended'])
        rows = list(external.get('rows', []))
        ROWS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROWS_CACHE_PATH.write_text(json.dumps({'rows': rows, 'external': external}, ensure_ascii=False), encoding='utf-8')
    if not rows:
        raise RuntimeError('No external posture rows were loaded')

    df = pd.DataFrame(rows)
    classes = ['stand', 'walk', 'run', 'sit', 'lie']
    df = df[df['posture'].isin(classes)].copy()
    class_counts = df['posture'].value_counts().to_dict()
    class_to_int = {c: i for i, c in enumerate(classes)}
    y = df['posture'].map(class_to_int).to_numpy()
    n_splits = min(3, min(int((y == i).sum()) for i in range(len(classes))))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    def models(n_classes):
        result = {}
        if has_xgb:
            result['xgb_regularized'] = XGBClassifier(
                n_estimators=160, max_depth=3, learning_rate=0.065,
                objective='multi:softprob', num_class=n_classes,
                eval_metric='mlogloss', random_state=42, n_jobs=2,
                min_child_weight=4, subsample=0.86, colsample_bytree=0.86,
                reg_alpha=0.08, reg_lambda=1.8,
            )
            result['xgb_shallow'] = XGBClassifier(
                n_estimators=180, max_depth=2, learning_rate=0.055,
                objective='multi:softprob', num_class=n_classes,
                eval_metric='mlogloss', random_state=7, n_jobs=2,
                min_child_weight=3, subsample=0.90, colsample_bytree=0.90,
                reg_alpha=0.04, reg_lambda=1.2,
            )
        result['extra_trees'] = ExtraTreesClassifier(
            n_estimators=180, max_depth=None, min_samples_leaf=2,
            class_weight='balanced', random_state=42, n_jobs=2,
        )
        return result

    trials = []
    for set_name, cols in feature_sets.items():
        cols = [c for c in cols if c in df.columns]
        X = df[cols].astype(float).to_numpy()
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        weights = compute_sample_weight(class_weight='balanced', y=y)
        for model_name, model in models(len(classes)).items():
            fit_params = {}
            if model_name.startswith('xgb'):
                fit_params = {'sample_weight': weights}
            if fit_params:
                y_oof = cross_val_predict(model, X, y, cv=cv, params=fit_params, method='predict')
            else:
                y_oof = cross_val_predict(model, X, y, cv=cv, method='predict')
            report = classification_report(y, y_oof, target_names=classes, output_dict=True, zero_division=0)
            trials.append({
                'feature_set': set_name,
                'model': model_name,
                'feature_count': len(cols),
                'oof_accuracy': round(float(accuracy_score(y, y_oof)), 4),
                'oof_f1_macro': round(float(f1_score(y, y_oof, average='macro', zero_division=0)), 4),
                'oof_recall': {cls: round(float(report[cls]['recall']), 4) for cls in classes},
                'features': cols,
            })

    trials.sort(key=lambda item: (item['oof_f1_macro'], item['oof_accuracy']), reverse=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'class_counts': {k: int(v) for k, v in class_counts.items()},
        'n_rows': int(len(df)),
        'n_splits': int(n_splits),
        'trials': trials,
        'best': trials[0] if trials else None,
        'external_dataset': {
            'counts': external.get('counts', {}),
            'used_files': external.get('used_files'),
            'aihub61_dataset': external.get('aihub61_dataset', {}),
        },
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'output': str(OUT_PATH),
        'class_counts': payload['class_counts'],
        'best': payload['best'],
        'top5': trials[:5],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
