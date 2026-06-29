#!/usr/bin/env bash
set -u

PROJECT="${PROJECT:-/opt/app/project/main}"
DATASET_ROOT="${AIHUB_DATASET_ROOT:-/opt/app/datasets}"
FACIAL_ROOT="$DATASET_ROOT/facial_state/aihub_82_korean_emotion/01.데이터"
RUN_DIR="$PROJECT/outputs/continuous_training"
STATUS_JSON="$RUN_DIR/aihub82_status.json"
MAIN_LOG="$RUN_DIR/aihub82_redownload_queue.log"
RESUMABLE="${AIHUB_RESUMABLE_DOWNLOADER:-/mnt/data/wiz/datasets/aihub_resumable_download_one.sh}"
MONITOR="$PROJECT/scripts/monitor_aihub82_redownload_status.sh"
PY="${FALLAI_PYTHON:-python3}"

mkdir -p "$RUN_DIR" "$(dirname "$MAIN_LOG")"

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
    data = {"ok": True, "name": "aihub82", "label": "AI-Hub 82 표정"}
data.update({
    "ok": True,
    "name": "aihub82",
    "label": "AI-Hub 82 표정",
    "stage": stage,
    "status": stage,
    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "eta_text": eta_text,
    "message": message,
    "latest_log": latest_log,
    "download_process_count": 1,
    "redownload_pid": int(pid),
    "redownload_current": current,
    "redownload_total": total,
    "redownload_log_path": log_path,
    "blocked_reason": "" if stage == "running" else data.get("blocked_reason", ""),
})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

if [ -z "${AIHUB_API_KEY:-}" ]; then
  write_status "blocked" "AIHUB_API_KEY 필요" \
    "AI-Hub 82 재수신을 시작하려 했지만 AIHUB_API_KEY 환경변수가 없습니다." \
    "재수신 차단: API key 없음" 0 0
  exit 2
fi

if [ ! -x "$RESUMABLE" ]; then
  write_status "blocked" "다운로더 없음" \
    "AI-Hub 82 재수신 스크립트를 찾지 못했습니다." \
    "재수신 차단: $RESUMABLE 실행 불가" 0 0
  exit 3
fi

entries=(
  "49100|$FACIAL_ROOT/1.Training/라벨링데이터/기쁨|82 train label happiness"
  "49101|$FACIAL_ROOT/1.Training/라벨링데이터/당황|82 train label embarrassed"
  "49102|$FACIAL_ROOT/1.Training/라벨링데이터/분노|82 train label anger"
  "49103|$FACIAL_ROOT/1.Training/라벨링데이터/불안|82 train label anxiety"
  "49104|$FACIAL_ROOT/1.Training/라벨링데이터/상처|82 train label hurt"
  "49105|$FACIAL_ROOT/1.Training/라벨링데이터/슬픔|82 train label sadness"
  "49106|$FACIAL_ROOT/1.Training/라벨링데이터/중립|82 train label neutral"
  "397137|$FACIAL_ROOT/2.Validation/라벨링데이터_231004_add/기쁨|82 val label happiness"
  "49052|$FACIAL_ROOT/2.Validation/라벨링데이터/당황|82 val label embarrassed"
  "49053|$FACIAL_ROOT/2.Validation/라벨링데이터/분노|82 val label anger"
  "49054|$FACIAL_ROOT/2.Validation/라벨링데이터/불안|82 val label anxiety"
  "49055|$FACIAL_ROOT/2.Validation/라벨링데이터/상처|82 val label hurt"
  "49056|$FACIAL_ROOT/2.Validation/라벨링데이터/슬픔|82 val label sadness"
  "49057|$FACIAL_ROOT/2.Validation/라벨링데이터/중립|82 val label neutral"
  "49107|$FACIAL_ROOT/1.Training/원천데이터_0114_add/기쁨|82 train source happiness 01"
  "49111|$FACIAL_ROOT/1.Training/원천데이터/당황|82 train source embarrassed 01"
  "49031|$FACIAL_ROOT/1.Training/원천데이터/분노|82 train source anger 01"
  "49035|$FACIAL_ROOT/1.Training/원천데이터/불안|82 train source anxiety 01"
  "49039|$FACIAL_ROOT/1.Training/원천데이터/상처|82 train source hurt 01"
  "49043|$FACIAL_ROOT/1.Training/원천데이터/슬픔|82 train source sadness 01"
  "49047|$FACIAL_ROOT/1.Training/원천데이터/중립|82 train source neutral 01"
  "397138|$FACIAL_ROOT/2.Validation/원천데이터_0114_add/기쁨|82 val source happiness"
  "49059|$FACIAL_ROOT/2.Validation/원천데이터/당황|82 val source embarrassed"
  "49060|$FACIAL_ROOT/2.Validation/원천데이터/분노|82 val source anger"
  "49061|$FACIAL_ROOT/2.Validation/원천데이터/불안|82 val source anxiety"
  "49062|$FACIAL_ROOT/2.Validation/원천데이터/상처|82 val source hurt"
  "49063|$FACIAL_ROOT/2.Validation/원천데이터/슬픔|82 val source sadness"
  "49064|$FACIAL_ROOT/2.Validation/원천데이터/중립|82 val source neutral"
)

