#!/usr/bin/env python3
"""
FN-0012: Extract person bounding boxes from fall-detection videos
using pretrained YOLO11n (COCO person=class 0) with ByteTrack tracking.

Processes all readable mp4 videos in /낙상영상/{Y,N}/ and outputs
per-video JSON files with frame-level person bbox + track_id data.

Usage:
    cd /opt/app/project/main
    python scripts/extract_person_bbox.py [--conf 0.3] [--imgsz 640]
"""

import argparse
import json
import os
import sys
import time
import unicodedata

import cv2


def find_video_dir():
    """Find 낙상영상 directory handling NFD/NFC unicode."""
    base = "/opt/app"
    for entry in os.listdir(base):
        nfc = unicodedata.normalize("NFC", entry)
        if nfc == "낙상영상":
            return os.path.join(base, entry)
    return None


def get_video_files(video_dir):
    """Get all readable mp4 files from Y/ and N/ subdirectories."""
    videos = []
    for label in ["Y", "N"]:
        subdir = os.path.join(video_dir, label)
        if not os.path.isdir(subdir):
            continue
        for fn in sorted(os.listdir(subdir)):
            if not fn.lower().endswith(".mp4"):
                continue
            fp = os.path.join(subdir, fn)
            cap = cv2.VideoCapture(fp)
            ok = cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0
            fps_val = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            if ok and fps_val > 0:
                video_name = f"{label}_{os.path.splitext(fn)[0]}"
                videos.append(
                    {
                        "path": fp,
                        "name": video_name,
                        "label": label,
                        "filename": fn,
                    }
                )
            else:
                print(f"  [SKIP] {label}/{fn} - not readable")
    return videos


def extract_person_bboxes(model, video_info, conf_threshold=0.3, imgsz=640):
    """
    Extract person bboxes with ByteTrack tracking from a single video.
    Processes ALL frames for tracking continuity.
    """
    video_path = video_info["path"]
    label = video_info["label"]

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    print(f"  Resolution: {width}x{height}, FPS: {fps:.1f}, Frames: {total_frames}")

    # Use model.track() with video source — streams frame-by-frame (memory safe)
    results = model.track(
        source=video_path,
        stream=True,
        persist=True,
        classes=[0],  # person only
        conf=conf_threshold,
        imgsz=imgsz,
        tracker="bytetrack.yaml",
        verbose=False,
    )

    frames_data = []
    t0 = time.time()

    for frame_idx, result in enumerate(results):
        boxes = result.boxes
        frame_bboxes = []

        if boxes is not None and len(boxes) > 0:
            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i])
                track_id = int(boxes.id[i]) if boxes.id is not None else -1

                frame_bboxes.append(
                    {
                        "track_id": track_id,
                        "x1": round(x1, 1),
                        "y1": round(y1, 1),
                        "x2": round(x2, 1),
                        "y2": round(y2, 1),
                        "confidence": round(conf, 4),
                    }
                )

        frames_data.append(
            {
                "frame_idx": frame_idx,
                "timestamp": round(frame_idx / fps, 3) if fps > 0 else 0,
                "persons": frame_bboxes,
            }
        )

        # Progress every 100 frames
        if (frame_idx + 1) % 100 == 0 or frame_idx == total_frames - 1:
            elapsed = time.time() - t0
            fps_proc = (frame_idx + 1) / elapsed if elapsed > 0 else 0
            n_det = sum(len(f["persons"]) for f in frames_data[max(0, frame_idx - 99) :])
            print(
                f"    Frame {frame_idx + 1}/{total_frames} "
                f"({fps_proc:.1f} proc-fps, last100 dets={n_det})"
            )

    elapsed = time.time() - t0

    # Summary statistics
    total_bboxes = sum(len(f["persons"]) for f in frames_data)
    frames_with_person = sum(1 for f in frames_data if len(f["persons"]) > 0)
    track_ids = set()
    for f in frames_data:
        for p in f["persons"]:
            if p["track_id"] >= 0:
                track_ids.add(p["track_id"])

    result_data = {
        "video_name": video_info["name"],
        "filename": video_info["filename"],
        "label": label,
        "video_meta": {
            "width": width,
            "height": height,
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "duration_sec": round(total_frames / fps, 2) if fps > 0 else 0,
        },
        "detection_config": {
            "model": "yolo11n.pt",
            "imgsz": imgsz,
            "conf_threshold": conf_threshold,
            "tracker": "bytetrack",
            "classes": [0],
        },
        "summary": {
            "total_bboxes": total_bboxes,
            "frames_with_person": frames_with_person,
            "frames_total": total_frames,
            "unique_tracks": len(track_ids),
            "track_ids": sorted(track_ids),
            "processing_time_sec": round(elapsed, 2),
            "processing_fps": round(total_frames / elapsed, 2) if elapsed > 0 else 0,
        },
        "frames": frames_data,
    }

    print(
        f"    Done: {total_bboxes} bboxes across {frames_with_person}/{total_frames} frames, "
        f"{len(track_ids)} unique tracks, {elapsed:.1f}s"
    )

    return result_data


