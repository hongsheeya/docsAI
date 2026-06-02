#!/usr/bin/env python3
"""Create lower-body occlusion augmentation videos without modifying originals.

The script reads posture/action videos from class directories or a manifest and
writes masked copies to a separate output root. It is intentionally conservative:
source files are never deleted, moved, or overwritten.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DEFAULT_LABELS = ("stand", "walk", "run", "sit", "lie", "fall", "Y", "N")


def load_manifest(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    if not path:
        return rows
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("entries") or data.get("rows") or data.get("items") or [])
    if isinstance(data, list):
        return data
    return rows


def discover_class_videos(input_root: Path, labels: Iterable[str], limit_per_class: int) -> List[Dict]:
    entries: List[Dict] = []
    for label in labels:
        class_dir = input_root / label
        if not class_dir.exists():
            continue
        count = 0
        for path in sorted(class_dir.rglob("*")):
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            entries.append({"path": str(path), "label": label, "group": path.stem})
            count += 1
            if limit_per_class > 0 and count >= limit_per_class:
                break
    return entries


def safe_output_name(src: Path, label: str, ratio: float, variant: int) -> str:
    ratio_key = str(int(round(ratio * 100)))
    stem = src.stem.replace(" ", "_")
    return f"{stem}__lbocc_r{ratio_key}_v{variant:02d}.mp4"


def mask_frame(frame, ratio: float, color: str):
    import cv2

    height, width = frame.shape[:2]
    y0 = max(0, min(height - 1, int(height * ratio)))
    if color == "blur":
        region = frame[y0:height, 0:width]
        if region.size > 0:
            blurred = cv2.GaussianBlur(region, (35, 35), 0)
            frame[y0:height, 0:width] = blurred
    else:
        fill = (18, 18, 18) if color == "dark" else (0, 0, 0)
        frame[y0:height, 0:width] = fill
    return frame


def augment_video(src: Path, dst: Path, ratio: float, color: str, max_frames: int) -> Dict:
    import cv2

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {src}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError(f"invalid video size: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(dst), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"cannot write video: {dst}")

    written = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            writer.write(mask_frame(frame, ratio=ratio, color=color))
            written += 1
            if max_frames > 0 and written >= max_frames:
                break
    finally:
        cap.release()
        writer.release()

    return {
        "source": str(src),
        "output": str(dst),
        "fps": float(fps),
        "width": width,
        "height": height,
        "source_frames": frame_count,
        "written_frames": written,
        "mask_start_ratio": ratio,
        "mask_color": color,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lower-body occlusion video augmentation")
    parser.add_argument("--input-root", default="", help="Root with class subdirectories")
    parser.add_argument("--manifest", default="", help="JSON/JSONL entries with path,label,group")
    parser.add_argument("--output-root", required=True, help="Separate output root for augmented videos")
    parser.add_argument("--labels", default=",".join(DEFAULT_LABELS), help="Comma-separated class names")
    parser.add_argument("--ratios", default="0.55,0.62,0.70", help="Mask start ratios from top of frame")
    parser.add_argument("--limit-per-class", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=0, help="Debug limit; 0 means full video")
    parser.add_argument("--mask-color", choices=("black", "dark", "blur"), default="dark")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    labels = [item.strip() for item in args.labels.split(",") if item.strip()]
    ratios = [float(item.strip()) for item in args.ratios.split(",") if item.strip()]
    output_root = Path(args.output_root)

    entries: List[Dict] = []
    if args.manifest:
        entries.extend(load_manifest(Path(args.manifest)))
    if args.input_root:
        entries.extend(discover_class_videos(Path(args.input_root), labels, args.limit_per_class))

    if not entries:
        raise SystemExit("no input videos found")

    manifest_rows = []
    errors = []
    for entry in entries:
        src = Path(str(entry.get("path") or entry.get("video") or ""))
        label = str(entry.get("label") or entry.get("posture") or "").strip() or "unknown"
        group = str(entry.get("group") or entry.get("group_id") or src.stem)
        if not src.is_file() or src.suffix.lower() not in VIDEO_EXTENSIONS:
            errors.append({"path": str(src), "reason": "not a video file"})
            continue
        for variant, ratio in enumerate(ratios, start=1):
            dst = output_root / label / safe_output_name(src, label, ratio, variant)
            meta = {
                "source": str(src),
                "output": str(dst),
                "label": label,
                "group": f"{group}:lower_body_occlusion",
                "augmentation": "lower_body_occlusion",
                "mask_start_ratio": ratio,
                "mask_color": args.mask_color,
            }
            if not args.dry_run:
                try:
                    meta.update(augment_video(src, dst, ratio, args.mask_color, args.max_frames))
                    dst.with_suffix(dst.suffix + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as exc:
                    errors.append({"path": str(src), "ratio": ratio, "reason": str(exc)})
                    continue
            manifest_rows.append(meta)

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "manifest.jsonl"
    summary_path = output_root / "summary.json"
    if not args.dry_run:
        with manifest_path.open("w", encoding="utf-8") as file:
            for row in manifest_rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "input_count": len(entries),
        "output_count": len(manifest_rows),
        "labels": labels,
        "ratios": ratios,
        "output_root": str(output_root),
        "manifest_path": str(manifest_path),
        "errors": errors[:100],
        "dry_run": bool(args.dry_run),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
