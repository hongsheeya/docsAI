#!/usr/bin/env python3
"""
FN-0014: Review and QC pseudo-label person detection dataset.
Auto-filters bad bboxes, generates confidence statistics, and creates
visual review images for fall-region frames.

Usage:
    cd /opt/app/project/main
    python scripts/review_person_labels.py [--dataset_dir ...] [--bbox_dir ...]
"""

import argparse
import json
import os
import sys
import statistics

import cv2
import numpy as np


def load_manifest(dataset_dir):
    """Load dataset manifest."""
    path = os.path.join(dataset_dir, "dataset_manifest.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_bbox_jsons(bbox_dir):
    """Load all per-video bbox JSONs into a dict keyed by video_name."""
    data = {}
    for fn in sorted(os.listdir(bbox_dir)):
        if fn == "manifest.json" or not fn.endswith(".json"):
            continue
        path = os.path.join(bbox_dir, fn)
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        data[d["video_name"]] = d
    return data


def qc_labels(dataset_dir, bbox_data, review_dir):
    """
    QC checks on generated labels:
    1. Tiny bboxes (area < 1% of image)
    2. Out-of-bound bboxes (>50% outside frame)
    3. Confidence distribution per video
    4. Generate review images for fall (Y) video frames
    """
    report = {
        "total_images": 0,
        "total_bboxes": 0,
        "filtered_tiny": 0,
        "filtered_oob": 0,
        "per_video": {},
        "low_conf_val": [],
    }

    os.makedirs(review_dir, exist_ok=True)

    for split in ["train", "val"]:
        img_dir = os.path.join(dataset_dir, "images", split)
        lbl_dir = os.path.join(dataset_dir, "labels", split)

        if not os.path.isdir(img_dir):
            continue

        for img_fn in sorted(os.listdir(img_dir)):
            if not img_fn.endswith(".jpg"):
                continue

            base = os.path.splitext(img_fn)[0]
            lbl_fn = base + ".txt"
            lbl_path = os.path.join(lbl_dir, lbl_fn)
            img_path = os.path.join(img_dir, img_fn)

            # Extract video name and frame from filename: {vname}_f{idx:05d}
            parts = base.rsplit("_f", 1)
            if len(parts) != 2:
                continue
            vname = parts[0]
            frame_idx = int(parts[1])

            report["total_images"] += 1

            if vname not in report["per_video"]:
                report["per_video"][vname] = {
                    "split": split,
                    "images": 0,
                    "bboxes": 0,
                    "confidences": [],
                    "tiny_filtered": 0,
                    "oob_filtered": 0,
                }

            vr = report["per_video"][vname]
            vr["images"] += 1

            # Read label
            if not os.path.exists(lbl_path):
                continue

            with open(lbl_path, "r") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]

            img = cv2.imread(img_path)
            if img is None:
                continue
            h, w = img.shape[:2]
            img_area = h * w

            # Look up confidences from bbox JSON
            vdata = bbox_data.get(vname)
            frame_confs = {}
            if vdata:
                for fdata in vdata["frames"]:
                    if fdata["frame_idx"] == frame_idx:
                        for p in fdata["persons"]:
                            key = (round(p["x1"]), round(p["y1"]))
                            frame_confs[key] = p["confidence"]
                        break

            good_lines = []
            for line in lines:
                parts_l = line.split()
                if len(parts_l) != 5:
                    continue

                cls, cx, cy, bw, bh = (
                    int(parts_l[0]),
                    float(parts_l[1]),
                    float(parts_l[2]),
                    float(parts_l[3]),
                    float(parts_l[4]),
                )

                # Denormalize
                px_w = bw * w
                px_h = bh * h
                bbox_area = px_w * px_h

                report["total_bboxes"] += 1
                vr["bboxes"] += 1

                # Check tiny bbox
                if bbox_area < img_area * 0.01:
                    report["filtered_tiny"] += 1
                    vr["tiny_filtered"] += 1
                    continue

                # Check out-of-bounds (center too far from image)
                x1 = (cx - bw / 2) * w
                y1 = (cy - bh / 2) * h
                x2 = (cx + bw / 2) * w
                y2 = (cy + bh / 2) * h

                # Visible area
                vx1 = max(0, x1)
                vy1 = max(0, y1)
                vx2 = min(w, x2)
                vy2 = min(h, y2)
                visible_area = max(0, vx2 - vx1) * max(0, vy2 - vy1)
                if visible_area < bbox_area * 0.5:
                    report["filtered_oob"] += 1
                    vr["oob_filtered"] += 1
                    continue

                good_lines.append(line)

                # Find confidence for this bbox
                approx_key = (round(x1), round(y1))
                conf = frame_confs.get(approx_key, 0.0)
                if conf > 0:
                    vr["confidences"].append(conf)

            # If any lines were filtered, rewrite the label
            if len(good_lines) != len(lines):
                with open(lbl_path, "w") as f:
                    for gl in good_lines:
                        f.write(gl + "\n")

                # Remove image if no labels left
                if not good_lines:
                    os.remove(lbl_path)
                    os.remove(img_path)
                    vr["images"] -= 1

    # Confidence stats per video
    for vname, vr in report["per_video"].items():
        confs = vr["confidences"]
        if confs:
            vr["conf_stats"] = {
                "min": round(min(confs), 4),
                "max": round(max(confs), 4),
                "median": round(statistics.median(confs), 4),
                "mean": round(statistics.mean(confs), 4),
            }
        else:
            vr["conf_stats"] = {"min": 0, "max": 0, "median": 0, "mean": 0}

        # Flag low-conf val items
        if vr["split"] == "val":
            low = [c for c in confs if c < 0.6]
            if low:
                report["low_conf_val"].append(
                    {
                        "video": vname,
                        "count": len(low),
                        "total": len(confs),
                        "min_conf": round(min(low), 4),
                    }
                )

        # Remove raw confidences list (too large for report)
        del vr["confidences"]

    # Generate review images for Y (fall) videos
    _generate_fall_review_images(dataset_dir, bbox_data, review_dir)

    return report


