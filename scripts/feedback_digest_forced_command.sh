#!/bin/sh
# Root-owned forced command for the dedicated feedback-digest SSH account.
set -eu

command_text=${SSH_ORIGINAL_COMMAND:-}
case "$command_text" in
  "feedback-digest prepare")
    set -- prepare
    ;;
  feedback-digest\ ack\ feedback-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]\ [0-9a-f]*)
    set -- $command_text
    [ "$#" -eq 4 ] || exit 64
    [ "$1" = "feedback-digest" ] || exit 64
    [ "$2" = "ack" ] || exit 64
    digest_id=$3
    payload_hash=$4
    echo "$digest_id" | grep -Eq '^feedback-[0-9]{4}-[0-9]{2}-[0-9]{2}$' || exit 64
    echo "$payload_hash" | grep -Eq '^[0-9a-f]{64}$' || exit 64
    set -- ack "$digest_id" "$payload_hash"
    ;;
  *)
    echo "feedback digest command denied" >&2
    exit 64
    ;;
esac

cd /opt/ai-lab-platform
exec /usr/bin/docker compose exec -T api \
  python -m backend.services.feedback_cli "$@"
