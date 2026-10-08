#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE="${AI_LAB_PUBLICATION_EXEC_LOCK:-/run/lock/ai-lab-publication-exec.lock}"
LOCK_TIMEOUT="${AI_LAB_PUBLICATION_EXEC_LOCK_TIMEOUT_SECONDS:-120}"
PROJECT="${AI_LAB_PUBLICATION_COMPOSE_PROJECT:-ai-lab-platform}"
SERVICE="${AI_LAB_PUBLICATION_COMPOSE_SERVICE:-api}"

if [[ $# -eq 0 ]]; then
  echo "usage: publication_container_exec.sh <container-command> [args...]" >&2
  exit 64
fi
if [[ ! "$LOCK_TIMEOUT" =~ ^[0-9]+$ ]] || (( LOCK_TIMEOUT < 1 || LOCK_TIMEOUT > 600 )); then
  echo "invalid publication execution lock timeout" >&2
  exit 64
fi

install -d -m 0755 "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -w "$LOCK_TIMEOUT" 9; then
  echo "publication execution busy" >&2
  exit 75
fi

mapfile -t containers < <(
  docker ps \
    --filter "label=com.docker.compose.project=${PROJECT}" \
    --filter "label=com.docker.compose.service=${SERVICE}" \
    --filter status=running \
    --format '{{.ID}}'
)
if (( ${#containers[@]} != 1 )); then
  echo "expected exactly one running ${PROJECT}/${SERVICE} container; found ${#containers[@]}" >&2
  exit 69
fi

exec timeout --foreground 180 docker exec -i "${containers[0]}" "$@"
