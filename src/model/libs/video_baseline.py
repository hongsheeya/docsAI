import csv
import datetime
import importlib.util
import json
import os
import pickle
import sys

if '/opt/app/my_libs' not in sys.path:
    sys.path.insert(0, '/opt/app/my_libs')

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, StratifiedGroupKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except Exception:
    HAS_XGB = False


SUMMARY_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'model', 'training_summary.json')
MODEL_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'model', 'baseline_model.json')
INTAKE_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'intake')
CLASSIFIER_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'fall-classifier')
HITL_REL_PATH = os.path.join('storage', 'training', 'fall-detection', 'hitl-features')
BASE_FEATURE_REL_PATHS = [
    os.path.join('storage', 'training', 'fall-detection', 'fall-features', 'fall_features_all.csv'),
    os.path.join('storage', 'training', 'fall-detection', 'validation-features', 'features_combined.csv'),
]
FEATURE_COLS = [
    'center_dy',
    'height_ratio',
    'aspect_change',
    'stillness',
    'floor_proximity',
    'area_change',
    'vert_horiz_ratio',
    'max_down_speed',
    'avg_conf',
    'n_points',
]


DEFAULT_SUMMARY = {
    'created_at': '',
    'dataset': {
        'sample_count': 0,
        'positive_count': 0,
        'negative_count': 0,
        'scene_group_count': 0,
        'duplicate_total': 0,
        'intake_count': 0,
        'decision_threshold': 0.5,
        'train_count': 0,
        'validation_count': 0,
        'train_ratio': 1.0,
        'validation_ratio': 0.0,
    },
    'train_metrics': {
        'threshold': 0.5,
        'accuracy': 0.0,
        'precision': 0.0,
        'recall': 0.0,
        'f1': 0.0,
        'tp': 0,
        'tn': 0,
        'fp': 0,
        'fn': 0,
    },
    'evaluation': {
        'folds': [],
        'average': {
            'accuracy': 0.0,
            'precision': 0.0,
            'recall': 0.0,
            'f1': 0.0,
            'roc_auc': 0.0,
        }
    }
}


def _path(project_root, rel_path):
    return os.path.join(project_root, rel_path)


def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path


def _resolve_existing_path(path):
    raw = str(path or '').strip()
    if len(raw) == 0:
        return raw
    candidates = [raw]
    if raw.startswith('/mnt/data/wiz/'):
        candidates.append('/opt/app/' + raw[len('/mnt/data/wiz/'):])
    if raw.startswith('/opt/app/'):
        candidates.append('/mnt/data/wiz/' + raw[len('/opt/app/'):])
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return raw


