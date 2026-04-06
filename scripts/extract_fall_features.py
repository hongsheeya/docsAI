#!/usr/bin/env python3
"""
FN-0016: Extract fall-detection features from person bbox trajectories.
Uses tracking data from FN-0012 to compute per-window motion features.

Features:
  1. center_dy: vertical movement speed (Δcy / Δframe)
  2. height_ratio: height change ratio (h_t - h_{t-k}) / h_{t-k}
  3. aspect_change: aspect ratio (w/h) change
  4. stillness: consecutive low-movement frames
  5. floor_proximity: bbox bottom near frame bottom
  6. area_change: bbox area change rate
  7. vert_horiz_ratio: vertical vs horizontal speed ratio

Output: per-video CSV + combined fall_features_all.csv

Usage:
    cd /opt/app/project/main
    python scripts/extract_fall_features.py
"""

import argparse
import csv
import json
import os
import sys
import math


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


def build_track_sequences(vdata):
    """
    For each track_id, build a sequence of (frame_idx, cx, cy, w, h, conf)
    sorted by frame_idx.
    """
    tracks = {}
    video_w = vdata["video_meta"]["width"]
    video_h = vdata["video_meta"]["height"]

    for fdata in vdata["frames"]:
        fi = fdata["frame_idx"]
        for p in fdata["persons"]:
            tid = p["track_id"]
            if tid < 0:
                continue

            x1, y1, x2, y2 = p["x1"], p["y1"], p["x2"], p["y2"]
            cx = (x1 + x2) / 2.0 / video_w  # normalized
            cy = (y1 + y2) / 2.0 / video_h
            w = (x2 - x1) / video_w
            h = (y2 - y1) / video_h
            conf = p["confidence"]

            if tid not in tracks:
                tracks[tid] = []
            tracks[tid].append((fi, cx, cy, w, h, conf))

    # Sort each track by frame_idx
    for tid in tracks:
        tracks[tid].sort(key=lambda x: x[0])

    return tracks


def compute_window_features(window_points, fps):
    """
    Compute features for a window of tracking points.
    window_points: list of (frame_idx, cx, cy, w, h, conf)
    Returns dict of features or None if insufficient data.
    """
    if len(window_points) < 3:
        return None

    frames = [p[0] for p in window_points]
    cxs = [p[1] for p in window_points]
    cys = [p[2] for p in window_points]
    ws = [p[3] for p in window_points]
    hs = [p[4] for p in window_points]
    confs = [p[5] for p in window_points]

    n = len(window_points)
    dt = (frames[-1] - frames[0]) / fps if fps > 0 else 1.0
    if dt <= 0:
        dt = 1.0 / fps

    # 1. center_dy: average vertical speed (normalized units per second)
    dy_total = cys[-1] - cys[0]
    center_dy = dy_total / dt

    # 2. height_ratio: relative height change (end vs start)
    h_start = hs[0] if hs[0] > 0.001 else 0.001
    height_ratio = (hs[-1] - hs[0]) / h_start

    # 3. aspect_change: change in aspect ratio (w/h)
    def aspect(w, h):
        return w / h if h > 0.001 else 0

    ar_start = aspect(ws[0], hs[0])
    ar_end = aspect(ws[-1], hs[-1])
    aspect_change = ar_end - ar_start

    # 4. stillness: fraction of consecutive frames with low center movement
    movement_threshold = 0.005  # normalized threshold
    still_count = 0
    for i in range(1, n):
        dx = abs(cxs[i] - cxs[i - 1])
        dy = abs(cys[i] - cys[i - 1])
        if math.sqrt(dx**2 + dy**2) < movement_threshold:
            still_count += 1
    stillness = still_count / (n - 1) if n > 1 else 0

    # 5. floor_proximity: max of (cy + h/2) in window — how close bottom gets to floor
    floor_vals = [cy + h / 2 for cy, h in zip(cys, hs)]
    floor_proximity = max(floor_vals)

    # 6. area_change: relative area change
    area_start = ws[0] * hs[0] if ws[0] * hs[0] > 0.0001 else 0.0001
    area_end = ws[-1] * hs[-1]
    area_change = (area_end - area_start) / area_start

    # 7. vert_horiz_ratio: ratio of vertical displacement to horizontal
    dx_total = abs(cxs[-1] - cxs[0])
    dy_abs = abs(dy_total)
    vert_horiz_ratio = dy_abs / (dx_total + 1e-6)

    # Additional: max downward speed within window
    max_down_speed = 0
    for i in range(1, n):
        d_frame = frames[i] - frames[i - 1]
        if d_frame > 0:
            speed = (cys[i] - cys[i - 1]) / (d_frame / fps)
            max_down_speed = max(max_down_speed, speed)

    # Average confidence in window
    avg_conf = sum(confs) / n

    return {
        "center_dy": round(center_dy, 6),
        "height_ratio": round(height_ratio, 6),
        "aspect_change": round(aspect_change, 6),
        "stillness": round(stillness, 6),
        "floor_proximity": round(floor_proximity, 6),
        "area_change": round(area_change, 6),
        "vert_horiz_ratio": round(vert_horiz_ratio, 6),
        "max_down_speed": round(max_down_speed, 6),
        "avg_conf": round(avg_conf, 4),
        "n_points": n,
    }


