#!/usr/bin/env python3
"""Calibration report for the active AI-Hub 82 facial auxiliary model."""

import argparse
import importlib.util
import json
import math
import time
from collections import Counter
from pathlib import Path

import torch
from torch.utils.data import DataLoader


PROJECT = Path('/opt/app/project/main')
TRAIN_SCRIPT = PROJECT / 'scripts' / 'train_facial_emotion_aihub82.py'
ACTIVE_MODEL = Path('/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_mobilenetv3.pt')
ACTIVE_SUMMARY = Path('/opt/app/storage/training/fall-detection/facial-state/aihub82_facial_emotion_summary.json')
OUT_DIR = PROJECT / 'outputs' / 'facial_aux_validation'


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot import {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


train82 = load_module(TRAIN_SCRIPT, 'train_facial_emotion_aihub82_calibration')


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return {}


def build_validation_rows(args):
    train82.configure_label_policy(args.label_policy)
    label_zips, source_zips = train82.find_zips(args.dataset_root)
    labels, _ = train82.load_labels(label_zips)
    rows = train82.build_rows(
        source_zips,
        labels,
        args.seed,
        args.max_train_per_class,
        args.max_val_per_class,
        min_agreement={'train': args.train_min_agreement, 'val': args.val_min_agreement, 'default': 1},
    )
    train_rows = [r for r in rows if r.get('split') != 'val']
    val_rows = [r for r in rows if r.get('split') == 'val']
    _, val_rows = train82.rebalance_missing_train_classes(train_rows, val_rows, args.seed)
    return val_rows


def load_active_model(path):
    ckpt = torch.load(path, map_location='cpu')
    class_names = list(ckpt.get('class_names') or [])
    model_type = ckpt.get('model_type', 'mobilenet_v3_large')
    image_size = int(ckpt.get('image_size') or 160)
    crop_pad_ratio = float(ckpt.get('crop_pad_ratio') or 0.18)
    model = train82.make_model(len(class_names), pretrained=False, model_type=model_type)
    model.load_state_dict(ckpt['state_dict'])
    model.eval()
    return model, class_names, image_size, crop_pad_ratio


def ece_from_samples(samples, bins=10):
    out = []
    total = len(samples)
    ece = 0.0
    for idx in range(bins):
        lo = idx / bins
        hi = (idx + 1) / bins
        group = [
            s for s in samples
            if (lo <= s['confidence'] < hi) or (idx == bins - 1 and lo <= s['confidence'] <= hi)
        ]
        if not group:
            out.append({'bin': f'{lo:.1f}-{hi:.1f}', 'count': 0, 'avg_confidence': 0.0, 'accuracy': 0.0, 'gap': 0.0})
            continue
        avg_conf = sum(s['confidence'] for s in group) / len(group)
        acc = sum(1 for s in group if s['correct']) / len(group)
        gap = abs(avg_conf - acc)
        ece += (len(group) / max(total, 1)) * gap
        out.append({
            'bin': f'{lo:.1f}-{hi:.1f}',
            'count': len(group),
            'avg_confidence': round(avg_conf, 4),
            'accuracy': round(acc, 4),
            'gap': round(gap, 4),
        })
    return round(ece, 4), out


def threshold_sweep(samples):
    rows = []
    for i in range(5, 96, 5):
        threshold = i / 100
        tp = tn = fp = fn = 0
        for s in samples:
            truth = bool(s['truth_distress'])
            pred = float(s['distress_prob']) >= threshold
            if truth and pred:
                tp += 1
            elif truth:
                fn += 1
            elif pred:
                fp += 1
            else:
                tn += 1
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        rows.append({
            'threshold': round(threshold, 2),
            'accuracy': round((tp + tn) / max(len(samples), 1), 4),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
            'tp': tp,
            'tn': tn,
            'fp': fp,
            'fn': fn,
        })
    best_f1 = max(rows, key=lambda r: (r['f1'], r['accuracy']))
    high_precision = [r for r in rows if r['precision'] >= 0.80]
    best_high_precision = max(high_precision, key=lambda r: (r['recall'], r['f1'])) if high_precision else None
    return rows, best_f1, best_high_precision


def write_md(path, result):
    lines = [
        '# AI-Hub 82 Facial Score Calibration',
        '',
        f"- created_at: `{result['created_at']}`",
        f"- model: `{result['model_path']}`",
        f"- label_policy: `{result['label_policy']}`",
        f"- validation_rows: `{result['validation_rows']}`",
        f"- classes: `{', '.join(result['classes'])}`",
        f"- top-label ECE: `{result['top_label_ece']}`",
        '',
        '## Distress Threshold',
        '',
        f"- default threshold 0.50: `{result['default_threshold']}`",
        f"- best F1 threshold: `{result['best_f1_threshold']}`",
    ]
    if result.get('best_high_precision_threshold'):
        lines.append(f"- precision>=0.80 candidate: `{result['best_high_precision_threshold']}`")
    lines.extend(['', '## Calibration Bins', '', '| Confidence bin | Count | Avg confidence | Accuracy | Gap |', '| --- | ---: | ---: | ---: | ---: |'])
    for row in result['confidence_bins']:
        lines.append(f"| {row['bin']} | {row['count']} | {row['avg_confidence']} | {row['accuracy']} | {row['gap']} |")
    lines.extend(['', '## Threshold Sweep', '', '| Threshold | Accuracy | Precision | Recall | F1 | FP | FN |', '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |'])
    for row in result['threshold_sweep']:
        lines.append(f"| {row['threshold']} | {row['accuracy']} | {row['precision']} | {row['recall']} | {row['f1']} | {row['fp']} | {row['fn']} |")
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    summary = read_json(ACTIVE_SUMMARY)
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-root', default='/opt/app/datasets/facial_state/aihub_82_korean_emotion')
    parser.add_argument('--model-path', default=str(ACTIVE_MODEL))
    parser.add_argument('--label-policy', default=summary.get('label_policy') or 'fall_aux4')
    parser.add_argument('--seed', type=int, default=2026060404)
    parser.add_argument('--max-train-per-class', type=int, default=3200)
    parser.add_argument('--max-val-per-class', type=int, default=900)
    parser.add_argument('--train-min-agreement', type=int, default=int((summary.get('min_agreement') or {}).get('train', 2)))
    parser.add_argument('--val-min-agreement', type=int, default=int((summary.get('min_agreement') or {}).get('val', 3)))
    parser.add_argument('--batch-size', type=int, default=64)
    args = parser.parse_args()

    try:
        torch.set_num_threads(1)
    except Exception:
        pass

    started = time.time()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model, class_names, image_size, crop_pad_ratio = load_active_model(args.model_path)
    model.to(device)
    train82.configure_label_policy(args.label_policy)
    rows = build_validation_rows(args)
    class_to_idx = {label: idx for idx, label in enumerate(class_names)}
    ds = train82.ZipFaceDataset(rows, class_to_idx, image_size, train=False, crop_pad_ratio=crop_pad_ratio, augment_strength='none')
    loader = DataLoader(ds, batch_size=args.batch_size, shuffle=False, num_workers=0)
    samples = []
    with torch.no_grad():
        for x, y in loader:
            probs = torch.softmax(model(x.to(device)), dim=1).cpu()
            pred = probs.argmax(dim=1)
            for truth, guess, row_probs in zip(y.view(-1).tolist(), pred.view(-1).tolist(), probs):
                p = [float(v) for v in row_probs.tolist()]
                truth_label = class_names[int(truth)]
                guess_label = class_names[int(guess)]
                if 'distress' in class_names:
                    distress_prob = p[class_names.index('distress')]
                else:
                    distress_prob = 0.0
                samples.append({
                    'truth': truth_label,
                    'pred': guess_label,
                    'confidence': max(p) if p else 0.0,
                    'correct': truth_label == guess_label,
                    'distress_prob': distress_prob,
                    'truth_distress': truth_label == 'distress',
                })
    ece, bins = ece_from_samples(samples)
    sweep, best_f1, best_high_precision = threshold_sweep(samples)
    default = min(sweep, key=lambda row: abs(row['threshold'] - 0.50))
    result = {
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'model_path': str(args.model_path),
        'label_policy': args.label_policy,
        'classes': class_names,
        'validation_rows': len(samples),
        'validation_class_counts': dict(Counter(s['truth'] for s in samples)),
        'top_label_ece': ece,
        'confidence_bins': bins,
        'default_threshold': default,
        'best_f1_threshold': best_f1,
        'best_high_precision_threshold': best_high_precision,
        'threshold_sweep': sweep,
        'elapsed_sec': round(time.time() - started, 2),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S', time.gmtime())
    json_path = OUT_DIR / f'aihub82_active_calibration_{args.label_policy}_{stamp}.json'
    md_path = OUT_DIR / f'aihub82_active_calibration_{args.label_policy}_{stamp}.md'
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    write_md(md_path, result)
    print(f'[output_json] {json_path}')
    print(f'[output_md] {md_path}')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