def _load_runtime_module(project_root):
    path = os.path.join(project_root, 'scripts', 'yolo_fall_runtime.py')
    spec = importlib.util.spec_from_file_location('project_yolo_fall_runtime', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('yolo_fall_runtime.py를 로드할 수 없습니다.')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def training_summary(project_root):
    data = read_json(_path(project_root, SUMMARY_REL_PATH), default=None)
    if data is not None:
        return data
    return dict(DEFAULT_SUMMARY)


def _baseline_model_meta(project_root):
    return read_json(_path(project_root, MODEL_REL_PATH), default={}) or {}


def _iter_intake_videos(project_root):
    intake_root = _path(project_root, INTAKE_REL_PATH)
    for label in ['Y', 'N']:
        label_dir = os.path.join(intake_root, label)
        if os.path.isdir(label_dir) is False:
            continue
        for name in sorted(os.listdir(label_dir)):
            if name.startswith('.') or name.endswith('.json'):
                continue
            yield label, os.path.join(label_dir, name), name


def _extract_video_feature_rows(runtime, detector, video_path, video_name, label):
    meta = runtime.video_meta(video_path)
    fps = float(meta.get('fps', 0.0) or 30.0)
    if fps <= 0:
        fps = 30.0
    video_w = int(meta.get('width', 0) or 1)
    video_h = int(meta.get('height', 0) or 1)
    # HITL 재학습은 응답성을 우선하므로 coarse profile로 특징을 추출한다.
    profile = runtime._person_feature_profile(meta, 'fast')
    if runtime._quick_person_presence_check(detector, video_path, meta, profile) is False:
        return []

    track_data = {}
    frame_idx = 0
    vid_stride = int(profile.get('vid_stride', 1) or 1)
    track_imgsz = int(profile.get('track_imgsz', 416) or 416)
    max_duration_sec = float(profile.get('max_duration_sec', 0.0) or 0.0)
    max_source_frame = int(max_duration_sec * fps) if max_duration_sec > 0 and fps > 0 else 0

    for result in detector.track(
        source=video_path,
        stream=True,
        persist=True,
        classes=[0],
        conf=float(profile.get('track_conf', 0.3) or 0.3),
        iou=float(profile.get('track_iou', 0.5) or 0.5),
        tracker='bytetrack.yaml',
        imgsz=track_imgsz,
        verbose=False,
        device='cpu',
        vid_stride=vid_stride,
    ):
        if max_source_frame > 0 and frame_idx > max_source_frame:
            break
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            frame_idx += vid_stride
            continue
        for i in range(len(boxes)):
            track_id_tensor = boxes.id
            if track_id_tensor is None:
                continue
            tid = int(track_id_tensor[i].item())
            if tid < 0:
                continue
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            conf = float(boxes.conf[i].item())
            cx = (x1 + x2) / 2.0 / max(video_w, 1)
            cy = (y1 + y2) / 2.0 / max(video_h, 1)
            w = (x2 - x1) / max(video_w, 1)
            h = (y2 - y1) / max(video_h, 1)
            track_data.setdefault(tid, []).append((frame_idx, cx, cy, w, h, conf))
        frame_idx += vid_stride

    if len(track_data) == 0:
        return []

    window_frames = int(fps * float(profile.get('window_sec', 1.0) or 1.0))
    stride_frames = int(fps * float(profile.get('stride_sec', 0.5) or 0.5))
    if window_frames < 2:
        window_frames = 2
    if stride_frames < 1:
        stride_frames = 1

    rows = []
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
            feats = runtime._compute_window_features(win_points, fps)
            if feats is not None:
                row = {
                    'video': video_name,
                    'label': label,
                    'track_id': tid,
                    'window_start': win_start,
                    'window_end': win_end,
                }
                for key in FEATURE_COLS:
                    row[key] = feats.get(key, 0)
                rows.append(row)
            win_start += stride_frames
    return rows


def _build_intake_features(project_root, force_rebuild=False):
    output_dir = _path(project_root, HITL_REL_PATH)
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, 'intake_features.csv')
    manifest_path = os.path.join(output_dir, 'intake_manifest.json')
    fieldnames = ['video', 'label', 'track_id', 'window_start', 'window_end'] + FEATURE_COLS

    videos = list(_iter_intake_videos(project_root))
    if force_rebuild is False and os.path.exists(csv_path) and os.path.exists(manifest_path):
        manifest = read_json(manifest_path, default={}) or {}
        current_keys = {(label, name) for label, _, name in videos}
        cached_keys = {
            (str(item.get('label', '')), str(item.get('video', '')))
            for item in (manifest.get('processed_videos', []) or []) + (manifest.get('skipped_videos', []) or [])
        }
        if current_keys == cached_keys:
            return {'csv_path': csv_path, 'row_count': int(manifest.get('row_count', 0) or 0), 'video_count': len(videos), 'manifest_path': manifest_path}
        # 신규 영상만 추가된 경우에는 기존 feature csv를 재사용하고 append만 수행한다.
        if cached_keys.issubset(current_keys):
            cached_rows = []
            try:
                with open(csv_path, 'r', encoding='utf-8', newline='') as file:
                    cached_rows = list(csv.DictReader(file))
            except Exception:
                cached_rows = []
            rows = list(cached_rows)
            processed_videos = list(manifest.get('processed_videos', []) or [])
            skipped_videos = list(manifest.get('skipped_videos', []) or [])

            runtime = _load_runtime_module(project_root)
            baseline = _baseline_model_meta(project_root)
            pd_info = baseline.get('person_detector', {}) or {}
            person_weights = _resolve_existing_path(pd_info.get('weights', ''))
            if len(person_weights) == 0 or os.path.exists(person_weights) is False:
                raise RuntimeError('HITL 재학습을 위한 person detector weights를 찾을 수 없습니다.')
            detector = runtime.YOLO(person_weights)

            for label, video_path, name in videos:
                key = (label, name)
                if key in cached_keys:
                    continue
                try:
                    extracted = _extract_video_feature_rows(runtime, detector, video_path, name, label)
                    rows.extend(extracted)
                    processed_videos.append({'video': name, 'label': label, 'rows': len(extracted)})
                except Exception as e:
                    skipped_videos.append({'video': name, 'label': label, 'reason': str(e)})

            with open(csv_path, 'w', encoding='utf-8', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)

            write_json(manifest_path, {
                'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'video_count': len(videos),
                'row_count': len(rows),
                'processed_videos': processed_videos,
                'skipped_videos': skipped_videos,
                'cache_mode': 'incremental',
            })
            return {'csv_path': csv_path, 'row_count': len(rows), 'video_count': len(videos), 'manifest_path': manifest_path}
    if len(videos) == 0:
        write_json(manifest_path, {
            'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'video_count': 0,
            'row_count': 0,
            'processed_videos': [],
            'skipped_videos': [],
        })
        if os.path.exists(csv_path) is False:
            with open(csv_path, 'w', encoding='utf-8', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
        return {'csv_path': csv_path, 'row_count': 0, 'video_count': 0}

    runtime = _load_runtime_module(project_root)
    baseline = _baseline_model_meta(project_root)
    pd_info = baseline.get('person_detector', {}) or {}
    person_weights = _resolve_existing_path(pd_info.get('weights', ''))
    if len(person_weights) == 0 or os.path.exists(person_weights) is False:
        raise RuntimeError('HITL 재학습을 위한 person detector weights를 찾을 수 없습니다.')
    detector = runtime.YOLO(person_weights)

    rows = []
    processed_videos = []
    skipped_videos = []
    for label, video_path, name in videos:
        try:
            extracted = _extract_video_feature_rows(runtime, detector, video_path, name, label)
            rows.extend(extracted)
            processed_videos.append({'video': name, 'label': label, 'rows': len(extracted)})
        except Exception as e:
            skipped_videos.append({'video': name, 'label': label, 'reason': str(e)})

    with open(csv_path, 'w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    write_json(manifest_path, {
        'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'video_count': len(videos),
        'row_count': len(rows),
        'processed_videos': processed_videos,
        'skipped_videos': skipped_videos,
    })
    return {'csv_path': csv_path, 'row_count': len(rows), 'video_count': len(videos), 'manifest_path': manifest_path}


