#!/bin/bash

set -euo pipefail

if [ "$#" -ne 5 ]; then
  echo "usage: $0 <ssh-host> <ssh-user> <identity-file> <known-hosts-file> <https-probe-url>" >&2
  exit 64
fi

ssh_host="$1"
ssh_user="$2"
identity_file="$3"
known_hosts_file="$4"
probe_url="$5"

case "$ssh_host" in *[!A-Za-z0-9.-]*|.*|*.) echo "ERROR: invalid SSH host" >&2; exit 64 ;; esac
case "$ssh_user" in ''|*[!A-Za-z0-9._-]*) echo "ERROR: invalid SSH user" >&2; exit 64 ;; esac
case "$probe_url" in https://*) ;; *) echo "ERROR: probe URL must use HTTPS" >&2; exit 64 ;; esac
case "$probe_url" in *'@'*|*'$'*|*'`'*|*' '*) echo "ERROR: unsafe probe URL" >&2; exit 64 ;; esac

file_metadata() {
  if stat -f '%Lp:%u' "$1" >/dev/null 2>&1; then
    stat -f '%Lp:%u' "$1"
  else
    stat -c '%a:%u' "$1"
  fi
}

require_private_file() {
  local path="$1" label="$2" metadata mode owner
  if [ -L "$path" ] || [ ! -f "$path" ]; then
    echo "ERROR: $label must be a regular non-symlink file" >&2
    exit 78
  fi
  metadata="$(file_metadata "$path")" || exit 78
  mode="${metadata%%:*}"
  owner="${metadata#*:}"
  if [ "$owner" != "$(id -u)" ] || { [ "$mode" != 400 ] && [ "$mode" != 600 ]; }; then
    echo "ERROR: $label must be owned by the launch user with mode 0400 or 0600" >&2
    exit 78
  fi
}

require_known_hosts() {
  local metadata mode owner
  if [ -L "$known_hosts_file" ] || [ ! -f "$known_hosts_file" ]; then
    echo "ERROR: known_hosts must be a regular non-symlink file" >&2
    exit 78
  fi
  metadata="$(file_metadata "$known_hosts_file")" || exit 78
  mode="${metadata%%:*}"
  owner="${metadata#*:}"
  if [ "$owner" != "$(id -u)" ] || [ $((8#$mode & 8#022)) -ne 0 ]; then
    echo "ERROR: known_hosts must be owned by the launch user and not group/world writable" >&2
    exit 78
  fi
}

require_private_file "$identity_file" "SSH identity"
require_known_hosts

if ! /usr/bin/nc -z -w 3 127.0.0.1 7897 >/dev/null 2>&1; then
  echo "ERROR: Clash Verge is not listening on 127.0.0.1:7897" >&2
  exit 69
fi
if ! /usr/bin/curl --fail --silent --show-error --output /dev/null \
  --connect-timeout 5 --max-time 20 --proxy http://127.0.0.1:7897 "$probe_url"; then
  echo "ERROR: HTTPS probe through Clash Verge failed" >&2
  exit 69
fi

exec /usr/bin/ssh \
  -N -T \
  -i "$identity_file" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o UserKnownHostsFile="$known_hosts_file" \
  -o StrictHostKeyChecking=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=3 \
  -o RequestTTY=no \
  -o ForwardAgent=no \
  -o ForwardX11=no \
  -o PermitLocalCommand=no \
  -R 127.0.0.1:17897:127.0.0.1:7897 \
  -- "$ssh_user@$ssh_host"
