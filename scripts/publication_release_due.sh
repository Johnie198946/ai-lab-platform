#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/docker compose -p ai-lab-platform -f /opt/ai-lab-platform/docker-compose.yml exec -T api \
  python /app/scripts/publication_operator.py --root /app/data/runtime/publications release-due
