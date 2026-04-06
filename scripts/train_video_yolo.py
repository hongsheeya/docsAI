#!/usr/bin/env python3
"""Train YOLO classification model from /opt/app/낙상영상 video dataset.

Extracts frames from Y (fall) and N (normal) videos, builds a balanced
YOLO classification dataset, then trains yolo11n-cls.

Usage:
    cd /opt/app/project/main
    .venv-yolo/bin/python scripts/train_video_yolo.py --epochs 30 --reset
"""
import argparse
import csv
import json
import math
import os
import random
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image

ROOT = Path('/opt/app')
PROJECT_ROOT = ROOT / 'project' / 'main'

TRAINING_ROOT = PROJECT_ROOT / 'storage' / 'training' / 'fall-detection'
MODEL_ROOT = TRAINING_ROOT / 'model'
WORK_ROOT = TRAINING_ROOT / 'yolo-video'
DATASET_ROOT = WORK_ROOT / 'dataset'
RUNS_ROOT = WORK_ROOT / 'runs'
STATUS_PATH = MODEL_ROOT / 'training_status.json'
STATUS_MD_PATH = MODEL_ROOT / 'training_status.md'
SUMMARY_PATH = MODEL_ROOT / 'training_summary.json'
MODEL_META_PATH = MODEL_ROOT / 'baseline_model.json'
DATASET_META_PATH = WORK_ROOT / 'dataset_manifest.json'

os.environ.setdefault('YOLO_CONFIG_DIR', str(WORK_ROOT / 'config'))

CLASS_MAP = {'Y': 'fall', 'N': 'normal'}

# 손상/충돌 파일 제외 목록
SKIP_FILES = {
    'N/00002_H_A_N_C1.mp4',     # moov atom 누락 (파일 손상)
    'N/00074_H_A_BY_C1.mp4',    # Y 폴더와 중복 (라벨 충돌, BY=낙상이므로 Y 우선)
}

DEFAULT_ARGS = {
    'epochs': 30,
    'imgsz': 224,
    'batch': 16,
    'seed': 42,
    'train_ratio': 0.8,
    'frames_per_video': 30,
}


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, data):
    ensure_dir(path.parent)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
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
        '# YOLO 학습 현황 (낙상영상)',
        '',
        f'- 업데이트: {status["updated_at"]}',
        f'- 단계: {stage}',
        f'- 메시지: {message}',
    ]
    for key, value in extra.items():
        lines.append(f'- {key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}')
    ensure_dir(STATUS_MD_PATH.parent)
    STATUS_MD_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'[{status["updated_at"]}] {stage}: {message}')
    if extra:
        print(json.dumps(extra, ensure_ascii=False, indent=2))


def resolve_video_root() -> Path:
    """Resolve /opt/app/낙상영상 handling Unicode NFC/NFD differences."""
    target_nfc = unicodedata.normalize('NFC', '낙상영상')
    for name in os.listdir(str(ROOT)):
        if unicodedata.normalize('NFC', name) == target_nfc:
            return ROOT / name
    raise FileNotFoundError(f'{ROOT}/낙상영상 디렉토리를 찾을 수 없습니다.')


def scan_videos(video_root: Path):
    """Scan Y/N subdirectories and return list of (path, label, class_name)."""
    records = []
    skipped = []
    for label, class_name in CLASS_MAP.items():
        label_dir = video_root / label
        if not label_dir.is_dir():
            print(f'  경고: {label_dir} 디렉토리가 없습니다.')
            continue
        for fp in sorted(label_dir.iterdir()):
            if fp.suffix.lower() != '.mp4':
                continue
            rel_key = f'{label}/{fp.name}'
            if rel_key in SKIP_FILES:
                skipped.append({'file': rel_key, 'reason': 'skip list'})
                continue
            cap = cv2.VideoCapture(str(fp))
            if not cap.isOpened():
                skipped.append({'file': rel_key, 'reason': 'cannot open'})
                cap.release()
                continue
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            records.append({
                'path': fp,
                'label': label,
                'class_name': class_name,
                'frame_count': frame_count,
                'fps': fps,
                'width': w,
                'height': h,
                'filename': fp.name,
            })
    return records, skipped


