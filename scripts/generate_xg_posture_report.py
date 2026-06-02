#!/usr/bin/env python3
import importlib.util
import json
import os
from collections import Counter, defaultdict

import numpy as np
from sklearn.metrics import classification_report


PROJECT_ROOT = '/opt/app/project/main'
MODULE_PATH = os.path.join(PROJECT_ROOT, 'src', 'model', 'struct', 'video_analysis.py')
REPORT_DIR = os.path.join(PROJECT_ROOT, 'storage', 'training', 'fall-detection', 'xg-posture', 'report')
BASELINE_SNAPSHOT = os.path.join(
    PROJECT_ROOT,
    'storage',
    'training',
    'fall-detection',
    'xg-posture',
    'training_summary.pre-expanded-mapping-2026-04-21.json',
)


class _Fs:
    def abspath(self):
        return PROJECT_ROOT


class _Project:
    def fs(self):
        return _Fs()


class _Wiz:
    project = _Project()


def _load_module():
    spec = importlib.util.spec_from_file_location('project_video_analysis', MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load module: {MODULE_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.wiz = _Wiz()
    return module


def _read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(text)


def _collect_training_rows(va, feature_cols):
    rows = []
    intake_root = va._training_dir()
    for cls_name in va._XG_POSTURE_CLASSES:
        cls_dir = os.path.join(intake_root, cls_name)
        if not os.path.isdir(cls_dir):
            continue
        for name in sorted(os.listdir(cls_dir)):
            if name.startswith('.') or name.endswith('.json'):
                continue
            video_path = os.path.join(cls_dir, name)
            try:
                ts = va._extract_unified_timeseries(video_path)
                windows = va._build_xg_feature_windows(
                    ts['timeseries'],
                    ts['vid_meta'],
                    window_sec=1.5,
                    stride_sec=0.5,
                )
                if not windows:
                    continue
                best_w = max(
                    windows,
                    key=lambda w: w.get('oscillation_count', 0)
                    + w.get('speed_std', 0) * 10
                    + w.get('center_y_periodicity', 0),
                )
                row = {'video': name, 'posture': cls_name, 'source': 'video'}
                for col in feature_cols:
                    row[col] = float(best_w.get(col, 0.0) or 0.0)
                rows.append(row)
            except Exception:
                continue
    rows.extend(va._load_external_pose_training_rows(feature_cols).get('rows', []))
    return rows


def _build_action_mapping_overview(va):
    dataset_root = va._external_pose_dataset_root()
    action_totals = Counter()
    mapped_totals = Counter()
    mapped_by_label = defaultdict(Counter)
    if len(dataset_root) == 0:
        return []

    for name in sorted(os.listdir(dataset_root)):
        if not name.endswith('.json'):
            continue
        data = _read_json(os.path.join(dataset_root, name), default={}) or {}
        action_map = {}
        category_map = {}
        for item in data.get('action_categories', []) or []:
            try:
                action_map[int(item.get('id'))] = str(item.get('name', '')).strip().lower()
            except Exception:
                continue
        for item in data.get('Categories', []) or []:
            try:
                category_map[int(item.get('id'))] = str(item.get('name', '')).strip().lower()
            except Exception:
                continue

        target_center = None
        action_infos = []
        for action in data.get('actions', []) or []:
            try:
                action_name = action_map.get(int(action.get('name', -1)), '')
            except Exception:
                action_name = ''
            try:
                object_name = category_map.get(int(action.get('object', -1)), '')
            except Exception:
                object_name = ''
            if len(action_name) == 0:
                continue
            action_totals[action_name] += 1
            action_infos.append({'action': action_name, 'object': object_name})
            boxes_h = list(action.get('boxes_h', []) or [])
            if target_center is None and len(boxes_h) >= 2:
                try:
                    img = ((data.get('images') or [{}])[0])
                    width = float(img.get('width', 0) or 0)
                    height = float(img.get('height', 0) or 0)
                    if width > 0 and height > 0:
                        target_center = (float(boxes_h[0]) / width, float(boxes_h[1]) / height)
                except Exception:
                    target_center = None

        anns = []
        for ann in data.get('annotations', []) or []:
            try:
                if int(ann.get('category_id', -1) or -1) != 1:
                    continue
            except Exception:
                continue
            keypoints = list(ann.get('keypoints', []) or [])
            bbox = list(ann.get('bbox', []) or [])
            if len(keypoints) < 51 or len(bbox) < 4:
                continue
            bx, by, bw, bh = [float(v or 0.0) for v in bbox[:4]]
            anns.append({'annotation': ann, 'cx': bx + bw / 2.0, 'cy': by + bh / 2.0})
        if len(action_infos) == 0 or len(anns) == 0:
            continue

        selected = anns[0]['annotation']
        img = ((data.get('images') or [{}])[0])
        width = float(img.get('width', 0) or 0)
        height = float(img.get('height', 0) or 0)
        if target_center is not None and width > 0 and height > 0:
            selected = min(
                anns,
                key=lambda item: (item['cx'] / width - target_center[0]) ** 2 + (item['cy'] / height - target_center[1]) ** 2,
            )['annotation']

        row = va._build_external_pose_feature_row('external', name, img, selected)
        if row is None:
            continue

        best = None
        for info in action_infos:
            scored = va._score_external_pose_label(info.get('action', ''), info.get('object', ''), row)
            if scored is None:
                continue
            if best is None or float(scored.get('confidence', 0.0) or 0.0) > float(best.get('confidence', 0.0) or 0.0):
                best = {
                    **scored,
                    'action': info.get('action', ''),
                }
        if best is None:
            continue
        mapped_totals[best['action']] += 1
        mapped_by_label[best['action']][best['label']] += 1

    rows = []
    for action_name, total in sorted(action_totals.items(), key=lambda item: (-item[1], item[0])):
        label_counts = dict(sorted(mapped_by_label.get(action_name, {}).items(), key=lambda item: (-item[1], item[0])))
        rows.append({
            'action': action_name,
            'total': int(total),
            'mapped_total': int(mapped_totals.get(action_name, 0)),
            'mapped_labels': label_counts,
            'status': 'mapped' if mapped_totals.get(action_name, 0) > 0 else 'unmapped',
        })
    return rows


def main():
    module = _load_module()
    va = module.VideoAnalysis(None)
    feature_cols = [c for c in va._XG_FEATURE_COLUMNS if c != 'n_points']
    rows = _collect_training_rows(va, feature_cols)
    bundle = va._get_xg_posture_model()
    model = bundle['model']
    classes = list(bundle['classes'])
    filtered = [r for r in rows if r.get('posture') in classes]

    X = np.array([[float(r.get(col, 0.0) or 0.0) for col in feature_cols] for r in filtered], dtype=float)
    y = np.array([classes.index(r['posture']) for r in filtered], dtype=int)
    y_pred = np.asarray(model.predict(X)).flatten().astype(int)
    report = classification_report(y, y_pred, target_names=classes, output_dict=True, zero_division=0)

    baseline = _read_json(BASELINE_SNAPSHOT, default={}) or {}
    summary = va._xg_posture_summary()
    external = summary.get('external_pose_dataset', {}) or {}
    action_overview = _build_action_mapping_overview(va)

    class_metrics = {}
    for cls in classes:
        class_metrics[cls] = {
            'precision': round(float(report[cls]['precision']), 4),
            'recall': round(float(report[cls]['recall']), 4),
            'f1': round(float(report[cls]['f1-score']), 4),
            'support': int(report[cls]['support']),
            'before_support': int((baseline.get('class_distribution', {}) or {}).get(cls, 0) or 0),
            'support_delta': int(report[cls]['support']) - int((baseline.get('class_distribution', {}) or {}).get(cls, 0) or 0),
        }

    report_json = {
        'generated_at': summary.get('trained_at') or summary.get('updated_at'),
        'baseline_snapshot_path': BASELINE_SNAPSHOT,
        'summary_path': va._project_abspath(va._XG_POSTURE_SUMMARY_REL_PATH),
        'overall': {
            'before_cv_accuracy': baseline.get('cv_accuracy'),
            'after_cv_accuracy': summary.get('cv_accuracy'),
            'before_train_accuracy': baseline.get('train_accuracy'),
            'after_train_accuracy': summary.get('train_accuracy'),
            'before_training_samples': baseline.get('training_samples'),
            'after_training_samples': summary.get('training_samples'),
            'macro_precision': round(float(report['macro avg']['precision']), 4),
            'macro_recall': round(float(report['macro avg']['recall']), 4),
            'macro_f1': round(float(report['macro avg']['f1-score']), 4),
            'accuracy': round(float(report['accuracy']), 4),
        },
        'external_mapping': external,
        'class_metrics': class_metrics,
        'action_overview': action_overview,
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    json_path = os.path.join(REPORT_DIR, '2026-04-21-xg-posture-class-action-report.json')
    md_path = os.path.join(REPORT_DIR, '2026-04-21-xg-posture-class-action-report.md')
    _write_json(json_path, report_json)

    lines = []
    lines.append('# XG-Posture 클래스/행동별 학습 리포트')
    lines.append('')
    lines.append(f"- 생성 시각: {report_json['generated_at']}")
    lines.append(f"- 요약 파일: {report_json['summary_path']}")
    lines.append(f"- 기준 스냅샷: {BASELINE_SNAPSHOT}")
    lines.append('')
    lines.append('## 전체 성능 비교')
    lines.append('')
    lines.append('| 항목 | 확장 전 | 확장 후 |')
    lines.append('|---|---:|---:|')
    lines.append(f"| CV accuracy | {baseline.get('cv_accuracy', 0)} | {summary.get('cv_accuracy', 0)} |")
    lines.append(f"| Train accuracy | {baseline.get('train_accuracy', 0)} | {summary.get('train_accuracy', 0)} |")
    lines.append(f"| Training samples | {baseline.get('training_samples', 0)} | {summary.get('training_samples', 0)} |")
    lines.append(f"| Macro precision | - | {report_json['overall']['macro_precision']} |")
    lines.append(f"| Macro recall | - | {report_json['overall']['macro_recall']} |")
    lines.append(f"| Macro F1 | {baseline.get('train_f1_macro', '-') } | {report_json['overall']['macro_f1']} |")
    lines.append('')
    lines.append('## 클래스별 성능')
    lines.append('')
    lines.append('| 클래스 | support(전) | support(후) | delta | precision | recall | f1 |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for cls in classes:
        item = class_metrics[cls]
        lines.append(
            f"| {cls} | {item['before_support']} | {item['support']} | {item['support_delta']} | {item['precision']} | {item['recall']} | {item['f1']} |"
        )
    lines.append('')
    lines.append('## 외부 매핑 선택 결과')
    lines.append('')
    lines.append(f"- 스캔 파일 수: {external.get('scanned_files', 0)}")
    lines.append(f"- 최종 사용 파일 수: {external.get('used_files', 0)}")
    lines.append(f"- 클래스별 사용량: {json.dumps(external.get('class_distribution', {}), ensure_ascii=False)}")
    lines.append(f"- 규칙별 사용량: {json.dumps(external.get('rule_distribution', {}), ensure_ascii=False)}")
    lines.append(f"- 행동별 사용량: {json.dumps(external.get('action_distribution', {}), ensure_ascii=False)}")
    lines.append('')
    lines.append('## 행동별 매핑 현황')
    lines.append('')
    lines.append('| 행동 | 전체 건수 | 매핑 건수 | 상태 | 매핑 라벨 |')
    lines.append('|---|---:|---:|---|---|')
    for item in action_overview:
        mapped_labels = ', '.join(f"{k}:{v}" for k, v in item['mapped_labels'].items()) if item['mapped_labels'] else '-'
        lines.append(f"| {item['action']} | {item['total']} | {item['mapped_total']} | {item['status']} | {mapped_labels} |")
    lines.append('')
    lines.append('## 선택 샘플 예시')
    lines.append('')
    for cls, items in (external.get('selected_examples', {}) or {}).items():
        lines.append(f"### {cls}")
        lines.append('')
        lines.append('| file | action | object | rule | confidence |')
        lines.append('|---|---|---|---|---:|')
        for item in items:
            lines.append(f"| {item.get('file', '')} | {item.get('action', '')} | {item.get('object', '')} | {item.get('rule', '')} | {item.get('confidence', 0)} |")
        lines.append('')
    _write_text(md_path, '\n'.join(lines) + '\n')
    print(json.dumps({'json': json_path, 'markdown': md_path}, ensure_ascii=False))


if __name__ == '__main__':
    main()
