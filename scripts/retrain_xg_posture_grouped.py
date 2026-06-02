#!/usr/bin/env python3
import datetime
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = '/opt/app/project/main'
MODULE_PATH = os.path.join(PROJECT_ROOT, 'src', 'model', 'struct', 'video_analysis.py')
REPORT_DIR = Path(PROJECT_ROOT) / 'outputs' / 'model_optimization'
REPORT_PATH = REPORT_DIR / 'xg_posture_grouped_training_report.json'
PROGRESS_PATH = REPORT_DIR / 'xg_posture_grouped_training_progress.log'


class _Fs:
    def abspath(self):
        return PROJECT_ROOT


class _Project:
    def fs(self):
        return _Fs()


class _Wiz:
    project = _Project()


def log(message):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    line = f'[{stamp}] {message}'
    print(line, flush=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with PROGRESS_PATH.open('a', encoding='utf-8') as file:
        file.write(line + '\n')


def load_video_analysis():
    spec = importlib.util.spec_from_file_location('project_video_analysis_grouped', MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load module: {MODULE_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.wiz = _Wiz()
    return module.VideoAnalysis(None)


def infer_group_id(row):
    video = str(row.get('video', '') or '')
    source = str(row.get('source', '') or '')
    if video.startswith('aihub61:'):
        rel = video.split(':', 1)[1]
        parts = [p for p in rel.split('/') if p]
        if len(parts) >= 2:
            return 'aihub61:' + '/'.join(parts[:2])
        if parts:
            return 'aihub61:' + parts[0]
        return 'aihub61:unknown'

    name = os.path.basename(video)
    stem = re.sub(r'\.json$', '', name, flags=re.IGNORECASE)
    stem = re.sub(r'_person\(person\).*$', '', stem)
    match = re.match(r'^(IMG|VID)_(\d+)', stem)
    if match:
        prefix, number = match.group(1), int(match.group(2))
        # AI-Hub 71461 files from the same capture sequence tend to be contiguous.
        # Bucket by hundreds to avoid adjacent frames/person crops crossing folds.
        return f'{source}:{prefix}:{number // 100:06d}'
    return f'{source}:{stem or video}'


def candidate_models(n_classes):
    from sklearn.ensemble import ExtraTreesClassifier
    from xgboost import XGBClassifier

    return {
        'xgb_regularized': XGBClassifier(
            n_estimators=190,
            max_depth=3,
            learning_rate=0.055,
            objective='multi:softprob',
            num_class=n_classes,
            eval_metric='mlogloss',
            random_state=42,
            n_jobs=2,
            min_child_weight=4,
            subsample=0.86,
            colsample_bytree=0.86,
            reg_alpha=0.10,
            reg_lambda=1.9,
        ),
        'xgb_shallow': XGBClassifier(
            n_estimators=220,
            max_depth=2,
            learning_rate=0.050,
            objective='multi:softprob',
            num_class=n_classes,
            eval_metric='mlogloss',
            random_state=7,
            n_jobs=2,
            min_child_weight=3,
            subsample=0.90,
            colsample_bytree=0.90,
            reg_alpha=0.06,
            reg_lambda=1.4,
        ),
        'xgb_conservative': XGBClassifier(
            n_estimators=260,
            max_depth=2,
            learning_rate=0.040,
            objective='multi:softprob',
            num_class=n_classes,
            eval_metric='mlogloss',
            random_state=11,
            n_jobs=2,
            min_child_weight=6,
            subsample=0.92,
            colsample_bytree=0.80,
            reg_alpha=0.16,
            reg_lambda=2.4,
        ),
        'extra_trees': ExtraTreesClassifier(
            n_estimators=260,
            max_depth=None,
            min_samples_leaf=2,
            class_weight='balanced',
            random_state=42,
            n_jobs=2,
        ),
    }


def sync_action_behavior_summary(xg_summary):
    class_order = ['stand', 'walk', 'run', 'sit', 'lie']
    class_dist = {c: int((xg_summary.get('class_distribution') or {}).get(c, 0) or 0) for c in class_order}
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    feature_count = int(xg_summary.get('feature_count') or len(xg_summary.get('features') or []))
    model_name = f'behavior-posture-aihub71461-aihub61-5class-grouped-feature{feature_count}-v3'
    validation = xg_summary.get('group_cv') or {}
    train = xg_summary.get('train_metrics') or {}

    summary = {
        'created_at': now,
        'updated_at': now,
        'model': model_name,
        'model_type': 'behavior-posture-5class',
        'ready_by_rules': False,
        'ready': True,
        'partial_ready': False,
        'multiclass_ready': True,
        'coverage_status': 'full-5class-group-split',
        'dataset': {
            'sample_count': int(xg_summary.get('n_windows') or sum(class_dist.values())),
            'train_count': int(xg_summary.get('training_samples') or sum(class_dist.values())),
            'validation_count': 0,
            'class_distribution': class_dist,
            'train_ratio': 1.0,
            'validation_ratio': 0.0,
            'split_strategy': 'StratifiedGroupKFold by inferred person/video group',
            'label_note': 'AI-Hub 71461 행동 라벨과 AI-Hub 61 기본동작 pose 라벨을 결합한 5-class 행동분류 학습 데이터입니다.',
        },
        'class_distribution': class_dist,
        'class_order': class_order,
        'active_classes': list(xg_summary.get('active_classes') or class_order),
        'missing_classes': [c for c in class_order if class_dist.get(c, 0) <= 0],
        'train_metrics': {
            'accuracy': train.get('accuracy'),
            'macro_f1': train.get('f1_macro'),
            'per_class_recall': train.get('class_recall') or {},
        },
        'validation_metrics': {
            'accuracy': validation.get('accuracy'),
            'macro_f1': validation.get('f1_macro'),
            'per_class_recall': validation.get('class_recall') or {},
            'folds': validation.get('folds'),
            'split_strategy': 'StratifiedGroupKFold',
            'note': '같은 영상/사람 묶음이 train과 validation에 동시에 들어가지 않도록 group split으로 검증했습니다.',
        },
        'confusion_matrix': xg_summary.get('confusion_matrix'),
        'feature_count': feature_count,
        'n_features': feature_count,
        'features': xg_summary.get('features') or [],
        'feature_importance': xg_summary.get('feature_importance') or {},
        'runtime_source': 'rf-dual xg-posture layer',
        'source': 'AI-Hub 71461 labels + AI-Hub 61 basic action pose labels',
        'xg_posture_model_path': xg_summary.get('model_path'),
        'xg_posture_summary_path': '/opt/app/storage/training/fall-detection/xg-posture/training_summary.json',
    }
    behavior_model = {
        'model': model_name,
        'updated_at': now,
        'class_order': class_order,
        'active_classes': summary['active_classes'],
        'missing_classes': summary['missing_classes'],
        'ready': True,
        'partial_ready': False,
        'multiclass_ready': True,
        'source': summary['source'],
        'runtime_source': summary['runtime_source'],
        'feature_count': feature_count,
        'xg_posture_model_path': xg_summary.get('model_path'),
        'xg_posture_summary_path': summary['xg_posture_summary_path'],
        'validation_metrics': summary['validation_metrics'],
        'notes': [
            '낙상 최종 판정은 RF-Dual RF binary 레이어가 담당합니다.',
            '행동분류는 XG-Posture가 stand/walk/run/sit/lie 5-class를 병렬 설명 레이어로 제공합니다.',
            '이번 버전은 StratifiedGroupKFold로 같은 영상/사람 묶음 누수를 줄여 검증했습니다.',
        ],
    }
    for root in [
        Path('/opt/app/storage/training/action-behavior/model'),
        Path('/opt/app/project/main/storage/training/action-behavior/model'),
    ]:
        root.mkdir(parents=True, exist_ok=True)
        (root / 'training_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        (root / 'behavior_model.json').write_text(json.dumps(behavior_model, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
    from sklearn.utils.class_weight import compute_sample_weight

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text('', encoding='utf-8')
    log('load video_analysis and feature definitions')
    va = load_video_analysis()
    feature_cols = [c for c in va._XG_FEATURE_COLUMNS if c != 'n_points']

    # Do not keep classes mechanically identical only because it is convenient.
    # Increase boundary-prone posture classes and rely on balanced sample weights.
    va._EXTERNAL_POSE_CLASS_LIMITS = {
        'stand': 500,
        'walk': 200,
        'sit': 450,
        'lie': 450,
    }
    va._AIHUB61_POSE_CLASS_TARGETS = {
        'walk': 650,
        'run': 650,
        'sit': 650,
        'lie': 650,
    }

    log('load AI-Hub 71461/61 rows and build 64-feature table')
    external = va._load_external_pose_training_rows(feature_cols)
    rows = list(external.get('rows') or [])
    if not rows:
        raise RuntimeError('No behavior rows loaded')

    classes = ['stand', 'walk', 'run', 'sit', 'lie']
    df = pd.DataFrame(rows)
    df = df[df['posture'].isin(classes)].copy()
    df['group_id'] = [infer_group_id(row) for row in df.to_dict('records')]
    class_dist = {c: int((df['posture'] == c).sum()) for c in classes}
    group_counts = df.groupby('posture')['group_id'].nunique().to_dict()
    log(f'loaded rows={len(df)} class_dist={class_dist} group_counts={group_counts}')

    X = df[feature_cols].astype(float).to_numpy()
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df['posture'].map({c: i for i, c in enumerate(classes)}).to_numpy()
    groups = df['group_id'].to_numpy()
    weights = compute_sample_weight(class_weight='balanced', y=y)
    n_splits = min(5, min(class_dist.values()), min(group_counts.values()))
    if n_splits < 3:
        n_splits = 3
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)

    trials = []
    best = None
    log(f'start grouped model comparison n_splits={n_splits} feature_count={len(feature_cols)}')
    for model_name, model in candidate_models(len(classes)).items():
        params = {'sample_weight': weights} if model_name.startswith('xgb') else None
        log(f'evaluate {model_name}')
        if params:
            y_oof = cross_val_predict(model, X, y, cv=cv, groups=groups, params=params, method='predict')
        else:
            y_oof = cross_val_predict(model, X, y, cv=cv, groups=groups, method='predict')
        y_oof = np.asarray(y_oof).flatten().astype(int)
        report = classification_report(y, y_oof, target_names=classes, output_dict=True, zero_division=0)
        recalls = {c: round(float(report[c]['recall']), 4) for c in classes}
        trial = {
            'model': model_name,
            'accuracy': round(float(accuracy_score(y, y_oof)), 4),
            'f1_macro': round(float(f1_score(y, y_oof, average='macro', zero_division=0)), 4),
            'class_recall': recalls,
            'class_precision': {c: round(float(report[c]['precision']), 4) for c in classes},
            'class_f1': {c: round(float(report[c]['f1-score']), 4) for c in classes},
            'confusion_matrix': confusion_matrix(y, y_oof, labels=list(range(len(classes)))).tolist(),
        }
        boundary_score = (recalls.get('walk', 0.0) + recalls.get('run', 0.0) + recalls.get('sit', 0.0) + recalls.get('lie', 0.0)) / 4.0
        trial['_rank'] = (trial['f1_macro'], boundary_score, trial['accuracy'])
        trials.append(trial)
        log(f"{model_name} grouped_macro_f1={trial['f1_macro']} acc={trial['accuracy']} recall={recalls}")
        if best is None or trial['_rank'] > best['_rank']:
            best = trial

    for trial in trials:
        trial.pop('_rank', None)
    best_name = best['model']
    log(f'fit final model={best_name} on all rows')
    final_model = candidate_models(len(classes))[best_name]
    if best_name.startswith('xgb'):
        final_model.fit(X, y, sample_weight=weights)
    else:
        final_model.fit(X, y)

    y_train = np.asarray(final_model.predict(X)).flatten().astype(int)
    train_report = classification_report(y, y_train, target_names=classes, output_dict=True, zero_division=0)
    train_metrics = {
        'accuracy': round(float(accuracy_score(y, y_train)), 4),
        'f1_macro': round(float(f1_score(y, y_train, average='macro', zero_division=0)), 4),
        'class_recall': {c: round(float(train_report[c]['recall']), 4) for c in classes},
    }
    feature_importance = {}
    if hasattr(final_model, 'feature_importances_'):
        feature_importance = {
            col: round(float(imp), 4)
            for col, imp in zip(feature_cols, final_model.feature_importances_)
        }

    model_data = {
        'model': final_model,
        'classes': classes,
        'feature_cols': list(feature_cols),
        'group_split': {
            'strategy': 'StratifiedGroupKFold',
            'n_splits': n_splits,
            'group_source': 'inferred video/person/session id',
        },
    }
    model_path = va._xg_posture_model_path()
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix='.pkl.tmp', dir=os.path.dirname(model_path))
    os.close(fd)
    try:
        joblib.dump(model_data, tmp_path)
        os.replace(tmp_path, model_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    summary = {
        'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'trained_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'model_type': f'xg-posture-grouped-{len(feature_cols)}',
        'ready': True,
        'training_samples': int(len(df)),
        'class_distribution': class_dist,
        'group_distribution': {k: int(v) for k, v in group_counts.items()},
        'features': list(feature_cols),
        'feature_count': len(feature_cols),
        'n_features': len(feature_cols),
        'classes': classes + ['fall'],
        'active_classes': classes,
        'n_classes': len(classes),
        'n_windows': int(len(df)),
        'model_path': model_path,
        'algorithm': best_name,
        'class_balance_strategy': 'boundary-aware sampling + balanced sample weights',
        'group_cv': {
            'folds': n_splits,
            'strategy': 'StratifiedGroupKFold',
            'accuracy': best['accuracy'],
            'f1_macro': best['f1_macro'],
            'class_recall': best['class_recall'],
            'class_precision': best['class_precision'],
            'class_f1': best['class_f1'],
        },
        'cv': {
            'folds': n_splits,
            'strategy': 'StratifiedGroupKFold',
            'accuracy': best['accuracy'],
            'f1_macro': best['f1_macro'],
        },
        'confusion_matrix': {
            'labels': classes,
            'matrix': best['confusion_matrix'],
        },
        'train_metrics': train_metrics,
        'train_accuracy': train_metrics['accuracy'],
        'feature_importance': feature_importance,
        'candidate_trials': trials,
        'external_pose_dataset': {
            'dataset_roots': external.get('dataset_roots', []),
            'class_distribution': external.get('counts', {}),
            'rule_distribution': external.get('rule_distribution', {}),
            'action_distribution': external.get('action_distribution', {}),
            'used_files': external.get('used_files'),
            'scanned_files': external.get('scanned_files'),
            'aihub61_dataset': external.get('aihub61_dataset', {}),
        },
    }
    va._write_json(va._xg_posture_summary_path(), summary)
    sync_action_behavior_summary(summary)

    report = {
        'summary_path': va._xg_posture_summary_path(),
        'model_path': model_path,
        'best': best,
        'class_distribution': class_dist,
        'group_distribution': {k: int(v) for k, v in group_counts.items()},
        'feature_count': len(feature_cols),
        'trials': trials,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f'complete best={best_name} grouped_macro_f1={best["f1_macro"]} report={REPORT_PATH}')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
