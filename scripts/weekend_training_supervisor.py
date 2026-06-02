#!/usr/bin/env python3
"""Run weekend training experiments sequentially and keep status files fresh."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


PROJECT = Path("/opt/app/project/main")
PY = "python3"
RUN_DIR = PROJECT / "outputs" / "weekend_training"
LOG_DIR = Path("/opt/app/datasets/approved_followup_queue_20260527")
FACIAL_ROOT = Path("/opt/app/storage/training/fall-detection/facial-state")
STATUS_JSON = RUN_DIR / "weekend_training_status.json"
STATUS_MD = RUN_DIR / "weekend_training_status.md"
MAIN_LOG = RUN_DIR / "weekend_training_supervisor.log"


def ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{ts()}] {msg}"
    print(line, flush=True)
    with MAIN_LOG.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_status(stage: str, extra: dict | None = None) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "stage": stage,
        "last_update": ts(),
        "supervisor_pid": os.getpid(),
        "main_log": str(MAIN_LOG),
    }
    if extra:
        data.update(extra)
    STATUS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Weekend Training Status",
        "",
        f"- stage: `{stage}`",
        f"- updated: `{data['last_update']}`",
        f"- supervisor pid: `{os.getpid()}`",
        f"- log: `{MAIN_LOG}`",
    ]
    for key, value in (extra or {}).items():
        lines.append(f"- {key}: `{value}`")
    STATUS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_presentation_refresh() -> None:
    try:
        subprocess.run([PY, str(PROJECT / "scripts" / "generate_monday_presentation.py")], cwd=str(PROJECT), timeout=180)
    except Exception as exc:
        log(f"presentation refresh failed: {exc}")


def process_matches(needle: str) -> list[str]:
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
    except Exception:
        return []
    lines = []
    for line in out.splitlines():
        if needle in line and "weekend_training_supervisor.py" not in line:
            lines.append(line.strip())
    return lines


def wait_for_existing(label: str, needle: str, progress_log: Path) -> None:
    log(f"wait for existing training: {label}")
    start = time.time()
    while True:
        matches = process_matches(needle)
        tail = "-"
        if progress_log.exists():
            try:
                lines = progress_log.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = lines[-1] if lines else "-"
            except Exception:
                pass
        write_status(f"waiting:{label}", {
            "elapsed_min": round((time.time() - start) / 60, 1),
            "running": len(matches),
            "latest_log": tail,
        })
        if not matches:
            log(f"existing training finished: {label}")
            break
        log(f"{label} still running; latest={tail}")
        run_presentation_refresh()
        time.sleep(300)


def metric(summary: dict, key: str) -> float:
    try:
        return float(((summary or {}).get("best_metrics") or {}).get(key) or 0.0)
    except Exception:
        return 0.0


def promote_if_better(kind: str, experiment_dir: Path) -> None:
    if kind == "aihub82":
        src_model = experiment_dir / "aihub82_facial_emotion_mobilenetv3.pt"
        src_summary = experiment_dir / "aihub82_facial_emotion_summary.json"
        dst_model = FACIAL_ROOT / "aihub82_facial_emotion_mobilenetv3.pt"
        dst_summary = FACIAL_ROOT / "aihub82_facial_emotion_summary.json"
    elif kind == "aihub173":
        src_model = experiment_dir / "aihub173_driver_state_mobilenetv3.pt"
        src_summary = experiment_dir / "aihub173_driver_state_summary.json"
        dst_model = FACIAL_ROOT / "aihub173_driver_state_mobilenetv3.pt"
        dst_summary = FACIAL_ROOT / "aihub173_driver_state_summary.json"
    else:
        return
    if not src_model.exists() or not src_summary.exists():
        log(f"promotion skipped; missing output for {kind}: {experiment_dir}")
        return
    src = read_json(src_summary)
    dst = read_json(dst_summary)
    src_score = metric(src, "macro_f1")
    dst_score = metric(dst, "macro_f1")
    if src_score >= dst_score:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_model = dst_model.with_name(dst_model.stem + f".backup_{stamp}" + dst_model.suffix)
        backup_summary = dst_summary.with_name(dst_summary.stem + f".backup_{stamp}" + dst_summary.suffix)
        if dst_model.exists():
            shutil.copy2(dst_model, backup_model)
        if dst_summary.exists():
            shutil.copy2(dst_summary, backup_summary)
        shutil.copy2(src_model, dst_model)
        shutil.copy2(src_summary, dst_summary)
        log(f"promoted {kind}: macro_f1 {dst_score:.4f} -> {src_score:.4f}")
    else:
        log(f"promotion skipped for {kind}: candidate {src_score:.4f} < active {dst_score:.4f}")


def run_command(label: str, cmd: list[str], log_path: Path, promote_kind: str | None = None, promote_dir: Path | None = None) -> int:
    log(f"start {label}: {' '.join(cmd)}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"\n[{ts()}] START {label}\n")
        proc = subprocess.Popen(cmd, cwd=str(PROJECT), stdout=fp, stderr=subprocess.STDOUT, text=True)
    while True:
        rc = proc.poll()
        tail = "-"
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = lines[-1] if lines else "-"
        except Exception:
            pass
        write_status(f"running:{label}", {
            "pid": proc.pid,
            "elapsed_min": round((time.time() - start) / 60, 1),
            "log": str(log_path),
            "latest_log": tail,
        })
        log(f"{label} progress: {tail}")
        run_presentation_refresh()
        if rc is not None:
            log(f"complete {label}: rc={rc}")
            if promote_kind and promote_dir and rc == 0:
                promote_if_better(promote_kind, promote_dir)
                run_presentation_refresh()
            return int(rc)
        time.sleep(300)


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    write_status("starting")
    run_presentation_refresh()

    wait_for_existing("AI-Hub82 v8 current", "aihub82_v8_agree3_large", LOG_DIR / "aihub82_v8_agree3_large.log")
    promote_if_better("aihub82", FACIAL_ROOT / "experiments" / "aihub82_v8_agree3_large")
    run_presentation_refresh()

    wait_for_existing("AI-Hub173 v3 current", "aihub173_v3_large_smooth", LOG_DIR / "aihub173_v3_large_smooth.log")
    promote_if_better("aihub173", FACIAL_ROOT / "experiments" / "aihub173_v3_large_smooth")
    run_presentation_refresh()

    tasks = [
        (
            "behavior_grouped_retrain",
            [PY, str(PROJECT / "scripts" / "retrain_xg_posture_grouped.py")],
            RUN_DIR / "behavior_grouped_retrain.log",
            None,
            None,
        ),
        (
            "aihub82_v9_agree2_large",
            [
                PY, str(PROJECT / "scripts" / "train_facial_emotion_aihub82.py"),
                "--dataset-root", "/opt/app/datasets/facial_state/aihub_82_korean_emotion",
                "--output-dir", str(FACIAL_ROOT / "experiments" / "aihub82_v9_agree2_large"),
                "--epochs", "5",
                "--batch-size", "32",
                "--image-size", "160",
                "--max-train-per-class", "10000",
                "--max-val-per-class", "2000",
                "--lr", "0.00012",
                "--num-workers", "0",
                "--seed", "20260601",
                "--train-min-agreement", "2",
                "--val-min-agreement", "2",
                "--model-type", "mobilenet_v3_large",
                "--label-smoothing", "0.04",
            ],
            RUN_DIR / "aihub82_v9_agree2_large.log",
            "aihub82",
            FACIAL_ROOT / "experiments" / "aihub82_v9_agree2_large",
        ),
        (
            "aihub173_v4_large_moredata",
            [
                PY, str(PROJECT / "scripts" / "train_driver_state_aihub173.py"),
                "--dataset-root", "/opt/app/datasets/facial_state/aihub_173_driver_state",
                "--output-dir", str(FACIAL_ROOT / "experiments" / "aihub173_v4_large_moredata"),
                "--epochs", "6",
                "--batch-size", "32",
                "--image-size", "160",
                "--max-train-per-class", "8000",
                "--max-val-per-class", "1500",
                "--lr", "0.00010",
                "--num-workers", "0",
                "--seed", "20260602",
                "--model-type", "mobilenet_v3_large",
                "--label-smoothing", "0.03",
            ],
            RUN_DIR / "aihub173_v4_large_moredata.log",
            "aihub173",
            FACIAL_ROOT / "experiments" / "aihub173_v4_large_moredata",
        ),
        (
            "aihub82_v10_strict_neutral_guard",
            [
                PY, str(PROJECT / "scripts" / "train_facial_emotion_aihub82.py"),
                "--dataset-root", "/opt/app/datasets/facial_state/aihub_82_korean_emotion",
                "--output-dir", str(FACIAL_ROOT / "experiments" / "aihub82_v10_strict_neutral_guard"),
                "--epochs", "4",
                "--batch-size", "32",
                "--image-size", "160",
                "--max-train-per-class", "9000",
                "--max-val-per-class", "1800",
                "--lr", "0.00008",
                "--num-workers", "0",
                "--seed", "20260603",
                "--train-min-agreement", "3",
                "--val-min-agreement", "2",
                "--model-type", "mobilenet_v3_large",
                "--label-smoothing", "0.04",
            ],
            RUN_DIR / "aihub82_v10_strict_neutral_guard.log",
            "aihub82",
            FACIAL_ROOT / "experiments" / "aihub82_v10_strict_neutral_guard",
        ),
    ]
    for label, cmd, log_path, promote_kind, promote_dir in tasks:
        run_command(label, cmd, log_path, promote_kind, promote_dir)

    write_status("completed")
    run_presentation_refresh()
    log("weekend training queue completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