total="${#entries[@]}"
failed=0
echo "[$(now_utc)] START AI-Hub82 redownload queue total=$total" >> "$MAIN_LOG"
write_status "running" "재수신 진행 중" \
  "AI-Hub 82 원천/라벨 데이터 재수신을 시작했습니다." \
  "AI-Hub 82 재수신 큐 시작 · 0/$total" 0 "$total"
if [ -x "$MONITOR" ] && ! pgrep -f 'monitor_aihub82_redownload_status.sh' >/dev/null 2>&1; then
  AIHUB82_MONITOR_INTERVAL_SEC="${AIHUB82_MONITOR_INTERVAL_SEC:-60}" \
  FALLAI_PYTHON="$PY" \
    setsid -f "$MONITOR" >/dev/null 2>&1 || true
fi

idx=0
for entry in "${entries[@]}"; do
  idx=$((idx + 1))
  IFS='|' read -r filekey target_dir label <<< "$entry"
  latest="filekey=$filekey · $label · $idx/$total"
  write_status "running" "재수신 진행 중" \
    "AI-Hub 82 원천/라벨 데이터 재수신 중입니다." \
    "$latest" "$idx" "$total"
  echo "[$(now_utc)] START filekey=$filekey label=$label dir=$target_dir" >> "$MAIN_LOG"
  "$RESUMABLE" 82 "$filekey" "$target_dir" "$label" >> "$MAIN_LOG" 2>&1
  rc=$?
  echo "[$(now_utc)] END filekey=$filekey rc=$rc" >> "$MAIN_LOG"
  if [ "$rc" -ne 0 ]; then
    failed=$((failed + 1))
    write_status "running" "재수신 재시도 필요" \
      "AI-Hub 82 일부 파일 재수신에 실패했습니다. 나머지 파일을 계속 확인합니다." \
      "filekey=$filekey 실패 rc=$rc · 계속 진행" "$idx" "$total"
  fi
done

if [ "$failed" -gt 0 ]; then
  write_status "blocked" "일부 파일 재수신 실패" \
    "AI-Hub 82 재수신 큐가 끝났지만 실패 파일이 있어 학습을 시작하지 않았습니다." \
    "AI-Hub 82 재수신 실패 $failed/$total · 로그 확인 필요" "$total" "$total"
  echo "[$(now_utc)] FINISH with failures failed=$failed total=$total" >> "$MAIN_LOG"
  exit 1
fi

write_status "running" "학습 재개 중" \
  "AI-Hub 82 재수신이 끝나 연속 학습 supervisor를 시작합니다." \
  "재수신 완료 · 연속 학습 supervisor 시작" "$total" "$total"
echo "[$(now_utc)] DOWNLOAD COMPLETE; START supervisor" >> "$MAIN_LOG"
FALLAI_AIHUB82_MAX_RUNS="${FALLAI_AIHUB82_MAX_RUNS:-3}" \
FALLAI_AIHUB82_HEARTBEAT_SEC="${FALLAI_AIHUB82_HEARTBEAT_SEC:-120}" \
  "$PY" "$PROJECT/scripts/continuous_aihub82_training_supervisor.py" >> "$MAIN_LOG" 2>&1
rc=$?
echo "[$(now_utc)] SUPERVISOR END rc=$rc" >> "$MAIN_LOG"
exit "$rc"
