#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import random
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image


ROOT = Path('/opt/app')
PROJECT_ROOT = ROOT / 'project' / 'main'
SAMPLE_ROOT = ROOT / 'Sample'
IMAGE_ROOT = SAMPLE_ROOT / '01.원천데이터' / '이미지'
LABEL_ROOT = SAMPLE_ROOT / '02.라벨링데이터' / '이미지'

TRAINING_ROOT = PROJECT_ROOT / 'storage' / 'training' / 'fall-detection'
MODEL_ROOT = TRAINING_ROOT / 'model'
WORK_ROOT = TRAINING_ROOT / 'yolo-sample'
DATASET_ROOT = WORK_ROOT / 'dataset'
RUNS_ROOT = WORK_ROOT / 'runs'
STATUS_PATH = MODEL_ROOT / 'training_status.json'
STATUS_MD_PATH = MODEL_ROOT / 'training_status.md'
SUMMARY_PATH = MODEL_ROOT / 'training_summary.json'
MODEL_META_PATH = MODEL_ROOT / 'baseline_model.json'
DATASET_META_PATH = WORK_ROOT / 'dataset_manifest.json'

os.environ.setdefault('YOLO_CONFIG_DIR', str(WORK_ROOT / 'config'))

CLASS_MAP = {
    'N': 'normal',
    'Y': 'fall',
}

DEFAULT_ARGS = {
    'epochs': 20,
    'imgsz': 224,
    'batch': 16,
    'seed': 42,
    'train_ratio': 0.8,
}


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def write_json(path: Path, data):
    ensure_dir(path.parent)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return path


def write_status(stage, message, **extra):
    status = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stage': stage,
        'message': message,
    }
    status.update(extra)
    write_json(STATUS_PATH, status)
    lines = [
        f"# YOLO 학습 현황",
        '',
        f"- 업데이트: {status['updated_at']}",
        f"- 단계: {stage}",
        f"- 메시지: {message}",
    ]
    for key, value in extra.items():
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")
    ensure_dir(STATUS_MD_PATH.parent)
    STATUS_MD_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"[{status['updated_at']}] {stage}: {message}")
    if extra:
        print(json.dumps(extra, ensure_ascii=False, indent=2))


def clamp(value, low, high):
    return max(low, min(high, value))


def parse_bbox(text, width, height):
    parts = [p.strip() for p in str(text).split(',')]
    if len(parts) != 4:
        raise ValueError(f'invalid bbox: {text}')
    x1, y1, x2, y2 = [float(p) for p in parts]
    pad_x = (x2 - x1) * 0.05
    pad_y = (y2 - y1) * 0.05
    left = int(clamp(math.floor(x1 - pad_x), 0, width - 1))
    top = int(clamp(math.floor(y1 - pad_y), 0, height - 1))
    right = int(clamp(math.ceil(x2 + pad_x), left + 1, width))
    bottom = int(clamp(math.ceil(y2 + pad_y), top + 1, height))
    return left, top, right, bottom


def collect_records():
    records = []
    missing = []
    for class_code, class_name in CLASS_MAP.items():
        image_root = IMAGE_ROOT / class_code
        if not image_root.exists():
            continue
        for image_path in image_root.rglob('*'):
            if image_path.suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
                continue
            rel = image_path.relative_to(IMAGE_ROOT)
            label_path = LABEL_ROOT / rel.with_suffix('.json')
            if not label_path.exists() and image_path.suffix != image_path.suffix.lower():
                label_path = LABEL_ROOT / rel.with_suffix('.json')
            if not label_path.exists():
                missing.append(str(rel))
                continue
            label = read_json(label_path, default={}) or {}
            bbox_text = (((label.get('bboxdata') or {}).get('bbox_location')) or '').strip()
            scene_id = ((label.get('metadata') or {}).get('scene_id')) or image_path.parent.name
            subtype = rel.parts[1] if len(rel.parts) > 2 else class_code
            records.append({
                'image_path': image_path,
                'label_path': label_path,
                'class_code': class_code,
                'class_name': class_name,
                'subtype': subtype,
                'scene_id': scene_id,
                'bbox_text': bbox_text,
                'filename': image_path.name,
            })
    if missing:
        write_status('scan-warning', '일부 라벨 파일이 없어 제외했습니다.', missing_count=len(missing), sample_missing=missing[:10])
    if not records:
        raise RuntimeError('학습에 사용할 Sample 이미지/라벨 데이터를 찾지 못했습니다.')
    return records


