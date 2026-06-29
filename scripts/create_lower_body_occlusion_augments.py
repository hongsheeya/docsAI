#!/usr/bin/env python3
"""Create occlusion augmentation videos without modifying originals.

The script reads posture/action videos from class directories or a manifest and
writes masked copies to a separate output root. It is intentionally conservative:
source files are never deleted, moved, or overwritten.

The original behavior is preserved: by default it creates fixed lower-body masks
from ``--ratios``. For more realistic blocked-body cases, enable staged random
profiles with ``--randomized-stages``.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DEFAULT_LABELS = ("stand", "walk", "run", "sit", "lie", "fall", "Y", "N")
DEFAULT_RANDOM_STAGE_PROFILES = (
    "lower_mild:0.68-0.78",
    "lower_moderate:0.55-0.68",
    "lower_severe:0.42-0.55",
    "vertical_left_mild:0.18-0.30",
    "vertical_left_moderate:0.30-0.45",
    "vertical_left_severe:0.45-0.58",
    "vertical_right_mild:0.18-0.30",
    "vertical_right_moderate:0.30-0.45",
    "vertical_right_severe:0.45-0.58",
)


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


def stable_unit(*parts) -> float:
    raw = "|".join(str(part) for part in parts).encode("utf-8", errors="ignore")
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def parse_range(raw: str):
    raw = str(raw or "").strip()
    if "-" not in raw:
        value = float(raw)
        return value, value
    lo, hi = raw.split("-", 1)
    lo_f = float(lo.strip())
    hi_f = float(hi.strip())
    return min(lo_f, hi_f), max(lo_f, hi_f)


def parse_stage_profiles(raw: str) -> List[Dict]:
    profiles = []
    for item in str(raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            name, span = item.split(":", 1)
        else:
            name, span = item, "0.55-0.70"
        name = name.strip()
        lo, hi = parse_range(span)
        kind = "vertical" if name.startswith("vertical_") else "lower"
        side = ""
        if kind == "vertical":
            side = "right" if "right" in name else "left"
        profiles.append({
            "name": name,
            "kind": kind,
            "side": side,
            "lo": max(0.0, min(1.0, lo)),
            "hi": max(0.0, min(1.0, hi)),
        })
    return profiles


def safe_output_name(src: Path, label: str, spec: Dict, variant: int) -> str:
    stem = src.stem.replace(" ", "_")
    if spec.get("kind") == "vertical":
        side = str(spec.get("side") or "left")
        width_key = str(int(round(float(spec.get("extent", 0.0)) * 100)))
        return f"{stem}__vocc_{side}_w{width_key}_v{variant:02d}.mp4"
    ratio_key = str(int(round(float(spec.get("ratio", 0.0)) * 100)))
    profile = str(spec.get("name") or "lower")
    return f"{stem}__lbocc_{profile}_r{ratio_key}_v{variant:02d}.mp4"


def _fill_region(frame, region, color: str):
    import cv2

    if region.size <= 0:
        return region
    if color == "blur":
        return cv2.GaussianBlur(region, (35, 35), 0)
    fill = (18, 18, 18) if color == "dark" else (0, 0, 0)
    region[:] = fill
    return region


def mask_frame(frame, spec: Dict, color: str):
    height, width = frame.shape[:2]
    if spec.get("kind") == "vertical":
        extent = max(0.05, min(0.95, float(spec.get("extent", 0.35) or 0.35)))
        side = str(spec.get("side") or "left")
        if side == "right":
            x0 = max(0, min(width - 1, int(width * (1.0 - extent))))
            frame[0:height, x0:width] = _fill_region(frame, frame[0:height, x0:width], color)
        elif side == "center":
            mask_w = int(width * extent)
            x0 = max(0, min(width - 1, int((width - mask_w) / 2)))
            x1 = max(x0 + 1, min(width, x0 + mask_w))
            frame[0:height, x0:x1] = _fill_region(frame, frame[0:height, x0:x1], color)
        else:
            x1 = max(1, min(width, int(width * extent)))
            frame[0:height, 0:x1] = _fill_region(frame, frame[0:height, 0:x1], color)
    else:
        ratio = max(0.0, min(0.98, float(spec.get("ratio", 0.62) or 0.62)))
        y0 = max(0, min(height - 1, int(height * ratio)))
        frame[y0:height, 0:width] = _fill_region(frame, frame[y0:height, 0:width], color)
    return frame


def augment_video(src: Path, dst: Path, spec: Dict, color: str, max_frames: int) -> Dict:
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
            writer.write(mask_frame(frame, spec=spec, color=color))
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
        "occlusion_kind": spec.get("kind") or "lower",
        "occlusion_profile": spec.get("name") or "",
        "mask_start_ratio": spec.get("ratio"),
        "vertical_side": spec.get("side") or "",
        "vertical_extent": spec.get("extent"),
        "mask_color": color,
    }


def build_specs(src: Path, args, ratios: List[float]) -> List[Dict]:
    if not args.randomized_stages:
        return [
            {"kind": "lower", "name": "fixed", "ratio": ratio, "variant": idx}
            for idx, ratio in enumerate(ratios, start=1)
        ]

    profiles = parse_stage_profiles(args.stage_profiles)
    specs: List[Dict] = []
    for profile_idx, profile in enumerate(profiles, start=1):
        for variant in range(1, max(1, args.variants_per_stage) + 1):
            unit = stable_unit(args.seed, src, profile["name"], variant)
            value = profile["lo"] + (profile["hi"] - profile["lo"]) * unit
            spec = dict(profile)
            spec["variant"] = len(specs) + 1
            if profile["kind"] == "vertical":
                spec["extent"] = value
            else:
                spec["ratio"] = value
            specs.append(spec)
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description="Body occlusion video augmentation")
    parser.add_argument("--input-root", default="", help="Root with class subdirectories")
    parser.add_argument("--manifest", default="", help="JSON/JSONL entries with path,label,group")
    parser.add_argument("--output-root", required=True, help="Separate output root for augmented videos")
    parser.add_argument("--labels", default=",".join(DEFAULT_LABELS), help="Comma-separated class names")
    parser.add_argument("--ratios", default="0.55,0.62,0.70", help="Mask start ratios from top of frame")
    parser.add_argument(
        "--randomized-stages",
        action="store_true",
        help="Use staged random lower/vertical occlusion profiles instead of fixed ratios",
    )
    parser.add_argument(
        "--stage-profiles",
        default=",".join(DEFAULT_RANDOM_STAGE_PROFILES),
        help="Comma profiles like lower_mild:0.68-0.78,vertical_left_moderate:0.28-0.44",
    )
    parser.add_argument("--variants-per-stage", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
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
        for spec in build_specs(src, args, ratios):
            variant = int(spec.get("variant") or 1)
            dst = output_root / label / safe_output_name(src, label, spec, variant)
            meta = {
                "source": str(src),
                "output": str(dst),
                "label": label,
                "group": f"{group}:occlusion",
                "augmentation": "vertical_body_occlusion" if spec.get("kind") == "vertical" else "lower_body_occlusion",
                "occlusion_kind": spec.get("kind"),
                "occlusion_profile": spec.get("name"),
                "mask_start_ratio": spec.get("ratio"),
                "vertical_side": spec.get("side") or "",
                "vertical_extent": spec.get("extent"),
                "mask_color": args.mask_color,
            }
            if not args.dry_run:
                try:
                    meta.update(augment_video(src, dst, spec, args.mask_color, args.max_frames))
                    dst.with_suffix(dst.suffix + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as exc:
                    errors.append({"path": str(src), "spec": spec, "reason": str(exc)})
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
        "randomized_stages": bool(args.randomized_stages),
        "stage_profiles": args.stage_profiles,
        "variants_per_stage": args.variants_per_stage,
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
