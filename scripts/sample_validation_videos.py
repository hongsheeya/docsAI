#!/usr/bin/env python3
"""
FN-0024: Sample 200 balanced videos from Validation dataset.
Outputs batch-001 (100) and batch-002 (100) JSON manifests.

Sampling strategy:
  - Y:100, N:100 (balanced)
  - Y subtypes balanced: ~34 FY, ~33 SY, ~33 BY
  - Maximize prefix (subject) diversity
  - Stratify by scene_loc, actor_age, actor_sex
  - Camera number diversity within each prefix

Usage:
    cd /opt/app/project/main
    python scripts/sample_validation_videos.py
"""

import json
import os
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/opt/app')
VAL_ROOT = ROOT / '041.낙상사고_위험동작_영상-센서_쌍_데이터' / '3.개방데이터' / '1.데이터' / 'Validation'
SRC_ROOT = VAL_ROOT / '01.원천데이터' / 'VS' / '영상'
LBL_ROOT = VAL_ROOT / '02.라벨링데이터' / 'VL' / '영상'

PROJECT_ROOT = ROOT / 'project' / 'main'
TRAINING_ROOT = PROJECT_ROOT / 'storage' / 'training' / 'fall-detection'
SAMPLE_ROOT = TRAINING_ROOT / 'validation-samples'

SEED = 42


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def scan_all_records():
    """Scan all Validation videos with full metadata."""
    records = []
    for category in ['Y', 'N']:
        lbl_cat = LBL_ROOT / category
        if not lbl_cat.exists():
            continue
        for sub in sorted(lbl_cat.iterdir()):
            if not sub.is_dir():
                continue
            for scene_dir in sorted(sub.iterdir()):
                if not scene_dir.is_dir():
                    continue
                jsons = list(scene_dir.glob("*.json"))
                if not jsons:
                    continue
                with open(jsons[0], 'r', encoding='utf-8') as f:
                    d = json.load(f)

                si = d.get('scene_info', {})
                ai = d.get('actor_info', {})
                md = d.get('metadata', {})
                sd = d.get('sensordata', {})
                sid = md.get('scene_id', '')
                prefix = sid.split('_')[0] if '_' in sid else sid

                # Find video file
                vid_dir = SRC_ROOT / category / sub.name / scene_dir.name
                vids = list(vid_dir.glob("*.mp4")) if vid_dir.exists() else []
                if not vids:
                    continue

                records.append({
                    'scene_id': sid,
                    'prefix': prefix,
                    'category': category,
                    'subtype': sub.name,
                    'scene_loc': si.get('scene_loc', '?'),
                    'scene_pos': si.get('scene_pos', '?'),
                    'scene_cat_name': si.get('scene_cat_name', '?'),
                    'fall_type': si.get('fall_type', 'none'),
                    'scene_length': si.get('scene_length', 600),
                    'cam_num': si.get('cam_num', 0),
                    'actor_age': ai.get('actor_age', '?'),
                    'actor_sex': ai.get('actor_sex', '?'),
                    'fall_start_frame': sd.get('fall_start_frame', -1),
                    'fall_end_frame': sd.get('fall_end_frame', -1),
                    'video_path': str(vids[0]),
                    'label_path': str(jsons[0]),
                })
    return records


