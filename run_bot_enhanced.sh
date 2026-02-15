#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/github"
MAIN_SCRIPT="$PROJECT_DIR/main.py"
LOG_FILE="$PROJECT_DIR/cron.log"
LOCK_FILE="$PROJECT_DIR/bot.lock"
LOG_MAX_SIZE=5242880  # 5MB

export NAVER_BOT_HEALTH_DIR="$PROJECT_DIR"
export NAVER_BOT_HEARTBEAT_FILE="$PROJECT_DIR/last_run.txt"
if [ ! -d "$PROJECT_DIR" ]; then
  echo "ERROR: project directory not found: $PROJECT_DIR" >&2
  exit 1
fi
if [ ! -f "$MAIN_SCRIPT" ]; then
  echo "ERROR: main script not found: $MAIN_SCRIPT" >&2
  exit 1
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  # 以묐났 ?ㅽ뻾 諛⑹?
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] SKIP: already running." >> "$LOG_FILE"
  exit 0
fi

VENV_PATH="$SCRIPT_DIR/../venv"
if [ ! -x "$VENV_PATH/bin/python3" ]; then
  VENV_PATH="$SCRIPT_DIR/venv"
fi

SYSTEM_PYTHON="$(command -v python3 || true)"
if [ -z "$SYSTEM_PYTHON" ]; then
  echo "ERROR: python3 executable not found in PATH." >&2
  exit 1
fi

if [ ! -x "$VENV_PATH/bin/python3" ]; then
  "$SYSTEM_PYTHON" -m venv "$VENV_PATH"
fi

PYTHON_BIN="$VENV_PATH/bin/python3"
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"
REQUIREMENTS_STAMP="$PROJECT_DIR/.requirements.sha256"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: venv python3 executable not found: $PYTHON_BIN" >&2
  exit 1
fi
if [ ! -f "$REQUIREMENTS_FILE" ]; then
  echo "ERROR: requirements file not found: $REQUIREMENTS_FILE" >&2
  exit 1
fi

MAX_EXECUTION_TIME=150

log() {
  local log_size=0
  if [ -f "$LOG_FILE" ]; then
    log_size="$(stat -c%s "$LOG_FILE" 2>/dev/null || stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)"
    if [ "$log_size" -gt "$LOG_MAX_SIZE" ]; then
      mv "$LOG_FILE" "${LOG_FILE}.bak"
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: log rotated." >> "$LOG_FILE"
    fi
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

ensure_dependencies() {
  local required_hash
  local installed_hash=""
  local needs_install=0

  required_hash="$(sha256sum "$REQUIREMENTS_FILE" | awk '{print $1}')"
  if [ -f "$REQUIREMENTS_STAMP" ]; then
    installed_hash="$(tr -d '[:space:]' < "$REQUIREMENTS_STAMP")"
  fi

  if [ "$required_hash" != "$installed_hash" ]; then
    needs_install=1
  fi

  if ! "$PYTHON_BIN" -c "import telegram, selenium, dotenv" >/dev/null 2>&1; then
    needs_install=1
  fi

  if [ "$needs_install" -eq 1 ]; then
    log "INFO: syncing python dependencies."
    "$PYTHON_BIN" -m pip install -r "$REQUIREMENTS_FILE" >> "$LOG_FILE" 2>&1
    echo "$required_hash" > "$REQUIREMENTS_STAMP"
    log "INFO: dependency sync completed."
  fi
}

AVAILABLE_MEM=$(free -m | awk 'NR==2{print $7}')
if [ "$AVAILABLE_MEM" -lt 100 ]; then
  log "WARN: low free memory (${AVAILABLE_MEM}MB)."
fi

DISK_USAGE=$(df / | awk 'NR==2{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 90 ]; then
  log "WARN: high disk usage (${DISK_USAGE}%). Cleaning /tmp."
  find /tmp -type f -mtime +7 -delete 2>/dev/null || true
fi

cd "$PROJECT_DIR" || exit 1
ensure_dependencies

MAIN_EXIT=255
MAIN_PID=""

cleanup() {
  if [ -n "${MAIN_PID}" ] && kill -0 "$MAIN_PID" 2>/dev/null; then
    kill -TERM "$MAIN_PID" 2>/dev/null || true
    wait "$MAIN_PID" 2>/dev/null || true
  fi
  exec 9>&- 2>/dev/null || true
  rm -f "$LOCK_FILE" 2>/dev/null || true

  if [ "$MAIN_EXIT" -eq 255 ]; then
    log "ERROR: script aborted before main launch."
  elif [ "$MAIN_EXIT" -eq 124 ]; then
    log "ERROR: timeout hit (${MAX_EXECUTION_TIME}s)."
  elif [ "$MAIN_EXIT" -eq 137 ]; then
    log "ERROR: main killed (code=137). Memory/OOM dump:"
    free -m >> "$LOG_FILE" 2>&1
    dmesg | tail -5 >> "$LOG_FILE" 2>&1
  elif [ "$MAIN_EXIT" -ne 0 ]; then
    log "ERROR: main exit code=$MAIN_EXIT"
  else
    log "OK: finished (${AVAILABLE_MEM}MB, disk ${DISK_USAGE}%)."
  fi
}

trap cleanup EXIT INT TERM

timeout --signal=INT --kill-after=10s "${MAX_EXECUTION_TIME}s" "$PYTHON_BIN" "$MAIN_SCRIPT" &
MAIN_PID=$!
wait "$MAIN_PID" && MAIN_EXIT=0 || MAIN_EXIT=$?
exit "$MAIN_EXIT"
