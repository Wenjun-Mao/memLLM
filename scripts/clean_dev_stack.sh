#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/_dev_stack_common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/clean_dev_stack.sh --yes [--include-gguf]

Destructive cleanup for the phase-1 Docker dev stack.

What it removes by default:
- Docker containers, networks, and named volumes for the memLLM stack
- Persisted Postgres data, including Letta memory and app metadata
- Persisted Ollama model cache and aliases stored in the Docker volume
- The local .runtime/ directory if present

What it keeps by default:
- infra/ollama/models/Qwen3.5-9B-Q4_K_M.gguf
- infra/letta/nltk_data/
- infra/env/.env

Options:
  --yes           Required confirmation flag.
  --include-gguf  Also remove the downloaded GGUF from infra/ollama/models/.
EOF
}

CONFIRMED=false
REMOVE_GGUF=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      CONFIRMED=true
      shift
      ;;
    --include-gguf)
      REMOVE_GGUF=true
      shift
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

if [[ "$CONFIRMED" != "true" ]]; then
  print_error "Refusing to run without --yes. This script destroys persisted dev data."
  usage
  exit 1
fi

load_env_file
validate_env_constraints

print_info "Stopping and removing Docker services, networks, and named volumes."
compose_cmd down --volumes --remove-orphans

if [[ -d "$ROOT_DIR/.runtime" ]]; then
  print_info "Removing $ROOT_DIR/.runtime"
  rm -rf "$ROOT_DIR/.runtime"
fi

if [[ "$REMOVE_GGUF" == "true" && -f "$MODEL_PATH" ]]; then
  print_info "Removing GGUF model file at $MODEL_PATH"
  rm -f "$MODEL_PATH"
fi

print_info "Cleanup complete. Preserved assets:"
if [[ -f "$MODEL_PATH" ]]; then
  printf -- "- GGUF: %s\n" "$MODEL_PATH"
else
  printf -- "- GGUF: not present\n"
fi
if [[ -d "$LETTA_NLTK_DATA_DIR" ]]; then
  printf -- "- Letta NLTK data: %s\n" "$LETTA_NLTK_DATA_DIR"
else
  printf -- "- Letta NLTK data: not present\n"
fi
printf -- "- Env file: %s\n" "$ENV_FILE"
