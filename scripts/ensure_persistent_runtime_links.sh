#!/usr/bin/env bash
set -u

PERSISTENT_ROOT="${PERSISTENT_ROOT:-/mnt/data/wiz}"
APP_ROOT="${APP_ROOT:-/opt/app}"
PROJECT_ROOT="${PROJECT_ROOT:-$APP_ROOT/project/main}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

link_path() {
  local link="$1"
  local target="$2"
  local parent
  parent="$(dirname "$link")"
  mkdir -p "$parent" "$target"

  if [ -L "$link" ]; then
    local current
    current="$(readlink "$link" 2>/dev/null || true)"
    if [ "$current" = "$target" ]; then
      echo "ok $link -> $target"
      return 0
    fi
    mv "$link" "${link}.old-link-$STAMP"
  elif [ -e "$link" ]; then
    mv "$link" "${link}.local-overlay-$STAMP"
  fi

  ln -s "$target" "$link"
  echo "linked $link -> $target"
}

link_path "$APP_ROOT/storage" "$PERSISTENT_ROOT/storage"
link_path "$APP_ROOT/_appdata/storage" "$PERSISTENT_ROOT/storage"
link_path "$APP_ROOT/datasets" "$PERSISTENT_ROOT/datasets"
link_path "$PROJECT_ROOT/storage" "$PERSISTENT_ROOT/storage"
link_path "$PROJECT_ROOT/outputs" "$PERSISTENT_ROOT/storage/project-main/outputs"
