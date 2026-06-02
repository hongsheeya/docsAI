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
HEARTBEAT_SEC = int(os.environ.get("FALLAI_AIHUB82_HEARTBEAT_SEC", "600") or 600)
SLEEP_BETWEEN_RUNS_SEC = int(os.environ.get("FALLAI_AIHUB82_SLEEP_BETWEEN_RUNS_SEC", "60") or 60)
MAX_RUNS = int(os.environ.get("FALLAI_AIHUB82_MAX_RUNS", "0") or 0)


EXPERIMENTS = [
    {
        "name": "agree2_large_192_smooth002",
        "epochs": 6,
        "batch_size": 24,
        "image_size": 192,
        "max_train_per_class": 12000,
        "max_val_per_class": 2500,
        "lr": "0.00010",
        "train_min_agreement": 2,
        "val_min_agreement": 2,
        "label_smoothing": "0.02",
        "seed": 2026060201,
    },
    {
        "name": "agree2_large_160_smooth006",
        "epochs": 7,
        "batch_size": 32,
        "image_size": 160,
        "max_train_per_class": 14000,
        "max_val_per_class": 2500,
        "lr": "0.00008",
        "train_min_agreement": 2,
        "val_min_agreement": 2,
        "label_smoothing": "0.06",
        "seed": 2026060202,
    },
    {
        "name": "agree3_large_192_smooth004",
        "epochs": 6,
        "batch_size": 24,
        "image_size": 192,
        "max_train_per_class": 12000,
        "max_val_per_class": 2200,
        "lr": "0.00008",
        "train_min_agreement": 3,
        "val_min_agreement": 2,
        "label_smoothing": "0.04",
        "seed": 2026060203,
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
        return float(((summary or {}).get("best_metrics") or {}).get(key) or 0.0)
    except Exception:
        return 0.0


def latest_log_line(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-1] if lines else "-"
    except Exception:
        return "-"


def log(message: str) -> None:
    ensure_dirs()
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    with MAIN_LOG.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def write_status(stage: str, **extra: Any) -> dict[str, Any]:
    ensure_dirs()
    active_summary = read_json(ACTIVE_SUMMARY)
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
    }
    data.update(extra)
    STATUS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
    for key in ["experiment", "candidate_macro_f1", "candidate_accuracy", "promoted", "latest_log", "elapsed_min"]:
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


def promote_if_better(experiment_dir: Path) -> tuple[bool, float, float]:
    src_model = experiment_dir / "aihub82_facial_emotion_mobilenetv3.pt"
    src_summary = experiment_dir / "aihub82_facial_emotion_summary.json"
    if not src_model.exists() or not src_summary.exists():
        log(f"promotion skipped; missing candidate outputs: {experiment_dir}")
        return False, 0.0, metric(read_json(ACTIVE_SUMMARY))

    candidate_summary = read_json(src_summary)
    active_summary = read_json(ACTIVE_SUMMARY)
    candidate_score = metric(candidate_summary)
    active_score = metric(active_summary)
    if candidate_score <= active_score + 1e-6:
        log(f"promotion skipped: candidate macro_f1 {candidate_score:.4f} <= active {active_score:.4f}")
        return False, candidate_score, active_score

    backup_stamp = stamp()
    if ACTIVE_MODEL.exists():
        shutil.copy2(ACTIVE_MODEL, ACTIVE_MODEL.with_name(ACTIVE_MODEL.stem + f".backup_{backup_stamp}" + ACTIVE_MODEL.suffix))
    if ACTIVE_SUMMARY.exists():
        shutil.copy2(ACTIVE_SUMMARY, ACTIVE_SUMMARY.with_name(ACTIVE_SUMMARY.stem + f".backup_{backup_stamp}" + ACTIVE_SUMMARY.suffix))
    shutil.copy2(src_model, ACTIVE_MODEL)
    shutil.copy2(src_summary, ACTIVE_SUMMARY)
    log(f"promoted AI-Hub82: macro_f1 {active_score:.4f} -> {candidate_score:.4f}")
    return True, candidate_score, active_score


def build_command(exp: dict[str, Any], out_dir: Path) -> list[str]:
    return [
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
        "0",
        "--seed",
        str(exp["seed"]),
        "--train-min-agreement",
        str(exp["train_min_agreement"]),
        "--val-min-agreement",
        str(exp["val_min_agreement"]),
        "--model-type",
        "mobilenet_v3_large",
        "--label-smoothing",
        str(exp["label_smoothing"]),
    ]


def run_experiment(exp: dict[str, Any], run_index: int) -> None:
    run_label = f"{run_index:04d}_{exp['name']}_{stamp()}"
    out_dir = FACIAL_ROOT / "experiments" / "aihub82_continuous" / run_label
    log_path = RUN_DIR / f"{run_label}.log"
    command = build_command(exp, out_dir)
    log(f"start experiment {run_label}: {' '.join(command)}")
    write_status("running", experiment=run_label, output_dir=str(out_dir), log_path=str(log_path), latest_log="-")
    env = os.environ.copy()
    env.setdefault("TORCH_NUM_THREADS", "2")
    started = time.time()
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"\n[{utc_now()}] START {run_label}\n")
        proc = subprocess.Popen(command, cwd=str(PROJECT), stdout=fp, stderr=subprocess.STDOUT, env=env, text=True)
    while True:
        rc = proc.poll()
        elapsed_min = round((time.time() - started) / 60.0, 1)
        write_status(
            "running",
            experiment=run_label,
            pid=proc.pid,
            elapsed_min=elapsed_min,
            log_path=str(log_path),
            latest_log=latest_log_line(log_path),
        )
        if rc is not None:
            log(f"complete experiment {run_label}: rc={rc}")
            if rc == 0:
                promoted, candidate, active_before = promote_if_better(out_dir)
                candidate_summary = read_json(out_dir / "aihub82_facial_emotion_summary.json")
                write_status(
                    "completed",
                    experiment=run_label,
                    promoted=promoted,
                    candidate_macro_f1=round(candidate, 4),
                    candidate_accuracy=round(metric(candidate_summary, "accuracy"), 4),
                    active_before_macro_f1=round(active_before, 4),
                    latest_log=latest_log_line(log_path),
                    log_path=str(log_path),
                )
            else:
                write_status("failed", experiment=run_label, rc=rc, latest_log=latest_log_line(log_path), log_path=str(log_path))
            return
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
    write_status("starting")
    run_index = 0
    while True:
        for exp in EXPERIMENTS:
            run_index += 1
            run_experiment(exp, run_index)
            if MAX_RUNS and run_index >= MAX_RUNS:
                write_status("completed-max-runs", run_count=run_index)
                return 0
            time.sleep(SLEEP_BETWEEN_RUNS_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
