#!/usr/bin/env python3
"""
FN-0013: Build pseudo-label dataset for YOLO person detection training.
Converts FN-0012 person-bbox JSON → YOLO detect format (images + txt labels).

- Reads bbox JSON from storage/training/fall-detection/person-bbox/
- Extracts frames from original videos as JPG images
- Creates YOLO txt label files (class x_center y_center w h)
- Video-level train/val split preserving Y/N ratio
- Generates dataset.yaml

Usage:
    cd /opt/app/project/main
    python scripts/build_person_dataset.py [--sample_fps 2] [--conf_min 0.4]
"""

import argparse
import json
import os
import random
import sys
import time
import unicodedata

import cv2
import yaml


def find_video_dir():
    """Find 낙상영상 directory handling NFD/NFC unicode."""
    base = "/opt/app"
    for entry in os.listdir(base):
        nfc = unicodedata.normalize("NFC", entry)
        if nfc == "낙상영상":
            return os.path.join(base, entry)
    return None


def load_bbox_data(bbox_dir):
    """Load all per-video bbox JSON files."""
    data = []
    for fn in sorted(os.listdir(bbox_dir)):
        if fn == "manifest.json" or not fn.endswith(".json"):
            continue
        path = os.path.join(bbox_dir, fn)
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        data.append(d)
    return data


def video_level_split(videos, val_ratio=0.3, seed=42):
    """
    Split videos into train/val at video level, preserving Y/N ratio.
    Returns (train_names, val_names) as sets.
    """
    random.seed(seed)
    y_videos = [v for v in videos if v["label"] == "Y"]
    n_videos = [v for v in videos if v["label"] == "N"]

    random.shuffle(y_videos)
    random.shuffle(n_videos)

    n_y_val = max(1, round(len(y_videos) * val_ratio))
    n_n_val = max(1, round(len(n_videos) * val_ratio))

    y_val = {v["video_name"] for v in y_videos[:n_y_val]}
    n_val = {v["video_name"] for v in n_videos[:n_n_val]}

    val_names = y_val | n_val
    train_names = {v["video_name"] for v in videos} - val_names

    return train_names, val_names


