#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE_PROJECT="${AI_LAB_COMPOSE_PROJECT:-ai-lab-platform}"
CERTBOT=/opt/certbot-venv/bin/certbot
CERTBOT_VERSION=5.8.0

verify_certbot_runtime() {
  [ -x "$CERTBOT" ] || {
    echo "ERROR: required Certbot executable is missing: $CERTBOT" >&2
    return 1
  }
  [ "$($CERTBOT --version 2>&1)" = "certbot $CERTBOT_VERSION" ] || {
    echo "ERROR: Certbot must be exactly $CERTBOT_VERSION" >&2
    return 1
  }
}

resolve_tls_sources() {
  docker compose -p "$COMPOSE_PROJECT" config --format json | python3 -c '
import json, sys
volumes = json.load(sys.stdin)["services"]["frontend"].get("volumes", [])
by_target = {item.get("target"): item.get("source") for item in volumes if item.get("type") == "bind"}
for target in ("/etc/nginx/ssl/ailab.crt", "/etc/nginx/ssl/ailab.key"):
    source = by_target.get(target)
    if not source:
        raise SystemExit(f"missing frontend TLS bind: {target}")
    print(source)
'
}

prepare_frontend_tls_access() {
  local sources cert key cert_real key_real path
  mapfile -t sources < <(resolve_tls_sources)
  cert="${sources[0]:-}"
  key="${sources[1]:-}"
  cert_real="$(readlink -f "$cert")"
  key_real="$(readlink -f "$key")"
  for path in "$cert" "$key"; do
    [[ "$path" == /etc/letsencrypt/live/*/* ]] || {
      echo "ERROR: frontend TLS source is outside the Let's Encrypt live tree: $path" >&2
      return 1
    }
  done
  TLS_CERT_NAME="$(basename "$(dirname "$cert")")"
  export TLS_CERT_NAME
  for path in "$cert_real" "$key_real"; do
    [[ "$path" == /etc/letsencrypt/archive/*/* ]] && [ -f "$path" ] || {
      echo "ERROR: frontend TLS target is outside the Let's Encrypt archive tree: $path" >&2
      return 1
    }
  done
  command -v setfacl >/dev/null
  command -v setpriv >/dev/null
  setfacl -m u:101:--x /etc/letsencrypt /etc/letsencrypt/live /etc/letsencrypt/archive \
    "$(dirname "$cert")" "$(dirname "$cert_real")"
  setfacl -m d:u:101:r-X "$(dirname "$cert_real")"
  setfacl -m u:101:r-- "$cert_real" "$key_real"
  setpriv --reuid=101 --regid=101 --clear-groups test -r "$key"
  openssl x509 -in "$cert" -noout -checkend 0 >/dev/null
  [ "$(openssl x509 -in "$cert" -pubkey -noout | sha256sum)" = \
    "$(openssl pkey -in "$key" -pubout | sha256sum)" ] || {
    echo "ERROR: frontend TLS certificate and key do not match" >&2
    return 1
  }
}

if [ "${AI_LAB_DEPLOY_LOCK_HELD:-0}" != "1" ]; then
  exec 9>/run/lock/ai-lab-platform-update.lock
  flock -n 9 || { echo "ERROR: deployment or certificate renewal already running" >&2; exit 1; }
fi

prepare_frontend_tls_access
verify_certbot_runtime
[ "${1:-}" = "--preflight-only" ] && exit 0

frontend_stopped=0
restore_frontend() {
  local rc=$? rollback_rc=0
  trap - EXIT
  if [ "$frontend_stopped" -eq 1 ]; then
    docker compose -p "$COMPOSE_PROJECT" up -d --no-deps --no-build --pull never frontend || rollback_rc=1
    docker compose -p "$COMPOSE_PROJECT" exec -T frontend \
      wget --no-check-certificate -q -O /dev/null https://127.0.0.1:9081/ || rollback_rc=1
  fi
  if [ "$rollback_rc" -ne 0 ]; then
    echo "ERROR: frontend recovery after certificate renewal failed" >&2
    exit 1
  fi
  exit "$rc"
}
trap restore_frontend EXIT

docker compose -p "$COMPOSE_PROJECT" stop frontend
frontend_stopped=1
"$CERTBOT" renew --cert-name "$TLS_CERT_NAME" --non-interactive --quiet
prepare_frontend_tls_access
docker compose -p "$COMPOSE_PROJECT" up -d --no-deps --no-build --pull never frontend
docker compose -p "$COMPOSE_PROJECT" exec -T frontend \
  wget --no-check-certificate -q -O /dev/null https://127.0.0.1:9081/
frontend_stopped=0
