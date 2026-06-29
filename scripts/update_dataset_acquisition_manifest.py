#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path("/mnt/data/wiz/project/main")
DATASETS = Path("/mnt/data/wiz/datasets")
OUT = DATASETS / "dataset_acquisition_manifest.json"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def du(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        return subprocess.check_output(["du", "-sh", str(path)], text=True).split()[0]
    except Exception:
        return "unknown"


def count_files(path: Path, suffixes: tuple[str, ...]) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and item.name.lower().endswith(suffixes):
            total += 1
    return total


def status(name: str) -> dict:
    return read_json(PROJECT / "outputs" / "continuous_training" / f"{name}_status.json")


def main() -> int:
    tmp_71461 = Path("/opt/app/tmp/datasets/action_behavior/aihub_71461")
    persistent_71461 = DATASETS / "action_behavior" / "aihub_71461"
    active_71461 = tmp_71461 if tmp_71461.exists() else persistent_71461
    entries = [
        {
            "key": "aihub82",
            "label": "AI-Hub 82 Korean emotion",
            "purpose": "facial auxiliary model retraining",
            "root": str(DATASETS / "facial_state" / "aihub_82_korean_emotion"),
            "status": status("aihub82"),
        },
        {
            "key": "aihub71641",
            "label": "AI-Hub 71641 fall/non-fall source",
            "purpose": "RF-Fall binary fall retraining",
            "root": str(DATASETS / "fall_classification" / "aihubs_71641"),
            "status": status("rf-fall-v2"),
        },
        {
            "key": "aihub71461",
            "label": "AI-Hub 71461 action/posture support",
            "purpose": "XG-Posture and occlusion auxiliary source",
            "root": str(active_71461),
            "persistent_root": str(persistent_71461),
            "storage_note": "현재 전체 확보본은 /opt/app/tmp에 있으며 /mnt/data 여유 공간 부족 시 영구 저장소에는 부분본만 남을 수 있습니다.",
            "status": status("xg-posture"),
        },
        {
            "key": "aihub173",
            "label": "AI-Hub 173 driver state",
            "purpose": "driver/facial state auxiliary model retraining",
            "root": str(DATASETS / "facial_state" / "aihub_173_driver_state"),
            "status": status("aihub173"),
        },
        {
            "key": "aihub61",
            "label": "AI-Hub 61 person action",
            "purpose": "posture/occlusion auxiliary source; current local files need compatible label conversion",
            "root": str(DATASETS / "action_behavior" / "aihub_61_person_action_2020"),
            "status": read_json(DATASETS / "action_behavior" / "aihub_61_person_action_2020" / "source_repair_status.json"),
        },
    ]
    for item in entries:
        root = Path(item["root"])
        item["size"] = du(root)
        item["counts"] = {
            "zip": count_files(root, (".zip",)),
            "tar": count_files(root, (".tar", ".tar.gz", ".tgz")),
            "json": count_files(root, (".json",)),
            "part": count_files(root, (".part0", ".part1073741824", ".part2147483648", ".part3221225472", ".part4294967296", ".part5368709120", ".part6442450944", ".part7516192768", ".part8589934592", ".part9663676416")),
        }
        st = item.get("status") or {}
        item["stage"] = st.get("stage") or st.get("status") or ""
        item["eta_text"] = st.get("eta_text") or ""
        item["latest_log"] = st.get("latest_log") or st.get("message") or ""
        item["required_files"] = st.get("required_files")
        item["completed_files"] = st.get("completed_files")
    manifest = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "persistent_dataset_root": str(DATASETS),
        "entries": entries,
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
