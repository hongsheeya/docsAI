#!/usr/bin/env python3
"""Quick A/B validation for the facial auxiliary score on existing uploads.

This is intentionally small and presentation-oriented: it replays a balanced
set of labeled uploaded clips, compares fall decision before/after facial
auxiliary score, and writes a compact JSON summary.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import time
from pathlib import Path


PROJECT = Path("/opt/app/project/main")
UPLOAD_DIR = Path("/opt/app/_appdata/data/uploads/fall-detection-prototype")
OUT_PATH = Path(
    os.environ.get(
        "FACIAL_AUX_OUT_PATH",
        str(PROJECT / "outputs" / "facial_aux_validation" / "quick_facial_aux_ab_20260601.json"),
    )
)


def infer_label(name: str) -> int | None:
    upper = name.upper()
    if "_FY_" in upper or "_BY_" in upper or "_SY_" in upper:
        return 1
    if "_N_" in upper:
        return 0
    return None


def normalize_origin(name: str) -> str:
    match = re.search(r"((?:\d{5}|\d{8,})_[A-Z]_[A-Z]_(?:N|FY|BY|SY)_C\d\.mp4)$", name, re.I)
    return match.group(1) if match else name


def load_video_analysis():
    module_path = PROJECT / "src" / "model" / "struct" / "video_analysis.py"
    spec = importlib.util.spec_from_file_location("quick_video_analysis", module_path)
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


def collect_candidates() -> list[dict]:
    rows = []
    seen = set()
    for meta_path in sorted(UPLOAD_DIR.glob("*.mp4.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        saved = str(meta.get("saved_name") or meta_path.name[:-5])
        video_path = UPLOAD_DIR / saved
        if not video_path.exists():
            continue
        origin = normalize_origin(saved)
        if origin in seen:
            continue
        label = infer_label(saved)
        if label is None:
            continue
        seen.add(origin)
        old = meta.get("last_analysis") or {}
        rows.append(
            {
                "video_path": str(video_path),
                "saved_name": saved,
                "origin_name": origin,
                "label": label,
                "old_risk": float(old.get("risk_score") or 0.0),
                "old_pred": 1 if old.get("fall_detected") else 0,
            }
        )
    return rows


def choose_sample(rows: list[dict], per_label: int) -> list[dict]:
    positives = [r for r in rows if r["label"] == 1]
    negatives = [r for r in rows if r["label"] == 0]
    # Positives: include easy and hard misses. Negatives: include hard high-risk nonfalls.
    pos_high = sorted(positives, key=lambda r: r["old_risk"], reverse=True)[: max(1, per_label // 2)]
    pos_low = sorted(positives, key=lambda r: r["old_risk"])[: per_label - len(pos_high)]
    neg_hard = sorted(negatives, key=lambda r: r["old_risk"], reverse=True)[:per_label]
    sample = []
    seen = set()
    for item in pos_high + pos_low + neg_hard:
        if item["origin_name"] not in seen:
            sample.append(item)
            seen.add(item["origin_name"])
    return sample


def metrics(rows: list[dict], pred_key: str) -> dict:
    tp = sum(1 for r in rows if r["label"] == 1 and r[pred_key] == 1)
    tn = sum(1 for r in rows if r["label"] == 0 and r[pred_key] == 0)
    fp = sum(1 for r in rows if r["label"] == 0 and r[pred_key] == 1)
    fn = sum(1 for r in rows if r["label"] == 1 and r[pred_key] == 0)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall / max(precision + recall, 1e-9)) if (precision + recall) else 0.0
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


def main() -> int:
    os.environ.setdefault("FACIAL_AUX_UPLOAD_CHUNK_FRAMES", "3")
    os.environ.setdefault("FACIAL_AUX_REALTIME_DRIVER", "true")
    per_label = int(os.environ.get("FACIAL_AUX_QUICK_PER_LABEL", "6"))
    rows = collect_candidates()
    sample = choose_sample(rows, per_label=per_label)
    analyzer = load_video_analysis()
    results = []
    started = time.time()

    for idx, item in enumerate(sample, start=1):
        label_name = "fall" if item["label"] == 1 else "nonfall"
        print(f"[{idx}/{len(sample)}] {label_name} {item['origin_name']} old_risk={item['old_risk']:.4f}", flush=True)
        t0 = time.time()
        try:
            result = analyzer._infer_rf_dual(
                item["video_path"],
                filename=item["origin_name"],
                analysis_profile="balanced",
                input_source="upload",
            )
            facial = result.get("facial_state") or {}
            threshold = float((result.get("fall_result") or {}).get("effective_threshold") or 0.455)
            post_score = float(result.get("risk_score") or 0.0)
            pre_score = float(facial.get("pre_fall_score", post_score) or post_score)
            pre_pred = 1 if pre_score >= threshold else 0
            post_pred = 1 if post_score >= threshold else 0
            results.append(
                {
                    **item,
                    "ok": True,
                    "threshold": round(threshold, 4),
                    "pre_score": round(pre_score, 4),
                    "post_score": round(post_score, 4),
                    "delta": round(post_score - pre_score, 4),
                    "pre_pred": pre_pred,
                    "post_pred": post_pred,
                    "pipeline_pred": 1 if bool(result.get("fall_detected")) else 0,
                    "facial_applied": bool(facial.get("applied")),
                    "facial_available": bool(facial.get("available")),
                    "facial_reason": facial.get("reason", ""),
                    "facial_label": facial.get("label", ""),
                    "facial_support_score": round(float(facial.get("support_score") or 0.0), 4),
                    "facial_blocked_by": facial.get("blocked_by", ""),
                    "posture_label": result.get("posture_label", ""),
                    "elapsed_sec": round(time.time() - t0, 3),
                }
            )
        except Exception as exc:
            results.append({**item, "ok": False, "error": str(exc), "elapsed_sec": round(time.time() - t0, 3)})
            print(f"  error: {exc}", flush=True)

    valid = [r for r in results if r.get("ok")]
    changed = [r for r in valid if r["pre_pred"] != r["post_pred"]]
    harmful = [r for r in changed if r["post_pred"] != r["label"] and r["pre_pred"] == r["label"]]
    helpful = [r for r in changed if r["post_pred"] == r["label"] and r["pre_pred"] != r["label"]]
    applied = [r for r in valid if r.get("facial_applied")]
    support = [r for r in valid if float(r.get("facial_support_score") or 0.0) > 0]
    blocked = [r for r in valid if r.get("facial_blocked_by")]

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": "Quick replay of labeled existing uploads; compare pre_fall_score vs post facial-aux score at the same threshold.",
        "sample_size": len(valid),
        "requested_per_label": per_label,
        "label_count": {
            "fall": sum(1 for r in valid if r["label"] == 1),
            "nonfall": sum(1 for r in valid if r["label"] == 0),
        },
        "before_facial": metrics(valid, "pre_pred"),
        "after_facial": metrics(valid, "post_pred"),
        "facial_applied_count": len(applied),
        "facial_support_count": len(support),
        "facial_blocked_count": len(blocked),
        "decision_changed_count": len(changed),
        "helpful_changes": len(helpful),
        "harmful_changes": len(harmful),
        "avg_score_delta_when_applied": round(sum(r["delta"] for r in applied) / max(len(applied), 1), 4),
        "elapsed_sec": round(time.time() - started, 3),
        "results": results,
        "changed": changed,
        "helpful": helpful,
        "harmful": harmful,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in [
        "sample_size", "label_count", "before_facial", "after_facial",
        "facial_applied_count", "facial_support_count", "facial_blocked_count",
        "decision_changed_count", "helpful_changes", "harmful_changes", "avg_score_delta_when_applied",
        "elapsed_sec",
    ]}, ensure_ascii=False, indent=2))
    print(f"saved {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
