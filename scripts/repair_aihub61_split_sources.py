#!/usr/bin/env python3
"""Assemble AI-Hub 61 split zip parts so posture/occlusion training can read them."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path("/opt/app/datasets/action_behavior/aihub_61_person_action_2020")
STATUS = ROOT / "source_repair_status.json"
LOG = ROOT / "source_repair.log"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(**updates):
    data = {}
    try:
        data = json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.update(updates)
    data["updated_at"] = now()
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log(message: str) -> None:
    line = f"[{now()}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def part_offset(path: Path) -> int:
    match = re.search(r"\.part(\d+)$", path.name)
    return int(match.group(1)) if match else 0


def extract_download_tars() -> None:
    for tar_path in ROOT.rglob("download.tar"):
        part_siblings = list(tar_path.parent.rglob("*.zip.part*"))
        if part_siblings:
            continue
        log(f"extract tar {tar_path}")
        write_status(stage="extracting_tar", current=str(tar_path))
        subprocess.run(["tar", "-xf", str(tar_path), "-C", str(tar_path.parent)], check=False)


def assemble_parts() -> None:
    groups: dict[str, list[Path]] = defaultdict(list)
    for part in ROOT.rglob("*.zip.part*"):
        base = re.sub(r"\.part\d+$", "", str(part))
        groups[base].append(part)
    write_status(stage="assembling", group_count=len(groups))
    for base, parts in sorted(groups.items()):
        output = Path(base)
        ordered = sorted(parts, key=part_offset)
        expected_size = sum(path.stat().st_size for path in ordered)
        if output.exists() and output.stat().st_size == expected_size:
            log(f"skip assembled {output}")
            continue
        tmp = output.with_suffix(output.suffix + ".assembling")
        log(f"assemble {output} parts={len(ordered)} size={expected_size}")
        write_status(stage="assembling_zip", current=str(output), parts=len(ordered), expected_size=expected_size)
        with tmp.open("wb") as out:
            for path in ordered:
                with path.open("rb") as inp:
                    shutil.copyfileobj(inp, out, length=16 * 1024 * 1024)
        os.replace(tmp, output)
        log(f"assembled {output}")


def main() -> int:
    if not ROOT.exists():
        write_status(stage="missing_root", ok=False, root=str(ROOT))
        return 2
    write_status(stage="started", ok=True, root=str(ROOT))
    extract_download_tars()
    assemble_parts()
    zip_count = sum(1 for _ in ROOT.rglob("*.zip"))
    write_status(stage="complete", ok=True, zip_count=zip_count)
    log(f"complete zip_count={zip_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
