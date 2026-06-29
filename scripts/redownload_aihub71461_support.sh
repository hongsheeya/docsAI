#!/usr/bin/env bash
set -u

PROJECT="${PROJECT:-/opt/app/project/main}"
DATASET_ROOT="${AIHUB_DATASET_ROOT:-/opt/app/datasets}"
ROOT="$DATASET_ROOT/action_behavior/aihub_71461"
RUN_DIR="$PROJECT/outputs/continuous_training"
STATUS_JSON="$RUN_DIR/xg-posture_status.json"
MAIN_LOG="$RUN_DIR/aihub71461_redownload_queue.log"
RESUMABLE="${AIHUB_RESUMABLE_DOWNLOADER:-/mnt/data/wiz/datasets/aihub_resumable_download_one.sh}"
MONITOR="$PROJECT/scripts/monitor_aihub71461_redownload_status.sh"
PY="${FALLAI_PYTHON:-python3}"

mkdir -p "$RUN_DIR"

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

write_status() {
  local stage="$1"
  local eta_text="$2"
  local message="$3"
  local latest_log="$4"
  local current="${5:-0}"
  local total="${6:-0}"
  "$PY" - "$STATUS_JSON" "$stage" "$eta_text" "$message" "$latest_log" "$current" "$total" "$$" "$MAIN_LOG" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
stage, eta_text, message, latest_log = sys.argv[2:6]
current, total = int(sys.argv[6]), int(sys.argv[7])
pid, log_path = sys.argv[8], sys.argv[9]
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {"ok": True, "name": "xg-posture", "label": "XG-Posture 재학습"}
data.update({
    "ok": True,
    "name": "xg-posture",
    "label": "XG-Posture 재학습",
    "stage": stage,
    "status": stage,
    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "eta_text": eta_text,
    "message": message,
    "latest_log": latest_log,
    "redownload_pid": int(pid),
    "redownload_current": current,
    "redownload_total": total,
    "redownload_log_path": log_path,
    "target_macro_f1": max(float(data.get("target_macro_f1") or 0.95), 0.95),
    "stretch_macro_f1": max(float(data.get("stretch_macro_f1") or 0.95), 0.95),
})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

if [ -z "${AIHUB_API_KEY:-}" ]; then
  write_status "blocked" "AIHUB_API_KEY 필요" \
    "AI-Hub 71461 자세 지원 데이터 재수신을 시작하려 했지만 API key 환경변수가 없습니다." \
    "71461 재수신 차단: API key 없음" 0 0
  exit 2
fi

if [ ! -x "$RESUMABLE" ]; then
  write_status "blocked" "다운로더 없음" \
    "AI-Hub 71461 재수신 스크립트를 찾지 못했습니다." \
    "71461 재수신 차단: $RESUMABLE 실행 불가" 0 0
  exit 3
fi

entries=(
  "485405|$ROOT/file_485405|71461 action support 485405"
  "485407|$ROOT/file_485407|71461 action support 485407"
  "485408|$ROOT/file_485408|71461 action support 485408"
  "485409|$ROOT/file_485409|71461 action support 485409"
  "485410|$ROOT/file_485410|71461 action support 485410"
  "485411|$ROOT/file_485411|71461 action support 485411"
)

total="${#entries[@]}"
failed=0
echo "[$(now_utc)] START AI-Hub71461 support redownload queue total=$total" >> "$MAIN_LOG"
write_status "running" "71461 재수신 시작" \
  "AI-Hub 71461 자세/행동 지원 데이터 재수신을 시작했습니다." \
  "71461 재수신 큐 시작 · 0/$total" 0 "$total"
if [ -x "$MONITOR" ] && ! pgrep -f 'monitor_aihub71461_redownload_status.sh' >/dev/null 2>&1; then
  AIHUB71461_MONITOR_INTERVAL_SEC="${AIHUB71461_MONITOR_INTERVAL_SEC:-20}" \
  FALLAI_PYTHON="$PY" \
    setsid -f "$MONITOR" >/dev/null 2>&1 || true
fi

idx=0
for entry in "${entries[@]}"; do
  idx=$((idx + 1))
  IFS='|' read -r filekey target_dir label <<< "$entry"
  latest="filekey=$filekey · $label · $idx/$total"
  write_status "running" "재수신 $idx/$total" \
    "AI-Hub 71461 자세/행동 지원 데이터 재수신 중입니다." \
    "$latest" "$idx" "$total"
  echo "[$(now_utc)] START filekey=$filekey label=$label dir=$target_dir" >> "$MAIN_LOG"
  "$RESUMABLE" 71461 "$filekey" "$target_dir" "$label" >> "$MAIN_LOG" 2>&1
  rc=$?
  echo "[$(now_utc)] END filekey=$filekey rc=$rc" >> "$MAIN_LOG"
  if [ "$rc" -ne 0 ]; then
    failed=$((failed + 1))
    write_status "running" "재시도 필요" \
      "AI-Hub 71461 일부 파일 재수신에 실패했습니다. 나머지 파일을 계속 확인합니다." \
      "filekey=$filekey 실패 rc=$rc · 계속 진행" "$idx" "$total"
  fi
done

if [ "$failed" -gt 0 ]; then
  write_status "blocked" "일부 파일 실패" \
    "AI-Hub 71461 재수신 큐가 끝났지만 실패 파일이 있습니다." \
    "71461 재수신 실패 $failed/$total · 로그 확인 필요" "$total" "$total"
  echo "[$(now_utc)] FINISH with failures failed=$failed total=$total" >> "$MAIN_LOG"
  exit 1
fi

write_status "queued" "자세 재학습 대기" \
  "AI-Hub 71461 재수신이 완료되었습니다. 다음 XG-Posture 재학습 사이클에서 사용합니다." \
  "71461 재수신 완료 · XG-Posture 재학습 대기" "$total" "$total"
echo "[$(now_utc)] FINISH ok total=$total" >> "$MAIN_LOG"