def load_feature_records(project_root, force_rebuild=False):
    frames = []
    for rel_path in BASE_FEATURE_REL_PATHS:
        abs_path = _path(project_root, rel_path)
        if os.path.exists(abs_path):
            frames.append(pd.read_csv(abs_path))
    intake_info = _build_intake_features(project_root, force_rebuild=force_rebuild)
    if intake_info.get('row_count', 0) > 0 and os.path.exists(intake_info.get('csv_path', '')):
        frames.append(pd.read_csv(intake_info['csv_path']))
    if len(frames) == 0:
        return pd.DataFrame(columns=['video', 'label'] + FEATURE_COLS), intake_info
    merged = pd.concat(frames, ignore_index=True, sort=False)
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna(subset=['label'])
    for col in FEATURE_COLS:
        if col not in merged.columns:
            merged[col] = 0.0
    return merged, intake_info


def _get_models():
    models = {
        'LogisticRegression': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', LogisticRegression(max_iter=1000, random_state=42)),
        ]),
        'RandomForest': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)),
        ]),
    }
    if HAS_XGB:
        models['XGBoost'] = Pipeline([
            ('scaler', StandardScaler()),
            ('clf', XGBClassifier(
                max_depth=3,
                n_estimators=300,
                learning_rate=0.05,
                min_child_weight=5,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                eval_metric='logloss',
                tree_method='hist',
                n_jobs=4,
            )),
        ])
    return models


