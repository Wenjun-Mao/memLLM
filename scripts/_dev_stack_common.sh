#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/infra/env/.env"
ENV_EXAMPLE_FILE="$ROOT_DIR/infra/env/ubuntu-dev.example.env"
COMPOSE_FILE="$ROOT_DIR/infra/compose/ubuntu-dev-stack.yml"
MODEL_DIR="$ROOT_DIR/infra/ollama/models"
LETTA_NLTK_DATA_DIR="$ROOT_DIR/infra/letta/nltk_data"
MODEL_REPO="unsloth/Qwen3.5-9B-GGUF"
MODEL_FILE="Qwen3.5-9B-Q4_K_M.gguf"
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"
DEFAULT_OLLAMA_MODEL_ALIAS="memllm-qwen3.5-9b-q4km"
DEFAULT_OLLAMA_EMBED_MODEL="mxbai-embed-large"
OLLAMA_MODELFILE="$ROOT_DIR/infra/ollama/Modelfile.qwen3.5-9b-q4km"
POSTGRES_CONTAINER="memllm-postgres"
OLLAMA_CONTAINER="memllm-ollama"
LETTA_CONTAINER="memllm-letta"
API_CONTAINER="memllm-api"
DEV_UI_CONTAINER="memllm-dev-ui"

MEMLLM_API_PORT="${MEMLLM_API_PORT:-8000}"
MEMLLM_DEV_UI_PORT="${MEMLLM_DEV_UI_PORT:-8501}"

print_info() {
  printf '[memllm] %s\n' "$*"
}

print_error() {
  printf '[memllm] ERROR: %s\n' "$*" >&2
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
  OLLAMA_MODEL_ALIAS="${OLLAMA_MODEL_ALIAS:-$DEFAULT_OLLAMA_MODEL_ALIAS}"
  OLLAMA_EMBED_MODEL="${OLLAMA_EMBED_MODEL:-$DEFAULT_OLLAMA_EMBED_MODEL}"
  LETTA_READY_TIMEOUT_SECONDS="${LETTA_READY_TIMEOUT_SECONDS:-600}"
  LETTA_READY_PROGRESS_INTERVAL_SECONDS="${LETTA_READY_PROGRESS_INTERVAL_SECONDS:-30}"

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

http_ok() {
  local url="$1"
  local ok_codes="${2:-200}"
  local code

  code=$(curl -sS -L -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || true)
  if [[ -z "$code" || "$code" == "000" ]]; then
    return 1
  fi

  local candidate
  IFS=',' read -r -a _memllm_ok_codes <<< "$ok_codes"
  for candidate in "${_memllm_ok_codes[@]}"; do
    candidate="${candidate//[[:space:]]/}"
    if [[ "$code" == "$candidate" ]]; then
      return 0
    fi
  done
  return 1
}

wait_for_http() {
  local description="$1"
  local url="$2"
  local ok_codes="$3"
  local attempts="${4:-30}"
  local exit_on_failure="${5:-true}"
  local progress_every_attempts="${6:-0}"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if http_ok "$url" "$ok_codes"; then
      print_info "$description is responding at $url."
      return 0
    fi
    if (( progress_every_attempts > 0 && attempt % progress_every_attempts == 0 )); then
      print_info "Still waiting for $description at $url ($((attempt * 2))s elapsed)."
    fi
    sleep 2
  done

  print_error "$description did not become ready at $url."
  if [[ "$exit_on_failure" == "true" ]]; then
    exit 1
  fi
  return 1
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
