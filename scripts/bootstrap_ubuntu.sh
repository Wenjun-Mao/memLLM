#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/_dev_stack_common.sh"

usage() {
  cat <<'HELP'
Usage: bash scripts/bootstrap_ubuntu.sh [--mode infra|api|full]

Modes:
  infra  Prepare the Docker stack, local models, and Python workspace only.
  api    Do everything in infra, then start the API container.
  full   Do everything in api, then start the model gateway and Streamlit dev UI container.
HELP
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
  require_command curl
  require_command docker
  require_command git
  require_command uv
  require_command nvidia-smi
  docker compose version >/dev/null
  docker info >/dev/null
  validate_nvidia_runtime
}

is_wsl_environment() {
  if grep -qiE '(microsoft|wsl)' /proc/sys/kernel/osrelease 2>/dev/null; then
    return 0
  fi
  grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null
}

docker_gpu_smoke_test() {
  docker run --pull missing --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi >/dev/null
}

validate_nvidia_runtime() {
  if ! docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
    print_error "Docker does not report an NVIDIA runtime. Install/configure the NVIDIA Container Toolkit first."
    print_error "Expected validation command: docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi"
    exit 1
  fi

  local missing_persistenced_socket=false
  if [[ ! -S /run/nvidia-persistenced/socket ]]; then
    missing_persistenced_socket=true
    # Docker Desktop on Windows exposes GPUs to WSL2 through GPU-PV. In that setup the Linux distro
    # may not have the native nvidia-persistenced socket even though Docker GPU containers work.
    if is_wsl_environment; then
      print_info "WSL2 detected; skipping the native nvidia-persistenced socket requirement and validating GPU containers directly."
    else
      # On a native Ubuntu host this socket is still a useful troubleshooting signal, but the real
      # source of truth is whether Docker can start a GPU-enabled container successfully.
      print_info "nvidia-persistenced socket is missing; falling back to a real Docker GPU smoke test."
    fi
  fi

  print_info "Validating Docker GPU access with a one-shot nvidia-smi container."
  if docker_gpu_smoke_test; then
    print_info "Docker GPU access is working."
    return 0
  fi

  if [[ "$missing_persistenced_socket" == "true" ]] && ! is_wsl_environment; then
    print_error "Docker GPU validation failed and /run/nvidia-persistenced/socket is missing."
    if command -v systemctl >/dev/null 2>&1; then
      if systemctl list-unit-files | grep -q '^nvidia-persistenced\.service'; then
        print_error "Start it with: sudo systemctl enable --now nvidia-persistenced"
      else
        print_error "Install the NVIDIA driver component that provides nvidia-persistenced, then enable the service."
      fi
    fi
  else
    print_error "Docker GPU validation failed even though the NVIDIA runtime is present."
  fi
  print_error "Validate manually with: docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi"
  exit 1
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

letta_nltk_data_ready() {
  NLTK_DOWNLOAD_DIR="$LETTA_NLTK_DATA_DIR" uv run --with nltk python - <<'PY'
from __future__ import annotations

import os
import sys

import nltk

nltk.data.path = [os.environ['NLTK_DOWNLOAD_DIR']]
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    sys.exit(1)
sys.exit(0)
PY
}

ensure_letta_nltk_data() {
  mkdir -p "$LETTA_NLTK_DATA_DIR"
  if letta_nltk_data_ready; then
    print_info "Letta NLTK data already present at $LETTA_NLTK_DATA_DIR."
    return 0
  fi

  print_info "Downloading Letta NLTK data (punkt_tab) to $LETTA_NLTK_DATA_DIR."
  NLTK_DOWNLOAD_DIR="$LETTA_NLTK_DATA_DIR" uv run --with nltk python - <<'PY'
from __future__ import annotations

import os

import nltk

nltk.download('punkt_tab', download_dir=os.environ['NLTK_DOWNLOAD_DIR'], quiet=True, raise_on_error=True)
PY

  if ! letta_nltk_data_ready; then
    print_error "Letta NLTK data is still not loadable from $LETTA_NLTK_DATA_DIR after download."
    exit 1
  fi
}

wait_for_postgres() {
  print_info "Waiting for Postgres readiness."
  wait_for_command \
    "Postgres" \
    30 \
    docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_BOOTSTRAP_DB"
}

wait_for_ollama() {
  print_info "Waiting for Ollama readiness."
  wait_for_command \
    "Ollama" \
    30 \
    docker exec "$OLLAMA_CONTAINER" ollama list
}

wait_for_letta() {
  local attempts=$(( (LETTA_READY_TIMEOUT_SECONDS + 1) / 2 ))
  local progress_every_attempts=$(( (LETTA_READY_PROGRESS_INTERVAL_SECONDS + 1) / 2 ))
  if (( attempts < 1 )); then
    attempts=1
  fi
  if (( progress_every_attempts < 1 )); then
    progress_every_attempts=1
  fi

  print_info "Waiting for Letta readiness at $LETTA_BASE_URL/v1/health/ (timeout ${LETTA_READY_TIMEOUT_SECONDS}s, progress every ${LETTA_READY_PROGRESS_INTERVAL_SECONDS}s)."
  if wait_for_http "Letta" "$LETTA_BASE_URL/v1/health/" "200" "$attempts" false "$progress_every_attempts"; then
    return 0
  fi

  print_error "Letta did not become ready within ${LETTA_READY_TIMEOUT_SECONDS}s. The bootstrap stops in the infra phase here, so the API and dev UI were not started. If Letta becomes healthy later, rerun the bootstrap or start the later services with docker compose. Recent Letta logs:"
  docker logs --tail 120 "$LETTA_CONTAINER" >&2 || true
  exit 1
}

wait_for_model_gateway() {
  print_info "Waiting for model gateway readiness."
  wait_for_http "memllm-model-gateway" "$MEMLLM_MODEL_GATEWAY_BASE_URL/health" "200" 60
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
  # Rebuild the alias on every bootstrap instead of only when it is missing.
  # Imported GGUF aliases otherwise keep Ollama's default `{{ .Prompt }}` template,
  # which removes chat/tool support and causes Letta's tool-enabled requests to fail.
  print_info "Rebuilding Ollama alias $OLLAMA_MODEL_ALIAS from the checked-in Modelfile."
  docker exec "$OLLAMA_CONTAINER" ollama create \
    "$OLLAMA_MODEL_ALIAS" \
    -f "/workspace/ollama/$(basename "$OLLAMA_MODELFILE")"
}

preload_chat_model() {
  print_info "Preloading $OLLAMA_MODEL_ALIAS and asking Ollama to keep it resident."
  OLLAMA_BASE_URL="$OLLAMA_BASE_URL" \
  OLLAMA_MODEL="$OLLAMA_MODEL_ALIAS:latest" \
  OLLAMA_PRELOAD_ATTEMPTS="$OLLAMA_PRELOAD_ATTEMPTS" \
  OLLAMA_PRELOAD_DELAY_SECONDS="$OLLAMA_PRELOAD_DELAY_SECONDS" \
  uv run --with httpx python - <<'PY'
from __future__ import annotations

import json
import os
import sys
import time

import httpx

base_url = os.environ['OLLAMA_BASE_URL'].rstrip('/')
model = os.environ['OLLAMA_MODEL']
attempts = int(os.environ['OLLAMA_PRELOAD_ATTEMPTS'])
delay_seconds = float(os.environ['OLLAMA_PRELOAD_DELAY_SECONDS'])
payload = {
    'model': model,
    'stream': False,
    'keep_alive': -1,
}

last_error: Exception | None = None
for attempt in range(1, attempts + 1):
    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f'{base_url}/api/generate', json=payload)
            response.raise_for_status()
        body = response.json()
        print(
            json.dumps(
                {
                    'attempt': attempt,
                    'load_duration': body.get('load_duration'),
                    'done_reason': body.get('done_reason'),
                },
                ensure_ascii=False,
            )
        )
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        print(
            f'preload attempt {attempt}/{attempts} failed for {model}: {exc}',
            file=sys.stderr,
        )
        if attempt < attempts:
            time.sleep(delay_seconds)

print(
    f'failed to preload {model} after {attempts} attempts: {last_error}',
    file=sys.stderr,
)
sys.exit(1)
PY
}