def split_records(records, train_ratio=0.8, seed=42, balance=True):
    grouped = defaultdict(list)
    for record in records:
        grouped[record['class_name']].append(record)
    rng = random.Random(seed)

    # Balance classes: undersample majority to match minority
    if balance and len(grouped) > 1:
        min_count = min(len(items) for items in grouped.values())
        for class_name in grouped:
            rng.shuffle(grouped[class_name])
            grouped[class_name] = grouped[class_name][:min_count]

    train, val = [], []
    for class_name, items in grouped.items():
        rng.shuffle(items)
        split_index = max(1, int(len(items) * train_ratio))
        if split_index >= len(items):
            split_index = len(items) - 1
        train.extend(items[:split_index])
        val.extend(items[split_index:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def export_records(records, split_name):
    exported = []
    for idx, record in enumerate(records, start=1):
        image_path = Path(record['image_path'])
        target_dir = ensure_dir(DATASET_ROOT / split_name / record['class_name'])
        target_name = f"{record['scene_id']}__{idx:04d}.jpg"
        target_path = target_dir / target_name
        with Image.open(image_path) as image:
            image = image.convert('RGB')
            left, top, right, bottom = parse_bbox(record['bbox_text'], image.width, image.height)
            crop = image.crop((left, top, right, bottom))
            crop.save(target_path, format='JPEG', quality=95)
        exported.append({
            **record,
            'target_path': str(target_path),
            'crop_bbox': [left, top, right, bottom],
        })
    return exported


def prepare_dataset(train_ratio=0.8, seed=42, reset=False, balance=True):
    if reset and DATASET_ROOT.exists():
        shutil.rmtree(DATASET_ROOT)
    ensure_dir(DATASET_ROOT)
    write_status('prepare', 'Sample 데이터셋을 스캔합니다.', sample_root=str(SAMPLE_ROOT))
    records = collect_records()
    train, val = split_records(records, train_ratio=train_ratio, seed=seed, balance=balance)
    write_status('prepare', 'BBox 기준 크롭 데이터를 생성합니다.', total=len(records), train=len(train), val=len(val))
    train_exported = export_records(train, 'train')
    val_exported = export_records(val, 'val')
    class_distribution = Counter(record['class_name'] for record in records)
    subtype_distribution = Counter(record['subtype'] for record in records)
    manifest = {
        'prepared_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_root': str(SAMPLE_ROOT),
        'dataset_root': str(DATASET_ROOT),
        'total_count': len(records),
        'train_count': len(train_exported),
        'validation_count': len(val_exported),
        'class_distribution': dict(class_distribution),
        'subtype_distribution': dict(subtype_distribution),
        'classes': sorted(class_distribution.keys()),
        'train_ratio': train_ratio,
        'seed': seed,
    }
    write_json(DATASET_META_PATH, manifest)
    write_status('prepare-complete', 'YOLO 분류용 데이터셋 준비가 완료되었습니다.', manifest=manifest)
    return manifest


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def build_summary_from_results(manifest, save_dir: Path, args_dict, model_name, best_path, results_csv: Path):
    rows = []
    if results_csv.exists():
        with open(results_csv, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            rows = list(reader)
    last_row = rows[-1] if rows else {}
    top1 = _safe_float(last_row.get('metrics/accuracy_top1') or last_row.get('metrics/accuracy_top1(B)'))
    top5 = _safe_float(last_row.get('metrics/accuracy_top5') or last_row.get('metrics/accuracy_top5(B)'))
    train_loss = _safe_float(last_row.get('train/loss'))
    val_loss = _safe_float(last_row.get('val/loss'))
    summary = {
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'dataset': {
            'sample_count': manifest['total_count'],
            'positive_count': int(manifest['class_distribution'].get('fall', 0)),
            'negative_count': int(manifest['class_distribution'].get('normal', 0)),
            'scene_group_count': len(manifest.get('subtype_distribution', {})),
            'duplicate_total': 0,
            'intake_count': manifest['train_count'],
            'decision_threshold': 0.5,
            'train_count': manifest['train_count'],
            'validation_count': manifest['validation_count'],
            'class_distribution': manifest['class_distribution'],
            'subtype_distribution': manifest['subtype_distribution'],
            'source': 'Sample',
            'model_family': 'YOLO classification',
        },
        'train_metrics': {
            'threshold': 0.5,
            'accuracy': top1,
            'precision': top1,
            'recall': top1,
            'f1': top1,
            'tp': 0,
            'tn': 0,
            'fp': 0,
            'fn': 0,
            'top1': top1,
            'top5': top5,
            'train_loss': train_loss,
            'val_loss': val_loss,
        },
        'evaluation': {
            'folds': [],
            'average': {
                'accuracy': top1,
                'precision': top1,
                'recall': top1,
                'f1': top1,
                'top1': top1,
                'top5': top5,
                'val_loss': val_loss,
            },
        },
        'runtime': {
            'framework': 'ultralytics',
            'task': 'classify',
            'save_dir': str(save_dir),
            'best_model_path': str(best_path) if best_path else '',
            'results_csv': str(results_csv),
            'arguments': args_dict,
            'model_name': model_name,
        }
    }
    return summary


def try_register_callbacks(model, total_epochs):
    def update_from_csv(trainer, stage):
        save_dir = Path(getattr(trainer, 'save_dir', ''))
        csv_path = save_dir / 'results.csv'
        epoch = int(getattr(trainer, 'epoch', -1)) + 1
        if not csv_path.exists():
            write_status(stage, '학습을 진행 중입니다.', epoch=epoch, total_epochs=total_epochs, save_dir=str(save_dir))
            return
        with open(csv_path, 'r', encoding='utf-8') as file:
            rows = list(csv.DictReader(file))
        last_row = rows[-1] if rows else {}
        write_status(
            stage,
            '에폭 학습 결과를 갱신했습니다.',
            epoch=epoch,
            total_epochs=total_epochs,
            top1=_safe_float(last_row.get('metrics/accuracy_top1') or last_row.get('metrics/accuracy_top1(B)')),
            top5=_safe_float(last_row.get('metrics/accuracy_top5') or last_row.get('metrics/accuracy_top5(B)')),
            train_loss=_safe_float(last_row.get('train/loss')),
            val_loss=_safe_float(last_row.get('val/loss')),
            save_dir=str(save_dir),
        )

    callbacks = {
        'on_train_start': lambda trainer: write_status('train-start', 'YOLO 학습을 시작했습니다.', total_epochs=total_epochs, save_dir=str(getattr(trainer, 'save_dir', ''))),
        'on_fit_epoch_end': lambda trainer: update_from_csv(trainer, 'train-epoch'),
        'on_train_end': lambda trainer: update_from_csv(trainer, 'train-end'),
    }
    for event, fn in callbacks.items():
        try:
            model.add_callback(event, fn)
        except Exception:
            pass


def run_training(epochs=20, imgsz=224, batch=16, seed=42, reset=False, balance=True):
    manifest = prepare_dataset(train_ratio=DEFAULT_ARGS['train_ratio'], seed=seed, reset=reset, balance=balance)
    try:
        from ultralytics import YOLO
    except Exception as error:
        write_status('error', 'ultralytics 를 불러오지 못했습니다.', error=str(error))
        raise

    ensure_dir(RUNS_ROOT)
    run_name = f"sample-yolo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    args_dict = {
        'epochs': epochs,
        'imgsz': imgsz,
        'batch': batch,
        'seed': seed,
        'data': str(DATASET_ROOT),
        'project': str(RUNS_ROOT),
        'name': run_name,
        'device': 'cpu',
    }
    model_name_candidates = ['yolo11n-cls.pt', 'yolov8n-cls.pt', 'yolo11n-cls.yaml', 'yolov8n-cls.yaml']
    model = None
    model_name = None
    last_error = None
    for candidate in model_name_candidates:
        try:
            model = YOLO(candidate)
            model_name = candidate
            break
        except Exception as error:
            last_error = error
    if model is None:
        write_status('error', 'YOLO 모델 초기화에 실패했습니다.', error=str(last_error))
        raise RuntimeError(f'YOLO model init failed: {last_error}')

    try_register_callbacks(model, epochs)
    write_status('train-ready', 'YOLO 분류 모델 학습을 준비했습니다.', model_name=model_name, arguments=args_dict, manifest=manifest)
    results = model.train(
        data=str(DATASET_ROOT),
        project=str(RUNS_ROOT),
        name=run_name,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        seed=seed,
        device='cpu',
        workers=0,
        pretrained=True if model_name.endswith('.pt') else False,
        plots=False,
        verbose=True,
        exist_ok=False,
        label_smoothing=0.1,
        flipud=0.3,
        fliplr=0.5,
        erasing=0.2,
        dropout=0.2,
    )
    save_dir = Path(getattr(results, 'save_dir', RUNS_ROOT / run_name))
    best_path = save_dir / 'weights' / 'best.pt'
    last_path = save_dir / 'weights' / 'last.pt'
    results_csv = save_dir / 'results.csv'
    summary = build_summary_from_results(manifest, save_dir, args_dict, model_name, best_path if best_path.exists() else last_path, results_csv)
    write_json(SUMMARY_PATH, summary)
    write_json(MODEL_META_PATH, {
        'model': model_name,
        'updated_at': summary['created_at'],
        'task': 'classify',
        'weights': str(best_path if best_path.exists() else last_path),
        'save_dir': str(save_dir),
        'source_dataset': 'Sample',
        'class_names': sorted(manifest['class_distribution'].keys()),
    })
    write_status('complete', 'YOLO 학습이 완료되었습니다.', summary=summary, best_model=str(best_path if best_path.exists() else last_path))
    return summary


def main():
    parser = argparse.ArgumentParser(description='Train YOLO classification model with /opt/app/Sample dataset')
    parser.add_argument('--epochs', type=int, default=DEFAULT_ARGS['epochs'])
    parser.add_argument('--imgsz', type=int, default=DEFAULT_ARGS['imgsz'])
    parser.add_argument('--batch', type=int, default=DEFAULT_ARGS['batch'])
    parser.add_argument('--seed', type=int, default=DEFAULT_ARGS['seed'])
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--reset', action='store_true')
    parser.add_argument('--no-balance', action='store_true', help='Disable class balancing (undersample)')
    args = parser.parse_args()

    ensure_dir(MODEL_ROOT)
    ensure_dir(WORK_ROOT)
    balance = not args.no_balance
    if args.prepare_only:
        manifest = prepare_dataset(train_ratio=DEFAULT_ARGS['train_ratio'], seed=args.seed, reset=args.reset, balance=balance)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    summary = run_training(epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, seed=args.seed, reset=args.reset, balance=balance)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        write_status('failed', 'YOLO 학습 스크립트 실행 중 오류가 발생했습니다.', error=str(error))
        raise
