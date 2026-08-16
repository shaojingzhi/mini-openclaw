#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG_FILE="$RUNTIME_DIR/backend.log"
FRONTEND_LOG_FILE="$RUNTIME_DIR/frontend.log"

BACKEND_HOST="${MINI_OPENCLAW_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${MINI_OPENCLAW_BACKEND_PORT:-8002}"
FRONTEND_HOST="${MINI_OPENCLAW_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${MINI_OPENCLAW_FRONTEND_PORT:-3004}"

BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"
FRONTEND_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:${BACKEND_PORT}}"
CORS_ORIGINS="${MINI_OPENCLAW_CORS_ORIGINS:-http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}}"

BACKEND_CMD=(env "MINI_OPENCLAW_CORS_ORIGINS=$CORS_ORIGINS" "$ROOT_DIR/.venv/bin/python" -m uvicorn backend.app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT")
FRONTEND_CMD=(env "NEXT_PUBLIC_API_URL=$FRONTEND_API_URL" "$ROOT_DIR/frontend/node_modules/.bin/next" dev --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT")

usage() {
  cat <<EOF
Usage: ./scripts/dev.sh <command>

Commands:
  start     Start backend and frontend in the background
  stop      Stop managed backend and frontend
  restart   Restart managed backend and frontend
  status    Show current service status
  logs      Tail backend/frontend logs
EOF
}

ensure_runtime_dir() {
  mkdir -p "$RUNTIME_DIR"
}

pid_is_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

read_pid() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    tr -d '[:space:]' < "$pid_file"
  fi
}

clear_stale_pid() {
  local pid_file="$1"
  local pid
  pid="$(read_pid "$pid_file")"
  if [ -n "${pid:-}" ] && ! pid_is_running "$pid"; then
    rm -f "$pid_file"
  fi
}

port_pid() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1
}

check_prerequisites() {
  if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
    echo "Missing backend Python at $ROOT_DIR/.venv/bin/python"
    echo "Create the venv first before using this script."
    exit 1
  fi

  if [ ! -x "$ROOT_DIR/frontend/node_modules/.bin/next" ]; then
    echo "Missing frontend dependencies at $ROOT_DIR/frontend/node_modules"
    echo "Run: cd $ROOT_DIR/frontend && npm install"
    exit 1
  fi
}

spawn_detached() {
  local pid_file="$1"
  local log_file="$2"
  local cwd="$3"
  shift 3

  python3 - "$pid_file" "$log_file" "$cwd" "$@" <<'PY'
import os
import subprocess
import sys

pid_file, log_file, cwd, *cmd = sys.argv[1:]

with open(log_file, "ab", buffering=0) as log_file_handle, open(os.devnull, "rb") as devnull:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=devnull,
        stdout=log_file_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

with open(pid_file, "w", encoding="utf-8") as pid_handle:
    pid_handle.write(str(process.pid))

print(process.pid)
PY
}

start_backend() {
  clear_stale_pid "$BACKEND_PID_FILE"
  local pid
  pid="$(read_pid "$BACKEND_PID_FILE")"
  if [ -n "${pid:-}" ] && pid_is_running "$pid"; then
    echo "Backend already running (pid $pid) at $BACKEND_URL"
    return
  fi

  local port_owner
  port_owner="$(port_pid "$BACKEND_PORT" || true)"
  if [ -n "${port_owner:-}" ]; then
    echo "Cannot start backend: port $BACKEND_PORT is already in use by pid $port_owner"
    exit 1
  fi

  : > "$BACKEND_LOG_FILE"
  local started_pid
  started_pid="$(spawn_detached "$BACKEND_PID_FILE" "$BACKEND_LOG_FILE" "$ROOT_DIR" "${BACKEND_CMD[@]}")"

  sleep 2
  if ! pid_is_running "$started_pid"; then
    echo "Backend failed to start. See $BACKEND_LOG_FILE"
    exit 1
  fi

  echo "Started backend (pid $started_pid) at $BACKEND_URL"
}

