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
  api    Do everything in infra, then start the API container.
  full   Do everything in api, then start the Streamlit dev UI container.
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
  validate_nvidia_runtime
}

validate_nvidia_runtime() {
  if ! docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
    print_error "Docker does not report an NVIDIA runtime. Install/configure the NVIDIA Container Toolkit first."
    print_error "Expected validation command: docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi"
    exit 1
  fi

  if [[ ! -S /run/nvidia-persistenced/socket ]]; then
    print_error "Missing NVIDIA persistence daemon socket: /run/nvidia-persistenced/socket"
    if command -v systemctl >/dev/null 2>&1; then
      if systemctl list-unit-files | grep -q '^nvidia-persistenced\.service'; then
        print_error "Start it with: sudo systemctl enable --now nvidia-persistenced"
      else
        print_error "Install the NVIDIA driver component that provides nvidia-persistenced, then enable the service."
      fi
    fi
    print_error "After that, verify GPU containers with: docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi"
    exit 1
  fi
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
  if wait_for_http "Letta" "$LETTA_BASE_URL/v1/health" "200" 90 false; then
    return 0
  fi

  print_error "Letta did not become ready. The bootstrap stops in the infra phase here, so the API and dev UI were not started. Recent container logs:"
  docker logs --tail 120 "$LETTA_CONTAINER" >&2 || true
  exit 1
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

preload_chat_model() {
  print_info "Preloading $OLLAMA_MODEL_ALIAS and asking Ollama to keep it resident."
  OLLAMA_BASE_URL="$OLLAMA_BASE_URL" OLLAMA_MODEL="$OLLAMA_MODEL_ALIAS:latest" uv run python - <<'PY2'
from __future__ import annotations

import os

import httpx

payload = {
    'model': os.environ['OLLAMA_MODEL'],
    'prompt': '<|im_start|>system\nStay ready.<|im_end|>\n<|im_start|>assistant\n',
    'stream': False,
    'raw': True,
    'keep_alive': -1,
    'options': {'num_predict': 1},
}
with httpx.Client(timeout=120.0) as client:
    response = client.post(f"{os.environ['OLLAMA_BASE_URL']}/api/generate", json=payload)
    response.raise_for_status()
PY2
}

start_infra() {
  print_info "Starting Docker services for Postgres/pgvector, Ollama, and Letta."
  compose_cmd up -d postgres ollama letta
  wait_for_postgres
  wait_for_ollama
  wait_for_letta
  ensure_ollama_model "$OLLAMA_EMBED_MODEL"
  ensure_custom_ollama_alias
  preload_chat_model
}

start_api() {
  print_info "Starting the API container."
  compose_cmd up -d api
  wait_for_http "memllm-api" "$MEMLLM_API_BASE_URL/health" "200" 60
}

start_dev_ui() {
  print_info "Starting the dev UI container."
  compose_cmd up -d dev_ui
  wait_for_http "memllm-dev-ui" "$MEMLLM_DEV_UI_BASE_URL" "200,302" 60
}

print_summary() {
  print_info "Bootstrap complete."
  print_info "Docker stack: Postgres on 127.0.0.1:${POSTGRES_PORT}, Ollama on $OLLAMA_BASE_URL, Letta on $LETTA_BASE_URL"
  if [[ "$MODE" == "api" || "$MODE" == "full" ]]; then
    print_info "API: $MEMLLM_API_BASE_URL"
  fi
  if [[ "$MODE" == "full" ]]; then
    print_info "Dev UI: $MEMLLM_DEV_UI_BASE_URL"
  fi
  print_info "Use bash scripts/status_dev_stack.sh to inspect the environment."
}

load_env_file
validate_env_constraints
select_hf_cmd
preflight_checks
sync_workspace
download_model_if_needed
start_infra

if [[ "$MODE" == "api" || "$MODE" == "full" ]]; then
  start_api
fi

if [[ "$MODE" == "full" ]]; then
  start_dev_ui
fi

print_summary
