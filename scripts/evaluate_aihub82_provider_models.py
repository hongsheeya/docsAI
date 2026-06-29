#!/usr/bin/env python3
"""Evaluate external AI-Hub 82 provider models against local validation rows."""

import argparse
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms


PROJECT = Path('/opt/app/project/main')
TRAIN_SCRIPT = PROJECT / 'scripts' / 'train_facial_emotion_aihub82.py'
EXTERNAL_WORKSPACE = Path('/opt/app/models/external/facialemotion/workspace_layer/workspace')
ACTIVE_MODEL = Path('/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_mobilenetv3.pt')
ACTIVE_SUMMARY = Path('/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_summary.json')
OUT_DIR = PROJECT / 'outputs' / 'facial_aux_validation'

RAW_CLASSES = ['happiness', 'embarrassed', 'anger', 'anxiety', 'hurt', 'sadness', 'neutral']
RAW_TO_FALL_AUX4 = {
    'happiness': 'happiness',
    'embarrassed': 'embarrassed',
    'anger': 'distress',
    'anxiety': 'distress',
    'hurt': 'distress',
    'sadness': 'distress',
    'neutral': 'neutral',
}
DISTRESS_RAW_CLASSES = {'anger', 'anxiety', 'hurt', 'sadness'}
NON_DISTRESS_RAW_CLASSES = {'happiness', 'embarrassed', 'neutral'}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot import {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


train82 = load_module(TRAIN_SCRIPT, 'train_facial_emotion_aihub82_eval')


def build_validation_rows(args):
    train82.configure_label_policy(args.label_policy)
    label_zips, source_zips = train82.find_zips(args.dataset_root)
    labels, label_stats = train82.load_labels(label_zips)
    min_agreement = {
        'train': int(args.train_min_agreement),
        'val': int(args.val_min_agreement),
        'default': 1,
    }
    rows = train82.build_rows(
        source_zips,
        labels,
        args.seed,
        args.max_train_per_class,
        args.max_val_per_class,
        min_agreement=min_agreement,
    )
    train_rows = [r for r in rows if r.get('split') != 'val']
    val_rows = [r for r in rows if r.get('split') == 'val']
    _, val_rows = train82.rebalance_missing_train_classes(train_rows, val_rows, args.seed)
    return val_rows, {
        'label_zips': len(label_zips),
        'source_zips': len(source_zips),
        'label_stats': {f'{k[0]}:{k[1]}': v for k, v in label_stats.items()},
        'val_counts': dict(Counter(r['label'] for r in val_rows)),
    }


class ProviderDataset(Dataset):
    def __init__(self, rows, label_to_idx, transform, crop_pad_ratio):
        self.rows = rows
        self.label_to_idx = label_to_idx
        self.transform = transform
        self.crop_pad_ratio = float(crop_pad_ratio)
        self._zip_cache = {}

    def __len__(self):
        return len(self.rows)

    def _zip(self, path):
        zf = self._zip_cache.get(path)
        if zf is None:
            import zipfile
            zf = zipfile.ZipFile(path)
            self._zip_cache[path] = zf
        return zf

    def _crop_face(self, img, bbox):
        if not bbox:
            return img
        w, h = img.size
        x1, y1, x2, y2 = bbox
        pad_x = (x2 - x1) * self.crop_pad_ratio
        pad_y = (y2 - y1) * self.crop_pad_ratio
        x1 = max(0, int(x1 - pad_x))
        y1 = max(0, int(y1 - pad_y))
        x2 = min(w, int(x2 + pad_x))
        y2 = min(h, int(y2 + pad_y))
        if x2 <= x1 or y2 <= y1 or (x2 - x1) < 16 or (y2 - y1) < 16:
            return img
        return img.crop((x1, y1, x2, y2))

    def __getitem__(self, idx):
        row = self.rows[idx]
        try:
            with self._zip(row['zip_path']).open(row['member']) as fp:
                img = Image.open(fp).convert('RGB')
                img.load()
        except Exception:
            img = Image.new('RGB', (224, 224), (0, 0, 0))
        img = self._crop_face(img, row.get('bbox'))
        return self.transform(img), self.label_to_idx[row['label']]


def metrics_from_confusion(confusion, class_names):
    total = sum(sum(row) for row in confusion)
    correct = sum(confusion[i][i] for i in range(len(confusion)))
    per_class = {}
    f1_values = []
    for i, label in enumerate(class_names):
        tp = confusion[i][i]
        fp = sum(confusion[r][i] for r in range(len(confusion)) if r != i)
        fn = sum(confusion[i][c] for c in range(len(confusion)) if c != i)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        per_class[label] = {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'support': int(sum(confusion[i])),
        }
        f1_values.append(f1)
    if 'distress' in class_names:
        positives = {'distress'}
    else:
        positives = {'anger', 'anxiety', 'hurt', 'sadness'}
    tp = tn = fp = fn = 0
    for ti, row in enumerate(confusion):
        truth_pos = class_names[ti] in positives
        for pi, count in enumerate(row):
            pred_pos = class_names[pi] in positives
            if truth_pos and pred_pos:
                tp += count
            elif truth_pos:
                fn += count
            elif pred_pos:
                fp += count
            else:
                tn += count
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return {
        'accuracy': round(correct / max(total, 1), 4),
        'macro_f1': round(sum(f1_values) / max(len(f1_values), 1), 4),
        'per_class': per_class,
        'confusion_matrix': confusion,
        'distress_binary': {
            'positive_labels': sorted(positives),
            'accuracy': round((tp + tn) / max(total, 1), 4),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'tp': int(tp),
            'tn': int(tn),
            'fp': int(fp),
            'fn': int(fn),
        },
    }


def load_external_model(model_name, model_path):
    old_path = list(sys.path)
    try:
        if str(EXTERNAL_WORKSPACE) not in sys.path:
            sys.path.insert(0, str(EXTERNAL_WORKSPACE))
        train = load_module(EXTERNAL_WORKSPACE / 'train.py', f'external_aihub82_{model_name.replace("-", "_")}')
        model = train.getModel(model_name)
        ckpt = torch.load(model_path, map_location='cpu')
        state = ckpt.get('model', ckpt) if isinstance(ckpt, dict) else ckpt
        model.load_state_dict(state)
        model.eval()
        return model
    finally:
        sys.path = old_path


def load_internal_model(model_path):
    ckpt = torch.load(model_path, map_location='cpu')
    class_names = list(ckpt.get('class_names') or [])
    model_type = ckpt.get('model_type', 'mobilenet_v3_small')
    model = train82.make_model(len(class_names), pretrained=False, model_type=model_type)
    model.load_state_dict(ckpt['state_dict'])
    model.eval()
    return model, class_names, int(ckpt.get('image_size') or 128), float(ckpt.get('crop_pad_ratio') or 0.18)


def evaluate_internal(rows, args, device):
    model, class_names, image_size, crop_pad_ratio = load_internal_model(args.internal_model)
    model.to(device)
    label_to_idx = {label: idx for idx, label in enumerate(class_names)}
    ds = train82.ZipFaceDataset(rows, label_to_idx, image_size, train=False, crop_pad_ratio=crop_pad_ratio, augment_strength='none')
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=False, num_workers=0)
    confusion = [[0 for _ in class_names] for _ in class_names]
    with torch.no_grad():
        for x, y in loader:
            logits = model(x.to(device))
            pred = logits.argmax(dim=1).cpu().tolist()
            for truth, guess in zip(y.view(-1).tolist(), pred):
                confusion[int(truth)][int(guess)] += 1
    return metrics_from_confusion(confusion, class_names)