def extract_features_for_video(vdata, window_sec=1.0, stride_sec=0.5):
    """
    Extract sliding-window features for all tracks in a video.
    Returns list of feature dicts.
    """
    fps = vdata["video_meta"]["fps"]
    label = vdata["label"]
    vname = vdata["video_name"]

    tracks = build_track_sequences(vdata)

    if not tracks:
        print(f"    No tracks found")
        return []

    window_frames = int(window_sec * fps)
    stride_frames = int(stride_sec * fps)
    if window_frames < 2:
        window_frames = 2
    if stride_frames < 1:
        stride_frames = 1

    features_list = []

    for tid, points in sorted(tracks.items()):
        if len(points) < 3:
            continue

        # Find track frame range
        first_frame = points[0][0]
        last_frame = points[-1][0]

        # Create sliding windows
        win_start = first_frame
        while win_start + window_frames <= last_frame + 1:
            win_end = win_start + window_frames

            # Gather points in this window
            win_points = [p for p in points if win_start <= p[0] < win_end]

            feats = compute_window_features(win_points, fps)
            if feats is not None:
                feats["video"] = vname
                feats["label"] = label
                feats["track_id"] = tid
                feats["window_start"] = win_start
                feats["window_end"] = win_end
                feats["window_start_sec"] = round(win_start / fps, 3)
                feats["window_end_sec"] = round(win_end / fps, 3)
                features_list.append(feats)

            win_start += stride_frames

    return features_list


def main():
    parser = argparse.ArgumentParser(
        description="Extract fall-detection features from person bbox trajectories"
    )
    parser.add_argument(
        "--bbox_dir",
        type=str,
        default="storage/training/fall-detection/person-bbox",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="storage/training/fall-detection/fall-features",
    )
    parser.add_argument("--window_sec", type=float, default=1.0)
    parser.add_argument("--stride_sec", type=float, default=0.5)
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
    os.makedirs(output_dir, exist_ok=True)

    print(f"BBox dir: {bbox_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Window: {args.window_sec}s, Stride: {args.stride_sec}s")

    bbox_data = load_bbox_data(bbox_dir)
    print(f"Loaded {len(bbox_data)} video bbox files")

    # Feature columns
    feature_cols = [
        "video",
        "label",
        "track_id",
        "window_start",
        "window_end",
        "window_start_sec",
        "window_end_sec",
        "center_dy",
        "height_ratio",
        "aspect_change",
        "stillness",
        "floor_proximity",
        "area_change",
        "vert_horiz_ratio",
        "max_down_speed",
        "avg_conf",
        "n_points",
    ]

    all_features = []

    for vdata in bbox_data:
        vname = vdata["video_name"]
        label = vdata["label"]
        print(f"\n  {label}/{vname}:")

        features = extract_features_for_video(
            vdata, window_sec=args.window_sec, stride_sec=args.stride_sec
        )
        print(f"    Extracted {len(features)} feature windows")

        if features:
            # Save per-video CSV
            csv_path = os.path.join(output_dir, f"{vname}.csv")
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=feature_cols)
                writer.writeheader()
                writer.writerows(features)

            all_features.extend(features)

    # Save combined CSV
    combined_path = os.path.join(output_dir, "fall_features_all.csv")
    with open(combined_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=feature_cols)
        writer.writeheader()
        writer.writerows(all_features)

    # Summary
    y_windows = sum(1 for f in all_features if f["label"] == "Y")
    n_windows = sum(1 for f in all_features if f["label"] == "N")

    print(f"\n{'='*60}")
    print(f"COMPLETE: {len(all_features)} total feature windows")
    print(f"  Y (fall): {y_windows}")
    print(f"  N (normal): {n_windows}")
    print(f"  Combined CSV: {combined_path}")

    # Save summary
    summary = {
        "total_windows": len(all_features),
        "y_windows": y_windows,
        "n_windows": n_windows,
        "config": {
            "window_sec": args.window_sec,
            "stride_sec": args.stride_sec,
        },
        "features": [c for c in feature_cols if c not in ("video", "label", "track_id", "window_start", "window_end", "window_start_sec", "window_end_sec")],
        "per_video": {},
    }
    for vdata in bbox_data:
        vname = vdata["video_name"]
        vf = [f for f in all_features if f["video"] == vname]
        summary["per_video"][vname] = {
            "label": vdata["label"],
            "windows": len(vf),
            "tracks": len(set(f["track_id"] for f in vf)) if vf else 0,
        }

    summary_path = os.path.join(output_dir, "feature_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
