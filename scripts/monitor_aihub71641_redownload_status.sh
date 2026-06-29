#!/usr/bin/env bash
set -u

PROJECT="${PROJECT:-/opt/app/project/main}"
RUN_DIR="$PROJECT/outputs/continuous_training"
STATUS_JSON="$RUN_DIR/rf-fall-v2_status.json"
MAIN_LOG="$RUN_DIR/aihub71641_redownload_queue.log"
PY="${FALLAI_PYTHON:-python3}"
INTERVAL="${AIHUB71641_MONITOR_INTERVAL_SEC:-20}"

mkdir -p "$RUN_DIR"

while true; do
  if ! pgrep -f 'redownload_aihub71641_sources.sh' >/dev/null 2>&1; then
    exit 0
  fi

  last_line="$(grep 'START filekey=' "$MAIN_LOG" 2>/dev/null | tail -1 || true)"
  if [ -n "$last_line" ]; then
    "$PY" - "$STATUS_JSON" "$last_line" <<'PY'
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

status_path = Path(sys.argv[1])
line = sys.argv[2]
try:
    data = json.loads(status_path.read_text(encoding="utf-8"))
except Exception:
    data = {"ok": True, "name": "rf-fall-v2", "label": "RF-Fall 운영 모델"}

match = re.search(r"filekey=([0-9]+).*?label=(.*?) tmp=(.*?) final=(.*)$", line)
if match:
    filekey, label, tmp_dir, _final_dir = match.group(1), match.group(2), match.group(3), match.group(4)
    start_match = re.search(r"\[([0-9TZ:\-]+)\]", line)
    elapsed_text = ""
    if start_match:
        try:
            start = datetime.strptime(start_match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            elapsed = max(0, int((datetime.now(timezone.utc) - start).total_seconds()))
            if elapsed >= 3600:
                elapsed_text = f"경과 {elapsed // 3600}시간 {(elapsed % 3600) // 60}분"
            elif elapsed >= 60:
                elapsed_text = f"경과 {elapsed // 60}분"
            else:
                elapsed_text = f"경과 {elapsed}초"
        except Exception:
            elapsed_text = ""
    tar_path = Path(tmp_dir) / "download.tar"
    size_bytes = tar_path.stat().st_size if tar_path.exists() else 0
    if size_bytes >= 1024 ** 3:
        size_text = f"{size_bytes / (1024 ** 3):.1f}GB"
    elif size_bytes >= 1024 ** 2:
        size_text = f"{size_bytes / (1024 ** 2):.0f}MB"
    elif size_bytes > 0:
        size_text = f"{size_bytes / 1024:.0f}KB"
    else:
        size_text = "0B"
    current = int(data.get("redownload_current") or 0)
    total = int(data.get("redownload_total") or 0)
    log_path = Path("/mnt/data/wiz/datasets/logs/aihub_recovery") / f"71641_{filekey}.log"
    log_tail = ""
    phase = "다운로드 중"
    try:
        if log_path.exists():
            log_tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
    except Exception:
        log_tail = ""
    if f"TAR_OK dataset=71641 filekey={filekey}" in log_tail:
        phase = "압축 해제 중"
    if f"DONE_RESUME dataset=71641 filekey={filekey}" in log_tail:
        phase = "파일 완료"
    if f"TAR_INCOMPLETE dataset=71641 filekey={filekey}" in log_tail:
        phase = "이어받기 재시도 중"
    eta_bits = [phase]
    if elapsed_text:
        eta_bits.append(elapsed_text)
    if size_text != "0B":
        eta_bits.append(size_text)
    if total > 0:
        eta_bits.append(f"{current}/{total}")
    data.update({
        "ok": True,
        "name": "rf-fall-v2",
        "label": "RF-Fall 운영 모델",
        "stage": "running",
        "status": "running",
        "eta_text": " · ".join(eta_bits),
        "message": "AI-Hub 71641 원천 영상 재수신 중입니다.",
        "latest_log": f"filekey={filekey} · {label} · {phase} · {size_text} · {current}/{total}",
        "redownload_current_filekey": filekey,
        "redownload_current_label": label,
        "redownload_current_phase": phase,
        "redownload_current_size_bytes": size_bytes,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    status_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
    "$PY" "$PROJECT/scripts/update_aihub_redownload_status.py" "$STATUS_JSON" "$MAIN_LOG" "71641" "$last_line" || true
  fi
  sleep "$INTERVAL"
done