def _generate_fall_review_images(dataset_dir, bbox_data, review_dir):
    """Create review images: fall video frames with bbox overlays."""
    fall_review_dir = os.path.join(review_dir, "fall_frames")
    os.makedirs(fall_review_dir, exist_ok=True)

    count = 0
    for split in ["train", "val"]:
        img_dir = os.path.join(dataset_dir, "images", split)
        lbl_dir = os.path.join(dataset_dir, "labels", split)
        if not os.path.isdir(img_dir):
            continue

        for img_fn in sorted(os.listdir(img_dir)):
            if not img_fn.endswith(".jpg"):
                continue
            if not img_fn.startswith("Y_"):
                continue

            base = os.path.splitext(img_fn)[0]
            lbl_path = os.path.join(lbl_dir, base + ".txt")
            img_path = os.path.join(img_dir, img_fn)

            img = cv2.imread(img_path)
            if img is None:
                continue
            h, w = img.shape[:2]

            # Draw bboxes
            if os.path.exists(lbl_path):
                with open(lbl_path, "r") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) != 5:
                            continue
                        _, cx, cy, bw, bh = (
                            int(parts[0]),
                            float(parts[1]),
                            float(parts[2]),
                            float(parts[3]),
                            float(parts[4]),
                        )
                        x1 = int((cx - bw / 2) * w)
                        y1 = int((cy - bh / 2) * h)
                        x2 = int((cx + bw / 2) * w)
                        y2 = int((cy + bh / 2) * h)

                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)
                        cv2.putText(
                            img,
                            "person",
                            (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.0,
                            (0, 255, 0),
                            2,
                        )

            # Add label text
            parts = base.rsplit("_f", 1)
            vname = parts[0] if len(parts) == 2 else base
            frame_idx = int(parts[1]) if len(parts) == 2 else 0
            cv2.putText(
                img,
                f"{vname} frame={frame_idx} [{split}]",
                (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5,
                (0, 0, 255),
                3,
            )

            # Resize for review (max 1280 width)
            if w > 1280:
                scale = 1280 / w
                img = cv2.resize(img, (1280, int(h * scale)))

            out_path = os.path.join(fall_review_dir, img_fn)
            cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            count += 1

    print(f"  Review images for fall videos: {count} images in {fall_review_dir}")


def print_report(report):
    """Print human-readable QC report."""
    print(f"\n{'='*60}")
    print("QUALITY CHECK REPORT")
    print(f"{'='*60}")
    print(f"Total images checked: {report['total_images']}")
    print(f"Total bboxes checked: {report['total_bboxes']}")
    print(f"Filtered (tiny <1%):  {report['filtered_tiny']}")
    print(f"Filtered (OOB >50%):  {report['filtered_oob']}")
    kept = report["total_bboxes"] - report["filtered_tiny"] - report["filtered_oob"]
    print(f"Kept bboxes:          {kept}")

    print(f"\nPer-video breakdown:")
    for vname, vr in sorted(report["per_video"].items()):
        cs = vr["conf_stats"]
        print(
            f"  {vname} [{vr['split']}]: "
            f"{vr['images']} imgs, {vr['bboxes']} bboxes, "
            f"tiny={vr['tiny_filtered']}, oob={vr['oob_filtered']}, "
            f"conf={cs['min']:.2f}/{cs['median']:.2f}/{cs['max']:.2f}"
        )

    if report["low_conf_val"]:
        print(f"\nLow-confidence val bboxes (conf < 0.6):")
        for lc in report["low_conf_val"]:
            print(
                f"  {lc['video']}: {lc['count']}/{lc['total']} bboxes, "
                f"min_conf={lc['min_conf']:.4f}"
            )


def main():
    parser = argparse.ArgumentParser(description="QC tool for person detection pseudo-labels")
    parser.add_argument(
        "--dataset_dir",
        type=str,
        default="storage/training/fall-detection/person-detect/dataset",
    )
    parser.add_argument(
        "--bbox_dir",
        type=str,
        default="storage/training/fall-detection/person-bbox",
    )
    parser.add_argument(
        "--review_dir",
        type=str,
        default="storage/training/fall-detection/person-detect/review",
    )
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    dataset_dir = os.path.join(project_root, args.dataset_dir) if not os.path.isabs(args.dataset_dir) else args.dataset_dir
    bbox_dir = os.path.join(project_root, args.bbox_dir) if not os.path.isabs(args.bbox_dir) else args.bbox_dir
    review_dir = os.path.join(project_root, args.review_dir) if not os.path.isabs(args.review_dir) else args.review_dir

    print(f"Dataset: {dataset_dir}")
    print(f"BBox data: {bbox_dir}")
    print(f"Review output: {review_dir}")

    # Load data
    bbox_data = load_bbox_jsons(bbox_dir)
    print(f"Loaded {len(bbox_data)} video bbox files")

    # Run QC
    report = qc_labels(dataset_dir, bbox_data, review_dir)

    # Print report
    print_report(report)

    # Save report
    report_path = os.path.join(review_dir, "review_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved: {report_path}")

    # After QC, recount actual images
    for split in ["train", "val"]:
        img_dir = os.path.join(dataset_dir, "images", split)
        if os.path.isdir(img_dir):
            count = len([f for f in os.listdir(img_dir) if f.endswith(".jpg")])
            print(f"  {split}: {count} images remaining after QC")


if __name__ == "__main__":
    main()