def evaluate_external(rows, args, device, provider):
    if provider == 'emotionnet':
        model_name = 'emotionnet'
        model_path = EXTERNAL_WORKSPACE / 'model.pth'
        image_size = 48
        channels = 1
        batch_size = args.batch_size
    else:
        model_name = 'efficientnet-b5'
        model_path = EXTERNAL_WORKSPACE / 'model_eff.pth'
        image_size = 224
        channels = 3
        batch_size = max(1, min(args.batch_size, args.efficientnet_batch_size))
    model = load_external_model(model_name, model_path).to(device)
    transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=channels),
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
    ])
    class_names = list(train82.CLASS_NAMES)
    label_to_idx = {label: idx for idx, label in enumerate(class_names)}
    ds = ProviderDataset(rows, label_to_idx, transform, args.crop_pad_ratio)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=0)
    confusion = [[0 for _ in class_names] for _ in class_names]
    raw_confusion = [[0 for _ in RAW_CLASSES] for _ in RAW_CLASSES] if class_names == RAW_CLASSES else None
    with torch.no_grad():
        for x, y in loader:
            logits = model(x.to(device))
            probs = torch.softmax(logits, dim=1).cpu()
            if class_names == RAW_CLASSES:
                pred = probs.argmax(dim=1).tolist()
            else:
                grouped = []
                for label in class_names:
                    if label == 'distress':
                        raw_labels = DISTRESS_RAW_CLASSES
                    elif label == 'non_distress':
                        raw_labels = NON_DISTRESS_RAW_CLASSES
                    elif label == 'neutral' and 'distress' in class_names and len(class_names) == 2:
                        raw_labels = NON_DISTRESS_RAW_CLASSES
                    else:
                        raw_labels = {raw for raw in RAW_CLASSES if RAW_TO_FALL_AUX4.get(raw) == label}
                    idxs = [i for i, raw in enumerate(RAW_CLASSES) if raw in raw_labels]
                    grouped.append(probs[:, idxs].sum(dim=1))
                pred = torch.stack(grouped, dim=1).argmax(dim=1).tolist()
            raw_pred = probs.argmax(dim=1).tolist()
            for idx, (truth, guess) in enumerate(zip(y.view(-1).tolist(), pred)):
                confusion[int(truth)][int(guess)] += 1
                if raw_confusion is not None:
                    raw_confusion[int(truth)][int(raw_pred[idx])] += 1
    result = metrics_from_confusion(confusion, class_names)
    result['model_path'] = str(model_path)
    result['provider'] = provider
    result['grouping'] = 'sum raw 7-class probabilities into fall_aux4 labels' if class_names != RAW_CLASSES else 'raw 7-class argmax'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-root', default='/opt/app/datasets/facial_state/aihub_82_korean_emotion')
    parser.add_argument('--label-policy', choices=sorted(train82.LABEL_POLICY_CONFIGS), default='fall_aux4')
    parser.add_argument('--seed', type=int, default=2026060401)
    parser.add_argument('--max-train-per-class', type=int, default=2600)
    parser.add_argument('--max-val-per-class', type=int, default=700)
    parser.add_argument('--train-min-agreement', type=int, default=2)
    parser.add_argument('--val-min-agreement', type=int, default=3)
    parser.add_argument('--crop-pad-ratio', type=float, default=0.18)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--efficientnet-batch-size', type=int, default=12)
    parser.add_argument('--providers', default='internal,emotionnet,efficientnet-b5')
    parser.add_argument('--internal-model', default=str(ACTIVE_MODEL))
    parser.add_argument('--output', default='')
    args = parser.parse_args()

    try:
        torch.set_num_threads(max(1, int(os.environ.get('TORCH_NUM_THREADS', '1') or 1)))
    except Exception:
        pass

    started = time.time()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    rows, dataset_info = build_validation_rows(args)
    results = {
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'device': device.type,
        'dataset_root': args.dataset_root,
        'label_policy': args.label_policy,
        'seed': args.seed,
        'max_val_per_class': args.max_val_per_class,
        'min_agreement': {'train': args.train_min_agreement, 'val': args.val_min_agreement},
        'crop_pad_ratio': args.crop_pad_ratio,
        'validation_rows': len(rows),
        'dataset_info': dataset_info,
        'models': {},
    }
    providers = [p.strip().lower() for p in args.providers.split(',') if p.strip()]
    for provider in providers:
        print(f'[eval] start provider={provider}', flush=True)
        t0 = time.time()
        if provider == 'internal':
            metrics = evaluate_internal(rows, args, device)
            metrics['model_path'] = str(args.internal_model)
            metrics['provider'] = 'internal_mobilenetv3'
        elif provider in ('emotionnet', 'external-emotionnet'):
            metrics = evaluate_external(rows, args, device, 'emotionnet')
        elif provider in ('efficientnet', 'efficientnet-b5', 'external-efficientnet-b5'):
            metrics = evaluate_external(rows, args, device, 'efficientnet-b5')
        else:
            raise SystemExit(f'Unknown provider: {provider}')
        metrics['elapsed_sec'] = round(time.time() - t0, 2)
        results['models'][provider] = metrics
        print(
            f"[eval] done provider={provider} acc={metrics['accuracy']:.4f} "
            f"macro_f1={metrics['macro_f1']:.4f} distress_f1={metrics['distress_binary']['f1']:.4f} "
            f"elapsed_sec={metrics['elapsed_sec']}",
            flush=True,
        )
    results['elapsed_sec'] = round(time.time() - started, 2)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output = Path(args.output) if args.output else OUT_DIR / f"aihub82_provider_compare_{args.label_policy}_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.json"
    with open(output, 'w', encoding='utf-8') as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)
    print(f'[output] {output}', flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