start_infra() {
  print_info "Starting Docker services for Postgres/pgvector and Ollama first."
  compose_cmd up -d postgres ollama
  wait_for_postgres
  wait_for_ollama
  ensure_ollama_model "$OLLAMA_EMBED_MODEL"
  ensure_custom_ollama_alias
  if ! preload_chat_model; then
    print_error "Failed to preload $OLLAMA_MODEL_ALIAS after ${OLLAMA_PRELOAD_ATTEMPTS} attempts. Continuing without a pinned warm model; first local reply may be slow or fail until Ollama settles. Recent Ollama logs:"
    docker logs --tail 120 "$OLLAMA_CONTAINER" >&2 || true
  fi

  # Start Letta only after the local Ollama models and GGUF alias are ready. Letta syncs
  # provider handles at startup, so starting it earlier means native ollama/<model> handles
  # never appear even though Ollama itself is healthy.
  print_info "Starting Letta and the model gateway after Ollama models are ready."
  compose_cmd up -d --build --force-recreate letta model_gateway
  wait_for_letta
  wait_for_model_gateway
}

start_api() {
  print_info "Starting the API container."
  # Keep API startup isolated from infra services. Recreating Letta here causes a race where
  # the API seeds characters while Letta is briefly restarting, which turns into a startup 500.
  compose_cmd up -d --build --no-deps api
  wait_for_http "memllm-api" "$MEMLLM_API_BASE_URL/health" "200" 60
}

start_dev_ui() {
  print_info "Starting the dev UI container."
  # The dev UI should not restart the API/infra layers during a normal full bootstrap.
  compose_cmd up -d --build --no-deps dev_ui
  wait_for_http "memllm-dev-ui" "$MEMLLM_DEV_UI_BASE_URL" "200,302" 60
}

print_summary() {
  print_info "Bootstrap complete."
  print_info "Docker stack: Postgres on 127.0.0.1:${POSTGRES_PORT}, Ollama on $OLLAMA_BASE_URL, Letta on $LETTA_BASE_URL, model gateway on $MEMLLM_MODEL_GATEWAY_BASE_URL"
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
ensure_letta_nltk_data
start_infra

if [[ "$MODE" == "api" || "$MODE" == "full" ]]; then
  start_api
fi

if [[ "$MODE" == "full" ]]; then
  start_dev_ui
fi

print_summary
