#!/usr/bin/env python3
"""Train a lightweight facial-state classifier from AI-Hub dataset 82.

The script reads AI-Hub label/source zip files in-place, crops the annotated
face region, and trains a 7-class Korean facial emotion model. It is designed
to run after the large AI-Hub downloads finish, without moving dataset files
into the project tree.
"""

import argparse
import hashlib
import io
import json
import math
import os
import random
import re
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image, ImageFile
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

try:
    _torch_threads = int(os.environ.get('TORCH_NUM_THREADS', '0') or 0)
    if _torch_threads > 0:
        torch.set_num_threads(_torch_threads)
except Exception:
    pass


CLASS_NAMES = ['happiness', 'embarrassed', 'anger', 'anxiety', 'hurt', 'sadness', 'neutral']
KOR_TO_CLASS = {
    '기쁨': 'happiness',
    '당황': 'embarrassed',
    '분노': 'anger',
    '불안': 'anxiety',
    '상처': 'hurt',
    '슬픔': 'sadness',
    '중립': 'neutral',
}
CLASS_TO_KOR = {v: k for k, v in KOR_TO_CLASS.items()}
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
ImageFile.LOAD_TRUNCATED_IMAGES = True


def stable_key(value):
    return hashlib.sha1(str(value).encode('utf-8')).hexdigest()


def filename_match_keys(filename):
    """Return robust keys for matching AI-Hub labels to mojibake zip members."""
    base = os.path.basename(str(filename or ''))
    keys = [base]
    parts = base.split('_')
    match = re.search(r'([0-9]{14}-[0-9]+-[0-9]+)\.[A-Za-z0-9]+$', base)
    if match and parts:
        keys.append(f'{parts[0]}:{match.group(1)}')
        keys.append(match.group(1))
    if parts:
        keys.append(parts[0])
    return [key for key in keys if key]


def infer_split(path):
    text = str(path)
    upper = text.upper()
    if 'VALID' in upper or 'VALIDATION' in upper or '2.Validation' in text:
        return 'val'
    return 'train'


def find_zips(root):
    root = Path(root)
    label_zips = []
    source_zips = []
    for path in root.rglob('*.zip'):
        text = str(path)
        if '라벨링데이터' in text:
            label_zips.append(path)
        elif '원천데이터' in text:
            source_zips.append(path)
    return sorted(label_zips), sorted(source_zips)


def average_box(entry):
    boxes = []
    for key in ['annot_A', 'annot_B', 'annot_C']:
        box = ((entry or {}).get(key) or {}).get('boxes') or {}
        try:
            x1 = float(box.get('minX'))
            y1 = float(box.get('minY'))
            x2 = float(box.get('maxX'))
            y2 = float(box.get('maxY'))
            if all(math.isfinite(v) for v in [x1, y1, x2, y2]) and x2 > x1 and y2 > y1:
                boxes.append((x1, y1, x2, y2))
        except Exception:
            pass
    if not boxes:
        return None
    return [sum(box[i] for box in boxes) / len(boxes) for i in range(4)]


def choose_label(entry):
    info = choose_label_info(entry)
    return info['label'] if info else None


def choose_label_info(entry):
    votes = []
    uploader = (entry or {}).get('faceExp_uploader')
    if uploader:
        votes.append(uploader)
    for key in ['annot_A', 'annot_B', 'annot_C']:
        value = ((entry or {}).get(key) or {}).get('faceExp')
        if value:
            votes.append(value)
    mapped = [KOR_TO_CLASS[v] for v in votes if v in KOR_TO_CLASS]
    if not mapped:
        return None
    counts = Counter(mapped)
    label, count = counts.most_common(1)[0]
    uploader_class = KOR_TO_CLASS.get(uploader)
    if count >= 2:
        selected = label
    else:
        selected = uploader_class or label
    return {
        'label': selected,
        'agreement': int(count),
        'votes_total': int(len(mapped)),
        'vote_counts': dict(counts),
    }


def load_labels(label_zips):
    labels = {}
    labels_by_key = {}
    stats = Counter()
    for zpath in label_zips:
        split = infer_split(zpath)
        try:
            with zipfile.ZipFile(zpath) as zf:
                json_names = [n for n in zf.namelist() if n.lower().endswith('.json')]
                for name in json_names:
                    with zf.open(name) as fp:
                        records = json.load(fp)
                    for entry in records:
                        filename = entry.get('filename')
                        label_info = choose_label_info(entry)
                        label = (label_info or {}).get('label')
                        if not filename or label not in CLASS_NAMES:
                            continue
                        labels[os.path.basename(filename)] = {
                            'label': label,
                            'agreement': int(label_info.get('agreement', 0)),
                            'votes_total': int(label_info.get('votes_total', 0)),
                            'vote_counts': label_info.get('vote_counts') or {},
                            'bbox': average_box(entry),
                            'split': split,
                            'age': entry.get('age'),
                            'gender': entry.get('gender'),
                        }
                        for key in filename_match_keys(filename):
                            labels_by_key.setdefault(key, labels[os.path.basename(filename)])
                        stats[(split, label)] += 1
        except Exception as exc:
            print(f'[labels] skip {zpath}: {exc}', flush=True)
    return labels_by_key, stats


