#!/usr/bin/env bash
set -euo pipefail

MEM_AVAILABLE_WARN_KB="${AI_LAB_MEM_AVAILABLE_WARN_KB:-512000}"
LOAD1_WARN="${AI_LAB_LOAD1_WARN:-2.0}"
SWAP_USED_WARN_KB="${AI_LAB_SWAP_USED_WARN_KB:-1048576}"
DOCKER_PING_WARN_SECONDS="${AI_LAB_DOCKER_PING_WARN_SECONDS:-2.0}"
STATE_DIR="${AI_LAB_RESOURCE_GUARD_STATE_DIR:-/var/lib/ai-lab-resource-guard}"
STATE_FILE="$STATE_DIR/state"

for value in "$MEM_AVAILABLE_WARN_KB" "$SWAP_USED_WARN_KB"; do
  [[ "$value" =~ ^[0-9]+$ ]] || { echo "invalid integer threshold" >&2; exit 64; }
done
for value in "$LOAD1_WARN" "$DOCKER_PING_WARN_SECONDS"; do
  [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "invalid decimal threshold" >&2; exit 64; }
done

mem_available_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
swap_total_kb=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
swap_free_kb=$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)
swap_used_kb=$((swap_total_kb - swap_free_kb))
load1=$(cut -d' ' -f1 /proc/loadavg)
docker_probe=$(curl --silent --show-error --max-time 4 --unix-socket /var/run/docker.sock \
  --output /dev/null --write-out '%{http_code} %{time_total}' http://localhost/_ping 2>/dev/null || printf '000 99')
docker_code=${docker_probe%% *}
docker_seconds=${docker_probe#* }

warnings=()
awk -v a="$mem_available_kb" -v b="$MEM_AVAILABLE_WARN_KB" 'BEGIN {exit !(a < b)}' && warnings+=("mem_available_kb=${mem_available_kb}<${MEM_AVAILABLE_WARN_KB}") || true
awk -v a="$load1" -v b="$LOAD1_WARN" 'BEGIN {exit !(a > b)}' && warnings+=("load1=${load1}>${LOAD1_WARN}") || true
awk -v a="$swap_used_kb" -v b="$SWAP_USED_WARN_KB" 'BEGIN {exit !(a > b)}' && warnings+=("swap_used_kb=${swap_used_kb}>${SWAP_USED_WARN_KB}") || true
if [[ "$docker_code" != "200" ]] || awk -v a="$docker_seconds" -v b="$DOCKER_PING_WARN_SECONDS" 'BEGIN {exit !(a > b)}'; then
  warnings+=("docker_ping=${docker_code}/${docker_seconds}s")
fi
for unit in hermes-bridge.service hermes-chat-worker.service docker.service; do
  systemctl is-active --quiet "$unit" || warnings+=("unit_inactive=${unit}")
done

install -d -m 0755 "$STATE_DIR"
new_state=$(IFS=,; printf '%s' "${warnings[*]:-ok}")
old_state=$(cat "$STATE_FILE" 2>/dev/null || true)
printf '%s\n' "$new_state" > "$STATE_FILE.tmp"
chmod 0644 "$STATE_FILE.tmp"
mv -f "$STATE_FILE.tmp" "$STATE_FILE"

if [[ "$new_state" != "$old_state" ]]; then
  if [[ "$new_state" == "ok" ]]; then
    logger -p daemon.notice -t ai-lab-resource-guard "recovered mem_available_kb=${mem_available_kb} load1=${load1} swap_used_kb=${swap_used_kb} docker_ping=${docker_seconds}s"
  else
    logger -p daemon.warning -t ai-lab-resource-guard "$new_state"
  fi
fi
printf 'status=%s mem_available_kb=%s load1=%s swap_used_kb=%s docker_ping_seconds=%s\n' \
  "$new_state" "$mem_available_kb" "$load1" "$swap_used_kb" "$docker_seconds"