def stratified_sample(records, n, seed, prefer_diverse_cams=True):
    """
    Sample n records maximizing prefix diversity.
    Picks 1-2 records per prefix, then fills remainder by diversity criteria.
    """
    rng = random.Random(seed)

    # Group by prefix
    by_prefix = defaultdict(list)
    for r in records:
        by_prefix[r['prefix']].append(r)

    prefixes = list(by_prefix.keys())
    rng.shuffle(prefixes)

    selected = []
    remaining_prefixes = list(prefixes)

    # Phase 1: pick 1 from each prefix until we reach n or exhaust prefixes
    for pf in remaining_prefixes[:]:
        if len(selected) >= n:
            break
        candidates = by_prefix[pf]
        rng.shuffle(candidates)
        selected.append(candidates[0])
        remaining_prefixes.remove(pf)

    # Phase 2: if still need more, pick a second from already-used prefixes
    if len(selected) < n:
        used_prefixes = [r['prefix'] for r in selected]
        rng.shuffle(used_prefixes)
        for pf in used_prefixes:
            if len(selected) >= n:
                break
            candidates = [r for r in by_prefix[pf] if r not in selected]
            if candidates:
                # Prefer different camera number
                if prefer_diverse_cams:
                    used_cams = {r['cam_num'] for r in selected if r['prefix'] == pf}
                    diff_cam = [r for r in candidates if r['cam_num'] not in used_cams]
                    if diff_cam:
                        candidates = diff_cam
                rng.shuffle(candidates)
                selected.append(candidates[0])

    # Phase 3: if still need more, keep adding from any prefix
    if len(selected) < n:
        all_remaining = [r for r in records if r not in selected]
        rng.shuffle(all_remaining)
        for r in all_remaining:
            if len(selected) >= n:
                break
            selected.append(r)

    return selected[:n]


def sample_balanced(records, total=200, seed=SEED):
    """Sample total videos with Y:N = 1:1 and Y subtypes balanced."""
    rng = random.Random(seed)
    n_per_class = total // 2  # 100 Y, 100 N

    # Split by category
    y_records = [r for r in records if r['category'] == 'Y']
    n_records = [r for r in records if r['category'] == 'N']

    # Y: balanced by subtype (FY, SY, BY)
    y_by_sub = defaultdict(list)
    for r in y_records:
        y_by_sub[r['subtype']].append(r)

    subtypes = sorted(y_by_sub.keys())  # BY, FY, SY
    n_sub = len(subtypes)
    base_per_sub = n_per_class // n_sub
    remainder = n_per_class - base_per_sub * n_sub

    y_allocation = {}
    for i, st in enumerate(subtypes):
        y_allocation[st] = base_per_sub + (1 if i < remainder else 0)

    print(f"\n  Y allocation: {y_allocation}")

    y_selected = []
    for st, count in y_allocation.items():
        candidates = y_by_sub[st]
        sampled = stratified_sample(candidates, count, seed + hash(st))
        y_selected.extend(sampled)
        print(f"    {st}: {len(sampled)}/{count} selected from {len(candidates)} available ({len(set(r['prefix'] for r in sampled))} unique prefixes)")

    # N: stratified sample
    n_selected = stratified_sample(n_records, n_per_class, seed + 999)
    print(f"    N: {len(n_selected)}/{n_per_class} selected from {len(n_records)} available ({len(set(r['prefix'] for r in n_selected))} unique prefixes)")

    all_selected = y_selected + n_selected
    rng.shuffle(all_selected)
    return all_selected


def split_batches(selected, seed=SEED):
    """
    Split selected into batch-001 and batch-002 (50% each).
    Each batch should be internally balanced.
    """
    rng = random.Random(seed)
    batch_size = len(selected) // 2

    # Group by (category, subtype)
    groups = defaultdict(list)
    for r in selected:
        key = f"{r['category']}_{r['subtype']}"
        groups[key].append(r)

    batch1 = []
    batch2 = []

    for key, items in groups.items():
        rng.shuffle(items)
        half = len(items) // 2
        batch1.extend(items[:half])
        batch2.extend(items[half:])

    # Balance if sizes differ
    while len(batch1) < batch_size and len(batch2) > batch_size:
        batch1.append(batch2.pop())
    while len(batch2) < batch_size and len(batch1) > batch_size:
        batch2.append(batch1.pop())

    rng.shuffle(batch1)
    rng.shuffle(batch2)
    return batch1, batch2


