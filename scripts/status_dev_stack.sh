#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/_dev_stack_common.sh"

report_process() {
  local label="$1"
  local pid_file="$2"
  local log_file="$3"

  cleanup_stale_pid "$pid_file"
  if is_pid_running "$pid_file"; then
    printf -- "- %s: running (pid %s, log %s)\n" "$label" "$(<"$pid_file")" "$log_file"
  else
    printf -- "- %s: not running\n" "$label"
  fi
}

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
ensure_runtime_dir

echo "Docker services"
compose_cmd ps

echo
echo "Host processes"
report_process "memllm-api" "$API_PID_FILE" "$API_LOG_FILE"
report_process "memllm-dev-ui" "$DEV_UI_PID_FILE" "$DEV_UI_LOG_FILE"

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
else
  printf -- "- Ollama alias: unavailable because the Ollama container is not responding\n"
fi

echo
echo "HTTP endpoints"
report_endpoint "Letta" "$LETTA_BASE_URL/v1/agents" "200,401,403"
report_endpoint "memllm-api" "$MEMLLM_API_BASE_URL/health" "200"
report_endpoint "memllm-dev-ui" "$MEMLLM_DEV_UI_BASE_URL" "200,302"
