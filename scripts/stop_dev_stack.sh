#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/_dev_stack_common.sh"

load_env_file

print_info "Stopping Docker services."
compose_cmd down
print_info "Docker services stopped. Named volumes were left intact."
