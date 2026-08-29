#!/bin/sh
set -eu

# The image keeps its development certificate as a safe fallback. Production
# mounts /etc/letsencrypt read-only; when the IP certificate exists, switch all
# TLS listeners to it before nginx validates and starts the configuration.
certificate_dir="${TLS_CERT_DIR:-/etc/letsencrypt/live/120.24.248.58}"
fullchain="${certificate_dir}/fullchain.pem"
private_key="${certificate_dir}/privkey.pem"
nginx_config="${NGINX_CONFIG:-/etc/nginx/conf.d/default.conf}"

if [ -r "${fullchain}" ] && [ -r "${private_key}" ]; then
    sed -i.bak \
        -e "s#/etc/nginx/ssl/ailab.crt#${fullchain}#g" \
        -e "s#/etc/nginx/ssl/ailab.key#${private_key}#g" \
        "${nginx_config}"
    rm -f "${nginx_config}.bak"
    echo "40-select-tls-cert: using mounted certificate from ${certificate_dir}"
else
    echo "40-select-tls-cert: mounted certificate unavailable; using bundled development certificate"
fi
