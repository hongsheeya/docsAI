#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/app/project/main"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv-yolo/bin/python" ]]; then
  echo "YOLO venv not found: $ROOT/.venv-yolo/bin/python" >&2
  exit 1
fi

mkdir -p "$ROOT/storage/training/fall-detection/model"

source "$ROOT/.venv-yolo/bin/activate"
python "$ROOT/scripts/train_sample_yolo.py" "$@" | tee "$ROOT/storage/training/fall-detection/model/training_console.log"
