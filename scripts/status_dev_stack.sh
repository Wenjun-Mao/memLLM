#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/_dev_stack_common.sh"

report_endpoint() {
  local label="$1"
  local url="$2"
  local ok_codes="$3"

  if http_ok "$url" "$ok_codes"; then
    printf -- "- %s: reachable at %s\n" "$label" "$url"
  else
    printf -- "- %s: not reachable at %s\n" "$label" "$url"
  fi
}

load_env_file
validate_env_constraints

echo "Docker services"
compose_cmd ps

echo
echo "Model assets"
if [[ -f "$MODEL_PATH" ]]; then
  printf -- "- GGUF: present at %s\n" "$MODEL_PATH"
else
  printf -- "- GGUF: missing (%s)\n" "$MODEL_PATH"
fi

if docker exec "$OLLAMA_CONTAINER" ollama list >/dev/null 2>&1; then
  if docker exec "$OLLAMA_CONTAINER" ollama list | grep -E "^${OLLAMA_MODEL_ALIAS}:latest[[:space:]]" >/dev/null; then
    printf -- "- Ollama alias: %s is available\n" "$OLLAMA_MODEL_ALIAS"
  else
    printf -- "- Ollama alias: %s is missing\n" "$OLLAMA_MODEL_ALIAS"
  fi
  if docker exec "$OLLAMA_CONTAINER" ollama list | awk '{print $1}' | grep -Fx "$OLLAMA_EMBED_MODEL" >/dev/null; then
    printf -- "- Embedding model: %s is available\n" "$OLLAMA_EMBED_MODEL"
  else
    printf -- "- Embedding model: %s is missing\n" "$OLLAMA_EMBED_MODEL"
  fi
else
  printf -- "- Ollama model state: unavailable because the Ollama container is not responding\n"
fi

echo
echo "Loaded Ollama models"
if ! docker exec "$OLLAMA_CONTAINER" ollama ps >/dev/null 2>&1; then
  printf -- "- Ollama is not responding\n"
else
  docker exec "$OLLAMA_CONTAINER" ollama ps
fi

echo
echo "HTTP endpoints"
report_endpoint "Letta" "$LETTA_BASE_URL/v1/health/" "200"
report_endpoint "memllm-model-gateway" "$MEMLLM_MODEL_GATEWAY_BASE_URL/health" "200"
report_endpoint "memllm-api" "$MEMLLM_API_BASE_URL/health" "200"
report_endpoint "memllm-dev-ui" "$MEMLLM_DEV_UI_BASE_URL" "200,302"
