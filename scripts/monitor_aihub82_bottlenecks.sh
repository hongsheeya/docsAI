#!/usr/bin/env bash
set -euo pipefail

PROJECT="/opt/app/project/main"
INTERVAL="${FALLAI_AIHUB82_BOTTLENECK_INTERVAL_SEC:-1800}"
LOG="$PROJECT/outputs/continuous_training/aihub82_bottleneck_monitor.log"
PID_FILE="$PROJECT/outputs/continuous_training/aihub82_bottleneck_monitor.pid"

mkdir -p "$PROJECT/outputs/continuous_training"
echo "$$" > "$PID_FILE"

while true; do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[$ts] refresh AI-Hub82 bottleneck report" >> "$LOG"
  python "$PROJECT/scripts/analyze_aihub82_bottlenecks.py" --trigger "periodic-monitor" >> "$LOG" 2>&1 || true
  sleep "$INTERVAL"
done