def main():
    parser = argparse.ArgumentParser(
        description="Extract person bboxes from fall-detection videos"
    )
    parser.add_argument(
        "--video_dir", type=str, default=None, help="Path to 낙상영상 directory"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="storage/training/fall-detection/person-bbox",
        help="Output directory for bbox JSON files",
    )
    parser.add_argument(
        "--model", type=str, default="yolo11n.pt", help="YOLO detection model path"
    )
    parser.add_argument(
        "--conf", type=float, default=0.3, help="Confidence threshold"
    )
    parser.add_argument(
        "--imgsz", type=int, default=640, help="YOLO inference image size"
    )
    parser.add_argument(
        "--single", type=str, default=None, help="Process single video (e.g. Y/00001)"
    )
    args = parser.parse_args()

    # --- Resolve paths ---
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    video_dir = args.video_dir or find_video_dir()
    if video_dir is None or not os.path.isdir(video_dir):
        print("ERROR: 낙상영상 directory not found")
        sys.exit(1)
    print(f"Video directory: {video_dir}")

    output_dir = (
        os.path.join(project_root, args.output_dir)
        if not os.path.isabs(args.output_dir)
        else args.output_dir
    )
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")

    model_path = args.model
    if not os.path.isabs(model_path):
        model_path = os.path.join(project_root, model_path)
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        sys.exit(1)

    # --- Load model ---
    print(f"Loading model: {model_path}")
    from ultralytics import YOLO

    model = YOLO(model_path)
    print(f"Model loaded: {len(model.names)} classes, task={model.task}")

    # --- Collect videos ---
    videos = get_video_files(video_dir)
    print(
        f"\nFound {len(videos)} readable videos "
        f"(Y: {sum(1 for v in videos if v['label']=='Y')}, "
        f"N: {sum(1 for v in videos if v['label']=='N')})"
    )

    if not videos:
        print("No videos found!")
        sys.exit(1)

    # Optional: single video mode
    if args.single:
        parts = args.single.replace("\\", "/").split("/")
        if len(parts) == 2:
            lbl, prefix = parts
            videos = [v for v in videos if v["label"] == lbl and v["name"].startswith(prefix)]
        else:
            videos = [v for v in videos if v["name"].startswith(args.single)]
        if not videos:
            print(f"No video matching --single={args.single}")
            sys.exit(1)
        print(f"Single mode: processing {len(videos)} video(s)")

    # --- Process ---
    all_summaries = []
    total_start = time.time()

    for i, video_info in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] {video_info['label']}/{video_info['filename']}")

        result = extract_person_bboxes(
            model, video_info, conf_threshold=args.conf, imgsz=args.imgsz
        )

        # Save per-video JSON
        out_path = os.path.join(output_dir, f"{video_info['name']}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        file_size = os.path.getsize(out_path) / 1024
        print(f"    Saved: {out_path} ({file_size:.0f} KB)")

        all_summaries.append(
            {
                "video_name": result["video_name"],
                "label": result["label"],
                "filename": result["filename"],
                "total_bboxes": result["summary"]["total_bboxes"],
                "frames_with_person": result["summary"]["frames_with_person"],
                "frames_total": result["summary"]["frames_total"],
                "unique_tracks": result["summary"]["unique_tracks"],
                "processing_time_sec": result["summary"]["processing_time_sec"],
            }
        )

    total_elapsed = time.time() - total_start

    # --- Save manifest ---
    manifest = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_videos": len(videos),
        "total_processing_time_sec": round(total_elapsed, 2),
        "detection_config": {
            "model": "yolo11n.pt",
            "imgsz": args.imgsz,
            "conf_threshold": args.conf,
            "tracker": "bytetrack",
        },
        "videos": all_summaries,
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"COMPLETE: {len(videos)} videos in {total_elapsed:.1f}s")
    print(f"Manifest: {manifest_path}")
    total_bbox = sum(s["total_bboxes"] for s in all_summaries)
    total_tracks = sum(s["unique_tracks"] for s in all_summaries)
    print(f"Total: {total_bbox} bboxes, {total_tracks} tracks")
    for s in all_summaries:
        print(
            f"  {s['label']}/{s['video_name']}: "
            f"{s['total_bboxes']} bboxes, {s['unique_tracks']} tracks, "
            f"{s['frames_with_person']}/{s['frames_total']} frames"
        )


if __name__ == "__main__":
    main()
