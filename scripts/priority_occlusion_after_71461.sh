#!/usr/bin/env bash
set -u

PROJECT="${PROJECT:-/opt/app/project/main}"
DATASET_ROOT="${FALLAI_71461_DATASET_ROOTS:-/opt/app/tmp/datasets/action_behavior/aihub_71461}"
RUN_DIR="$PROJECT/outputs/continuous_training"
LOG="$RUN_DIR/priority_occlusion_after_71461.log"
STATUS="$RUN_DIR/xg-posture_status.json"
TARGET="${POSTURE_OCC_PRIORITY_TARGET:-0.90}"
PY="${FALLAI_PYTHON:-python3}"

mkdir -p "$RUN_DIR"

if [ "${FALLAI_USE_LEGACY_OCCLUSION_WATCHER:-0}" != "1" ]; then
  exec "$PY" "$PROJECT/scripts/targeted_occlusion_weak_pose_loop.py"
fi

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

write_status() {
  local stage="$1"
  local eta_text="$2"
  local message="$3"
  local latest_log="$4"
  "$PY" - "$STATUS" "$stage" "$eta_text" "$message" "$latest_log" "$TARGET" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
stage, eta_text, message, latest_log, target = sys.argv[2:7]
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {"ok": True, "name": "xg-posture", "label": "XG-Posture 재학습"}
data.update({
    "ok": True,
    "name": "xg-posture",
    "label": "XG-Posture/가림 보조 우선 학습",
    "stage": stage,
    "status": stage,
    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "eta_text": eta_text,
    "message": message,
    "latest_log": latest_log,
    "target_macro_f1": float(target),
    "occlusion_priority_target_macro_f1": float(target),
    "priority": "occlusion-first-after-71461",
    "bottleneck": {
        "ready": True,
        "posture_intake_counts": (data.get("bottleneck") or {}).get("posture_intake_counts", {}),
        "usable_posture_label_count": max(1, int((data.get("bottleneck") or {}).get("usable_posture_label_count") or 0)),
        "occlusion_source_ready": True,
        "message": "71461 라벨 zip을 추출했고 가림 보조 학습 입력으로 인식했습니다.",
    },
})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

count_labels() {
  find "$DATASET_ROOT" -type f -path '*02.라벨링데이터*' -name '*.json' 2>/dev/null \
    | awk 'NR >= 10000 { print NR; exit } END { if (NR < 10000) print NR }' \
    | tr -d ' '
}

extract_label_zips() {
  "$PY" - "$DATASET_ROOT" "$LOG" <<'PY'
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
log_path = Path(sys.argv[2])

def log(message):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as file:
            file.write(f"[{stamp}] {message}\n")
    except Exception:
        pass

if not root.exists():
    sys.exit(0)

zips = [
    path for path in root.rglob("*.zip")
    if "02.라벨링데이터" in str(path)
]
for zip_path in zips:
    extract_dir = zip_path.with_suffix("")
    marker = extract_dir / ".fallai_label_zip_extracted"
    if marker.exists() and any(extract_dir.rglob("*.json")):
        continue
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            json_names = [
                name for name in archive.namelist()
                if name.lower().endswith(".json") and "/._" not in name and not os.path.basename(name).startswith("._")
            ]
            if not json_names:
                log(f"LABEL_ZIP_NO_JSON path={zip_path}")
                continue
            extracted = 0
            for name in json_names:
                safe_name = name.replace("\\", "/").lstrip("/")
                parts = [part for part in safe_name.split("/") if part and part not in (".", "..")]
                if not parts:
                    continue
                out_path = extract_dir.joinpath(*parts)
                if out_path.exists():
                    extracted += 1
                    continue
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, out_path.open("wb") as dst:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
                extracted += 1
            marker.write_text(
                f"source={zip_path}\njson_count={len(json_names)}\nextracted_at={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
                encoding="utf-8",
            )
            log(f"LABEL_ZIP_EXTRACTED path={zip_path} json={len(json_names)} extracted={extracted} dir={extract_dir}")
    except Exception as exc:
        log(f"LABEL_ZIP_EXTRACT_FAILED path={zip_path} reason={type(exc).__name__}:{str(exc)[:180]}")
PY
}

count_label_zip_jsons() {
  "$PY" - "$DATASET_ROOT" <<'PY'
import os
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
total = 0
if root.exists():
    for zip_path in root.rglob("*.zip"):
        if "02.라벨링데이터" not in str(zip_path):
            continue
        try:
            with zipfile.ZipFile(zip_path) as archive:
                total += sum(
                    1 for name in archive.namelist()
                    if name.lower().endswith(".json") and "/._" not in name and not os.path.basename(name).startswith("._")
                )
        except Exception:
            pass
print(total)
PY
}

count_done_files() {
  find "$DATASET_ROOT" -maxdepth 2 -type f -name '.aihub_71461_*.done' 2>/dev/null | wc -l | tr -d ' '
}

current_aux_f1() {
  "$PY" - <<'PY'
import json
from pathlib import Path
path = Path('/opt/app/storage/training/fall-detection/xg-posture-occlusion-aux/training_summary.json')
try:
    data = json.loads(path.read_text(encoding='utf-8'))
    print(float((data.get('group_cv') or {}).get('f1_macro') or data.get('f1_macro') or 0.0))
except Exception:
    print(0.0)
PY
}

labels_seen=0
done_seen=0
echo "[$(now_utc)] START priority occlusion watcher dataset_root=$DATASET_ROOT target=$TARGET" >> "$LOG"

while true; do
  if pgrep -f 'retrain_xg_posture_sequence.py' >/dev/null 2>&1; then
    write_status "running" "가림 보조 학습 중" \
      "71461 라벨 확보 후 가림 보조 학습이 진행 중입니다." \
      "가림 보조 학습 프로세스 실행 중"
    sleep 60
    continue
  fi

  extract_label_zips
  label_count="$(count_labels)"
  if [ "$label_count" -le 0 ]; then
    zip_label_count="$(count_label_zip_jsons)"
    if [ "$zip_label_count" -gt 0 ]; then
      label_count="$zip_label_count"
    fi
  fi
  done_count="$(count_done_files)"
  if [ "$label_count" -le 0 ]; then
    sleep 60
    continue
  fi

  if [ "$label_count" -eq "$labels_seen" ] && [ "$done_count" -eq "$done_seen" ]; then
    sleep 180
    continue
  fi
  labels_seen="$label_count"
  done_seen="$done_count"

  train_log="$RUN_DIR/priority_occlusion_train_$(date -u +%Y%m%dT%H%M%SZ).log"
  echo "[$(now_utc)] START train labels=$label_count done_files=$done_count log=$train_log" >> "$LOG"
  write_status "running" "학습 시작" \
    "71461 자세 라벨을 감지해 가림 보조 학습을 시작했습니다." \
    "라벨 ${label_count}개 · 완료 파일 ${done_count}개 · 가림 우선 학습"

  FALLAI_71461_DATASET_ROOTS="$DATASET_ROOT" \
  POSTURE_INCLUDE_SYNTH_LOWER_OCCLUSION=1 \
  POSTURE_INCLUDE_SYNTH_VERTICAL_OCCLUSION=1 \
  POSTURE_SAVE_OCCLUSION_AUX=1 \
  POSTURE_OCC_AUX_MIN_SAVE_F1="$TARGET" \
  POSTURE_DISABLE_ACTIVE_REPLACEMENT=1 \
  POSTURE_ALLOW_MISSING_RUN="${POSTURE_ALLOW_MISSING_RUN:-1}" \
  POSTURE_STATIC_RUN_LIMIT="${POSTURE_STATIC_RUN_LIMIT:-0}" \
  POSTURE_AIHUB61_SEQ_RUN_LIMIT="${POSTURE_AIHUB61_SEQ_RUN_LIMIT:-0}" \
  POSTURE_AIHUB62_SEQ_RUN_LIMIT="${POSTURE_AIHUB62_SEQ_RUN_LIMIT:-0}" \
  POSTURE_AIHUB62_RAW_RUN_LIMIT="${POSTURE_AIHUB62_RAW_RUN_LIMIT:-0}" \
  POSTURE_LOWER_OCCLUSION_RUN_LIMIT="${POSTURE_LOWER_OCCLUSION_RUN_LIMIT:-0}" \
  POSTURE_SYNTH_SEQ_OCC_RUN_LIMIT="${POSTURE_SYNTH_SEQ_OCC_RUN_LIMIT:-0}" \
  POSTURE_SYNTH_SEQ_VERTICAL_OCC_RUN_LIMIT="${POSTURE_SYNTH_SEQ_VERTICAL_OCC_RUN_LIMIT:-0}" \
  POSTURE_RF_INTAKE_PSEUDO_RUN_LIMIT="${POSTURE_RF_INTAKE_PSEUDO_RUN_LIMIT:-0}" \
  POSTURE_INCLUDE_TREE_ENSEMBLES="${POSTURE_INCLUDE_TREE_ENSEMBLES:-1}" \
  POSTURE_MODEL_FILTER="${POSTURE_MODEL_FILTER:-extra_trees}" \
  POSTURE_FEATURE_SET_FILTER="${POSTURE_FEATURE_SET_FILTER:-occlusion_aware,upper_body_motion_focus,temporal_pose_core}" \
  "$PY" "$PROJECT/scripts/retrain_xg_posture_sequence.py" >> "$train_log" 2>&1
  rc=$?
  f1="$(current_aux_f1)"
  echo "[$(now_utc)] END train rc=$rc aux_f1=$f1 labels=$label_count done_files=$done_count" >> "$LOG"

  "$PY" - "$f1" "$TARGET" "$rc" <<'PY' >/tmp/fallai_occ_priority_decision.txt
import sys
f1 = float(sys.argv[1] or 0)
target = float(sys.argv[2] or 0.9)
rc = int(sys.argv[3] or 0)
print("complete" if rc == 0 and f1 >= target else "continue")
PY
  decision="$(cat /tmp/fallai_occ_priority_decision.txt 2>/dev/null || echo continue)"
  if [ "$decision" = "complete" ]; then
    write_status "completed" "목표 달성" \
      "가림 보조 모델이 목표 성능을 달성했습니다. 다른 모델 학습을 순차 재개할 수 있습니다." \
      "가림 보조 macro F1 ${f1} · 목표 ${TARGET}"
    exit 0
  fi

  write_status "waiting_label_balance" "목표 미달 · 자세 라벨 보강 필요" \
    "가림 보조 학습은 실행됐지만 목표에 미달했습니다. 현재는 run 라벨을 제외하고 확보된 walk 자세 라벨과 71461 전처리 가림 데이터로 계속 재학습합니다." \
    "현재 가림 보조 macro F1 ${f1} · 목표 ${TARGET} · 라벨 ${label_count}개 · 완료 파일 ${done_count}개"
  sleep 180
done