def _evaluate_models(X, y, models, n_splits=5, groups=None):
    if groups is not None:
        cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
    else:
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scoring = {
        'accuracy': 'accuracy',
        'precision': 'precision',
        'recall': 'recall',
        'f1': 'f1',
        'roc_auc': 'roc_auc',
    }
    results = {}
    for name, pipeline in models.items():
        cv_results = cross_validate(pipeline, X, y, cv=cv, scoring=scoring, return_train_score=True, groups=groups)
        results[name] = {}
        for metric_name in scoring:
            vals = cv_results[f'test_{metric_name}']
            train_vals = cv_results.get(f'train_{metric_name}')
            entry = {
                'mean': round(float(np.mean(vals)), 4),
                'std': round(float(np.std(vals)), 4),
                'per_fold': [round(float(v), 4) for v in vals],
            }
            if train_vals is not None:
                entry['train_mean'] = round(float(np.mean(train_vals)), 4)
                entry['train_std'] = round(float(np.std(train_vals)), 4)
            results[name][metric_name] = entry
    return results


def _feature_importance(pipeline):
    clf = pipeline.named_steps['clf']
    if hasattr(clf, 'feature_importances_'):
        imp = clf.feature_importances_
        pairs = sorted([(FEATURE_COLS[i], float(imp[i])) for i in range(len(FEATURE_COLS))], key=lambda item: item[1], reverse=True)
        return {k: round(v, 4) for k, v in pairs[:5]}
    return {}


