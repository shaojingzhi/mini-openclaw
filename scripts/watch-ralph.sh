#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RALPH_DIR="$ROOT_DIR/scripts/ralph"
PRD_FILE="$RALPH_DIR/prd.json"
STATE_FILE="$RALPH_DIR/.watch-ralph.state"

if [ -f "$STATE_FILE" ]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
fi

OUTPUT_FILE="${OUTPUT_FILE:-}"
TASK_ID="${TASK_ID:-}"

latest_output_file() {
  find /private/tmp/claude-501 -path "*/tasks/*.output" -name "*.output" 2>/dev/null | while IFS= read -r file; do
    if [ -s "$file" ]; then
      printf '%s\n' "$file"
    fi
  done | xargs ls -t 2>/dev/null | head -1
}

derive_task_id() {
  local output_file="$1"
  basename "$output_file" .output
}

persist_state() {
  cat > "$STATE_FILE" <<EOF
OUTPUT_FILE="$OUTPUT_FILE"
TASK_ID="$TASK_ID"
EOF
}

ensure_output_file() {
  if [ -n "$OUTPUT_FILE" ] && [ -f "$OUTPUT_FILE" ]; then
    return
  fi

  OUTPUT_FILE="$(latest_output_file)"
  if [ -n "$OUTPUT_FILE" ]; then
    TASK_ID="$(derive_task_id "$OUTPUT_FILE")"
    persist_state
  fi
}

current_story() {
  if [ ! -f "$PRD_FILE" ]; then
    return
  fi

  jq -r 'first(.userStories[] | select(.passes == false) | "\(.id) \(.title)") // "complete"' "$PRD_FILE"
}

ralph_status() {
  if ps -ef | grep -F "./scripts/ralph/ralph.sh --tool claude" | grep -v grep >/dev/null 2>&1; then
    echo "running"
    return
  fi

  echo "idle"
}

show_snapshot() {
  clear
  echo "== Ralph Status =="
  date
  echo

  echo "[Git]"
  git -C "$ROOT_DIR" branch --show-current || true
  git -C "$ROOT_DIR" rev-list --count origin/ralph/mini-openclaw..ralph/mini-openclaw 2>/dev/null | xargs -I{} echo "unpushed commits: {}" || echo "unpushed commits: unknown"
  echo

  ensure_output_file

  echo "[Run]"
  echo "status: $(ralph_status)"
  if [ -n "$TASK_ID" ]; then
    echo "task id: $TASK_ID"
  fi
  if [ -n "$OUTPUT_FILE" ]; then
    echo "output: $OUTPUT_FILE"
  else
    echo "output: unavailable"
  fi
  echo "current story: $(current_story)"
  echo

  echo "[Progress]"
  if [ -f "$PRD_FILE" ]; then
    jq -r '(.userStories | map(select(.passes)) | length) as $done | (.userStories | length) as $total | "done: \($done)/\($total)"' "$PRD_FILE"
    echo
    jq -r '.userStories[] | select(.passes == false) | "- \(.id) \(.title)"' "$PRD_FILE" | head -10
  else
    echo "prd.json not found: $PRD_FILE"
  fi
  echo

  echo "[Recent Commits]"
  git -C "$ROOT_DIR" log --oneline -6 2>/dev/null || true
  echo

  echo "[Latest Ralph Output]"
  if [ -n "$OUTPUT_FILE" ] && [ -f "$OUTPUT_FILE" ]; then
    tail -20 "$OUTPUT_FILE"
  else
    echo "No Ralph output file found under /private/tmp/claude-501"
  fi
}

if [ "${1:-}" = "--follow" ]; then
  while true; do
    show_snapshot
    sleep 5
  done
else
  show_snapshot
fi
