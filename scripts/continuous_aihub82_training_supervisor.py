#!/usr/bin/env python3
"""Continuously improve the AI-Hub 82 facial emotion model.

The supervisor runs one candidate training job at a time, writes progress every
10 minutes, and promotes a candidate only when its macro F1 is higher than the
currently active AI-Hub 82 model.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


PROJECT = Path("/opt/app/project/main")
PY = os.environ.get("FALLAI_PYTHON", "python3")
DATASET_ROOT = Path("/opt/app/datasets/facial_state/aihub_82_korean_emotion")
FACIAL_ROOT = Path("/opt/app/storage/training/fall-detection/facial-state")
ACTIVE_MODEL = FACIAL_ROOT / "aihub82_facial_emotion_mobilenetv3.pt"
ACTIVE_SUMMARY = FACIAL_ROOT / "aihub82_facial_emotion_summary.json"
RUN_DIR = PROJECT / "outputs" / "continuous_training"
STATUS_JSON = RUN_DIR / "aihub82_status.json"
STATUS_MD = RUN_DIR / "aihub82_status.md"
MAIN_LOG = RUN_DIR / "aihub82_supervisor.log"
PID_FILE = RUN_DIR / "aihub82_supervisor.pid"
BOTTLENECK_JSON = RUN_DIR / "aihub82_bottleneck_report.json"
BOTTLENECK_MD = RUN_DIR / "aihub82_bottleneck_report.md"
HEARTBEAT_SEC = int(os.environ.get("FALLAI_AIHUB82_HEARTBEAT_SEC", "600") or 600)
SLEEP_BETWEEN_RUNS_SEC = int(os.environ.get("FALLAI_AIHUB82_SLEEP_BETWEEN_RUNS_SEC", "60") or 60)
MAX_RUNS = int(os.environ.get("FALLAI_AIHUB82_MAX_RUNS", "0") or 0)
LOW_MACRO_F1_THRESHOLD = float(os.environ.get("FALLAI_AIHUB82_LOW_MACRO_F1", "0.68") or 0.68)
TARGET_MACRO_F1 = float(os.environ.get("FALLAI_AIHUB82_TARGET_MACRO_F1", "0.95") or 0.95)
STRETCH_MACRO_F1 = float(os.environ.get("FALLAI_AIHUB82_STRETCH_MACRO_F1", "0.95") or 0.95)
PAUSE_AFTER_NO_PROMOTION_CYCLES = int(os.environ.get("FALLAI_AIHUB82_PAUSE_AFTER_NO_PROMOTION_CYCLES", "0") or 0)
CLASS_NAMES = ["happiness", "embarrassed", "anger", "anxiety", "hurt", "sadness", "neutral"]


EXPERIMENTS = [
    {
        "name": "boundary_focal_192_crop20_seed_sweep",
        "epochs": 5,
        "batch_size": 40,
        "image_size": 192,
        "max_train_per_class": 9000,
        "max_val_per_class": 2200,
        "lr": "0.00007",
        "train_min_agreement": 3,
        "val_min_agreement": 3,
        "model_type": "mobilenet_v3_large",
        "label_policy": "distress_binary",
        "crop_pad_ratio": "0.20",
        "augment_strength": "light",
        "label_smoothing": "0.02",
        "loss_type": "focal",
        "focal_gamma": "1.35",
        "distress_boundary_margin": "0.08",
        "distress_boundary_penalty": "0.22",
        "class_weight_multipliers": "distress=0.98",
        "selection_metric": "operating_distress",
        "min_distress_precision": "0.865",
        "min_distress_recall": "0.84",
        "num_workers": 0,
        "torch_num_threads": 4,
        "max_epochs_without_improvement": 2,
        "max_runtime_min": 150,
        "min_val_rows": 1000,
        "seed": 2026062211,
        "seed_stride": 41,
    },
    {
        "name": "boundary_focal_224_crop24_boundary_guard",
        "epochs": 5,
        "batch_size": 28,
        "image_size": 224,
        "max_train_per_class": 9000,
        "max_val_per_class": 2200,
        "lr": "0.000055",
        "train_min_agreement": 3,
        "val_min_agreement": 3,
        "model_type": "mobilenet_v3_large",
        "label_policy": "distress_binary",
        "crop_pad_ratio": "0.24",
        "augment_strength": "light",
        "label_smoothing": "0.015",
        "loss_type": "focal",
        "focal_gamma": "1.45",
        "distress_boundary_margin": "0.09",
        "distress_boundary_penalty": "0.28",
        "class_weight_multipliers": "distress=1.00",
        "selection_metric": "operating_distress",
        "min_distress_precision": "0.87",
        "min_distress_recall": "0.85",
        "num_workers": 0,
        "torch_num_threads": 4,
        "max_epochs_without_improvement": 2,
        "max_runtime_min": 175,
        "min_val_rows": 1000,
        "seed": 2026062501,
        "seed_stride": 53,
    },
    {
        "name": "boundary_focal_192_high_agreement_audit",
        "epochs": 4,
        "batch_size": 36,
        "image_size": 192,
        "max_train_per_class": 7000,
        "max_val_per_class": 1800,
        "lr": "0.00006",
        "train_min_agreement": 4,
        "val_min_agreement": 4,
        "model_type": "mobilenet_v3_large",
        "label_policy": "distress_binary",
        "crop_pad_ratio": "0.20",
        "augment_strength": "light",
        "label_smoothing": "0.01",
        "loss_type": "focal",
        "focal_gamma": "1.20",
        "distress_boundary_margin": "0.07",
        "distress_boundary_penalty": "0.18",
        "class_weight_multipliers": "distress=1.00",
        "selection_metric": "operating_distress",
        "min_distress_precision": "0.865",
        "min_distress_recall": "0.85",
        "num_workers": 0,
        "torch_num_threads": 4,
        "max_epochs_without_improvement": 2,
        "max_runtime_min": 140,
        "min_val_rows": 700,
        "seed": 2026062511,
        "seed_stride": 59,
    },
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def ensure_dirs() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (FACIAL_ROOT / "experiments" / "aihub82_continuous").mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def metric(summary: dict[str, Any], key: str = "macro_f1") -> float:
    try:
        best = ((summary or {}).get("best_metrics") or {})
        if "." in key:
            value: Any = best
            for part in key.split("."):
                value = (value or {}).get(part) if isinstance(value, dict) else None
            return float(value or 0.0)
        return float(best.get(key) or 0.0)
    except Exception:
        return 0.0


def parse_experiment_version(label: str) -> dict[str, Any]:
    raw = Path(str(label or "").strip()).name
    match = re.match(r"^(\d+)_([A-Za-z0-9_.-]+?)(?:_\d{8}_\d{6})?$", raw)
    if not match:
        return {"label": raw, "index": None, "name": raw, "text": raw or "-"}
    idx = int(match.group(1))
    name = match.group(2).replace("_", " ")
    return {"label": raw, "index": idx, "name": name, "text": f"#{idx:04d} {name}"}


def active_experiment_version(active_summary: dict[str, Any]) -> dict[str, Any]:
    output_model = str((active_summary or {}).get("output_model") or "")
    if not output_model:
        return {"label": "", "index": None, "name": "", "text": "-"}
    return parse_experiment_version(Path(output_model).parent.name)


def candidate_version_count() -> int:
    root = FACIAL_ROOT / "experiments" / "aihub82_continuous"
    try:
        return sum(1 for item in root.iterdir() if item.is_dir())
    except Exception:
        return 0


def next_run_index() -> int:
    root = FACIAL_ROOT / "experiments" / "aihub82_continuous"
    max_idx = 0
    try:
        for item in root.iterdir():
            if not item.is_dir():
                continue
            prefix = item.name.split("_", 1)[0]
            if prefix.isdigit():
                max_idx = max(max_idx, int(prefix))
    except Exception:
        pass
    return max_idx + 1


def latest_log_line(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-1] if lines else "-"
    except Exception:
        return "-"


def latest_train_progress_line(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return "-"
    for line in reversed(lines[-200:]):
        if re.search(r"epoch=\d+/\d+\s+step=\d+/\d+", line):
            return line
    return "-"


def estimate_training_progress(latest: str, elapsed_min: float) -> dict[str, Any]:
    match = re.search(r"epoch=(\d+)/(\d+)\s+step=(\d+)/(\d+)", str(latest or ""))
    if not match or elapsed_min <= 0:
        return {}
    epoch = max(1, int(match.group(1)))
    epochs = max(1, int(match.group(2)))
    step = max(0, int(match.group(3)))
    steps = max(1, int(match.group(4)))
    progress = max(0.0, min(0.995, ((epoch - 1) + min(step / steps, 1.0)) / epochs))
    if progress <= 0:
        return {"progress": 0.0, "progress_text": f"epoch {epoch}/{epochs} · step {step}/{steps}"}
    eta_sec = max(0.0, (elapsed_min * 60.0) * (1.0 - progress) / progress)
    if eta_sec < 60:
        eta_text = f"{round(eta_sec)}초"
    elif eta_sec < 3600:
        eta_text = f"{int(eta_sec // 60)}분 {round(eta_sec % 60)}초"
    else:
        eta_text = f"{int(eta_sec // 3600)}시간 {int((eta_sec % 3600) // 60)}분"
    return {
        "progress": round(progress, 4),
        "progress_text": f"epoch {epoch}/{epochs} · step {step}/{steps}",
        "eta_sec": round(eta_sec, 1),
        "eta_text": eta_text,
    }


def log(message: str) -> None:
    ensure_dirs()
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    with MAIN_LOG.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def write_status(stage: str, **extra: Any) -> dict[str, Any]:
    ensure_dirs()
    active_summary = read_json(ACTIVE_SUMMARY)
    experiment_label = str(extra.get("experiment") or "")
    candidate_version = parse_experiment_version(experiment_label)
    active_version = active_experiment_version(active_summary)
    total_candidates = candidate_version_count()
    version_bits = []
    if candidate_version.get("label"):
        version_bits.append(f"진행 {candidate_version.get('text')}")
    if active_version.get("label"):
        version_bits.append(f"active {active_version.get('text')}")
    if total_candidates:
        version_bits.append(f"누적 후보 {total_candidates}개")
    data: dict[str, Any] = {
        "ok": True,
        "stage": stage,
        "updated_at": utc_now(),
        "supervisor_pid": os.getpid(),
        "active_macro_f1": round(metric(active_summary), 4),
        "active_accuracy": round(metric(active_summary, "accuracy"), 4),
        "active_summary": str(ACTIVE_SUMMARY),
        "active_model": str(ACTIVE_MODEL),
        "main_log": str(MAIN_LOG),
        "heartbeat_sec": HEARTBEAT_SEC,
        "target_macro_f1": TARGET_MACRO_F1,
        "stretch_macro_f1": STRETCH_MACRO_F1,
        "strategy": "aihub82_precision_seed_sweep",
        "strategy_reason": "가림 보조는 목표를 넘겨 중단했고, AI-Hub 82는 고정 seed/동일 레시피 반복을 중단했습니다. distress FP를 줄이는 crop/weight/smoothing/validation 조합을 seed sweep으로 우선 탐색합니다.",
        "bottleneck_report": str(BOTTLENECK_MD) if BOTTLENECK_MD.exists() else "",
        "bottleneck_report_json": str(BOTTLENECK_JSON) if BOTTLENECK_JSON.exists() else "",
        "candidate_version": candidate_version,
        "candidate_version_text": candidate_version.get("text"),
        "active_version": active_version,
        "active_version_text": active_version.get("text"),
        "total_candidate_versions": total_candidates,
        "training_version_text": " · ".join(version_bits) if version_bits else "-",
    }
    latest = str(extra.get("latest_log") or "")
    elapsed_min = float(extra.get("elapsed_min") or 0.0)
    if latest and elapsed_min > 0:
        progress = estimate_training_progress(latest, elapsed_min)
        if not progress and extra.get("log_path"):
            progress_source = latest_train_progress_line(Path(str(extra.get("log_path"))))
            progress = estimate_training_progress(progress_source, elapsed_min)
            if progress:
                data["progress_source_log"] = progress_source
        data.update(progress)
    data.update(extra)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp_path = STATUS_JSON.with_name(f".{STATUS_JSON.name}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, STATUS_JSON)
    lines = [
        "# AI-Hub 82 Continuous Training",
        "",
        f"- stage: `{data.get('stage')}`",
        f"- updated: `{data.get('updated_at')}`",
        f"- active macro F1: `{data.get('active_macro_f1')}`",
        f"- active accuracy: `{data.get('active_accuracy')}`",
        f"- supervisor pid: `{data.get('supervisor_pid')}`",
        f"- heartbeat sec: `{HEARTBEAT_SEC}`",
        f"- log: `{MAIN_LOG}`",
    ]
    for key in ["strategy", "strategy_reason", "bottleneck_report", "training_version_text", "experiment", "resolved_seed", "progress_text", "eta_text", "candidate_macro_f1", "candidate_accuracy", "candidate_operating_score", "candidate_distress_precision", "candidate_distress_recall", "candidate_train_rows", "candidate_val_rows", "promoted", "promotion_reason", "low_score", "diagnosis_md", "latest_log", "elapsed_min"]:
        if key in data:
            lines.append(f"- {key}: `{data.get(key)}`")
    STATUS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


def pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace").split()
        if len(stat) > 2 and stat[2] == "Z":
            return False
    except Exception:
        pass
    return True


def prevent_duplicate() -> bool:
    ensure_dirs()
    old_pid = 0
    try:
        old_pid = int(PID_FILE.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        old_pid = 0
    if old_pid and old_pid != os.getpid() and pid_running(old_pid):
        write_status("already-running", existing_pid=old_pid)
        log(f"another AI-Hub82 supervisor is already running: pid={old_pid}")
        return False
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def promotion_metrics(summary: dict[str, Any]) -> dict[str, float]:
    best = (summary.get("best_metrics") or {}) if isinstance(summary, dict) else {}
    distress = best.get("distress_binary") or {}
    return {
        "macro_f1": metric(summary),
        "accuracy": metric(summary, "accuracy"),
        "selection_score": float(best.get("selection_score") or metric(summary)),
        "distress_f1": float(distress.get("f1") or 0.0),
        "distress_precision": float(distress.get("precision") or 0.0),
        "distress_recall": float(distress.get("recall") or 0.0),
    }


def promote_if_better(experiment_dir: Path) -> tuple[bool, float, float, str]:
    src_model = experiment_dir / "aihub82_facial_emotion_mobilenetv3.pt"
    src_summary = experiment_dir / "aihub82_facial_emotion_summary.json"
    if not src_model.exists() or not src_summary.exists():
        log(f"promotion skipped; missing candidate outputs: {experiment_dir}")
        return False, 0.0, metric(read_json(ACTIVE_SUMMARY)), "missing_candidate_outputs"

    candidate_summary = read_json(src_summary)
    active_summary = read_json(ACTIVE_SUMMARY)
    candidate_score = metric(candidate_summary)
    active_score = metric(active_summary)
    candidate_ops = promotion_metrics(candidate_summary)
    active_ops = promotion_metrics(active_summary)
    label_policy = str(candidate_summary.get("label_policy") or "")
    operating_policy = label_policy in {"distress_binary", "distress_operational_clean"}
    promotion_reason = ""
    if operating_policy:
        precision_ok = candidate_ops["distress_precision"] >= max(0.86, active_ops["distress_precision"] + 0.02)
        recall_ok = candidate_ops["distress_recall"] >= max(0.78, active_ops["distress_recall"] - 0.06)
        f1_ok = candidate_ops["distress_f1"] >= active_ops["distress_f1"] - 0.01
        selection_ok = candidate_ops["selection_score"] > max(active_ops["selection_score"], active_ops["distress_f1"]) + 0.005
        macro_ok = candidate_score > active_score + 0.006
        if (precision_ok and recall_ok and f1_ok) or (selection_ok and candidate_ops["distress_precision"] >= active_ops["distress_precision"]) or macro_ok:
            promotion_reason = (
                f"operating improvement: precision {active_ops['distress_precision']:.4f}->{candidate_ops['distress_precision']:.4f}, "
                f"recall {active_ops['distress_recall']:.4f}->{candidate_ops['distress_recall']:.4f}, "
                f"distress_f1 {active_ops['distress_f1']:.4f}->{candidate_ops['distress_f1']:.4f}"
            )
        else:
            log(
                "promotion skipped: operating candidate did not improve enough "
                f"macro {candidate_score:.4f}<={active_score:.4f}, "
                f"precision {candidate_ops['distress_precision']:.4f}<target, "
                f"recall {candidate_ops['distress_recall']:.4f}"
            )
            return False, candidate_score, active_score, "operating_metrics_not_better"
    elif candidate_score > active_score + 1e-6:
        promotion_reason = f"macro_f1 improved {active_score:.4f}->{candidate_score:.4f}"
    else:
        log(f"promotion skipped: candidate macro_f1 {candidate_score:.4f} <= active {active_score:.4f}")
        return False, candidate_score, active_score, "macro_f1_not_better"

    backup_stamp = stamp()
    if ACTIVE_MODEL.exists():
        shutil.copy2(ACTIVE_MODEL, ACTIVE_MODEL.with_name(ACTIVE_MODEL.stem + f".backup_{backup_stamp}" + ACTIVE_MODEL.suffix))
    if ACTIVE_SUMMARY.exists():
        shutil.copy2(ACTIVE_SUMMARY, ACTIVE_SUMMARY.with_name(ACTIVE_SUMMARY.stem + f".backup_{backup_stamp}" + ACTIVE_SUMMARY.suffix))
    shutil.copy2(src_model, ACTIVE_MODEL)
    shutil.copy2(src_summary, ACTIVE_SUMMARY)
    log(f"promoted AI-Hub82: {promotion_reason}")
    return True, candidate_score, active_score, promotion_reason


def refresh_bottleneck_report(trigger: str) -> dict[str, Any]:
    """Refresh aggregate bottleneck report without blocking training for long."""
    ensure_dirs()
    command = [
        PY,
        str(PROJECT / "scripts" / "analyze_aihub82_bottlenecks.py"),
        "--trigger",
        trigger,
        "--output-json",
        str(BOTTLENECK_JSON),
        "--output-md",
        str(BOTTLENECK_MD),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT),
            text=True,
            capture_output=True,
            timeout=90,
        )
        if completed.returncode != 0:
            log(f"bottleneck analysis failed rc={completed.returncode}: {(completed.stderr or completed.stdout).strip()[-500:]}")
            return {"ok": False, "rc": completed.returncode}
        log(f"bottleneck analysis refreshed: {BOTTLENECK_MD}")
        return {"ok": True, "json": str(BOTTLENECK_JSON), "md": str(BOTTLENECK_MD)}
    except Exception as exc:
        log(f"bottleneck analysis failed: {type(exc).__name__}: {exc}")
        return {"ok": False, "error": str(exc)}


def diagnose_candidate(experiment_dir: Path, run_label: str, elapsed_min: float = 0.0) -> dict[str, Any]:
    summary = read_json(experiment_dir / "aihub82_facial_emotion_summary.json")
    best = (summary.get("best_metrics") or {}) if isinstance(summary, dict) else {}
    per_class = best.get("per_class") or {}
    confusion = best.get("confusion_matrix") or []
    classes = list(summary.get("classes") or CLASS_NAMES)
    macro_f1 = metric(summary)
    weak = []
    for label in classes:
        item = per_class.get(label) or {}
        weak.append({
            "label": label,
            "f1": round(float(item.get("f1") or 0.0), 4),
            "precision": round(float(item.get("precision") or 0.0), 4),
            "recall": round(float(item.get("recall") or 0.0), 4),
            "support": int(item.get("support") or 0),
        })
    weak = sorted(weak, key=lambda item: item["f1"])

    confusion_pairs = []
    if isinstance(confusion, list):
        for truth_idx, row in enumerate(confusion[:len(classes)]):
            if not isinstance(row, list):
                continue
            total = sum(int(v or 0) for v in row)
            if total <= 0:
                continue
            for pred_idx, count in enumerate(row[:len(classes)]):
                count = int(count or 0)
                if truth_idx == pred_idx or count <= 0:
                    continue
                confusion_pairs.append({
                    "truth": classes[truth_idx],
                    "pred": classes[pred_idx],
                    "count": count,
                    "rate": round(count / max(total, 1), 4),
                })
    confusion_pairs = sorted(confusion_pairs, key=lambda item: (item["rate"], item["count"]), reverse=True)[:12]

    root_causes = []
    if set(classes) == {"non_distress", "distress"}:
        bidirectional = [
            pair for pair in confusion_pairs[:4]
            if {pair["truth"], pair["pred"]} == {"non_distress", "distress"} and pair["rate"] >= 0.09
        ]
        if bidirectional:
            root_causes.append("핵심 병목은 non_distress와 distress의 경계 혼동입니다. 최근 후보들이 양방향으로 약 10% 이상 뒤바뀌어 단순 seed 반복으로는 90% 이상 상승 폭이 작습니다.")
        if abs((per_class.get("non_distress") or {}).get("f1", 0.0) - (per_class.get("distress") or {}).get("f1", 0.0)) < 0.02 and macro_f1 < 0.9:
            root_causes.append("두 클래스 F1이 비슷하게 낮아 특정 클래스 하나가 아니라 라벨 경계/검증셋 노이즈가 macro F1 상한을 만들고 있습니다.")
    weak_labels = {item["label"] for item in weak[:3]}
    if {"hurt", "anxiety"} & weak_labels:
        root_causes.append("hurt/anxiety 계열 F1이 낮아 라벨 의미가 가까운 감정 간 혼동이 큽니다.")
    if any(pair["truth"] in {"hurt", "anxiety", "sadness", "anger"} and pair["pred"] in {"hurt", "anxiety", "sadness", "anger"} for pair in confusion_pairs[:6]):
        root_causes.append("distress 계열 내부 혼동이 상위 confusion에 포함되어 단순 모델 크기보다 라벨 신뢰도/평가셋 정제가 중요합니다.")
    if int(summary.get("val_rows") or 0) >= 10000 and (summary.get("min_agreement") or {}).get("val", 1) <= 2:
        root_causes.append("검증셋이 크지만 agreement 기준이 낮아 애매한 표정까지 평가에 들어가 macro F1을 낮출 수 있습니다.")
    if elapsed_min >= 300 or float(summary.get("elapsed_sec") or 0.0) >= 18000:
        root_causes.append("ZIP 내부 이미지를 매 step 읽고 crop/augment하는 CPU 데이터 로딩이 길어진 학습 시간의 주요 원인입니다.")
    if not root_causes:
        root_causes.append("macro F1이 목표보다 낮아 약한 클래스와 confusion pair 중심으로 다음 실험을 조정해야 합니다.")

    actions = [
        "다음 반복은 non_distress↔distress hard-boundary 샘플을 별도 집계해 FP/FN을 분리 관리합니다.",
        "no_aug/val2 반복은 성과가 낮으므로 비중을 줄이고 precision_smooth_192 계열을 기준선으로 유지합니다.",
        "macro F1과 운영 selection score가 충돌하므로 후보마다 threshold/calibration 표를 같이 남깁니다.",
        "성능이 개선되는 후보만 active 모델로 승격하고, 낮은 후보는 실험 산출물로만 보존합니다.",
    ]
    if {"hurt", "anxiety"} & weak_labels:
        actions.append("hurt/anxiety/sadness 혼동이 계속되면 해당 계열을 distress binary 보조 신호로도 평가합니다.")

    diagnosis = {
        "run_label": run_label,
        "created_at": utc_now(),
        "macro_f1": round(macro_f1, 4),
        "accuracy": round(metric(summary, "accuracy"), 4),
        "low_macro_f1_threshold": LOW_MACRO_F1_THRESHOLD,
        "is_low_score": bool(macro_f1 < LOW_MACRO_F1_THRESHOLD),
        "elapsed_min": elapsed_min,
        "weak_classes": weak[:5],
        "top_confusion_pairs": confusion_pairs,
        "root_causes": root_causes,
        "next_actions": actions,
    }
    json_path = RUN_DIR / f"{run_label}.diagnosis.json"
    md_path = RUN_DIR / f"{run_label}.diagnosis.md"
    json_path.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [
        f"# AI-Hub 82 Diagnosis - {run_label}",
        "",
        f"- macro F1: `{diagnosis['macro_f1']}`",
        f"- accuracy: `{diagnosis['accuracy']}`",
        f"- low score threshold: `{LOW_MACRO_F1_THRESHOLD}`",
        f"- elapsed_min: `{elapsed_min}`",
        "",
        "## Weak Classes",
    ]
    for item in diagnosis["weak_classes"]:
        md_lines.append(f"- {item['label']}: f1={item['f1']} precision={item['precision']} recall={item['recall']} support={item['support']}")
    md_lines.extend(["", "## Top Confusion Pairs"])
    for item in diagnosis["top_confusion_pairs"]:
        md_lines.append(f"- {item['truth']} -> {item['pred']}: count={item['count']} rate={item['rate']}")
    md_lines.extend(["", "## Root Causes"])
    for item in root_causes:
        md_lines.append(f"- {item}")
    md_lines.extend(["", "## Next Actions"])
    for item in actions:
        md_lines.append(f"- {item}")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    diagnosis["diagnosis_json"] = str(json_path)
    diagnosis["diagnosis_md"] = str(md_path)
    return diagnosis


def build_command(exp: dict[str, Any], out_dir: Path) -> list[str]:
    command = [
        PY,
        str(PROJECT / "scripts" / "train_facial_emotion_aihub82.py"),
        "--dataset-root",
        str(DATASET_ROOT),
        "--output-dir",
        str(out_dir),
        "--epochs",
        str(exp["epochs"]),
        "--batch-size",
        str(exp["batch_size"]),
        "--image-size",
        str(exp["image_size"]),
        "--max-train-per-class",
        str(exp["max_train_per_class"]),
        "--max-val-per-class",
        str(exp["max_val_per_class"]),
        "--lr",
        str(exp["lr"]),
        "--num-workers",
        str(exp.get("num_workers", 0)),
        "--seed",
        str(exp["seed"]),
        "--train-min-agreement",
        str(exp["train_min_agreement"]),
        "--val-min-agreement",
        str(exp["val_min_agreement"]),
        "--model-type",
        str(exp.get("model_type", "mobilenet_v3_large")),
        "--label-policy",
        str(exp.get("label_policy", "seven")),
        "--crop-pad-ratio",
        str(exp.get("crop_pad_ratio", "0.14")),
        "--augment-strength",
        str(exp.get("augment_strength", "medium")),
        "--label-smoothing",
        str(exp["label_smoothing"]),
        "--max-epochs-without-improvement",
        str(exp.get("max_epochs_without_improvement", 0)),
    ]
    if exp.get("class_weight_multipliers"):
        command.extend(["--class-weight-multipliers", str(exp["class_weight_multipliers"])])
    if exp.get("selection_metric"):
        command.extend(["--selection-metric", str(exp["selection_metric"])])
    if exp.get("min_distress_precision"):
        command.extend(["--min-distress-precision", str(exp["min_distress_precision"])])
    if exp.get("min_distress_recall"):
        command.extend(["--min-distress-recall", str(exp["min_distress_recall"])])
    if exp.get("loss_type"):
        command.extend(["--loss-type", str(exp["loss_type"])])
    if exp.get("focal_gamma"):
        command.extend(["--focal-gamma", str(exp["focal_gamma"])])
    if exp.get("distress_boundary_margin"):
        command.extend(["--distress-boundary-margin", str(exp["distress_boundary_margin"])])
    if exp.get("distress_boundary_penalty"):
        command.extend(["--distress-boundary-penalty", str(exp["distress_boundary_penalty"])])
    return command


def resolved_experiment(exp: dict[str, Any], run_index: int) -> dict[str, Any]:
    resolved = dict(exp or {})
    if not resolved.get("fixed_seed"):
        base_seed = int(resolved.get("seed", 42) or 42)
        stride = int(resolved.get("seed_stride", 31) or 31)
        resolved["seed"] = base_seed + max(int(run_index or 1), 1) * stride
    return resolved


def run_experiment(exp: dict[str, Any], run_index: int) -> dict[str, Any]:
    exp = resolved_experiment(exp, run_index)
    run_label = f"{run_index:04d}_{exp['name']}_{stamp()}"
    out_dir = FACIAL_ROOT / "experiments" / "aihub82_continuous" / run_label
    log_path = RUN_DIR / f"{run_label}.log"
    command = build_command(exp, out_dir)
    log(f"start experiment {run_label}: {' '.join(command)}")
    write_status(
        "running",
        experiment=run_label,
        output_dir=str(out_dir),
        log_path=str(log_path),
        latest_log="-",
        resolved_seed=exp.get("seed"),
        experiment_recipe={
            key: exp.get(key)
            for key in [
                "label_policy",
                "image_size",
                "crop_pad_ratio",
                "augment_strength",
                "label_smoothing",
                "class_weight_multipliers",
                "train_min_agreement",
                "val_min_agreement",
                "selection_metric",
                "loss_type",
                "focal_gamma",
                "distress_boundary_margin",
                "distress_boundary_penalty",
            ]
        },
    )
    env = os.environ.copy()
    env["TORCH_NUM_THREADS"] = str(exp.get("torch_num_threads", env.get("TORCH_NUM_THREADS", "2")))
    started = time.time()
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"\n[{utc_now()}] START {run_label}\n")
        proc = subprocess.Popen(command, cwd=str(PROJECT), stdout=fp, stderr=subprocess.STDOUT, env=env, text=True)
    while True:
        rc = proc.poll()
        elapsed_min = round((time.time() - started) / 60.0, 1)
        max_runtime_min = float(exp.get("max_runtime_min") or 0.0)
        if rc is None and max_runtime_min > 0 and elapsed_min >= max_runtime_min:
            log(f"timeout experiment {run_label}: elapsed_min={elapsed_min} max_runtime_min={max_runtime_min}")
            proc.terminate()
            try:
                rc = proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = proc.wait(timeout=20)
            write_status(
                "timeout",
                experiment=run_label,
                pid=proc.pid,
                elapsed_min=elapsed_min,
                max_runtime_min=max_runtime_min,
                latest_log=latest_log_line(log_path),
                log_path=str(log_path),
            )
            return {"stage": "timeout", "promoted": False}
        write_status(
            "running",
            experiment=run_label,
            pid=proc.pid,
            elapsed_min=elapsed_min,
            log_path=str(log_path),
            latest_log=latest_log_line(log_path),
            resolved_seed=exp.get("seed"),
        )
        if rc is not None:
            log(f"complete experiment {run_label}: rc={rc}")
            if rc == 0:
                candidate_summary = read_json(out_dir / "aihub82_facial_emotion_summary.json")
                candidate = metric(candidate_summary)
                active_before = metric(read_json(ACTIVE_SUMMARY))
                candidate_ops = promotion_metrics(candidate_summary)
                train_rows = int(candidate_summary.get("train_rows") or 0)
                val_rows = int(candidate_summary.get("val_rows") or 0)
                min_val_rows = int(exp.get("min_val_rows", 500) or 500)
                diagnosis = diagnose_candidate(out_dir, run_label, elapsed_min=elapsed_min)
                bottleneck = refresh_bottleneck_report(f"candidate_complete:{run_label}")
                if val_rows < min_val_rows:
                    promotion_reason = f"invalid_validation_rows: val_rows {val_rows} < required {min_val_rows}"
                    log(f"promotion skipped: {promotion_reason} for {run_label}")
                    write_status(
                        "invalid-candidate",
                        experiment=run_label,
                        promoted=False,
                        candidate_macro_f1=round(candidate, 4),
                        candidate_accuracy=round(metric(candidate_summary, "accuracy"), 4),
                        candidate_train_rows=train_rows,
                        candidate_val_rows=val_rows,
                        min_val_rows=min_val_rows,
                        active_before_macro_f1=round(active_before, 4),
                        promotion_reason=promotion_reason,
                        low_score=True,
                        diagnosis_md=diagnosis.get("diagnosis_md"),
                        bottleneck_report=bottleneck.get("md") or str(BOTTLENECK_MD),
                        weak_classes=diagnosis.get("weak_classes"),
                        top_confusion_pairs=diagnosis.get("top_confusion_pairs"),
                        root_causes=diagnosis.get("root_causes"),
                        latest_log=latest_log_line(log_path),
                        log_path=str(log_path),
                        resolved_seed=exp.get("seed"),
                    )
                    return {"stage": "invalid-candidate", "promoted": False, "candidate_macro_f1": candidate}
                promoted, candidate, active_before, promotion_reason = promote_if_better(out_dir)
                write_status(
                    "completed",
                    experiment=run_label,
                    promoted=promoted,
                    candidate_macro_f1=round(candidate, 4),
                    candidate_accuracy=round(metric(candidate_summary, "accuracy"), 4),
                    candidate_operating_score=round(candidate_ops["selection_score"], 4),
                    candidate_distress_precision=round(candidate_ops["distress_precision"], 4),
                    candidate_distress_recall=round(candidate_ops["distress_recall"], 4),
                    candidate_train_rows=train_rows,
                    candidate_val_rows=val_rows,
                    active_before_macro_f1=round(active_before, 4),
                    promotion_reason=promotion_reason,
                    low_score=bool(candidate < LOW_MACRO_F1_THRESHOLD),
                    diagnosis_md=diagnosis.get("diagnosis_md"),
                    bottleneck_report=bottleneck.get("md") or str(BOTTLENECK_MD),
                    weak_classes=diagnosis.get("weak_classes"),
                    top_confusion_pairs=diagnosis.get("top_confusion_pairs"),
                    root_causes=diagnosis.get("root_causes"),
                    latest_log=latest_log_line(log_path),
                    log_path=str(log_path),
                    resolved_seed=exp.get("seed"),
                )
                return {"stage": "completed", "promoted": promoted, "candidate_macro_f1": candidate}
            else:
                write_status("failed", experiment=run_label, rc=rc, latest_log=latest_log_line(log_path), log_path=str(log_path))
                return {"stage": "failed", "promoted": False}
        time.sleep(max(30, HEARTBEAT_SEC))


def handle_stop(signum: int, _frame: Any) -> None:
    write_status("stopping", signal=signum)
    raise SystemExit(0)


def main() -> int:
    ensure_dirs()
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    if not prevent_duplicate():
        return 0
    refresh_bottleneck_report("supervisor_start")
    write_status("starting")
    run_index = next_run_index() - 1
    no_promotion_cycles = 0
    while True:
        cycle_promoted = False
        for exp in EXPERIMENTS:
            run_index += 1
            result = run_experiment(exp, run_index)
            cycle_promoted = cycle_promoted or bool((result or {}).get("promoted"))
            if MAX_RUNS and run_index >= MAX_RUNS:
                write_status("completed-max-runs", run_count=run_index)
                return 0
            time.sleep(SLEEP_BETWEEN_RUNS_SEC)
        if cycle_promoted:
            no_promotion_cycles = 0
        else:
            no_promotion_cycles += 1
            if PAUSE_AFTER_NO_PROMOTION_CYCLES and no_promotion_cycles >= PAUSE_AFTER_NO_PROMOTION_CYCLES:
                write_status(
                    "plateau-paused",
                    run_count=run_index,
                    no_promotion_cycles=no_promotion_cycles,
                    latest_log="No candidate beat active under the reset operating policy; supervisor paused instead of repeating versions.",
                )
                log("plateau paused: no reset-strategy candidate promoted; not repeating the same recipes.")
                return 0


if __name__ == "__main__":
    raise SystemExit(main())