def build_rows(source_zips, labels, seed, max_train_per_class, max_val_per_class, min_agreement=1):
    rows_by_split_class = defaultdict(list)
    skipped_low_agreement = Counter()
    for zpath in source_zips:
        split_hint = infer_split(zpath)
        try:
            with zipfile.ZipFile(zpath) as zf:
                for member in zf.namelist():
                    if not member.lower().endswith(IMAGE_EXTS):
                        continue
                    meta = None
                    for key in filename_match_keys(member)[:-1]:
                        meta = labels.get(key)
                        if meta:
                            break
                    if not meta:
                        continue
                    split = meta.get('split') or split_hint
                    label = meta.get('label')
                    if label not in CLASS_NAMES:
                        continue
                    agreement = int(meta.get('agreement') or 0)
                    if isinstance(min_agreement, dict):
                        required_agreement = int(min_agreement.get(split, min_agreement.get('default', 1)))
                    else:
                        required_agreement = int(min_agreement)
                    if agreement < required_agreement:
                        skipped_low_agreement[(split, label)] += 1
                        continue
                    rows_by_split_class[(split, label)].append({
                        'zip_path': str(zpath),
                        'member': member,
                        'label': label,
                        'split': split,
                        'agreement': agreement,
                        'votes_total': int(meta.get('votes_total') or 0),
                        'bbox': meta.get('bbox'),
                        'filename': os.path.basename(member),
                    })
        except Exception as exc:
            print(f'[source] skip {zpath}: {exc}', flush=True)
    if skipped_low_agreement:
        print(f'[filter] min_agreement={min_agreement} skipped_low_agreement={dict(skipped_low_agreement)}', flush=True)

    rng = random.Random(seed)
    rows = []
    for split in ['train', 'val']:
        cap = max_train_per_class if split == 'train' else max_val_per_class
        for label in CLASS_NAMES:
            group = rows_by_split_class.get((split, label), [])
            group = sorted(group, key=lambda r: stable_key(r['filename']))
            rng.shuffle(group)
            if cap and cap > 0:
                group = group[:cap]
            rows.extend(group)
    return rows


def rebalance_missing_train_classes(train_rows, val_rows, seed):
    """Use validation rows as train fallback when a downloaded train source is corrupt."""
    rng = random.Random(seed)
    by_val_label = defaultdict(list)
    for row in val_rows:
        by_val_label[row['label']].append(row)
    train_labels = {row['label'] for row in train_rows}
    moved = []
    kept_val = []
    for label in CLASS_NAMES:
        candidates = by_val_label.get(label, [])
        if label in train_labels or not candidates:
            continue
        candidates = candidates[:]
        rng.shuffle(candidates)
        n_move = max(1, int(len(candidates) * 0.8))
        for row in candidates[:n_move]:
            clone = dict(row)
            clone['split'] = 'train'
            clone['source_split'] = 'val_fallback_for_missing_train_source'
            moved.append(clone)
        by_val_label[label] = candidates[n_move:]
        print(f'[split] moved {len(moved)} validation rows into train fallback for missing train class: {label}', flush=True)
    moved_ids = {(row['zip_path'], row['member'], row['label']) for row in moved}
    for row in val_rows:
        if (row['zip_path'], row['member'], row['label']) in moved_ids:
            continue
        if by_val_label.get(row['label']) is not None and row in by_val_label[row['label']]:
            kept_val.append(row)
        elif row['label'] in train_labels:
            kept_val.append(row)
    return train_rows + moved, kept_val