start_frontend() {
  clear_stale_pid "$FRONTEND_PID_FILE"
  local pid
  pid="$(read_pid "$FRONTEND_PID_FILE")"
  if [ -n "${pid:-}" ] && pid_is_running "$pid"; then
    echo "Frontend already running (pid $pid) at $FRONTEND_URL"
    return
  fi

  local port_owner
  port_owner="$(port_pid "$FRONTEND_PORT" || true)"
  if [ -n "${port_owner:-}" ]; then
    echo "Cannot start frontend: port $FRONTEND_PORT is already in use by pid $port_owner"
    exit 1
  fi

  : > "$FRONTEND_LOG_FILE"
  local started_pid
  started_pid="$(spawn_detached "$FRONTEND_PID_FILE" "$FRONTEND_LOG_FILE" "$ROOT_DIR/frontend" "${FRONTEND_CMD[@]}")"
  sleep 2
  if [ -z "${started_pid:-}" ] || ! pid_is_running "$started_pid"; then
    echo "Frontend failed to start. See $FRONTEND_LOG_FILE"
    exit 1
  fi

  echo "Started frontend (pid $started_pid) at $FRONTEND_URL"
}

stop_service() {
  local name="$1"
  local pid_file="$2"

  clear_stale_pid "$pid_file"
  local pid
  pid="$(read_pid "$pid_file")"
  if [ -z "${pid:-}" ]; then
    echo "$name is not running"
    return
  fi

  kill "$pid" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    if ! pid_is_running "$pid"; then
      rm -f "$pid_file"
      echo "Stopped $name"
      return
    fi
    sleep 0.25
  done

  kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$pid_file"
  echo "Force stopped $name"
}

show_status() {
  clear_stale_pid "$BACKEND_PID_FILE"
  clear_stale_pid "$FRONTEND_PID_FILE"

  local backend_pid frontend_pid backend_port_pid frontend_port_pid
  backend_pid="$(read_pid "$BACKEND_PID_FILE")"
  frontend_pid="$(read_pid "$FRONTEND_PID_FILE")"
  backend_port_pid="$(port_pid "$BACKEND_PORT" || true)"
  frontend_port_pid="$(port_pid "$FRONTEND_PORT" || true)"

  if [ -n "${backend_pid:-}" ] && pid_is_running "$backend_pid"; then
    echo "backend: running (pid $backend_pid) $BACKEND_URL"
  elif [ -n "${backend_port_pid:-}" ]; then
    echo "backend: listening on $BACKEND_URL via unmanaged pid $backend_port_pid"
  else
    echo "backend: stopped"
  fi

  if [ -n "${frontend_pid:-}" ] && pid_is_running "$frontend_pid"; then
    echo "frontend: running (pid $frontend_pid) $FRONTEND_URL"
  elif [ -n "${frontend_port_pid:-}" ]; then
    echo "frontend: listening on $FRONTEND_URL via unmanaged pid $frontend_port_pid"
  else
    echo "frontend: stopped"
  fi

  echo "logs:"
  echo "  backend  $BACKEND_LOG_FILE"
  echo "  frontend $FRONTEND_LOG_FILE"
}

tail_logs() {
  ensure_runtime_dir
  touch "$BACKEND_LOG_FILE" "$FRONTEND_LOG_FILE"
  tail -n 40 -f "$BACKEND_LOG_FILE" "$FRONTEND_LOG_FILE"
}

start_all() {
  ensure_runtime_dir
  check_prerequisites
  start_backend
  start_frontend
}

stop_all() {
  stop_service "frontend" "$FRONTEND_PID_FILE"
  stop_service "backend" "$BACKEND_PID_FILE"
}

command="${1:-}"
case "$command" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    ensure_runtime_dir
    show_status
    ;;
  logs)
    tail_logs
    ;;
  *)
    usage
    exit 1
    ;;
esac
