#!/usr/bin/env bash
set -euo pipefail

PROJECT="/opt/app/project/main"
RUN_DIR="$PROJECT/outputs/continuous_training"
SUPERVISOR_PID_FILE="$RUN_DIR/aihub82_supervisor.pid"

mkdir -p "$RUN_DIR"

matching_pids() {
  ps -eo pid=,cmd= | awk -v self="$$" -v parent="${PPID:-}" '
    $1 == self { next }
    parent != "" && $1 == parent { next }
    /continuous_aihub82_training_supervisor\.py/ ||
    /train_facial_emotion_aihub82\.py .*aihub82_continuous/ ||
    /monitor_aihub82_bottlenecks\.sh/ {
      print $1
    }
  '
}

for pid_file in "$SUPERVISOR_PID_FILE" "$RUN_DIR/aihub82_bottleneck_monitor.pid"; do
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file" || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  fi
done

pids="$(matching_pids || true)"
if [ -n "$pids" ]; then
  kill $pids 2>/dev/null || true
fi

sleep 2

pids="$(matching_pids || true)"
if [ -n "$pids" ]; then
  kill -9 $pids 2>/dev/null || true
fi

setsid -f bash -lc "cd '$PROJECT' && exec python3 scripts/continuous_aihub82_training_supervisor.py" \
  > "$RUN_DIR/aihub82_supervisor.restart.out" 2>&1

setsid -f bash -lc "cd '$PROJECT' && exec bash scripts/monitor_aihub82_bottlenecks.sh" \
  > "$RUN_DIR/aihub82_bottleneck_monitor.out" 2>&1

sleep 5

supervisor_pid="$(
  ps -eo pid=,cmd= | awk '/continuous_aihub82_training_supervisor\.py/ { print $1; exit }'
)"
if [ -n "$supervisor_pid" ]; then
  printf '%s\n' "$supervisor_pid" > "$SUPERVISOR_PID_FILE"
fi

printf 'supervisor_pid=%s\n' "${supervisor_pid:-none}"
printf 'monitor_pid=%s\n' "$(cat "$RUN_DIR/aihub82_bottleneck_monitor.pid" 2>/dev/null || printf 'none')"
ps -fp ${supervisor_pid:-99999999} "$(cat "$RUN_DIR/aihub82_bottleneck_monitor.pid" 2>/dev/null || printf '99999998')" || true
