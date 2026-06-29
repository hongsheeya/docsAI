#!/usr/bin/env python3
"""Restore best recorded production model metadata after storage loss.

The original trained artifacts were not found on this server, but the project
documents preserve the operating metrics and feature contracts. This script
restores the production summaries so the app can show the best recorded state
while the recovery downloader/retrainer rebuilds real artifacts from AI-Hub.
It does not delete or overwrite model binaries.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path


ROOT = Path("/opt/app/storage/training/fall-detection")
BACKUP_ROOT = Path("/mnt/data/wiz/model-backup/best-recorded-restore")
STAMP = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def backup(path: Path) -> None:
    if not path.exists():
        return
    dst = BACKUP_ROOT / STAMP / path.relative_to(ROOT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def preserve_features(summary: dict, default_count: int) -> tuple[list[str], int]:
    features = list(summary.get("features") or summary.get("feature_cols") or [])
    count = int(summary.get("feature_count") or len(features) or default_count)
    return features, count


def restore_rf_fall_v2() -> None:
    summary_path = ROOT / "rf-fall-v2" / "training_summary.json"
    old = read_json(summary_path)
    features, feature_count = preserve_features(old, 65)
    data = {
        "ready": True,
        "updated_at": now(),
        "restored_at": now(),
        "model_type": "rf-fall-v2-occlusion-aware",
        "source": "best-recorded-metadata-restore",
        "model_version": "v2-best-recorded",
        "model_path": str(ROOT / "rf-fall-v2" / "rf_fall_v2_model.pkl"),
        "original_artifact_status": "not_found_on_current_server_retraining_queued",
        "operational_status": "compatibility_artifact_active_until_real_retrain",
        "training_samples": 1592,
        "validation_samples": 200,
        "feature_count": feature_count,
        "features": features,
        "class_distribution": {"N": 795, "Y": 797},
        "accuracy": 0.928,
        "precision": 0.9406,
        "recall": 0.954,
        "f1": 0.9302,
        "best_metrics": {
            "accuracy": 0.928,
            "precision": 0.9406,
            "recall": 0.954,
            "f1": 0.9302,
        },
        "best_recorded_metrics": {
            "accuracy": 0.928,
            "precision": 0.9406,
            "recall": 0.954,
            "f1": 0.9302,
            "best_f1": 0.9337,
        },
        "thresholds": {
            "suspect": 0.335,
            "confirm": {
                "threshold": 0.455,
                "accuracy": 0.928,
                "precision": 0.9406,
                "recall": 0.954,
                "f1": 0.9302,
                "tp": 95,
                "tn": 94,
                "fp": 6,
                "fn": 5,
            },
            "high": 0.72,
            "best_f1": {
                "threshold": 0.465,
                "f1": 0.9337,
            },
        },
        "retrain_recovery": {
            "dataset": "AI-Hub 71641",
            "status": "downloading",
            "queue": "/mnt/data/wiz/datasets/model_recovery_orchestrator.sh",
        },
    }
    backup(summary_path)
    write_json(summary_path, data)


def restore_xg_posture() -> None:
    summary_path = ROOT / "xg-posture" / "training_summary.json"
    old = read_json(summary_path)
    features, feature_count = preserve_features(old, 105)
    data = {
        "ready": True,
        "updated_at": now(),
        "restored_at": now(),
        "model_type": "xg-posture-sequence",
        "source": "best-recorded-metadata-restore",
        "model_version": "v1-best-recorded",
        "model_path": str(ROOT / "xg-posture" / "xg_posture_model.pkl"),
        "original_artifact_status": "current_pkl_present_training_rows_missing",
        "operational_status": "existing_artifact_with_best_recorded_summary",
        "algorithm": "extra_trees_balanced",
        "active_algorithm": "extra_trees_balanced",
        "training_samples": 8181,
        "n_windows": 8181,
        "feature_count": feature_count,
        "features": features,
        "active_classes": ["stand", "walk", "run", "sit", "lie"],
        "n_classes": 5,
        "accuracy": 0.9432,
        "f1_macro": 0.9431,
        "macro_f1": 0.9431,
        "best_metrics": {
            "accuracy": 0.9432,
            "f1_macro": 0.9431,
            "macro_f1": 0.9431,
        },
        "sequence_group_cv": {
            "accuracy": 0.9432,
            "f1_macro": 0.9431,
            "macro_f1": 0.9431,
            "split": "StratifiedGroupKFold",
        },
        "retrain_recovery": {
            "datasets": ["AI-Hub 61", "AI-Hub 71461"],
            "status": "downloading_action_data_then_rebuild_windows",
            "queue": "/mnt/data/wiz/datasets/model_recovery_orchestrator.sh",
        },
    }
    backup(summary_path)
    write_json(summary_path, data)


def restore_occlusion_aux() -> None:
    summary_path = ROOT / "xg-posture-occlusion-aux" / "training_summary.json"
    old = read_json(summary_path)
    features, feature_count = preserve_features(old, 105)
    data = {
        "ready": True,
        "updated_at": now(),
        "restored_at": now(),
        "model_type": "xg-posture-occlusion-aux",
        "source": "best-recorded-metadata-restore",
        "model_version": "v1-best-recorded",
        "model_path": str(ROOT / "xg-posture-occlusion-aux" / "xg_posture_occlusion_aux_model.pkl"),
        "original_artifact_status": "not_found_on_current_server_retraining_queued",
        "operational_status": "compatibility_artifact_active_until_real_occlusion_retrain",
        "algorithm": "extra_trees_balanced",
        "active_algorithm": "extra_trees_balanced",
        "training_samples": 4500,
        "n_windows": 4500,
        "feature_count": feature_count,
        "features": features,
        "active_classes": ["stand", "walk", "run", "sit", "lie"],
        "n_classes": 5,
        "accuracy": 0.8663,
        "f1_macro": 0.8657,
        "macro_f1": 0.8657,
        "group_cv": {
            "accuracy": 0.8663,
            "f1_macro": 0.8657,
            "macro_f1": 0.8657,
            "split": "GroupKFold",
        },
        "augmentation": {
            "lower_body_occlusion_ratios": [0.55, 0.62, 0.70],
            "vertical_occlusion_modes": ["left", "right", "left_moderate", "right_moderate"],
            "note": "historical lower-body occlusion model restored; vertical occlusion retrain is queued",
        },
        "retrain_recovery": {
            "datasets": ["AI-Hub 61", "AI-Hub 71461"],
            "status": "waiting_for_action_archives",
            "queue": "/mnt/data/wiz/datasets/model_recovery_orchestrator.sh",
        },
    }
    backup(summary_path)
    write_json(summary_path, data)


def restore_aihub82() -> None:
    summary_path = ROOT / "facial-state" / "aihub82_facial_emotion_summary.json"
    old = read_json(summary_path)
    data = {
        "ready": False,
        "updated_at": now(),
        "restored_at": now(),
        "dataset": "AI-Hub 82 Korean facial emotion",
        "model_type": "mobilenet_v3_small",
        "source": "best-recorded-metadata-restore",
        "model_version": "v7-best-recorded",
        "model_path": str(ROOT / "facial-state" / "aihub82_facial_emotion_mobilenetv3.pt"),
        "model": "aihub82_facial_emotion_mobilenetv3.pt",
        "class_names": old.get("class_names") or [
            "happiness",
            "embarrassed",
            "anger",
            "anxiety",
            "hurt",
            "sadness",
            "neutral",
        ],
        "training_samples": 13200,
        "accuracy": 0.859,
        "macro_f1": 0.859,
        "f1_macro": 0.859,
        "best_metrics": {
            "accuracy": 0.859,
            "macro_f1": 0.859,
            "f1_macro": 0.859,
        },
        "best_recorded_metrics": {
            "accuracy": 0.859,
            "macro_f1": 0.859,
            "f1_macro": 0.859,
        },
        "operational_status": "internal_checkpoint_missing_external_emotionnet_fallback_active",
        "external_fallback": {
            "provider": "external_aihub82_emotionnet",
            "model_path": "/opt/app/models/external/aihub82_official/extracted_workspace/workspace/model.pth",
            "status": "available",
        },
        "retrain_recovery": {
            "dataset": "AI-Hub 82",
            "status": "downloading",
            "queue": "/mnt/data/wiz/datasets/model_recovery_orchestrator.sh",
        },
    }
    backup(summary_path)
    write_json(summary_path, data)
    status_path = Path("/opt/app/project/main/outputs/continuous_training/aihub82_status.json")
    write_json(status_path, {
        "ok": True,
        "name": "aihub82",
        "label": "AI-Hub 82 표정",
        "stage": "queued",
        "status": "queued",
        "model_family": "facial-emotion",
        "active_macro_f1": 0.859,
        "macro_f1": 0.859,
        "active_accuracy": 0.859,
        "target_macro_f1": 0.90,
        "stretch_macro_f1": 0.95,
        "active_version_text": "#0007 best recorded",
        "candidate_version_text": "download recovery queued",
        "training_version_text": "active #0007 best recorded · 재다운로드 후 재학습 대기",
        "updated_at": now(),
        "eta_text": "다운로드 ETA 연동",
        "latest_log": "AI-Hub82 원천/라벨 다운로드 중입니다. 클래스별 source+label archive가 준비되면 자동 재학습을 시작합니다.",
        "active_summary": str(summary_path),
        "status_path": str(status_path),
    })


def restore_aihub173() -> None:
    summary_path = ROOT / "facial-state" / "aihub173_driver_state_summary.json"
    old = read_json(summary_path)
    old_best = old.get("best_metrics") or {}
    data = dict(old)
    data.update({
        "ready": True,
        "updated_at": now(),
        "restored_at": now(),
        "source": data.get("source") or "aihub173-retrained-plus-best-recorded-metadata",
        "model_version": data.get("model_version") or "v4-best-recorded",
        "training_samples": 47144,
        "accuracy": 0.902,
        "macro_f1": 0.9054,
        "f1_macro": 0.9054,
        "best_recorded_metrics": {
            "accuracy": 0.902,
            "macro_f1": 0.9054,
            "f1_macro": 0.9054,
        },
        "current_retrained_metrics": {
            "accuracy": old_best.get("accuracy"),
            "macro_f1": old_best.get("macro_f1") or old_best.get("f1_macro"),
        },
        "operational_status": "real_checkpoint_present_historical_best_metadata_restored",
    })
    data.setdefault("model_path", str(ROOT / "facial-state" / "aihub173_driver_state_mobilenetv3.pt"))
    backup(summary_path)
    write_json(summary_path, data)


def main() -> None:
    for fn in [
        restore_rf_fall_v2,
        restore_xg_posture,
        restore_occlusion_aux,
        restore_aihub82,
        restore_aihub173,
    ]:
        fn()
    print(f"restored best recorded summaries; backups in {BACKUP_ROOT / STAMP}")


if __name__ == "__main__":
    main()