class ZipFaceDataset(Dataset):
    def __init__(self, rows, class_to_idx, image_size, train):
        self.rows = rows
        self.class_to_idx = class_to_idx
        self._zip_cache = {}
        if train:
            self.transform = transforms.Compose([
                transforms.Resize((image_size, image_size)),
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.10),
                transforms.RandomAffine(degrees=8, translate=(0.04, 0.04), scale=(0.92, 1.08)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
        else:
            self.transform = transforms.Compose([
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

    def __len__(self):
        return len(self.rows)

    def _zip(self, path):
        zf = self._zip_cache.get(path)
        if zf is None:
            zf = zipfile.ZipFile(path)
            self._zip_cache[path] = zf
        return zf

    def _crop_face(self, img, bbox):
        if not bbox:
            return img
        w, h = img.size
        x1, y1, x2, y2 = bbox
        pad_x = (x2 - x1) * 0.14
        pad_y = (y2 - y1) * 0.14
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
                img = Image.open(io.BytesIO(fp.read())).convert('RGB')
        except Exception:
            img = Image.new('RGB', (self.transform.transforms[0].size[0], self.transform.transforms[0].size[1]), (0, 0, 0))
        img = self._crop_face(img, row.get('bbox'))
        return self.transform(img), self.class_to_idx[row['label']]


def make_model(num_classes, pretrained=True, model_type='mobilenet_v3_small'):
    weights = None
    model_type = str(model_type or 'mobilenet_v3_small').strip().lower()
    if pretrained:
        try:
            if model_type == 'mobilenet_v3_large':
                weights = models.MobileNet_V3_Large_Weights.DEFAULT
            else:
                weights = models.MobileNet_V3_Small_Weights.DEFAULT
        except Exception:
            weights = None
    try:
        if model_type == 'mobilenet_v3_large':
            model = models.mobilenet_v3_large(weights=weights)
        else:
            model = models.mobilenet_v3_small(weights=weights)
    except Exception as exc:
        print(f'[model] pretrained load failed, using random init: {exc}', flush=True)
        if model_type == 'mobilenet_v3_large':
            model = models.mobilenet_v3_large(weights=None)
        else:
            model = models.mobilenet_v3_small(weights=None)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model


def metrics_from_confusion(confusion):
    total = sum(sum(row) for row in confusion)
    correct = sum(confusion[i][i] for i in range(len(confusion)))
    per_class = {}
    f1_values = []
    for i, label in enumerate(CLASS_NAMES):
        tp = confusion[i][i]
        fp = sum(confusion[r][i] for r in range(len(confusion)) if r != i)
        fn = sum(confusion[i][c] for c in range(len(confusion)) if c != i)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = (2 * precision * recall) / max(precision + recall, 1e-9)
        per_class[label] = {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'support': int(sum(confusion[i])),
        }
        f1_values.append(f1)
    distress_labels = {'anger', 'anxiety', 'hurt', 'sadness'}
    tp = tn = fp = fn = 0
    for truth_idx, row in enumerate(confusion):
        truth_positive = CLASS_NAMES[truth_idx] in distress_labels
        for pred_idx, count in enumerate(row):
            pred_positive = CLASS_NAMES[pred_idx] in distress_labels
            if truth_positive and pred_positive:
                tp += count
            elif truth_positive and not pred_positive:
                fn += count
            elif not truth_positive and pred_positive:
                fp += count
            else:
                tn += count
    distress_precision = tp / max(tp + fp, 1)
    distress_recall = tp / max(tp + fn, 1)
    distress_f1 = (2 * distress_precision * distress_recall) / max(distress_precision + distress_recall, 1e-9)
    return {
        'accuracy': round(correct / max(total, 1), 4),
        'macro_f1': round(sum(f1_values) / max(len(f1_values), 1), 4),
        'per_class': per_class,
        'confusion_matrix': confusion,
        'distress_binary': {
            'positive_labels': sorted(distress_labels),
            'negative_labels': [label for label in CLASS_NAMES if label not in distress_labels],
            'accuracy': round((tp + tn) / max(total, 1), 4),
            'precision': round(distress_precision, 4),
            'recall': round(distress_recall, 4),
            'f1': round(distress_f1, 4),
            'tp': int(tp),
            'tn': int(tn),
            'fp': int(fp),
            'fn': int(fn),
        },
    }


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    confusion = [[0 for _ in CLASS_NAMES] for _ in CLASS_NAMES]
    for x, y in loader:
        x = x.to(device)
        logits = model(x)
        pred = logits.argmax(dim=1).cpu()
        for truth, guess in zip(y.view(-1).tolist(), pred.view(-1).tolist()):
            confusion[int(truth)][int(guess)] += 1
    return metrics_from_confusion(confusion)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-root', default='/opt/app/datasets/facial_state/aihub_82_korean_emotion')
    parser.add_argument('--output-dir', default='/opt/app/storage/training/fall-detection/facial-state')
    parser.add_argument('--epochs', type=int, default=5)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--image-size', type=int, default=160)
    parser.add_argument('--max-train-per-class', type=int, default=5000)
    parser.add_argument('--max-val-per-class', type=int, default=1000)
    parser.add_argument('--lr', type=float, default=2e-4)
    parser.add_argument('--num-workers', type=int, default=2)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--min-agreement', type=int, default=1)
    parser.add_argument('--train-min-agreement', type=int, default=None)
    parser.add_argument('--val-min-agreement', type=int, default=None)
    parser.add_argument('--model-type', choices=['mobilenet_v3_small', 'mobilenet_v3_large'], default='mobilenet_v3_small')
    parser.add_argument('--label-smoothing', type=float, default=0.0)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-pretrained', action='store_true')
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    start = time.time()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    label_zips, source_zips = find_zips(args.dataset_root)
    print(f'[scan] label_zips={len(label_zips)} source_zips={len(source_zips)}', flush=True)
    labels, label_stats = load_labels(label_zips)
    print(f'[labels] records={len(labels)} stats={dict(label_stats)}', flush=True)
    min_agreement = {
        'train': int(args.train_min_agreement if args.train_min_agreement is not None else args.min_agreement),
        'val': int(args.val_min_agreement if args.val_min_agreement is not None else args.min_agreement),
        'default': int(args.min_agreement),
    }
    rows = build_rows(source_zips, labels, args.seed, args.max_train_per_class, args.max_val_per_class, min_agreement=min_agreement)
    counts = Counter((r['label'], r.get('split', 'train')) for r in rows)
    split_counts = Counter(r.get('split', 'train') for r in rows)
    print(f'[rows] total={len(rows)} split_counts={dict(split_counts)} class_counts={dict(counts)}', flush=True)
    if args.dry_run:
        return
    if not rows:
        raise SystemExit('No training rows found. Check AI-Hub source/label zip downloads.')

    class_to_idx = {label: idx for idx, label in enumerate(CLASS_NAMES)}
    train_rows = [r for r in rows if r.get('split') != 'val']
    val_rows = [r for r in rows if r.get('split') == 'val']
    train_rows, val_rows = rebalance_missing_train_classes(train_rows, val_rows, args.seed)
    if not val_rows:
        rng = random.Random(args.seed)
        rng.shuffle(train_rows)
        n_val = max(1, int(len(train_rows) * 0.15))
        val_rows = train_rows[:n_val]
        train_rows = train_rows[n_val:]
    print(f'[split] train={len(train_rows)} val={len(val_rows)}', flush=True)

    train_ds = ZipFaceDataset(train_rows, class_to_idx, args.image_size, train=True)
    val_ds = ZipFaceDataset(val_rows, class_to_idx, args.image_size, train=False)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, pin_memory=False)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=False)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = make_model(len(CLASS_NAMES), pretrained=not args.no_pretrained, model_type=args.model_type).to(device)
    class_counts = Counter(r['label'] for r in train_rows)
    weights = [1.0 / max(class_counts.get(label, 1), 1) for label in CLASS_NAMES]
    weights = torch.tensor(weights, dtype=torch.float32, device=device)
    weights = weights / weights.mean()
    try:
        criterion = nn.CrossEntropyLoss(weight=weights, label_smoothing=float(args.label_smoothing))
    except TypeError:
        criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    best = None
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        seen = 0
        for step, (x, y) in enumerate(train_loader, start=1):
            x = x.to(device)
            y = y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * int(y.numel())
            seen += int(y.numel())
            if step % max(1, round(1000 / max(args.batch_size, 1))) == 0 or step == len(train_loader):
                print(f'[train] epoch={epoch}/{args.epochs} step={step}/{len(train_loader)} loss={running_loss / max(seen, 1):.4f}', flush=True)
        metrics = evaluate(model, val_loader, device)
        metrics['epoch'] = epoch
        metrics['train_loss'] = round(running_loss / max(seen, 1), 4)
        history.append(metrics)
        distress = metrics.get('distress_binary') or {}
        print(
            f"[eval] epoch={epoch} acc={metrics['accuracy']:.4f} "
            f"macro_f1={metrics['macro_f1']:.4f} distress_f1={float(distress.get('f1', 0.0)):.4f}",
            flush=True,
        )
        if best is None or metrics['macro_f1'] > best['macro_f1']:
            best = metrics
            ckpt = {
                'model_type': args.model_type,
                'class_names': CLASS_NAMES,
                'class_to_korean': CLASS_TO_KOR,
                'image_size': args.image_size,
                'state_dict': model.state_dict(),
                'metrics': metrics,
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            }
            torch.save(ckpt, out_dir / 'aihub82_facial_emotion_mobilenetv3.pt')

    summary = {
        'ready': True,
        'dataset': 'AI-Hub 82 Korean facial emotion compound image',
        'classes': CLASS_NAMES,
        'class_to_korean': CLASS_TO_KOR,
        'label_zips': len(label_zips),
        'source_zips': len(source_zips),
        'model_type': args.model_type,
        'min_agreement': min_agreement,
        'label_smoothing': float(args.label_smoothing),
        'train_rows': len(train_rows),
        'val_rows': len(val_rows),
        'best_metrics': best,
        'history': history,
        'output_model': str(out_dir / 'aihub82_facial_emotion_mobilenetv3.pt'),
        'elapsed_sec': round(time.time() - start, 2),
    }
    with open(out_dir / 'aihub82_facial_emotion_summary.json', 'w', encoding='utf-8') as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
