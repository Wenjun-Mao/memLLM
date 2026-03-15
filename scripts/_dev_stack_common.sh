#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
ENV_FILE="$ROOT_DIR/infra/env/.env"
ENV_EXAMPLE_FILE="$ROOT_DIR/infra/env/ubuntu-dev.example.env"
COMPOSE_FILE="$ROOT_DIR/infra/compose/ubuntu-dev-stack.yml"
MODEL_DIR="$ROOT_DIR/infra/ollama/models"
MODEL_REPO="unsloth/Qwen3.5-9B-GGUF"
MODEL_FILE="Qwen3.5-9B-Q4_K_M.gguf"
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"
OLLAMA_MODEL_ALIAS="memllm-qwen3.5-9b-q4km"
OLLAMA_EMBED_MODEL="mxbai-embed-large"
OLLAMA_MODELFILE="$ROOT_DIR/infra/ollama/Modelfile.qwen3.5-9b-q4km"
POSTGRES_CONTAINER="memllm-postgres"
OLLAMA_CONTAINER="memllm-ollama"
LETTA_CONTAINER="memllm-letta"
API_PID_FILE="$RUNTIME_DIR/api.pid"
API_LOG_FILE="$RUNTIME_DIR/api.log"
DEV_UI_PID_FILE="$RUNTIME_DIR/dev_ui.pid"
DEV_UI_LOG_FILE="$RUNTIME_DIR/dev_ui.log"

MEMLLM_API_HOST="${MEMLLM_API_HOST:-127.0.0.1}"
MEMLLM_API_PORT="${MEMLLM_API_PORT:-8000}"
MEMLLM_DEV_UI_PORT="${MEMLLM_DEV_UI_PORT:-8501}"

print_info() {
  printf '[memllm] %s\n' "$*"
}

print_error() {
  printf '[memllm] ERROR: %s\n' "$*" >&2
}

ensure_runtime_dir() {
  mkdir -p "$RUNTIME_DIR"
}

ensure_env_file() {
  mkdir -p "$(dirname "$ENV_FILE")"
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
    print_info "Created $ENV_FILE from the example template."
  fi
}

load_env_file() {
  ensure_env_file
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a

  POSTGRES_USER="${POSTGRES_USER:-memllm}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-memllm}"
  POSTGRES_BOOTSTRAP_DB="${POSTGRES_BOOTSTRAP_DB:-postgres}"
  POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  LETTA_DB_NAME="${LETTA_DB_NAME:-letta}"
  LETTA_PORT="${LETTA_PORT:-8283}"
  OLLAMA_PORT="${OLLAMA_PORT:-11434}"

  MEMLLM_API_BASE_URL="${MEMLLM_API_BASE_URL:-http://127.0.0.1:${MEMLLM_API_PORT}}"
  MEMLLM_DEV_UI_BASE_URL="${MEMLLM_DEV_UI_BASE_URL:-http://127.0.0.1:${MEMLLM_DEV_UI_PORT}}"
  LETTA_BASE_URL="http://127.0.0.1:${LETTA_PORT}"
  OLLAMA_BASE_URL="http://127.0.0.1:${OLLAMA_PORT}"
}

validate_env_constraints() {
  if [[ "$LETTA_DB_NAME" != "letta" ]]; then
    print_error "LETTA_DB_NAME must remain 'letta' unless infra/compose/postgres-init is updated too."
    exit 1
  fi
}

compose_cmd() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    print_error "Missing required command: $command_name"
    exit 1
  fi
}

cleanup_stale_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]] && ! is_pid_running "$pid_file"; then
    rm -f "$pid_file"
  fi
}

is_pid_running() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi
  local pid
  pid="$(<"$pid_file")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_background_process() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3

  cleanup_stale_pid "$pid_file"
  if is_pid_running "$pid_file"; then
    local existing_pid
    existing_pid="$(<"$pid_file")"
    print_info "$name is already running with pid $existing_pid."
    return 0
  fi

  ensure_runtime_dir
  (
    cd "$ROOT_DIR"
    nohup "$@" >"$log_file" 2>&1 < /dev/null &
    echo $! > "$pid_file"
  )
  local new_pid
  new_pid="$(<"$pid_file")"
  print_info "Started $name with pid $new_pid. Log: $log_file"
}

stop_background_process() {
  local name="$1"
  local pid_file="$2"

  cleanup_stale_pid "$pid_file"
  if [[ ! -f "$pid_file" ]]; then
    print_info "$name is not running."
    return 0
  fi

  local pid
  pid="$(<"$pid_file")"
  kill "$pid" 2>/dev/null || true

  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_file"
      print_info "Stopped $name."
      return 0
    fi
    sleep 0.5
  done

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  print_info "Force-stopped $name."
}

http_ok() {
  local url="$1"
  local ok_codes="${2:-200}"
  URL="$url" OK_CODES="$ok_codes" uv run python - <<'PY'
from __future__ import annotations

import os
import sys

import httpx

ok_codes = {int(item) for item in os.environ["OK_CODES"].split(",") if item.strip()}
try:
    response = httpx.get(os.environ["URL"], timeout=5.0, follow_redirects=False)
except Exception:
    sys.exit(1)

sys.exit(0 if response.status_code in ok_codes else 1)
PY
}

wait_for_http() {
  local description="$1"
  local url="$2"
  local ok_codes="$3"
  local attempts="${4:-30}"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if http_ok "$url" "$ok_codes"; then
      print_info "$description is responding at $url."
      return 0
    fi
    sleep 2
  done

  print_error "$description did not become ready at $url."
  exit 1
}

wait_for_command() {
  local description="$1"
  local attempts="$2"
  shift 2

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if "$@" >/dev/null 2>&1; then
      print_info "$description is ready."
      return 0
    fi
    sleep 2
  done

  print_error "$description did not become ready."
  exit 1
}