def build_dataset(
    bbox_data_list,
    video_dir,
    output_dir,
    sample_fps=2,
    conf_min=0.4,
    fall_dense_fps=10,
    fall_window_sec=2.0,
):
    """
    Build YOLO detection dataset from bbox JSONs + original videos.
    
    Args:
        bbox_data_list: List of per-video bbox dicts
        video_dir: Path to 낙상영상/
        output_dir: Dataset output root
        sample_fps: Sparse sampling rate (frames per second)
        conf_min: Minimum confidence to include bbox
        fall_dense_fps: Dense sampling fps for fall videos near midpoint
        fall_window_sec: ±seconds around midpoint for dense sampling (Y videos)
    """
    # Directories
    img_train = os.path.join(output_dir, "images", "train")
    img_val = os.path.join(output_dir, "images", "val")
    lbl_train = os.path.join(output_dir, "labels", "train")
    lbl_val = os.path.join(output_dir, "labels", "val")
    for d in [img_train, img_val, lbl_train, lbl_val]:
        os.makedirs(d, exist_ok=True)

    # Split
    train_names, val_names = video_level_split(bbox_data_list)
    print(f"Split: train={len(train_names)} videos, val={len(val_names)} videos")
    print(f"  Train: {sorted(train_names)}")
    print(f"  Val:   {sorted(val_names)}")

    manifest = {
        "config": {
            "sample_fps": sample_fps,
            "conf_min": conf_min,
            "fall_dense_fps": fall_dense_fps,
            "fall_window_sec": fall_window_sec,
        },
        "split": {
            "train": sorted(train_names),
            "val": sorted(val_names),
        },
        "videos": {},
    }

    total_images = 0
    total_bboxes = 0

    for vdata in bbox_data_list:
        vname = vdata["video_name"]
        label = vdata["label"]
        meta = vdata["video_meta"]
        orig_fps = meta["fps"]
        width = meta["width"]
        height = meta["height"]
        total_frames = meta["total_frames"]

        # Determine split
        split = "val" if vname in val_names else "train"
        img_dir = img_val if split == "val" else img_train
        lbl_dir = lbl_val if split == "val" else lbl_train

        # Determine which frames to sample
        # Sparse: every N frames for sample_fps
        sparse_interval = max(1, round(orig_fps / sample_fps))

        # Dense region for fall videos (Y): ±fall_window_sec around midpoint
        dense_frames = set()
        if label == "Y":
            mid = total_frames // 2
            dense_start = max(0, int(mid - fall_window_sec * orig_fps))
            dense_end = min(total_frames, int(mid + fall_window_sec * orig_fps))
            dense_interval = max(1, round(orig_fps / fall_dense_fps))
            for fi in range(dense_start, dense_end, dense_interval):
                dense_frames.add(fi)

        # Sparse frames
        sample_frames = set()
        for fi in range(0, total_frames, sparse_interval):
            sample_frames.add(fi)

        # Combine
        all_frames = sorted(sample_frames | dense_frames)

        # Build a lookup for bbox data by frame_idx
        frames_by_idx = {}
        for fdata in vdata["frames"]:
            frames_by_idx[fdata["frame_idx"]] = fdata

        # Find video file
        subdir = os.path.join(video_dir, label)
        video_path = None
        for fn in os.listdir(subdir):
            base_name = vname.split("_", 1)[1] if "_" in vname else vname
            if fn.startswith(base_name[:5]) and fn.endswith(".mp4"):
                video_path = os.path.join(subdir, fn)
                break

        if video_path is None:
            print(f"  [WARN] Video file not found for {vname}, skipping")
            continue

        # Open video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"  [WARN] Cannot open {video_path}")
            continue

        v_images = 0
        v_bboxes = 0
        frame_idx = 0
        sample_set = set(all_frames)

        print(f"  {label}/{vname} → {split}: {len(all_frames)} frames to extract")

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx in sample_set:
                fdata = frames_by_idx.get(frame_idx)
                persons = fdata["persons"] if fdata else []

                # Filter by confidence
                persons = [p for p in persons if p["confidence"] >= conf_min]

                # Only save frames with at least one person
                if persons:
                    # Save image
                    img_name = f"{vname}_f{frame_idx:05d}.jpg"
                    img_path = os.path.join(img_dir, img_name)
                    cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

                    # Save YOLO label
                    lbl_name = f"{vname}_f{frame_idx:05d}.txt"
                    lbl_path = os.path.join(lbl_dir, lbl_name)
                    with open(lbl_path, "w") as lf:
                        for p in persons:
                            # Convert xyxy to normalized xywh
                            cx = ((p["x1"] + p["x2"]) / 2) / width
                            cy = ((p["y1"] + p["y2"]) / 2) / height
                            bw = (p["x2"] - p["x1"]) / width
                            bh = (p["y2"] - p["y1"]) / height
                            # Clamp to [0, 1]
                            cx = max(0, min(1, cx))
                            cy = max(0, min(1, cy))
                            bw = max(0, min(1, bw))
                            bh = max(0, min(1, bh))
                            lf.write(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
                            v_bboxes += 1

                    v_images += 1

            frame_idx += 1

        cap.release()
        total_images += v_images
        total_bboxes += v_bboxes

        manifest["videos"][vname] = {
            "label": label,
            "split": split,
            "sampled_frames": len(all_frames),
            "saved_images": v_images,
            "saved_bboxes": v_bboxes,
            "sparse_interval": sparse_interval,
            "dense_frames": len(dense_frames) if label == "Y" else 0,
        }
        print(f"    Saved: {v_images} images, {v_bboxes} bboxes")

    # Count per split
    train_imgs = len(os.listdir(img_train))
    val_imgs = len(os.listdir(img_val))

    # Write dataset.yaml
    dataset_yaml = {
        "path": os.path.abspath(output_dir),
        "train": "images/train",
        "val": "images/val",
        "nc": 1,
        "names": ["person"],
    }
    yaml_path = os.path.join(output_dir, "dataset.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(dataset_yaml, f, default_flow_style=False)

    manifest["summary"] = {
        "total_images": total_images,
        "total_bboxes": total_bboxes,
        "train_images": train_imgs,
        "val_images": val_imgs,
    }

    manifest_path = os.path.join(output_dir, "dataset_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nDataset built: {total_images} images, {total_bboxes} bboxes")
    print(f"  Train: {train_imgs} images")
    print(f"  Val: {val_imgs} images")
    print(f"  dataset.yaml: {yaml_path}")
    print(f"  manifest: {manifest_path}")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Build YOLO person detection dataset from bbox JSONs"
    )
    parser.add_argument(
        "--bbox_dir",
        type=str,
        default="storage/training/fall-detection/person-bbox",
        help="Directory with per-video bbox JSON files",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="storage/training/fall-detection/person-detect/dataset",
        help="Output dataset directory",
    )
    parser.add_argument(
        "--sample_fps",
        type=float,
        default=2,
        help="Sparse sampling rate in FPS",
    )
    parser.add_argument(
        "--conf_min",
        type=float,
        default=0.4,
        help="Minimum confidence threshold for including bbox",
    )
    parser.add_argument(
        "--fall_dense_fps",
        type=float,
        default=10,
        help="Dense sampling FPS for fall (Y) videos near midpoint",
    )
    parser.add_argument(
        "--fall_window_sec",
        type=float,
        default=2.0,
        help="±seconds around midpoint for dense sampling",
    )
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    bbox_dir = (
        os.path.join(project_root, args.bbox_dir)
        if not os.path.isabs(args.bbox_dir)
        else args.bbox_dir
    )
    output_dir = (
        os.path.join(project_root, args.output_dir)
        if not os.path.isabs(args.output_dir)
        else args.output_dir
    )

    video_dir = find_video_dir()
    if video_dir is None:
        print("ERROR: 낙상영상 directory not found")
        sys.exit(1)

    print(f"BBox dir: {bbox_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Video dir: {video_dir}")
    print(f"Config: sample_fps={args.sample_fps}, conf_min={args.conf_min}, "
          f"fall_dense_fps={args.fall_dense_fps}, fall_window=±{args.fall_window_sec}s")

    # Load bbox data
    bbox_data = load_bbox_data(bbox_dir)
    print(f"\nLoaded {len(bbox_data)} video bbox files")

    if not bbox_data:
        print("No bbox data found!")
        sys.exit(1)

    t0 = time.time()
    manifest = build_dataset(
        bbox_data,
        video_dir,
        output_dir,
        sample_fps=args.sample_fps,
        conf_min=args.conf_min,
        fall_dense_fps=args.fall_dense_fps,
        fall_window_sec=args.fall_window_sec,
    )
    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