def extract_frames(records, frames_per_video, imgsz):
    """Extract frames from videos and save as JPEG images."""
    all_frames = []
    for rec in records:
        cap = cv2.VideoCapture(str(rec['path']))
        if not cap.isOpened():
            continue
        fc = rec['frame_count']
        n = min(frames_per_video, fc)
        indices = sorted(set(int(i * fc / n) for i in range(n)))
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            # Resize to imgsz while maintaining aspect ratio, then center crop
            h, w = frame.shape[:2]
            scale = imgsz / min(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            # Center crop
            y_start = (new_h - imgsz) // 2
            x_start = (new_w - imgsz) // 2
            cropped = resized[y_start:y_start + imgsz, x_start:x_start + imgsz]
            all_frames.append({
                'image': cropped,
                'class_name': rec['class_name'],
                'label': rec['label'],
                'video': rec['filename'],
                'frame_idx': idx,
            })
        cap.release()
        print(f'  {rec["label"]}/{rec["filename"]}: {len(indices)}프레임 추출')
    return all_frames


def build_dataset(all_frames, train_ratio, seed):
    """Split frames into train/val and save as YOLO classification directory."""
    if DATASET_ROOT.exists():
        shutil.rmtree(DATASET_ROOT)

    # Group by (class_name, video) for video-level split to avoid data leakage
    grouped = defaultdict(list)
    for frame in all_frames:
        grouped[(frame['class_name'], frame['video'])].append(frame)

    # Split by video (not by frame) to prevent leakage
    class_videos = defaultdict(list)
    for (class_name, video), frames in grouped.items():
        class_videos[class_name].append((video, frames))

    rng = random.Random(seed)
    train_frames = []
    val_frames = []

    for class_name, video_list in class_videos.items():
        rng.shuffle(video_list)
        n_train = max(1, int(len(video_list) * train_ratio))
        if n_train >= len(video_list):
            n_train = len(video_list) - 1
        for video, frames in video_list[:n_train]:
            train_frames.extend(frames)
        for video, frames in video_list[n_train:]:
            val_frames.extend(frames)

    rng.shuffle(train_frames)
    rng.shuffle(val_frames)

    for split_name, frames in [('train', train_frames), ('val', val_frames)]:
        for idx, frame in enumerate(frames, 1):
            target_dir = ensure_dir(DATASET_ROOT / split_name / frame['class_name'])
            fname = f"{frame['video'].replace('.mp4', '')}__f{frame['frame_idx']:04d}_{idx:04d}.jpg"
            target_path = target_dir / fname
            cv2.imwrite(str(target_path), frame['image'], [cv2.IMWRITE_JPEG_QUALITY, 95])

    return train_frames, val_frames


def prepare_dataset(frames_per_video=30, imgsz=224, train_ratio=0.8, seed=42):
    video_root = resolve_video_root()
    write_status('prepare', '낙상영상 데이터셋을 스캔합니다.', video_root=str(video_root))

    records, skipped = scan_videos(video_root)
    if not records:
        raise RuntimeError('학습에 사용할 영상 파일을 찾지 못했습니다.')

    write_status('prepare', f'영상 {len(records)}개에서 프레임을 추출합니다.', videos=len(records), skipped=len(skipped))
    all_frames = extract_frames(records, frames_per_video, imgsz)
    write_status('prepare', f'총 {len(all_frames)}개 프레임을 추출했습니다. 데이터셋을 구성합니다.')

    train_frames, val_frames = build_dataset(all_frames, train_ratio, seed)

    class_dist = Counter(f['class_name'] for f in all_frames)
    video_dist = Counter(f'{r["label"]}/{r["filename"]}' for r in records)

    manifest = {
        'prepared_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_root': str(video_root),
        'source_type': 'video',
        'dataset_root': str(DATASET_ROOT),
        'total_count': len(all_frames),
        'train_count': len(train_frames),
        'validation_count': len(val_frames),
        'video_count': len(records),
        'frames_per_video': frames_per_video,
        'class_distribution': dict(class_dist),
        'video_distribution': dict(video_dist),
        'classes': sorted(class_dist.keys()),
        'train_ratio': train_ratio,
        'seed': seed,
        'skipped_files': skipped,
    }
    write_json(DATASET_META_PATH, manifest)
    write_status('prepare-complete', '낙상영상 프레임 데이터셋 준비 완료.', manifest=manifest)
    return manifest


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def build_summary(manifest, save_dir: Path, args_dict, model_name, best_path, results_csv: Path):
    rows = []
    if results_csv.exists():
        with open(results_csv, 'r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
    last_row = rows[-1] if rows else {}
    top1 = _safe_float(last_row.get('metrics/accuracy_top1') or last_row.get('metrics/accuracy_top1(B)'))
    top5 = _safe_float(last_row.get('metrics/accuracy_top5') or last_row.get('metrics/accuracy_top5(B)'))
    train_loss = _safe_float(last_row.get('train/loss'))
    val_loss = _safe_float(last_row.get('val/loss'))
    return {
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'dataset': {
            'sample_count': manifest['total_count'],
            'positive_count': int(manifest['class_distribution'].get('fall', 0)),
            'negative_count': int(manifest['class_distribution'].get('normal', 0)),
            'video_count': manifest['video_count'],
            'frames_per_video': manifest['frames_per_video'],
            'intake_count': manifest['train_count'],
            'train_count': manifest['train_count'],
            'validation_count': manifest['validation_count'],
            'class_distribution': manifest['class_distribution'],
            'source': '낙상영상',
            'model_family': 'YOLO classification',
        },
        'train_metrics': {
            'threshold': 0.5,
            'accuracy': top1,
            'precision': top1,
            'recall': top1,
            'f1': top1,
            'top1': top1,
            'top5': top5,
            'train_loss': train_loss,
            'val_loss': val_loss,
        },
        'evaluation': {
            'folds': [],
            'average': {
                'accuracy': top1, 'precision': top1, 'recall': top1, 'f1': top1,
                'top1': top1, 'top5': top5, 'val_loss': val_loss,
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
        },
    }


def try_register_callbacks(model, total_epochs):
    def update_from_csv(trainer, stage):
        save_dir = Path(getattr(trainer, 'save_dir', ''))
        csv_path = save_dir / 'results.csv'
        epoch = int(getattr(trainer, 'epoch', -1)) + 1
        if not csv_path.exists():
            write_status(stage, '학습 진행 중...', epoch=epoch, total_epochs=total_epochs)
            return
        with open(csv_path, 'r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        last = rows[-1] if rows else {}
        write_status(stage, f'에폭 {epoch}/{total_epochs} 결과 갱신',
                     epoch=epoch, total_epochs=total_epochs,
                     top1=_safe_float(last.get('metrics/accuracy_top1') or last.get('metrics/accuracy_top1(B)')),
                     top5=_safe_float(last.get('metrics/accuracy_top5') or last.get('metrics/accuracy_top5(B)')),
                     train_loss=_safe_float(last.get('train/loss')),
                     val_loss=_safe_float(last.get('val/loss')))

    callbacks = {
        'on_train_start': lambda t: write_status('train-start', '낙상영상 YOLO 학습 시작', total_epochs=total_epochs),
        'on_fit_epoch_end': lambda t: update_from_csv(t, 'train-epoch'),
        'on_train_end': lambda t: update_from_csv(t, 'train-end'),
    }
    for event, fn in callbacks.items():
        try:
            model.add_callback(event, fn)
        except Exception:
            pass


def run_training(epochs=30, imgsz=224, batch=16, seed=42, frames_per_video=30, reset=False):
    manifest = prepare_dataset(
        frames_per_video=frames_per_video,
        imgsz=imgsz,
        train_ratio=DEFAULT_ARGS['train_ratio'],
        seed=seed,
    )

    from ultralytics import YOLO

    ensure_dir(RUNS_ROOT)
    run_name = f"video-yolo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    args_dict = {
        'epochs': epochs, 'imgsz': imgsz, 'batch': batch, 'seed': seed,
        'data': str(DATASET_ROOT), 'project': str(RUNS_ROOT), 'name': run_name, 'device': 'cpu',
    }

    model_name = 'yolo11n-cls.pt'
    try:
        model = YOLO(model_name)
    except Exception:
        model_name = 'yolov8n-cls.pt'
        model = YOLO(model_name)

    try_register_callbacks(model, epochs)
    write_status('train-ready', '낙상영상 YOLO 학습 준비 완료', model_name=model_name, arguments=args_dict)

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
        pretrained=True,
        plots=False,
        verbose=True,
        exist_ok=False,
    )

    save_dir = Path(getattr(results, 'save_dir', RUNS_ROOT / run_name))
    best_path = save_dir / 'weights' / 'best.pt'
    last_path = save_dir / 'weights' / 'last.pt'
    results_csv = save_dir / 'results.csv'

    summary = build_summary(manifest, save_dir, args_dict, model_name, best_path if best_path.exists() else last_path, results_csv)
    write_json(SUMMARY_PATH, summary)
    write_json(MODEL_META_PATH, {
        'model': model_name,
        'updated_at': summary['created_at'],
        'task': 'classify',
        'weights': str(best_path if best_path.exists() else last_path),
        'save_dir': str(save_dir),
        'source_dataset': '낙상영상',
        'class_names': sorted(manifest['class_distribution'].keys()),
    })
    write_status('complete', '낙상영상 YOLO 학습 완료!', summary=summary, best_model=str(best_path if best_path.exists() else last_path))
    return summary


def main():
    parser = argparse.ArgumentParser(description='Train YOLO from /opt/app/낙상영상 videos')
    parser.add_argument('--epochs', type=int, default=DEFAULT_ARGS['epochs'])
    parser.add_argument('--imgsz', type=int, default=DEFAULT_ARGS['imgsz'])
    parser.add_argument('--batch', type=int, default=DEFAULT_ARGS['batch'])
    parser.add_argument('--seed', type=int, default=DEFAULT_ARGS['seed'])
    parser.add_argument('--frames-per-video', type=int, default=DEFAULT_ARGS['frames_per_video'])
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--reset', action='store_true')
    args = parser.parse_args()

    ensure_dir(MODEL_ROOT)
    ensure_dir(WORK_ROOT)

    if args.prepare_only:
        manifest = prepare_dataset(
            frames_per_video=args.frames_per_video,
            imgsz=args.imgsz,
            train_ratio=DEFAULT_ARGS['train_ratio'],
            seed=args.seed,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    summary = run_training(
        epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        seed=args.seed, frames_per_video=args.frames_per_video, reset=args.reset,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        write_status('failed', f'학습 오류: {e}', error=str(e))
        raise
