#!/usr/bin/env python3
"""Continuously train FallAI model families toward a gradual 95% target."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any


PROJECT = Path("/opt/app/project/main")
PY = os.environ.get("FALLAI_PYTHON", sys.executable)
RUN_DIR = Path("/mnt/data/wiz/storage/training/fall-detection/continuous-model-supervisor")
STATUS_JSON = RUN_DIR / "status.json"
MAIN_LOG = RUN_DIR / "supervisor.log"
PID_FILE = RUN_DIR / "supervisor.pid"
HISTORY_JSONL = RUN_DIR / "model_feature_version_audit.jsonl"
LATEST_SNAPSHOT_JSON = RUN_DIR / "latest_model_feature_snapshot.json"
FINAL_TARGET_F1 = float(os.environ.get("FALLAI_ALL_MODEL_FINAL_TARGET_F1", os.environ.get("FALLAI_ALL_MODEL_TARGET_F1", "0.95")) or 0.95)
TARGET_LADDER = [
    float(value)
    for value in str(os.environ.get("FALLAI_ALL_MODEL_TARGET_LADDER", "0.90,0.93,0.95") or "0.90,0.93,0.95").split(",")
    if str(value).strip()
]
if FINAL_TARGET_F1 not in TARGET_LADDER:
    TARGET_LADDER.append(FINAL_TARGET_F1)
TARGET_LADDER = sorted({round(max(0.0, min(1.0, value)), 4) for value in TARGET_LADDER})
TARGET_F1 = FINAL_TARGET_F1
HEARTBEAT_SEC = int(os.environ.get("FALLAI_ALL_MODEL_HEARTBEAT_SEC", "30") or 30)
IDLE_SLEEP_SEC = int(os.environ.get("FALLAI_ALL_MODEL_IDLE_SLEEP_SEC", "45") or 45)
DASHBOARD_RETRY_COOLDOWN_SEC = int(os.environ.get("FALLAI_DASHBOARD_RETRY_COOLDOWN_SEC", "1800") or 1800)
MODEL_FAMILIES = {
    "rf-dual",
    "rf-pipeline",
    "rf-fall-v2",
    "xg-posture",
    "xg-posture-occlusion-aux",
    "facial-aihub82",
    "driver-aihub173",
}

OCCLUSION_POLICY_GRID = [
    {"avg_conf_lt": 0.30, "lower_body_visibility_lt": 0.36, "posture_margin_lt": 0.05},
    {"avg_conf_lt": 0.34, "lower_body_visibility_lt": 0.38, "posture_margin_lt": 0.05},
    {"avg_conf_lt": 0.36, "lower_body_visibility_lt": 0.40, "posture_margin_lt": 0.06},
    {"avg_conf_lt": 0.38, "lower_body_visibility_lt": 0.42, "posture_margin_lt": 0.07},
    {"avg_conf_lt": 0.40, "lower_body_visibility_lt": 0.44, "posture_margin_lt": 0.08},
    {"avg_conf_lt": 0.42, "lower_body_visibility_lt": 0.46, "posture_margin_lt": 0.07},
    {"avg_conf_lt": 0.44, "lower_body_visibility_lt": 0.48, "posture_margin_lt": 0.08},
    {"avg_conf_lt": 0.46, "lower_body_visibility_lt": 0.50, "posture_margin_lt": 0.09},
    {"avg_conf_lt": 0.50, "lower_body_visibility_lt": 0.52, "posture_margin_lt": 0.10},
    {"avg_conf_lt": 0.52, "lower_body_visibility_lt": 0.56, "posture_margin_lt": 0.11},
]


def target_percent_text() -> str:
    return f"{FINAL_TARGET_F1 * 100:.0f}%"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)


def log(message: str) -> None:
    ensure_dirs()
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    with MAIN_LOG.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


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
        log(f"another all-model supervisor is already running: pid={old_pid}")
        return False
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def load_video_analysis():
    module_path = PROJECT / "src" / "model" / "struct" / "video_analysis.py"
    spec = importlib.util.spec_from_file_location("all_model_supervisor_video_analysis", module_path)
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


def metric(item: dict[str, Any]) -> float:
    metrics = item.get("metrics") or {}
    for key in ("f1", "macro_f1", "accuracy"):
        try:
            value = metrics.get(key)
            if value is not None:
                return float(value)
        except Exception:
            pass
    return 0.0


def staged_target_for_score(score: float) -> float:
    score = float(score or 0.0)
    for target in TARGET_LADDER:
        if score + 1e-6 < target:
            return target
    return FINAL_TARGET_F1


def summary_feature_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
    features = (
        summary.get("features")
        or summary.get("feature_names")
        or summary.get("feature_cols")
        or summary.get("feature_columns")
        or []
    )
    if not isinstance(features, list):
        features = []
    importance = (
        summary.get("feature_importance")
        or summary.get("feature_importances")
        or summary.get("all_importance")
        or {}
    )
    if not isinstance(importance, dict):
        importance = {}
    return {
        "feature_count": int(summary.get("feature_count", 0) or summary.get("n_features", 0) or len(features) or 0),
        "features": [str(value) for value in features],
        "feature_importance": importance,
        "algorithm": summary.get("algorithm") or summary.get("selected_model") or summary.get("model_type") or "",
        "thresholds": summary.get("thresholds") or summary.get("tuned_thresholds") or summary.get("trigger_policy") or {},
        "class_distribution": summary.get("class_distribution") or {},
        "summary_path": item.get("summary_path") or "",
        "primary_model_path": item.get("primary_model_path") or "",
    }


def active_model_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in registry.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("source") != "active":
            continue
        if item.get("family") not in MODEL_FAMILIES:
            continue
        rows.append(item)
    return rows


def current_state() -> dict[str, Any]:
    analyzer = load_video_analysis()
    registry = analyzer.model_registry()
    rows = active_model_rows(registry)
    low = []
    below_final = []
    for item in rows:
        score = metric(item)
        next_target = staged_target_for_score(score)
        if score and score < FINAL_TARGET_F1:
            below_final.append({
                "model_id": item.get("model_id"),
                "family": item.get("family"),
                "label": item.get("label"),
                "version": item.get("display_version") or item.get("version_badge") or "-",
                "score": round(score, 4),
                "next_target_f1": round(next_target, 4),
                "final_target_f1": round(FINAL_TARGET_F1, 4),
            })
        if score and score < next_target:
            low.append({
                "model_id": item.get("model_id"),
                "family": item.get("family"),
                "label": item.get("label"),
                "version": item.get("display_version") or item.get("version_badge") or "-",
                "score": round(score, 4),
                "target_f1": round(next_target, 4),
                "final_target_f1": round(FINAL_TARGET_F1, 4),
            })
    return {
        "registry_updated_at": registry.get("updated_at"),
        "active_models": [
            {
                "model_id": item.get("model_id"),
                "family": item.get("family"),
                "label": item.get("label"),
                "version": item.get("display_version") or item.get("version_badge") or "-",
                "score": round(metric(item), 4),
                "next_target_f1": round(staged_target_for_score(metric(item)), 4),
                "final_target_f1": round(FINAL_TARGET_F1, 4),
                "target_met": metric(item) >= staged_target_for_score(metric(item)),
                "final_target_met": metric(item) >= FINAL_TARGET_F1,
                **summary_feature_snapshot(item),
            }
            for item in rows
        ],
        "below_target": low,
        "below_final_target": below_final,
        "occlusion_policy": registry.get("occlusion_policy") or {},
    }


def write_status(stage: str, **extra: Any) -> dict[str, Any]:
    data = read_json(STATUS_JSON)
    current_command = str(extra.get("current_command") or data.get("current_command") or "")
    if "message" not in extra:
        if current_command:
            extra["message"] = f"{current_command} 실행 중입니다. 전체 모델 목표는 {target_percent_text()}입니다."
        elif stage in {"checking", "cycle-complete"}:
            extra["message"] = f"전체 모델을 {target_percent_text()} 목표 기준으로 점검 중입니다."
    if "eta_text" not in extra and current_command:
        extra["eta_text"] = "학습 중"
    data.update({
        "ok": True,
        "stage": stage,
        "status": extra.get("status", stage),
        "updated_at": utc_now(),
        "supervisor_pid": os.getpid(),
        "target_f1": FINAL_TARGET_F1,
        "final_target_f1": FINAL_TARGET_F1,
        "target_ladder": TARGET_LADDER,
        "heartbeat_sec": HEARTBEAT_SEC,
        "main_log": str(MAIN_LOG),
        "audit_log": str(HISTORY_JSONL),
        "latest_feature_snapshot": str(LATEST_SNAPSHOT_JSON),
    })
    data.update(extra)
    write_json(STATUS_JSON, data)
    return data


def append_audit_snapshot(cycle: int, state: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    record = {
        "updated_at": utc_now(),
        "cycle": cycle,
        "final_target_f1": FINAL_TARGET_F1,
        "target_ladder": TARGET_LADDER,
        "active_models": state.get("active_models") or [],
        "below_target": state.get("below_target") or [],
        "below_final_target": state.get("below_final_target") or [],
        "actions": actions,
    }
    ensure_dirs()
    with HISTORY_JSONL.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    write_json(LATEST_SNAPSHOT_JSON, record)


def run_command(name: str, command: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.time()
    log_path = RUN_DIR / f"{name}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        merged_env.setdefault(key, "1")
    log(f"start {name}: {' '.join(command)}")
    with log_path.open("ab") as log_file:
        proc = subprocess.Popen(
            command,
            cwd=str(PROJECT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=merged_env,
            start_new_session=True,
        )
        while proc.poll() is None:
            elapsed = round(time.time() - started, 1)
            write_status(
                "running-command",
                current_command=name,
                current_command_pid=proc.pid,
                current_command_log=str(log_path),
                current_command_elapsed_sec=elapsed,
            )
            time.sleep(HEARTBEAT_SEC)
    elapsed = round(time.time() - started, 2)
    ok = proc.returncode == 0
    log(f"finish {name}: returncode={proc.returncode} elapsed={elapsed}s log={log_path}")
    return {"name": name, "ok": ok, "returncode": proc.returncode, "elapsed_sec": elapsed, "log_path": str(log_path)}


def ensure_aihub82_supervisor() -> dict[str, Any]:
    status_path = PROJECT / "outputs" / "continuous_training" / "aihub82_status.json"
    status = read_json(status_path)
    redownload_pid = int(status.get("redownload_pid") or 0)
    redownload_current = int(status.get("redownload_current") or 0)
    redownload_total = int(status.get("redownload_total") or 0)
    if (
        pid_running(redownload_pid)
        and redownload_total > 0
        and redownload_current < redownload_total
        and str(status.get("stage") or status.get("status") or "") == "running"
    ):
        status.update({
            "target_macro_f1": FINAL_TARGET_F1,
            "stretch_macro_f1": FINAL_TARGET_F1,
            "status": "running",
            "stage": "running",
            "message": status.get("message") or "AI-Hub 82 표정 데이터 재수신 완료 후 학습을 시작합니다.",
        })
        write_json(status_path, status)
        return {
            "ok": True,
            "status": "waiting_for_redownload",
            "redownload_pid": redownload_pid,
            "redownload_current": redownload_current,
            "redownload_total": redownload_total,
            "status_path": str(status_path),
        }
    pid = int(status.get("supervisor_pid") or 0)
    if pid_running(pid) and status.get("stage") in {"running", "already-running", "sleeping", "completed"}:
        status.update({
            "target_macro_f1": FINAL_TARGET_F1,
            "stretch_macro_f1": FINAL_TARGET_F1,
            "status": status.get("status") or status.get("stage") or "running",
            "message": status.get("message") or f"AI-Hub 82 표정 모델 {target_percent_text()} 목표 연속 학습 중입니다.",
        })
        write_json(status_path, status)
        return {"ok": True, "already_running": True, "pid": pid, "status_path": str(status_path)}
    env = os.environ.copy()
    env.update({
        "FALLAI_AIHUB82_TARGET_MACRO_F1": str(FINAL_TARGET_F1),
        "FALLAI_AIHUB82_STRETCH_MACRO_F1": str(FINAL_TARGET_F1),
        "FALLAI_AIHUB82_MAX_RUNS": "0",
        "FALLAI_AIHUB82_SLEEP_BETWEEN_RUNS_SEC": "15",
        "FALLAI_AIHUB82_HEARTBEAT_SEC": str(max(60, HEARTBEAT_SEC)),
    })
    log_path = RUN_DIR / "aihub82-supervisor.spawn.log"
    with log_path.open("ab") as fp:
        proc = subprocess.Popen(
            [PY, str(PROJECT / "scripts" / "continuous_aihub82_training_supervisor.py")],
            cwd=str(PROJECT),
            stdout=fp,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    return {"ok": True, "started": True, "pid": proc.pid, "log_path": str(log_path), "status_path": str(status_path)}


def normalize_dashboard_target(value: str) -> str:
    raw = str(value or "").strip()
    if raw in {"rf-dual", "rf-pipeline", "rf-fall-v2", "rf"}:
        return "rf-fall-v2"
    if raw in {"xg-posture", "posture"}:
        return "xg-posture"
    return raw


def dashboard_job_files() -> list[Path]:
    root = Path("/mnt/data/wiz/storage/training/fall-detection/training-jobs")
    try:
        return sorted(root.glob("*.json"))
    except Exception:
        return []


def recent_dashboard_job(target_model: str, statuses: set[str] | None = None) -> dict[str, Any]:
    target_model = normalize_dashboard_target(target_model)
    rows: list[tuple[float, Path, dict[str, Any]]] = []
    for path in dashboard_job_files():
        data = read_json(path)
        status = str(data.get("status") or "")
        if statuses and status not in statuses:
            continue
        if normalize_dashboard_target(data.get("target_model") or data.get("job_type") or "") != target_model:
            continue
        try:
            mtime = path.stat().st_mtime
        except Exception:
            mtime = 0.0
        rows.append((mtime, path, data))
    if not rows:
        return {}
    rows.sort(key=lambda row: row[0], reverse=True)
    latest = dict(rows[0][2])
    latest["_path"] = str(rows[0][1])
    latest["_mtime"] = rows[0][0]
    return latest


def dashboard_retry_block(target_model: str) -> dict[str, Any]:
    latest = recent_dashboard_job(target_model, {"failed", "blocked", "completed"})
    if not latest:
        return {}
    age = time.time() - float(latest.get("_mtime") or 0.0)
    if age > DASHBOARD_RETRY_COOLDOWN_SEC:
        return {}
    return {
        "ok": False,
        "status": "cooldown",
        "job_id": latest.get("job_id"),
        "target_model": normalize_dashboard_target(target_model),
        "age_sec": round(age, 1),
        "cooldown_sec": DASHBOARD_RETRY_COOLDOWN_SEC,
        "message": latest.get("message") or "최근 같은 대상 학습이 끝나서 중복 실행을 잠시 막았습니다.",
    }


def reconcile_dashboard_jobs() -> list[dict[str, Any]]:
    analyzer = load_video_analysis()
    actions = []
    for path in dashboard_job_files():
        data = read_json(path)
        if data.get("status") != "completed_pending_apply":
            continue
        job_id = data.get("job_id") or path.stem
        try:
            applied = analyzer.apply_training_job(job_id)
            actions.append({"dashboard_apply": {"ok": True, "job_id": job_id, "status": applied.get("status"), "message": applied.get("message")}})
        except Exception as exc:
            data["status"] = "completed"
            data["manual_apply_required"] = False
            data["archived_from_status"] = "completed_pending_apply"
            data["archived_at"] = utc_now()
            data["message"] = str(exc) or "운영 모델보다 낮아 적용하지 않고 보관했습니다."
            write_json(path, data)
            actions.append({"dashboard_archive": {"ok": True, "job_id": job_id, "reason": data["message"]}})
    return actions


def run_occlusion_training(cycle: int) -> dict[str, Any]:
    policy = OCCLUSION_POLICY_GRID[cycle % len(OCCLUSION_POLICY_GRID)]
    env = {
        "POSTURE_SAVE_OCCLUSION_AUX": "1",
        "POSTURE_OCC_AUX_MIN_SAVE_F1": "0.0",
        "POSTURE_INCLUDE_SYNTH_LOWER_OCCLUSION": "1",
        "POSTURE_INCLUDE_SYNTH_VERTICAL_OCCLUSION": "1",
        "POSTURE_INCLUDE_TREE_ENSEMBLES": "1",
        "POSTURE_FEATURE_SET_FILTER": "motion_breakthrough,geometry_motion,full,occlusion_aware,upper_body_motion_focus",
        "POSTURE_MODEL_FILTER": "extra_trees,xgb",
        "POSTURE_SYNTH_STATIC_OCC_LIMIT": "220",
        "POSTURE_SYNTH_STATIC_VERTICAL_OCC_LIMIT": "220",
        "POSTURE_SYNTH_SEQ_OCC_LIMIT": "72",
        "POSTURE_SYNTH_SEQ_VERTICAL_OCC_LIMIT": "72",
        "POSTURE_SYNTH_LOWER_OCCLUSION_MODES": "waist,thigh,knee,random_mild,random_moderate,random_severe",
        "POSTURE_SYNTH_VERTICAL_OCCLUSION_MODES": "left,right,left_mild,left_moderate,left_severe,right_mild,right_moderate,right_severe",
        "POSTURE_SYNTH_STATIC_VERTICAL_OCCLUSION_MODES": "left,right,left_mild,left_moderate,left_severe,right_mild,right_moderate,right_severe",
        "POSTURE_LOWER_OCCLUSION_LIMIT": "90",
        "POSTURE_OCC_AUX_AVG_CONF_LT": str(policy["avg_conf_lt"]),
        "POSTURE_OCC_AUX_LOWER_VIS_LT": str(policy["lower_body_visibility_lt"]),
        "POSTURE_OCC_AUX_MARGIN_LT": str(policy["posture_margin_lt"]),
    }
    write_status("occlusion-training", occlusion_policy_candidate=policy)
    result = run_command("occlusion-aux-train", [PY, str(PROJECT / "scripts" / "retrain_xg_posture_sequence.py")], env=env)
    result["policy"] = policy
    return result


def occlusion_source_status() -> dict[str, Any]:
    analyzer = load_video_analysis()
    sources = analyzer._aihub61_label_zip_paths()
    labels = sorted({label for label, _path in sources})
    usable_sources = []
    unusable_sources = []
    for label, raw_path in sources:
        path = Path(str(raw_path))
        usable_json = 0
        reason = ""
        try:
            if path.is_dir():
                usable_json = sum(1 for _ in path.rglob("*.json"))
                if usable_json <= 0:
                    reason = "no_json_labels"
            elif path.is_file() and path.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(path) as archive:
                        usable_json = sum(
                            1
                            for name in archive.namelist()
                            if name.endswith(".json") and "/._" not in name and not Path(name).name.startswith("._")
                        )
                    if usable_json <= 0:
                        reason = "no_json_labels"
                except zipfile.BadZipFile:
                    reason = "bad_zip"
            else:
                reason = "unsupported_source"
        except Exception as exc:
            reason = f"{type(exc).__name__}:{str(exc)[:80]}"
        row = {"label": label, "path": str(path), "json_count": usable_json}
        if usable_json > 0:
            usable_sources.append(row)
        else:
            row["reason"] = reason or "no_usable_labels"
            unusable_sources.append(row)
    split_parts = []
    search_root = Path("/opt/app/datasets/action_behavior/aihub_61_person_action_2020")
    if search_root.exists():
        split_parts = [str(path) for path in list(search_root.rglob("*.part*"))[:20]]
    aihub71461_label_count = count_71461_pose_labels()
    if aihub71461_label_count > 0:
        usable_sources.append({
            "label": "AI-Hub 71461 pose labels",
            "path": os.environ.get("FALLAI_71461_DATASET_ROOTS", "/opt/app/tmp/datasets/action_behavior/aihub_71461"),
            "json_count": aihub71461_label_count,
        })
    ready = bool(usable_sources)
    return {
        "ready": ready,
        "labels": labels,
        "source_count": len(sources),
        "usable_source_count": len(usable_sources),
        "aihub71461_pose_label_count": aihub71461_label_count,
        "usable_sources": usable_sources[:20],
        "unusable_sources": unusable_sources[:20],
        "sources": [{"label": label, "path": path} for label, path in sources[:20]],
        "split_part_count": sum(1 for _ in search_root.rglob("*.part*")) if search_root.exists() else 0,
        "split_part_examples": split_parts,
        "message": (
            "AI-Hub61/71461 JSON label source ready"
            if ready
            else (
                "AI-Hub61 files exist, but no usable 2D JSON labels were found; occlusion retrain is blocked until JSON/HITL posture labels are added."
                if sources
                else "AI-Hub61 source exists only as split zip/tar parts or is missing; occlusion retrain is waiting for source assembly."
            )
        ),
    }


def count_71461_pose_labels(limit: int = 10000) -> int:
    raw_roots = os.environ.get("FALLAI_71461_DATASET_ROOTS", "/opt/app/tmp/datasets/action_behavior/aihub_71461")
    roots = [Path(item.strip()) for item in re.split(r"[,;:]", raw_roots) if item.strip()]
    count = 0
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*.json"):
                if "02.라벨링데이터" not in str(path):
                    continue
                count += 1
                if count >= limit:
                    return count
        except Exception:
            continue
    return count


def start_dashboard_training(target_model: str = "rf-fall-v2", job_type: str = "rf") -> dict[str, Any]:
    target_model = normalize_dashboard_target(target_model)
    running = recent_dashboard_job(target_model, {"queued", "running", "completed_pending_apply"})
    if running:
        return {
            "ok": True,
            "already_active": True,
            "job_id": running.get("job_id"),
            "status": running.get("status"),
            "target_model": target_model,
            "message": "같은 대상의 학습 job이 이미 진행/적용 대기 중입니다.",
        }
    retry = dashboard_retry_block(target_model)
    if retry:
        return retry
    analyzer = load_video_analysis()
    job = analyzer.start_training_job(
        job_type=job_type,
        note=f"continuous all-model supervisor: gradual target active model F1 >= {FINAL_TARGET_F1:.2f}",
        apply_mode="manual",
        target_model=target_model,
    )
    return {"ok": bool(job.get("ok")), "job": job}


def posture_source_status() -> dict[str, Any]:
    analyzer = load_video_analysis()
    intake = analyzer._intake_summary()
    posture_counts = intake.get("posture_intake") or {}
    usable_posture = {
        str(label): int(count or 0)
        for label, count in posture_counts.items()
        if int(count or 0) >= 2
    }
    occlusion_sources = occlusion_source_status()
    aihub71461_label_count = count_71461_pose_labels()
    ready = len(usable_posture) >= 2 or bool(occlusion_sources.get("ready")) or aihub71461_label_count > 0
    return {
        "ready": ready,
        "posture_intake_counts": posture_counts,
        "usable_posture_label_count": len(usable_posture),
        "aihub71461_pose_label_count": aihub71461_label_count,
        "occlusion_source_ready": bool(occlusion_sources.get("ready")),
        "message": (
            "Posture/HITL or AI-Hub pose source ready"
            if ready
            else f"XG-Posture {target_percent_text()} 재학습에 필요한 2개 이상 자세 라벨/HITL 또는 AI-Hub 2D JSON 라벨이 부족합니다."
        ),
    }


def facial_root() -> Path:
    return Path("/mnt/data/wiz/storage/training/fall-detection/facial-state")


def write_continuous_status(name: str, data: dict[str, Any]) -> None:
    path = PROJECT / "outputs" / "continuous_training" / f"{name}_status.json"
    current = read_json(path)
    current.update(data)
    current.setdefault("ok", True)
    current["updated_at"] = utc_now()
    write_json(path, current)


def promote_aihub173_if_better(experiment_dir: Path) -> dict[str, Any]:
    src_summary = experiment_dir / "aihub173_driver_state_summary.json"
    src_model = experiment_dir / "aihub173_driver_state_mobilenetv3.pt"
    dst_summary = facial_root() / "aihub173_driver_state_summary.json"
    dst_model = facial_root() / "aihub173_driver_state_mobilenetv3.pt"
    candidate_summary = read_json(src_summary)
    active_summary = read_json(dst_summary)
    candidate_metrics = candidate_summary.get("best_metrics") or candidate_summary
    active_metrics = active_summary.get("best_metrics") or active_summary
    candidate_f1 = float(candidate_metrics.get("macro_f1") or candidate_metrics.get("f1_macro") or candidate_metrics.get("f1") or 0.0)
    active_f1 = float(active_metrics.get("macro_f1") or active_metrics.get("f1_macro") or active_metrics.get("f1") or 0.0)
    if candidate_f1 > active_f1 + 0.0005 and src_model.is_file():
        dst_model.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(src_model, dst_model)
        candidate_summary["promoted_from"] = str(experiment_dir)
        candidate_summary["promoted_at"] = utc_now()
        candidate_summary["target_macro_f1"] = FINAL_TARGET_F1
        write_json(dst_summary, candidate_summary)
        return {"promoted": True, "candidate_macro_f1": round(candidate_f1, 4), "active_before_macro_f1": round(active_f1, 4)}
    return {"promoted": False, "candidate_macro_f1": round(candidate_f1, 4), "active_before_macro_f1": round(active_f1, 4), "reason": "candidate_not_better"}


def run_aihub173_training(cycle: int) -> dict[str, Any]:
    running = recent_command_running("train_driver_state_aihub173.py")
    if running:
        first = running[0] if running else {}
        write_continuous_status("aihub173", {
            "stage": "running",
            "status": "running",
            "target_macro_f1": FINAL_TARGET_F1,
            "stretch_macro_f1": FINAL_TARGET_F1,
            "pid": first.get("pid") or "",
            "eta_text": "학습 중",
            "message": f"AI-Hub 173 상태 모델 {target_percent_text()} 목표 재학습 중입니다.",
            "processes": running[:3],
        })
        return {"ok": True, "already_running": True, "processes": running[:3]}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_tag = f"target{int(round(FINAL_TARGET_F1 * 100))}"
    exp_dir = facial_root() / "experiments" / "aihub173_continuous" / f"cycle{cycle:04d}_{target_tag}_large_{stamp}"
    command = [
        PY, str(PROJECT / "scripts" / "train_driver_state_aihub173.py"),
        "--dataset-root", "/opt/app/datasets/facial_state/aihub_173_driver_state",
        "--output-dir", str(exp_dir),
        "--epochs", "6",
        "--batch-size", "48",
        "--image-size", "192",
        "--max-train-per-class", "7000",
        "--max-val-per-class", "1400",
        "--num-workers", "0",
        "--lr", "0.00012",
        "--model-type", "mobilenet_v3_large",
        "--label-smoothing", "0.03",
        "--seed", str(2026061000 + cycle),
    ]
    write_continuous_status("aihub173", {
        "stage": "running",
        "status": "running",
        "target_macro_f1": FINAL_TARGET_F1,
        "stretch_macro_f1": FINAL_TARGET_F1,
        "experiment": exp_dir.name,
        "output_dir": str(exp_dir),
        "message": f"AI-Hub 173 상태 모델 {target_percent_text()} 목표 재학습 중입니다.",
    })
    started = time.time()
    log_path = RUN_DIR / f"aihub173-driver-train-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    merged_env = os.environ.copy()
    for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        merged_env.setdefault(key, "1")
    log(f"start aihub173-driver-train: {' '.join(command)}")
    with log_path.open("ab") as log_file:
        proc = subprocess.Popen(
            command,
            cwd=str(PROJECT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=merged_env,
            start_new_session=True,
        )
        while proc.poll() is None:
            elapsed = round(time.time() - started, 1)
            latest_line = ""
            try:
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                latest_line = next((line for line in reversed(lines[-80:]) if line.strip()), "")
            except Exception:
                latest_line = ""
            write_status(
                "running-command",
                current_command="aihub173-driver-train",
                current_command_pid=proc.pid,
                current_command_log=str(log_path),
                current_command_elapsed_sec=elapsed,
            )
            write_continuous_status("aihub173", {
                "stage": "running",
                "status": "running",
                "pid": proc.pid,
                "target_macro_f1": FINAL_TARGET_F1,
                "stretch_macro_f1": FINAL_TARGET_F1,
                "experiment": exp_dir.name,
                "output_dir": str(exp_dir),
                "log_path": str(log_path),
                "elapsed_min": round(elapsed / 60.0, 1),
                "eta_text": "학습 중",
                "latest_log": latest_line,
                "message": f"AI-Hub 173 상태 모델 {target_percent_text()} 목표 재학습 중입니다.",
            })
            time.sleep(HEARTBEAT_SEC)
    elapsed = round(time.time() - started, 2)
    result = {
        "name": "aihub173-driver-train",
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "elapsed_sec": elapsed,
        "log_path": str(log_path),
    }
    log(f"finish aihub173-driver-train: returncode={proc.returncode} elapsed={elapsed}s log={log_path}")
    promotion = promote_aihub173_if_better(exp_dir) if result.get("ok") else {}
    active_after = read_json(facial_root() / "aihub173_driver_state_summary.json")
    active_metrics = active_after.get("best_metrics") or active_after
    active_macro = float(active_metrics.get("macro_f1") or active_metrics.get("f1_macro") or active_metrics.get("f1") or 0.0)
    write_continuous_status("aihub173", {
        "stage": "completed" if result.get("ok") else "failed",
        "status": "completed" if result.get("ok") else "failed",
        "target_macro_f1": FINAL_TARGET_F1,
        "stretch_macro_f1": FINAL_TARGET_F1,
        "active_macro_f1": round(active_macro, 4),
        "candidate_macro_f1": promotion.get("candidate_macro_f1", 0),
        "promoted": bool(promotion.get("promoted")),
        "message": "AI-Hub 173 후보를 평가했고 더 좋은 경우 운영 모델에 반영했습니다." if result.get("ok") else "AI-Hub 173 재학습 실패",
        "promotion": promotion,
    })
    result["promotion"] = promotion
    return result


def recent_command_running(needle: str) -> list[dict[str, Any]]:
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,etime,pcpu,pmem,cmd"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    rows = []
    for line in out.splitlines()[1:]:
        if needle not in line or "rg " in line or "grep" in line:
            continue
        parts = line.split(None, 4)
        if len(parts) == 5:
            rows.append({"pid": parts[0], "elapsed": parts[1], "cpu": parts[2], "mem": parts[3], "cmd": parts[4]})
    return rows


def main() -> int:
    ensure_dirs()
    if not prevent_duplicate():
        return 0
    log("all-model supervisor started")
    cycle = int(read_json(STATUS_JSON).get("cycle", 0) or 0)
    while True:
        cycle += 1
        reconcile_actions = reconcile_dashboard_jobs()
        state = current_state()
        low = state.get("below_target") or []
        write_status("checking", cycle=cycle, state=state, actions=reconcile_actions)
        log(f"cycle={cycle} below_target={low}")

        families_low = {row.get("family") for row in low}
        actions = list(reconcile_actions)
        if "facial-aihub82" in families_low:
            actions.append({"aihub82": ensure_aihub82_supervisor()})
        if "driver-aihub173" in families_low:
            actions.append({"aihub173": run_aihub173_training(cycle)})
        if "xg-posture-occlusion-aux" in families_low:
            source_status = occlusion_source_status()
            if source_status.get("ready"):
                actions.append({"occlusion_aux": run_occlusion_training(cycle)})
            else:
                actions.append({"occlusion_aux": {"ok": False, "status": "waiting_for_source", **source_status}})
        if families_low.intersection({"rf-dual", "rf-fall-v2", "rf-pipeline"}):
            actions.append({"dashboard_rf_training": start_dashboard_training("rf-fall-v2", "rf")})
        if "xg-posture" in families_low:
            posture_sources = posture_source_status()
            if posture_sources.get("ready"):
                actions.append({"dashboard_posture_training": start_dashboard_training("xg-posture", "posture")})
            else:
                write_continuous_status("xg-posture", {
                    "stage": "blocked",
                    "status": "blocked",
                    "target_macro_f1": FINAL_TARGET_F1,
                    "stretch_macro_f1": FINAL_TARGET_F1,
                    "message": posture_sources.get("message"),
                    "bottleneck": posture_sources,
                })
                actions.append({"xg_posture": {"ok": False, "status": "waiting_for_source", **posture_sources}})

        refreshed = current_state()
        bottlenecks = []
        for action in actions:
            for name, payload in action.items():
                if isinstance(payload, dict) and payload.get("ok") is False:
                    bottlenecks.append({
                        "name": name,
                        "status": payload.get("status") or "blocked",
                        "message": payload.get("message") or payload.get("reason") or "",
                        "details": payload,
                    })
        append_audit_snapshot(cycle, refreshed, actions)
        write_status(
            "cycle-complete",
            cycle=cycle,
            state=refreshed,
            actions=actions,
            bottlenecks=bottlenecks,
            current_command="",
            current_command_pid="",
            current_command_log="",
            current_command_elapsed_sec=0,
        )
        time.sleep(IDLE_SLEEP_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
