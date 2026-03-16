#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/_dev_stack_common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/clean_dev_stack.sh --yes [--preserve-memory] [--include-ollama-cache] [--include-gguf]

Destructive cleanup for the phase-1 Docker dev stack.

What it removes by default:
- Docker containers and networks for the memLLM stack
- Persisted Postgres data, including Letta memory and app metadata
- The local .runtime/ directory if present

What it keeps by default:
- Ollama's Docker volume, including pulled embedding/chat models and aliases
- infra/ollama/models/Qwen3.5-9B-Q4_K_M.gguf
- infra/letta/nltk_data/
- infra/env/.env

Options:
  --yes                   Required confirmation flag.
  --preserve-memory       Keep the Postgres volume, so Letta memory and app metadata survive.
  --include-ollama-cache  Also remove Ollama's Docker volume, which forces model re-downloads.
  --include-gguf          Also remove the downloaded GGUF from infra/ollama/models/.
EOF
}

CONFIRMED=false
PRESERVE_MEMORY=false
REMOVE_OLLAMA_CACHE=false
REMOVE_GGUF=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      CONFIRMED=true
      shift
      ;;
    --preserve-memory)
      PRESERVE_MEMORY=true
      shift
      ;;
    --include-ollama-cache)
      REMOVE_OLLAMA_CACHE=true
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

print_info "Stopping and removing Docker services and networks."
compose_cmd down --remove-orphans

# Postgres stores Letta memory and app metadata, so wiping this volume is the real reset path.
# `--preserve-memory` exists because sometimes we want a container/network cleanup without losing
# the current Letta state or app-side session metadata.
if [[ "$PRESERVE_MEMORY" != "true" ]] && docker volume inspect "$POSTGRES_VOLUME" >/dev/null 2>&1; then
  print_info "Removing Docker volume $POSTGRES_VOLUME"
  docker volume rm "$POSTGRES_VOLUME" >/dev/null
fi

# Keep Ollama's volume by default so pulled embedding models and local aliases survive resets.
if [[ "$REMOVE_OLLAMA_CACHE" == "true" ]] && docker volume inspect "$OLLAMA_VOLUME" >/dev/null 2>&1; then
  print_info "Removing Docker volume $OLLAMA_VOLUME"
  docker volume rm "$OLLAMA_VOLUME" >/dev/null
fi

if [[ -d "$ROOT_DIR/.runtime" ]]; then
  print_info "Removing $ROOT_DIR/.runtime"
  rm -rf "$ROOT_DIR/.runtime"
fi

if [[ "$REMOVE_GGUF" == "true" && -f "$MODEL_PATH" ]]; then
  print_info "Removing GGUF model file at $MODEL_PATH"
  rm -f "$MODEL_PATH"
fi

print_info "Cleanup complete. Preserved assets:"
if docker volume inspect "$POSTGRES_VOLUME" >/dev/null 2>&1; then
  printf -- "- Postgres memory volume: %s
" "$POSTGRES_VOLUME"
else
  printf -- "- Postgres memory volume: not present
"
fi
if docker volume inspect "$OLLAMA_VOLUME" >/dev/null 2>&1; then
  printf -- "- Ollama cache volume: %s
" "$OLLAMA_VOLUME"
else
  printf -- "- Ollama cache volume: not present
"
fi
if [[ -f "$MODEL_PATH" ]]; then
  printf -- "- GGUF: %s
" "$MODEL_PATH"
else
  printf -- "- GGUF: not present
"
fi
if [[ -d "$LETTA_NLTK_DATA_DIR" ]]; then
  printf -- "- Letta NLTK data: %s
" "$LETTA_NLTK_DATA_DIR"
else
  printf -- "- Letta NLTK data: not present
"
fi
printf -- "- Env file: %s
" "$ENV_FILE"