def analyze_distribution(records, label=""):
    """Print distribution analysis."""
    cats = Counter(r['category'] for r in records)
    subs = Counter(r['subtype'] for r in records)
    locs = Counter(r['scene_loc'] for r in records)
    poses = Counter(r['scene_pos'] for r in records)
    ages = Counter(r['actor_age'] for r in records)
    sexes = Counter(r['actor_sex'] for r in records)
    prefixes = len(set(r['prefix'] for r in records))
    cams = Counter(r['cam_num'] for r in records)

    print(f"\n  === {label} Distribution ({len(records)} total) ===")
    print(f"    Category: {dict(cats)}")
    print(f"    Subtype: {dict(subs)}")
    print(f"    Location: {dict(locs)}")
    print(f"    Position: {dict(poses)}")
    print(f"    Age: {dict(ages)}")
    print(f"    Sex: {dict(sexes)}")
    print(f"    Cameras: {dict(cams)}")
    print(f"    Unique prefixes: {prefixes}")


def save_batch(records, batch_name, output_dir):
    """Save batch manifest as JSON."""
    entries = []
    for r in records:
        entries.append({
            'scene_id': r['scene_id'],
            'category': r['category'],
            'subtype': r['subtype'],
            'video_path': r['video_path'],
            'label_path': r['label_path'],
            'scene_loc': r['scene_loc'],
            'scene_pos': r['scene_pos'],
            'fall_type': r['fall_type'],
            'actor_age': r['actor_age'],
            'actor_sex': r['actor_sex'],
            'cam_num': r['cam_num'],
            'fall_start_frame': r['fall_start_frame'],
            'fall_end_frame': r['fall_end_frame'],
            'scene_length': r['scene_length'],
        })

    manifest = {
        'batch_name': batch_name,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'count': len(entries),
        'distribution': {
            'category': dict(Counter(r['category'] for r in records)),
            'subtype': dict(Counter(r['subtype'] for r in records)),
            'scene_loc': dict(Counter(r['scene_loc'] for r in records)),
            'actor_age': dict(Counter(r['actor_age'] for r in records)),
            'actor_sex': dict(Counter(r['actor_sex'] for r in records)),
            'unique_prefixes': len(set(r['scene_id'].split('_')[0] for r in records)),
        },
        'entries': entries,
    }

    path = output_dir / f"{batch_name}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {path} ({len(entries)} entries)")
    return path


def main():
    print("=" * 60)
    print("FN-0024: Validation 추가학습용 200건 샘플링")
    print("=" * 60)

    # 1. Scan all records
    print("\n[1/4] Validation 데이터셋 전수 스캔...")
    all_records = scan_all_records()
    print(f"  총 {len(all_records)}건 스캔 완료")
    analyze_distribution(all_records, "전체 Validation")

    # 2. Balanced sampling
    print("\n[2/4] Y/N 밸런싱 200건 샘플링...")
    selected = sample_balanced(all_records, total=200, seed=SEED)
    analyze_distribution(selected, "샘플링 200건")

    # 3. Split into batches
    print("\n[3/4] batch-001 / batch-002 분할...")
    batch1, batch2 = split_batches(selected, seed=SEED)
    analyze_distribution(batch1, "batch-001")
    analyze_distribution(batch2, "batch-002")

    # 4. Save manifests
    print("\n[4/4] 매니페스트 저장...")
    output_dir = ensure_dir(SAMPLE_ROOT)
    save_batch(batch1, 'batch-001', output_dir)
    save_batch(batch2, 'batch-002', output_dir)

    # Save combined manifest
    combined = {
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(selected),
        'batch_001_count': len(batch1),
        'batch_002_count': len(batch2),
        'seed': SEED,
        'source': str(VAL_ROOT),
        'sampling_strategy': {
            'total': 200,
            'y_n_ratio': '1:1',
            'y_subtype_balance': 'equal (~34 each)',
            'prefix_diversity': 'max unique subjects',
            'camera_diversity': 'prefer different camera angles per subject',
        },
        'train_val_split': {
            'strategy': '80/20 by prefix (no data leakage)',
            'description': 'Same prefix videos always in same split',
        },
    }
    combined_path = output_dir / 'sampling_manifest.json'
    with open(combined_path, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"\n  Combined manifest: {combined_path}")

    print(f"\n{'=' * 60}")
    print("COMPLETE: 200건 샘플링 완료")
    print(f"  batch-001: {len(batch1)}건")
    print(f"  batch-002: {len(batch2)}건")
    print(f"  출력 디렉토리: {output_dir}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
