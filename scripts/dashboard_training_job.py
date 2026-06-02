#!/usr/bin/env python3
"""Background training runner for dashboard bulk-upload training mode."""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable


PROJECT = Path("/opt/app/project/main")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        try:
            return _sanitize(value.item())
        except Exception:
            return str(value)
    return value


def write_status(job_file: Path, **updates: Any) -> dict[str, Any]:
    try:
        data = json.loads(job_file.read_text(encoding="utf-8")) if job_file.exists() else {}
    except Exception:
        data = {}
    data.update(updates)
    data["updated_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    job_file.parent.mkdir(parents=True, exist_ok=True)
    job_file.write_text(json.dumps(_sanitize(data), ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_video_analysis():
    module_path = PROJECT / "src" / "model" / "struct" / "video_analysis.py"
    spec = importlib.util.spec_from_file_location("dashboard_training_video_analysis", module_path)
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


def _run_step(name: str, fn: Callable[[], dict[str, Any] | None]) -> dict[str, Any]:
    started = time.time()
    try:
        result = fn() or {}
        return {
            "name": name,
            "ok": True,
            "elapsed_sec": round(time.time() - started, 2),
            "result": result,
        }
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "elapsed_sec": round(time.time() - started, 2),
            "error": str(exc),
        }


def _run_step_with_heartbeat(
    name: str,
    fn: Callable[[], dict[str, Any] | None],
    job_file: Path,
    started: float,
    total_samples: int,
    idx: int,
    total_steps: int,
    finished_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    box: dict[str, Any] = {}

    def target() -> None:
        box["step"] = _run_step(name, fn)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    step_started = time.time()
    base_progress = max(0.02, (idx - 1) / max(total_steps, 1))
    step_span = 1.0 / max(total_steps, 1)
    last_write = 0.0
    while thread.is_alive():
        now = time.time()
        if now - last_write >= 15:
            step_elapsed = max(0.1, now - step_started)
            soft_ratio = min(0.92, step_elapsed / 300.0)
            progress = min(0.99, base_progress + step_span * soft_ratio)
            elapsed_total = max(0.1, now - started)
            eta = round(elapsed_total * (1.0 - progress) / max(progress, 0.01), 1)
            write_status(
                job_file,
                status="running",
                stage=name,
                progress=round(progress, 4),
                processed=int(total_samples * min(progress, 0.99)) if total_samples else 0,
                total=total_samples,
                eta_sec=eta,
                elapsed_sec=round(elapsed_total, 1),
                message=f"{name} 학습 진행 중 ({idx}/{total_steps}) · 단계 경과 {round(step_elapsed, 1)}초",
                steps=finished_steps,
            )
            last_write = now
        thread.join(timeout=1.0)
    return box.get("step") or {
        "name": name,
        "ok": False,
        "elapsed_sec": round(time.time() - step_started, 2),
        "error": "학습 단계 결과를 수집하지 못했습니다.",
    }


def _skip_result(name: str, reason: str) -> Callable[[], dict[str, Any]]:
    def run() -> dict[str, Any]:
        return {"summary": {"ready": False, "skipped": True, "stage": name, "reason": reason}, "errors": []}
    return run


def _run_sequence_posture_training() -> dict[str, Any]:
    script = PROJECT / "scripts" / "retrain_xg_posture_sequence.py"
    if not script.exists():
        raise RuntimeError(f"missing posture sequence trainer: {script}")
    subprocess.run([sys.executable, str(script)], cwd=str(PROJECT), check=True)
    report_path = PROJECT / "outputs" / "model_optimization" / "xg_posture_sequence_training_report.json"
    summary_path = Path("/opt/app/storage/training/fall-detection/xg-posture/training_summary.json")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    return {"summary": summary, "report": report, "errors": []}


def _sync_behavior_summary_from_persistent() -> dict[str, Any]:
    persistent_summary = Path("/opt/app/storage/training/action-behavior/model/training_summary.json")
    persistent_model = Path("/opt/app/storage/training/action-behavior/model/behavior_model.json")
    project_dir = PROJECT / "storage" / "training" / "action-behavior" / "model"
    project_dir.mkdir(parents=True, exist_ok=True)
    summary = json.loads(persistent_summary.read_text(encoding="utf-8")) if persistent_summary.exists() else {}
    model = json.loads(persistent_model.read_text(encoding="utf-8")) if persistent_model.exists() else {}
    if summary:
        (project_dir / "training_summary.json").write_text(json.dumps(_sanitize(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    if model:
        (project_dir / "behavior_model.json").write_text(json.dumps(_sanitize(model), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "model": model, "errors": []}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--job-file", required=True)
    parser.add_argument("--job-type", default="full", choices=["full", "rf", "posture"])
    args = parser.parse_args()

    job_file = Path(args.job_file)
    started = time.time()
    analyzer = load_video_analysis()
    intake = analyzer._intake_summary()
    total_samples = int(
        (intake.get("fall_sample_count", 0) or 0)
        + (intake.get("posture_sample_count", 0) or 0)
        + (intake.get("Y", 0) or 0)
        + (intake.get("N", 0) or 0)
        + (intake.get("posture_intake_total", 0) or 0)
    )

    write_status(
        job_file,
        ok=True,
        status="running",
        stage="initializing",
        progress=0.01,
        processed=0,
        total=total_samples,
        eta_sec=None,
        started_at=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        started_monotonic=started,
        intake_summary=intake,
        message="학습 환경 준비 중",
        steps=[],
    )

    baseline_summary = analyzer._baseline_summary() or {}
    behavior_summary = analyzer._behavior_summary() or {}
    rf_pipeline_summary = analyzer._rf_project_summary()
    rf_pose_summary: dict[str, Any] = {}

    steps: list[tuple[str, Callable[[], dict[str, Any] | None]]] = []
    enough_binary_intake = int(intake.get("Y", 0) or 0) >= 2 and int(intake.get("N", 0) or 0) >= 2
    if args.job_type == "full":
        baseline_module = analyzer._baseline_module()
        behavior_module = analyzer._behavior_module()
        if baseline_module is not None and enough_binary_intake:
            steps.append(("baseline", lambda: baseline_module.train_and_save(analyzer._project_root(), force_rebuild=False)))
        elif baseline_module is not None:
            steps.append(("baseline", _skip_result("baseline", "HITL Y/N intake가 클래스별 2건 미만이라 운영 요약 덮어쓰기를 건너뜁니다.")))
        if behavior_module is not None:
            steps.append(("behavior", _sync_behavior_summary_from_persistent))
        if enough_binary_intake:
            steps.append(("rf_pipeline", analyzer.retrain_rf_pipeline))
        else:
            steps.append(("rf_pipeline", _skip_result("rf_pipeline", "HITL Y/N intake가 클래스별 2건 미만이라 RF-HITL 덮어쓰기를 건너뜁니다.")))
        steps.append(("xg_posture_sequence", _run_sequence_posture_training))
    elif args.job_type == "rf":
        if enough_binary_intake:
            steps.append(("rf_pipeline", analyzer.retrain_rf_pipeline))
        else:
            steps.append(("rf_pipeline", _skip_result("rf_pipeline", "HITL Y/N intake가 클래스별 2건 미만이라 RF-HITL 덮어쓰기를 건너뜁니다.")))
    else:
        steps.append(("xg_posture_sequence", _run_sequence_posture_training))

    finished_steps: list[dict[str, Any]] = []
    errors: list[str] = []
    total_steps = max(len(steps), 1)

    for idx, (name, fn) in enumerate(steps, start=1):
        elapsed = max(0.1, time.time() - started)
        progress = max(0.02, (idx - 1) / total_steps)
        eta = round(elapsed * (1.0 - progress) / max(progress, 0.01), 1) if progress > 0.02 else None
        write_status(
            job_file,
            status="running",
            stage=name,
            progress=round(progress, 4),
            processed=int(total_samples * (idx - 1) / total_steps),
            total=total_samples,
            eta_sec=eta,
            message=f"{name} 학습 진행 중 ({idx}/{total_steps})",
            steps=finished_steps,
        )
        step = _run_step_with_heartbeat(name, fn, job_file, started, total_samples, idx, total_steps, finished_steps)
        finished_steps.append(step)
        if not step.get("ok"):
            errors.append(f"{name}: {step.get('error')}")
        result = step.get("result") or {}
        if name == "baseline":
            baseline_summary = result.get("summary", baseline_summary) if isinstance(result, dict) else baseline_summary
        elif name == "behavior":
            behavior_summary = result.get("summary", behavior_summary) if isinstance(result, dict) else behavior_summary
        elif name == "rf_pipeline":
            rf_pipeline_summary = result.get("summary", rf_pipeline_summary) if isinstance(result, dict) else rf_pipeline_summary
            errors.extend((result.get("errors") or []) if isinstance(result, dict) else [])
        elif name in ("xg_posture", "xg_posture_sequence"):
            errors.extend((result.get("errors") or []) if isinstance(result, dict) else [])

    model_comparison = analyzer._build_model_comparison_report(baseline_summary, rf_pipeline_summary, rf_pose_summary)
    elapsed_total = round(time.time() - started, 2)
    status = "failed" if errors and not any(step.get("ok") for step in finished_steps) else "completed_pending_apply"
    write_status(
        job_file,
        status=status,
        stage="finished",
        progress=1.0,
        processed=total_samples,
        total=total_samples,
        eta_sec=0,
        elapsed_sec=elapsed_total,
        finished_at=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        steps=finished_steps,
        errors=errors,
        result={
            "dataset": (baseline_summary or {}).get("dataset", {}),
            "train_metrics": (baseline_summary or {}).get("train_metrics", {}),
            "evaluation": (baseline_summary or {}).get("evaluation", {}),
            "action_behavior_training": behavior_summary,
            "rf_pipeline_training": rf_pipeline_summary,
            "xg_posture_training": (finished_steps[-1].get("result") or {}).get("summary", {}) if finished_steps else {},
            "model_comparison": model_comparison,
        },
        message="학습 완료. 적용 버튼을 눌러 캐시를 갱신하고 운영 화면에 반영하세요." if status != "failed" else "학습 실패",
        manual_apply_required=status != "failed",
    )
    return 0 if status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
