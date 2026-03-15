#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/_dev_stack_common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/bootstrap_ubuntu.sh [--mode infra|api|full]

Modes:
  infra  Prepare the Docker stack, local models, and Python workspace only.
  api    Do everything in infra, then start the FastAPI service and seed characters.
  full   Do everything in api, then start the Streamlit dev UI.
EOF
}

MODE="infra"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      if [[ $# -lt 2 ]]; then
        print_error "--mode requires a value."
        usage
        exit 1
      fi
      MODE="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      print_error "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

case "$MODE" in
  infra|api|full) ;;
  *)
    print_error "Invalid mode: $MODE"
    usage
    exit 1
    ;;
esac

select_hf_cmd() {
  if command -v hf >/dev/null 2>&1; then
    HF_CMD=(hf)
  else
    HF_CMD=(uvx --from huggingface_hub hf)
  fi
}

preflight_checks() {
  require_command docker
  require_command git
  require_command uv
  require_command nvidia-smi
  docker compose version >/dev/null
  docker info >/dev/null
}

sync_workspace() {
  print_info "Syncing the uv workspace."
  (
    cd "$ROOT_DIR"
    uv sync --all-packages
  )
}

download_model_if_needed() {
  mkdir -p "$MODEL_DIR"
  if [[ -f "$MODEL_PATH" ]]; then
    print_info "Model file already present at $MODEL_PATH."
    return 0
  fi

  print_info "Downloading $MODEL_FILE from Hugging Face."
  local -a command=("${HF_CMD[@]}" download "$MODEL_REPO" "$MODEL_FILE" --local-dir "$MODEL_DIR")
  if [[ -n "${HF_TOKEN:-}" ]]; then
    command+=(--token "$HF_TOKEN")
  fi
  "${command[@]}"
}

wait_for_postgres() {
  wait_for_command \
    "Postgres" \
    30 \
    docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_BOOTSTRAP_DB"
}

wait_for_ollama() {
  wait_for_command \
    "Ollama" \
    30 \
    docker exec "$OLLAMA_CONTAINER" ollama list
}

wait_for_letta() {
  wait_for_http "Letta" "$LETTA_BASE_URL/v1/agents" "200,401,403" 30
}

ensure_ollama_model() {
  local model_name="$1"
  if docker exec "$OLLAMA_CONTAINER" ollama list | grep -E "^${model_name}:latest[[:space:]]" >/dev/null; then
    print_info "Ollama model already present: $model_name"
    return 0
  fi
  print_info "Pulling Ollama model $model_name."
  docker exec "$OLLAMA_CONTAINER" ollama pull "$model_name"
}

ensure_custom_ollama_alias() {
  if docker exec "$OLLAMA_CONTAINER" ollama list | grep -E "^${OLLAMA_MODEL_ALIAS}:latest[[:space:]]" >/dev/null; then
    print_info "Ollama alias already present: $OLLAMA_MODEL_ALIAS"
    return 0
  fi
  print_info "Creating Ollama alias $OLLAMA_MODEL_ALIAS from the local GGUF."
  docker exec "$OLLAMA_CONTAINER" ollama create \
    "$OLLAMA_MODEL_ALIAS" \
    -f "/workspace/ollama/$(basename "$OLLAMA_MODELFILE")"
}

start_infra() {
  print_info "Starting Docker services for Postgres/pgvector, Ollama, and Letta."
  compose_cmd up -d
  wait_for_postgres
  wait_for_ollama
  wait_for_letta
  ensure_ollama_model "$OLLAMA_EMBED_MODEL"
  ensure_custom_ollama_alias
}

start_api() {
  local database_url="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/memllm"
  start_background_process \
    "memllm-api" \
    "$API_PID_FILE" \
    "$API_LOG_FILE" \
    env \
      MEMLLM_API_HOST="$MEMLLM_API_HOST" \
      MEMLLM_API_PORT="$MEMLLM_API_PORT" \
      MEMLLM_API_DATABASE_BACKEND="sqlalchemy" \
      MEMLLM_API_DATABASE_URL="$database_url" \
      MEMLLM_API_LETTA_MODE="real" \
      MEMLLM_API_LETTA_BASE_URL="$LETTA_BASE_URL" \
      MEMLLM_API_LETTA_MODEL="ollama/${OLLAMA_MODEL_ALIAS}" \
      MEMLLM_API_LETTA_EMBEDDING="ollama/${OLLAMA_EMBED_MODEL}" \
      MEMLLM_API_MEMORY_EXTRACTOR_KIND="ollama_json" \
      MEMLLM_API_MEMORY_EXTRACTOR_BASE_URL="$OLLAMA_BASE_URL" \
      MEMLLM_API_MEMORY_EXTRACTOR_MODEL="$OLLAMA_MODEL_ALIAS" \
      uv run --package memllm-api memllm-api
  wait_for_http "memllm-api" "$MEMLLM_API_BASE_URL/health" "200" 30
}

seed_characters() {
  print_info "Seeding character manifests through the API."
  (
    cd "$ROOT_DIR"
    MEMLLM_API_BASE_URL="$MEMLLM_API_BASE_URL" uv run python scripts/seed_characters.py
  )
}

start_dev_ui() {
  start_background_process \
    "memllm-dev-ui" \
    "$DEV_UI_PID_FILE" \
    "$DEV_UI_LOG_FILE" \
    env \
      MEMLLM_DEV_UI_API_BASE_URL="$MEMLLM_API_BASE_URL" \
      STREAMLIT_SERVER_PORT="$MEMLLM_DEV_UI_PORT" \
      uv run --package memllm-dev-ui memllm-dev-ui
  wait_for_http "memllm-dev-ui" "$MEMLLM_DEV_UI_BASE_URL" "200,302" 30
}

print_summary() {
  print_info "Bootstrap complete."
  print_info "Docker stack: Postgres on 127.0.0.1:${POSTGRES_PORT}, Ollama on $OLLAMA_BASE_URL, Letta on $LETTA_BASE_URL"
  if [[ "$MODE" == "api" || "$MODE" == "full" ]]; then
    print_info "API: $MEMLLM_API_BASE_URL (log: $API_LOG_FILE)"
  fi
  if [[ "$MODE" == "full" ]]; then
    print_info "Dev UI: $MEMLLM_DEV_UI_BASE_URL (log: $DEV_UI_LOG_FILE)"
  fi
  print_info "Use bash scripts/status_dev_stack.sh to inspect the environment."
}

load_env_file
validate_env_constraints
ensure_runtime_dir
select_hf_cmd
preflight_checks
sync_workspace
download_model_if_needed
start_infra

if [[ "$MODE" == "api" || "$MODE" == "full" ]]; then
  start_api
  seed_characters
fi

if [[ "$MODE" == "full" ]]; then
  start_dev_ui
fi

print_summary