def train_and_save(project_root, force_rebuild=False):
    summary = training_summary(project_root) or dict(DEFAULT_SUMMARY)
    dataset_df, intake_info = load_feature_records(project_root, force_rebuild=force_rebuild)
    if len(dataset_df) == 0:
        summary['created_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        write_json(_path(project_root, SUMMARY_REL_PATH), summary)
        return {'summary': summary, 'intake': intake_info}

    X = dataset_df[FEATURE_COLS].astype(float).to_numpy()
    y = (dataset_df['label'].astype(str).str.upper() == 'Y').astype(int).to_numpy()
    # Scene-group based CV to prevent data leakage from same-video windows
    groups = None
    if 'video' in dataset_df.columns:
        unique_videos = dataset_df['video'].nunique()
        if unique_videos >= 5:
            groups = dataset_df['video'].values
    models = _get_models()
    n_splits = 3 if X.shape[0] >= 300 else 5
    cv_results = _evaluate_models(X, y, models, n_splits=n_splits, groups=groups)
    best_name = max(cv_results, key=lambda key: cv_results[key]['f1']['mean'])

    output_dir = _path(project_root, CLASSIFIER_REL_PATH)
    os.makedirs(output_dir, exist_ok=True)
    best_pipeline = models[best_name]
    best_pipeline.fit(X, y)
    with open(os.path.join(output_dir, 'best_model.pkl'), 'wb') as file:
        pickle.dump(best_pipeline, file)

    y_pred = best_pipeline.predict(X)
    y_proba = best_pipeline.predict_proba(X)[:, 1]
    cm = confusion_matrix(y, y_pred)
    evaluation = {
        'best_model': best_name,
        'cv_method': ('StratifiedGroupKFold' if groups is not None else 'StratifiedKFold') + f'({n_splits}-fold)',
        'cv_group_column': 'video' if groups is not None else None,
        'dataset': {
            'total_samples': int(X.shape[0]),
            'y_count': int(np.sum(y == 1)),
            'n_count': int(np.sum(y == 0)),
            'unique_videos': int(dataset_df['video'].nunique()) if 'video' in dataset_df.columns else 0,
            'feature_names': FEATURE_COLS,
            'intake_count': int(intake_info.get('row_count', 0)),
            'training_source': 'base+validation+intake',
        },
        'cv_results': cv_results,
        'feature_importance': _feature_importance(best_pipeline),
        'full_data_metrics': {
            'accuracy': round(float(accuracy_score(y, y_pred)), 4),
            'precision': round(float(precision_score(y, y_pred)), 4),
            'recall': round(float(recall_score(y, y_pred)), 4),
            'f1': round(float(f1_score(y, y_pred)), 4),
            'auc_roc': round(float(roc_auc_score(y, y_proba)), 4),
            'confusion_matrix': {
                'TN': int(cm[0][0]),
                'FP': int(cm[0][1]),
                'FN': int(cm[1][0]),
                'TP': int(cm[1][1]),
            },
        },
        'updated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    write_json(os.path.join(output_dir, 'evaluation.json'), evaluation)

    baseline = _baseline_model_meta(project_root)
    fall_classifier = baseline.get('fall_classifier', {}) or {}
    fall_classifier.update({
        'type': best_name,
        'path': 'storage/training/fall-detection/fall-classifier/best_model.pkl',
        'cv_f1': cv_results[best_name]['f1']['mean'],
        'cv_auc': cv_results[best_name]['roc_auc']['mean'],
        'features': FEATURE_COLS,
        'training_source': 'base+validation+intake',
        'training_samples': int(X.shape[0]),
        'training_videos': int(dataset_df['video'].nunique()) if 'video' in dataset_df.columns else 0,
        'updated_at': evaluation['updated_at'],
        'intake_rows': int(intake_info.get('row_count', 0)),
        'intake_videos': int(intake_info.get('video_count', 0)),
    })
    baseline['fall_classifier'] = fall_classifier
    baseline['updated_at'] = evaluation['updated_at']
    write_json(_path(project_root, MODEL_REL_PATH), baseline)

    summary['created_at'] = evaluation['updated_at']
    summary['dataset'] = {
        **(summary.get('dataset', {}) or {}),
        'sample_count': int(X.shape[0]),
        'positive_count': int(np.sum(y == 1)),
        'negative_count': int(np.sum(y == 0)),
        'scene_group_count': int(dataset_df['video'].nunique()) if 'video' in dataset_df.columns else 0,
        'intake_count': int(intake_info.get('row_count', 0)),
        'decision_threshold': float((summary.get('dataset', {}) or {}).get('decision_threshold', 0.5) or 0.5),
        'train_count': int(X.shape[0]),
        'validation_count': 0,
        'train_ratio': 1.0,
        'validation_ratio': 0.0,
        'training_source': 'base+validation+intake',
    }
    summary['train_metrics'] = {
        **(summary.get('train_metrics', {}) or {}),
        'threshold': float((summary.get('train_metrics', {}) or {}).get('threshold', 0.5) or 0.5),
        'accuracy': evaluation['full_data_metrics']['accuracy'],
        'precision': evaluation['full_data_metrics']['precision'],
        'recall': evaluation['full_data_metrics']['recall'],
        'f1': evaluation['full_data_metrics']['f1'],
        'tp': evaluation['full_data_metrics']['confusion_matrix']['TP'],
        'tn': evaluation['full_data_metrics']['confusion_matrix']['TN'],
        'fp': evaluation['full_data_metrics']['confusion_matrix']['FP'],
        'fn': evaluation['full_data_metrics']['confusion_matrix']['FN'],
    }
    summary['evaluation'] = {
        'folds': [],
        'average': {
            'accuracy': cv_results[best_name]['accuracy']['mean'],
            'precision': cv_results[best_name]['precision']['mean'],
            'recall': cv_results[best_name]['recall']['mean'],
            'f1': cv_results[best_name]['f1']['mean'],
            'roc_auc': cv_results[best_name]['roc_auc']['mean'],
        },
    }
    summary['fall_classifier'] = {
        'type': best_name,
        'cv_f1': cv_results[best_name]['f1']['mean'],
        'cv_auc': cv_results[best_name]['roc_auc']['mean'],
        'training_samples': int(X.shape[0]),
        'training_videos': int(dataset_df['video'].nunique()) if 'video' in dataset_df.columns else 0,
        'training_source': 'base+validation+intake',
        'intake_rows': int(intake_info.get('row_count', 0)),
        'intake_videos': int(intake_info.get('video_count', 0)),
        'updated_at': evaluation['updated_at'],
    }
    write_json(_path(project_root, SUMMARY_REL_PATH), summary)
    return {
        'summary': summary,
        'evaluation': evaluation,
        'intake': intake_info,
    }
