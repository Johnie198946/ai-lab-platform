#!/usr/bin/env bash
# Production deployments use the serialized, hash-attested exact-SHA updater.
set -euo pipefail

if [ "$#" -ne 1 ] || [[ ! "$1" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERROR: usage: bash scripts/deploy.sh <40-character commit SHA>" >&2
  exit 2
fi

exec bash "$(dirname "$0")/update.sh" "$1"
