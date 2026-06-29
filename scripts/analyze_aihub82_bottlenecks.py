#!/usr/bin/env python3
"""Aggregate AI-Hub 82 facial model runs and write a bottleneck report.

This is intentionally lightweight so the continuous supervisor can refresh it
after every candidate run. It does not train; it explains why recent candidates
are not beating the active model and which recipe should be tried next.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT = Path("/opt/app/project/main")
FACIAL_ROOT = Path("/opt/app/storage/training/fall-detection/facial-state")
ACTIVE_SUMMARY = FACIAL_ROOT / "aihub82_facial_emotion_summary.json"
EXPERIMENT_ROOT = FACIAL_ROOT / "experiments" / "aihub82_continuous"
RUN_DIR = PROJECT / "outputs" / "continuous_training"
REPORT_JSON = RUN_DIR / "aihub82_bottleneck_report.json"
REPORT_MD = RUN_DIR / "aihub82_bottleneck_report.md"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        if value != value:
            return default
        return value
    except Exception:
        return default


def best_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    best = summary.get("best_metrics")
    if isinstance(best, dict):
        return best
    hist = summary.get("history")
    if isinstance(hist, list) and hist:
        return max(hist, key=lambda item: as_float((item or {}).get("macro_f1"), -1.0))
    return summary


def metric(summary: dict[str, Any], key: str = "macro_f1") -> float:
    metrics = best_metrics(summary)
    if "." in key:
        value: Any = metrics
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break
        return as_float(value)
    return as_float(metrics.get(key))


def selection_score(summary: dict[str, Any]) -> float:
    metrics = best_metrics(summary)
    return as_float(metrics.get("selection_score"), metric(summary))


def per_class(summary: dict[str, Any]) -> dict[str, Any]:
    return best_metrics(summary).get("per_class") or {}


def confusion_pairs(summary: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = best_metrics(summary)
    classes = list(summary.get("classes") or metrics.get("classes") or [])
    if not classes:
        classes = list((metrics.get("per_class") or {}).keys())
    confusion = metrics.get("confusion_matrix") or []
    pairs: list[dict[str, Any]] = []
    if not isinstance(confusion, list):
        return pairs
    for truth_idx, row in enumerate(confusion[: len(classes)]):
        if not isinstance(row, list):
            continue
        row_total = sum(int(v or 0) for v in row)
        if row_total <= 0:
            continue
        for pred_idx, count in enumerate(row[: len(classes)]):
            count = int(count or 0)
            if pred_idx == truth_idx or count <= 0:
                continue
            pairs.append(
                {
                    "truth": classes[truth_idx],
                    "pred": classes[pred_idx],
                    "count": count,
                    "rate": round(count / max(row_total, 1), 4),
                }
            )
    return sorted(pairs, key=lambda item: (item["rate"], item["count"]), reverse=True)


def run_name(path: Path) -> str:
    return path.parent.name


def recipe_name(label: str) -> str:
    parts = str(label or "").split("_")
    if parts and parts[0].isdigit():
        parts = parts[1:]
    if len(parts) > 2 and parts[-2].isdigit():
        parts = parts[:-2]
    return "_".join(parts) or str(label or "")


def load_runs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(EXPERIMENT_ROOT.glob("*/aihub82_facial_emotion_summary.json")):
        summary = read_json(path)
        if not summary:
            continue
        name = run_name(path)
        metrics = best_metrics(summary)
        distress = metrics.get("distress_binary") or {}
        rows.append(
            {
                "name": name,
                "recipe": recipe_name(name),
                "path": str(path),
                "mtime": path.stat().st_mtime,
                "macro_f1": round(metric(summary), 4),
                "accuracy": round(metric(summary, "accuracy"), 4),
                "selection_score": round(selection_score(summary), 4),
                "distress_f1": round(as_float(distress.get("f1")), 4),
                "distress_precision": round(as_float(distress.get("precision")), 4),
                "distress_recall": round(as_float(distress.get("recall")), 4),
                "per_class": per_class(summary),
                "top_confusion_pairs": confusion_pairs(summary)[:6],
                "train_rows": int(summary.get("train_rows") or 0),
                "val_rows": int(summary.get("val_rows") or 0),
                "label_policy": str(summary.get("label_policy") or ""),
                "image_size": int(summary.get("image_size") or 0),
                "output_model": str(summary.get("output_model") or ""),
            }
        )
    return rows


def summarize_recipes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["recipe"]].append(row)
    summary = []
    for recipe, items in grouped.items():
        macros = [item["macro_f1"] for item in items]
        selections = [item["selection_score"] for item in items]
        best = max(items, key=lambda item: item["macro_f1"])
        recent = sorted(items, key=lambda item: item["mtime"])[-5:]
        summary.append(
            {
                "recipe": recipe,
                "runs": len(items),
                "best_macro_f1": round(max(macros), 4),
                "mean_macro_f1": round(statistics.mean(macros), 4),
                "best_selection_score": round(max(selections), 4),
                "recent_mean_macro_f1": round(statistics.mean([item["macro_f1"] for item in recent]), 4),
                "best_run": best["name"],
            }
        )
    return sorted(summary, key=lambda item: (item["best_macro_f1"], item["recent_mean_macro_f1"]), reverse=True)


def weak_class_summary(rows: list[dict[str, Any]], take: int = 20) -> list[dict[str, Any]]:
    recent = sorted(rows, key=lambda item: item["mtime"])[-take:]
    values: dict[str, list[float]] = defaultdict(list)
    recalls: dict[str, list[float]] = defaultdict(list)
    precisions: dict[str, list[float]] = defaultdict(list)
    for row in recent:
        for label, item in (row.get("per_class") or {}).items():
            values[label].append(as_float((item or {}).get("f1")))
            recalls[label].append(as_float((item or {}).get("recall")))
            precisions[label].append(as_float((item or {}).get("precision")))
    out = []
    for label, f1s in values.items():
        out.append(
            {
                "label": label,
                "recent_mean_f1": round(statistics.mean(f1s), 4),
                "recent_mean_precision": round(statistics.mean(precisions[label]), 4),
                "recent_mean_recall": round(statistics.mean(recalls[label]), 4),
                "observations": len(f1s),
            }
        )
    return sorted(out, key=lambda item: item["recent_mean_f1"])


def confusion_summary(rows: list[dict[str, Any]], take: int = 20) -> list[dict[str, Any]]:
    recent = sorted(rows, key=lambda item: item["mtime"])[-take:]
    counts: Counter[tuple[str, str]] = Counter()
    rates: dict[tuple[str, str], list[float]] = defaultdict(list)
    raw_counts: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in recent:
        for pair in row.get("top_confusion_pairs") or []:
            key = (str(pair.get("truth")), str(pair.get("pred")))
            counts[key] += 1
            rates[key].append(as_float(pair.get("rate")))
            raw_counts[key].append(int(pair.get("count") or 0))
    out = []
    for key, seen in counts.most_common(8):
        out.append(
            {
                "truth": key[0],
                "pred": key[1],
                "seen_in_recent_runs": int(seen),
                "mean_rate": round(statistics.mean(rates[key]), 4),
                "mean_count": round(statistics.mean(raw_counts[key]), 1),
            }
        )
    return out


def build_report(trigger: str) -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    active = read_json(ACTIVE_SUMMARY)
    rows = load_runs()
    recent = sorted(rows, key=lambda item: item["mtime"])[-20:]
    best_macro = max(rows, key=lambda item: item["macro_f1"], default={})
    best_selection = max(rows, key=lambda item: item["selection_score"], default={})
    recent_best = max(recent, key=lambda item: item["macro_f1"], default={})
    active_macro = round(metric(active), 4)
    active_selection = round(selection_score(active), 4)
    active_pairs = confusion_pairs(active)[:6]
    recipes = summarize_recipes(rows)
    weak_recent = weak_class_summary(rows)
    recurring_confusions = confusion_summary(rows)

    bottlenecks = []
    if active_macro < 0.90:
        bottlenecks.append(
            {
                "type": "plateau",
                "severity": "high",
                "message": "active macro F1이 0.90 아래에서 정체되어 95% 목표와 간극이 큽니다.",
            }
        )
    if active_pairs:
        top = active_pairs[0]
        if {top["truth"], top["pred"]} == {"non_distress", "distress"} or top["rate"] >= 0.10:
            bottlenecks.append(
                {
                    "type": "decision_boundary",
                    "severity": "high",
                    "message": "주 병목은 모델 속도가 아니라 non_distress/distress 경계 혼동입니다.",
                    "evidence": active_pairs[:2],
                }
            )
    if best_macro and best_macro.get("macro_f1", 0) > active_macro and best_macro.get("selection_score", 0) < active_selection:
        bottlenecks.append(
            {
                "type": "metric_mismatch",
                "severity": "medium",
                "message": "과거 macro F1 최고 후보는 운영 selection score가 낮아 승격 기준과 충돌합니다.",
                "evidence": {
                    "best_macro_run": best_macro.get("name"),
                    "best_macro_f1": best_macro.get("macro_f1"),
                    "best_selection_score": best_macro.get("selection_score"),
                    "active_macro_f1": active_macro,
                    "active_selection_score": active_selection,
                },
            }
        )
    if recent_best and recent_best.get("macro_f1", 0) <= active_macro + 0.002:
        bottlenecks.append(
            {
                "type": "recipe_repetition",
                "severity": "medium",
                "message": "최근 seed sweep은 active를 의미 있게 넘지 못했습니다. 같은 레시피 반복의 기대값이 낮습니다.",
                "evidence": {"recent_best_run": recent_best.get("name"), "recent_best_macro_f1": recent_best.get("macro_f1")},
            }
        )

    next_actions = [
        "no_aug_160과 val2_noise_boundary 반복 비중을 낮추고 precision_smooth_192 계열을 기준선으로 둡니다.",
        "false positive/false negative 샘플을 따로 수집하는 hard-boundary set을 만들고, non_distress→distress와 distress→non_distress를 분리 평가합니다.",
        "현 2-class 운영 모델은 90% 근처가 구조적 상한으로 보이므로, 95% 목표는 라벨 정제 또는 추가 얼굴 품질 필터 없이 반복 학습만으로 달성하기 어렵다고 표시합니다.",
        "다음 후보는 threshold/calibration report를 필수 산출물로 남겨 macro F1과 운영 selection score가 충돌하는지 즉시 보여줍니다.",
    ]

    report = {
        "ok": True,
        "trigger": trigger,
        "updated_at": utc_now(),
        "active": {
            "macro_f1": active_macro,
            "accuracy": round(metric(active, "accuracy"), 4),
            "selection_score": active_selection,
            "summary_path": str(ACTIVE_SUMMARY),
        },
        "run_count": len(rows),
        "best_macro": best_macro,
        "best_selection": best_selection,
        "recent_best": recent_best,
        "recipe_summary": recipes,
        "weak_recent": weak_recent,
        "recurring_confusions": recurring_confusions,
        "active_top_confusions": active_pairs,
        "bottlenecks": bottlenecks,
        "next_actions": next_actions,
    }
    return report


def write_report(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    active = report.get("active") or {}
    best_macro = report.get("best_macro") or {}
    best_selection = report.get("best_selection") or {}
    recent_best = report.get("recent_best") or {}
    lines = [
        "# AI-Hub 82 표정 모델 병목 분석",
        "",
        f"- 갱신: `{report.get('updated_at')}`",
        f"- 트리거: `{report.get('trigger')}`",
        f"- active macro F1: `{active.get('macro_f1')}`",
        f"- active selection score: `{active.get('selection_score')}`",
        f"- 후보 수: `{report.get('run_count')}`",
        "",
        "## 결론",
        "",
        "현재 88%대 정체의 핵심은 학습이 멈춘 것이 아니라 `non_distress`와 `distress` 경계가 서로 10% 안팎으로 뒤바뀌는 라벨/판정 경계 병목입니다. 과거 macro F1 최고 후보는 있었지만 운영 selection score가 낮아 active로 쓰기 어렵습니다.",
        "",
        "## Best Runs",
        "",
        f"- macro F1 최고: `{best_macro.get('macro_f1')}` · `{best_macro.get('name')}` · selection `{best_macro.get('selection_score')}`",
        f"- selection 최고: `{best_selection.get('selection_score')}` · `{best_selection.get('name')}` · macro `{best_selection.get('macro_f1')}`",
        f"- 최근 20개 최고: `{recent_best.get('macro_f1')}` · `{recent_best.get('name')}`",
        "",
        "## 반복 병목",
        "",
    ]
    for item in report.get("bottlenecks") or []:
        lines.append(f"- [{item.get('severity')}] {item.get('message')}")
    lines.extend(["", "## 최근 약한 클래스"])
    for item in report.get("weak_recent") or []:
        lines.append(
            f"- {item.get('label')}: F1 {item.get('recent_mean_f1')} · P {item.get('recent_mean_precision')} · R {item.get('recent_mean_recall')}"
        )
    lines.extend(["", "## 반복 혼동"])
    for item in report.get("recurring_confusions") or []:
        lines.append(
            f"- {item.get('truth')} -> {item.get('pred')}: 최근 {item.get('seen_in_recent_runs')}회, 평균 rate {item.get('mean_rate')}, 평균 count {item.get('mean_count')}"
        )
    lines.extend(["", "## 레시피별 성과"])
    for item in report.get("recipe_summary") or []:
        lines.append(
            f"- {item.get('recipe')}: best {item.get('best_macro_f1')} · recent mean {item.get('recent_mean_macro_f1')} · runs {item.get('runs')} · best run `{item.get('best_run')}`"
        )
    lines.extend(["", "## 다음 조치"])
    for item in report.get("next_actions") or []:
        lines.append(f"- {item}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--output-json", default=str(REPORT_JSON))
    parser.add_argument("--output-md", default=str(REPORT_MD))
    args = parser.parse_args()

    report = build_report(args.trigger)
    write_report(report, Path(args.output_json), Path(args.output_md))
    print(json.dumps({"ok": True, "json": args.output_json, "md": args.output_md, "active_macro_f1": report["active"]["macro_f1"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
