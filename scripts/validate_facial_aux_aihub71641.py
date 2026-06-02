#!/usr/bin/env python3
"""Balanced A/B validation for FacialRisk-Aux on AI-Hub 71641 videos.

The earlier quick validation uses only previously uploaded clips. This script
samples the larger AI-Hub 71641 fall/non-fall video pool and writes checkpointed
results after every clip so long runs can be monitored or resumed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import random
import re
import time
from pathlib import Path
from typing import Any


PROJECT = Path("/opt/app/project/main")
DATASET_ROOTS = [
    Path("/opt/app/datasets/fall_classification/aihubs_71641/extracted_retry_20260511/영상"),
    Path("/opt/app/datasets/fall_classification/aihubs_71641/extracted/영상"),
]
OUT_PATH = Path(
    os.environ.get(
        "FACIAL_AUX_OUT_PATH",
        str(PROJECT / "outputs" / "facial_aux_validation" / "aihub71641_facial_aux_ab_20260601.json"),
    )
)
VIDEO_EXTS = {".mp4", ".webm", ".avi", ".mov", ".mkv"}


def load_video_analysis():
    module_path = PROJECT / "src" / "model" / "struct" / "video_analysis.py"
    spec = importlib.util.spec_from_file_location("aihub_facial_video_analysis", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)

    class _FS:
        @staticmethod
        def abspath(*parts):
            return str(PROJECT.joinpath(*parts)) if parts else str(PROJECT)

    class _Project:
        @staticmethod
        def fs():
            return _FS()

    class _Wiz:
        project = _Project()

    module.wiz = _Wiz()
    spec.loader.exec_module(module)
    module.wiz = _Wiz()
    return module.VideoAnalysis(None)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def round_float(value: Any, ndigits: int = 4, default: float = 0.0) -> float:
    return round(safe_float(value, default), ndigits)


def normalize_origin(path: Path) -> str:
    match = re.search(r"((?:\d{5}|\d{8,})_[A-Z]_[A-Z]_(?:N|FY|BY|SY)_C\d\.[a-z0-9]+)$", path.name, re.I)
    return match.group(1) if match else path.name


def infer_label(path: Path) -> int | None:
    text = str(path)
    if "/영상/Y/" in text:
        return 1
    if "/영상/N/" in text:
        return 0
    upper = path.name.upper()
    if "_FY_" in upper or "_BY_" in upper or "_SY_" in upper:
        return 1
    if "_N_" in upper:
        return 0
    return None


def stable_bucket(path: Path) -> str:
    name = path.stem.upper()
    # Example: 01533_O_E_N_C2 -> O_E_N_C2. This gives variety across places,
    # actions, fall type, and camera without needing label JSON parsing.
    parts = name.split("_")
    if len(parts) >= 5:
        return "_".join(parts[1:5])
    return path.parent.name


def collect_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in DATASET_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTS:
                continue
            label = infer_label(path)
            if label is None:
                continue
            origin = normalize_origin(path)
            key = f"{origin}:{path.stat().st_size}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "video_path": str(path),
                    "origin_name": origin,
                    "label": label,
                    "bucket": stable_bucket(path),
                    "bytes": path.stat().st_size,
                }
            )
    return rows


def choose_sample(rows: list[dict[str, Any]], per_label: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    sample: list[dict[str, Any]] = []
    for label in [1, 0]:
        label_rows = [row for row in rows if row["label"] == label]
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in label_rows:
            buckets.setdefault(str(row["bucket"]), []).append(row)
        bucket_names = sorted(buckets)
        for bucket in bucket_names:
            rng.shuffle(buckets[bucket])
        rng.shuffle(bucket_names)

        chosen: list[dict[str, Any]] = []
        while len(chosen) < per_label and bucket_names:
            progressed = False
            for bucket in list(bucket_names):
                if buckets[bucket]:
                    chosen.append(buckets[bucket].pop())
                    progressed = True
                    if len(chosen) >= per_label:
                        break
                if not buckets[bucket]:
                    bucket_names.remove(bucket)
            if not progressed:
                break
        sample.extend(chosen)
    rng.shuffle(sample)
    return sample


def metrics(rows: list[dict[str, Any]], pred_key: str) -> dict[str, Any]:
    tp = sum(1 for row in rows if row["label"] == 1 and row[pred_key] == 1)
    tn = sum(1 for row in rows if row["label"] == 0 and row[pred_key] == 0)
    fp = sum(1 for row in rows if row["label"] == 0 and row[pred_key] == 1)
    fn = sum(1 for row in rows if row["label"] == 1 and row[pred_key] == 0)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9) if precision + recall else 0.0
    accuracy = (tp + tn) / max(len(rows), 1)
    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def normalize_prediction_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row.get("ok"):
        return row
    threshold = safe_float(row.get("threshold"), 0.455)
    pre_score = safe_float(row.get("pre_score"), 0.0)
    post_score = safe_float(row.get("post_score"), pre_score)
    row["pre_pred"] = 1 if pre_score >= threshold else 0
    row["post_pred"] = 1 if post_score >= threshold else 0
    return row


def summarize(results: list[dict[str, Any]], started: float, sample: list[dict[str, Any]], pool: list[dict[str, Any]]) -> dict[str, Any]:
    for row in results:
        normalize_prediction_row(row)
    valid = [row for row in results if row.get("ok")]
    changed = [row for row in valid if row.get("pre_pred") != row.get("post_pred")]
    helpful = [row for row in changed if row.get("post_pred") == row.get("label") and row.get("pre_pred") != row.get("label")]
    harmful = [row for row in changed if row.get("post_pred") != row.get("label") and row.get("pre_pred") == row.get("label")]
    applied = [row for row in valid if row.get("facial_applied")]
    support = [row for row in valid if safe_float(row.get("facial_support_score")) > 0]
    blocked = [row for row in valid if row.get("facial_blocked_by")]
    label_count = {
        "fall": sum(1 for row in valid if row.get("label") == 1),
        "nonfall": sum(1 for row in valid if row.get("label") == 0),
    }
    pool_count = {
        "fall": sum(1 for row in pool if row.get("label") == 1),
        "nonfall": sum(1 for row in pool if row.get("label") == 0),
    }
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": "Balanced replay of AI-Hub 71641 videos; compare pre_fall_score vs post FacialRisk-Aux score at the same threshold.",
        "dataset_roots": [str(path) for path in DATASET_ROOTS],
        "pool_count": pool_count,
        "requested_sample_size": len(sample),
        "sample_size": len(valid),
        "label_count": label_count,
        "before_facial": metrics(valid, "pre_pred") if valid else {},
        "after_facial": metrics(valid, "post_pred") if valid else {},
        "facial_applied_count": len(applied),
        "facial_support_count": len(support),
        "facial_blocked_count": len(blocked),
        "decision_changed_count": len(changed),
        "helpful_changes": len(helpful),
        "harmful_changes": len(harmful),
        "avg_score_delta_when_applied": round(sum(safe_float(row.get("delta")) for row in applied) / max(len(applied), 1), 4),
        "error_count": sum(1 for row in results if not row.get("ok")),
        "elapsed_sec": round(time.time() - started, 3),
        "results": results,
        "changed": changed,
        "helpful": helpful,
        "harmful": harmful,
    }


def save_checkpoint(summary: dict[str, Any]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def compact_print(summary: dict[str, Any]) -> None:
    keys = [
        "requested_sample_size",
        "sample_size",
        "label_count",
        "before_facial",
        "after_facial",
        "facial_applied_count",
        "facial_support_count",
        "facial_blocked_count",
        "decision_changed_count",
        "helpful_changes",
        "harmful_changes",
        "error_count",
        "elapsed_sec",
    ]
    print(json.dumps({key: summary.get(key) for key in keys}, ensure_ascii=False, indent=2), flush=True)


def item_hash(item: dict[str, Any]) -> str:
    raw = f"{item['video_path']}|{item['label']}|{item['bytes']}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_existing_results() -> list[dict[str, Any]]:
    if os.environ.get("FACIAL_AUX_RESUME", "true").lower() not in {"1", "true", "yes"}:
        return []
    if not OUT_PATH.exists():
        return []
    try:
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("results")
    return rows if isinstance(rows, list) else []


def run_validation(sample: list[dict[str, Any]], pool: list[dict[str, Any]]) -> int:
    analyzer = load_video_analysis()
    started = time.time()
    results = load_existing_results()
    completed = {row.get("item_hash") for row in results if row.get("item_hash")}

    for idx, item in enumerate(sample, start=1):
        digest = item_hash(item)
        if digest in completed:
            continue
        label_name = "fall" if item["label"] == 1 else "nonfall"
        print(f"[{idx}/{len(sample)}] {label_name} {item['origin_name']} bucket={item['bucket']}", flush=True)
        t0 = time.time()
        try:
            result = analyzer._infer_rf_dual(
                item["video_path"],
                filename=item["origin_name"],
                analysis_profile="balanced",
                input_source="upload",
            )
            facial = result.get("facial_state") or {}
            fall_result = result.get("fall_result") or {}
            threshold = safe_float(fall_result.get("effective_threshold"), 0.455)
            post_score = safe_float(result.get("risk_score"), 0.0)
            pre_score = safe_float(facial.get("pre_fall_score"), post_score)
            pre_pred = 1 if pre_score >= threshold else 0
            post_pred = 1 if post_score >= threshold else 0
            row = {
                **item,
                "item_hash": digest,
                "ok": True,
                "threshold": round_float(threshold),
                "pre_score": round_float(pre_score),
                "post_score": round_float(post_score),
                "delta": round_float(post_score - pre_score),
                "pre_pred": pre_pred,
                "post_pred": post_pred,
                "pipeline_pred": 1 if bool(result.get("fall_detected")) else 0,
                "facial_applied": bool(facial.get("applied")),
                "facial_available": bool(facial.get("available")),
                "facial_reason": facial.get("reason", ""),
                "facial_label": facial.get("label", ""),
                "facial_support_score": round_float(facial.get("support_score")),
                "facial_blocked_by": facial.get("blocked_by", ""),
                "face_detected": bool(facial.get("face_detected")),
                "face_visible": bool(facial.get("face_visible")),
                "actual_face_ratio": round_float(facial.get("actual_face_ratio"), 5),
                "pose_head_roi_ratio": round_float(facial.get("pose_head_roi_ratio"), 5),
                "emotion_top": facial.get("emotion_top", ""),
                "emotion_confidence": round_float(facial.get("emotion_confidence")),
                "emotion_reliable": bool(facial.get("emotion_reliable")),
                "driver_state_top": facial.get("driver_state_top", ""),
                "driver_state_risk": round_float(facial.get("driver_state_risk")),
                "driver_state_reliable": bool(facial.get("driver_state_reliable")),
                "near_miss_rescue_candidate": bool(facial.get("near_miss_rescue_candidate")),
                "evidence_summary": facial.get("evidence_summary", ""),
                "posture_label": result.get("posture_label", ""),
                "elapsed_sec": round(time.time() - t0, 3),
            }
            results.append(row)
            print(
                "  "
                f"pre={row['pre_score']:.4f}/{row['pre_pred']} "
                f"post={row['post_score']:.4f}/{row['post_pred']} "
                f"facial={row['facial_label'] or '-'} applied={row['facial_applied']} "
                f"{row['elapsed_sec']:.1f}s",
                flush=True,
            )
        except Exception as exc:
            row = {
                **item,
                "item_hash": digest,
                "ok": False,
                "error": str(exc),
                "elapsed_sec": round(time.time() - t0, 3),
            }
            results.append(row)
            print(f"  error: {exc}", flush=True)
        summary = summarize(results, started, sample, pool)
        save_checkpoint(summary)
        completed.add(digest)

    summary = summarize(results, started, sample, pool)
    save_checkpoint(summary)
    compact_print(summary)
    print(f"saved {OUT_PATH}", flush=True)
    return 0


def main() -> int:
    os.environ.setdefault("FACIAL_AUX_UPLOAD_CHUNK_FRAMES", "3")
    os.environ.setdefault("FACIAL_AUX_REALTIME_DRIVER", "true")
    per_label = int(os.environ.get("FACIAL_AUX_SAMPLE_PER_LABEL", "50"))
    seed = int(os.environ.get("FACIAL_AUX_SAMPLE_SEED", "71641"))
    pool = collect_candidates()
    sample = choose_sample(pool, per_label=per_label, seed=seed)

    print(
        json.dumps(
            {
                "pool": {
                    "fall": sum(1 for row in pool if row["label"] == 1),
                    "nonfall": sum(1 for row in pool if row["label"] == 0),
                    "total": len(pool),
                },
                "sample": {
                    "fall": sum(1 for row in sample if row["label"] == 1),
                    "nonfall": sum(1 for row in sample if row["label"] == 0),
                    "total": len(sample),
                },
                "out": str(OUT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    if os.environ.get("FACIAL_AUX_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        return 0
    return run_validation(sample, pool)


if __name__ == "__main__":
    raise SystemExit(main())
