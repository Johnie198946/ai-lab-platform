#!/usr/bin/env bash
set -euo pipefail

IMAGE_COUNT_WARN="${AI_LAB_IMAGE_COUNT_WARN:-200}"
STATE_DIR="${AI_LAB_RESOURCE_GUARD_STATE_DIR:-/var/lib/ai-lab-resource-guard}"
STATE_FILE="$STATE_DIR/image-state"

[[ "$IMAGE_COUNT_WARN" =~ ^[0-9]+$ ]] || { echo "invalid image threshold" >&2; exit 64; }
install -d -m 0755 "$STATE_DIR"
image_count=$(docker image ls -q | sort -u | wc -l | tr -d ' ')
if (( image_count > IMAGE_COUNT_WARN )); then
  new_state="docker_images=${image_count}>${IMAGE_COUNT_WARN}"
else
  new_state="ok"
fi
old_state=$(cat "$STATE_FILE" 2>/dev/null || true)
printf '%s\n' "$new_state" > "$STATE_FILE.tmp"
chmod 0644 "$STATE_FILE.tmp"
mv -f "$STATE_FILE.tmp" "$STATE_FILE"
if [[ "$new_state" != "$old_state" ]]; then
  if [[ "$new_state" == "ok" ]]; then
    logger -p daemon.notice -t ai-lab-image-inventory-guard "recovered docker_images=${image_count}"
  else
    logger -p daemon.warning -t ai-lab-image-inventory-guard "$new_state"
  fi
fi
printf 'status=%s docker_images=%s\n' "$new_state" "$image_count"
