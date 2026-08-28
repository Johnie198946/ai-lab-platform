#!/usr/bin/env bash
# Install the pinned Agency Agents lazy router plus the AI Lab capability router.
set -euo pipefail

cd "$(dirname "$0")/.."

AGENCY_AGENTS_SHA="${AGENCY_AGENTS_SHA:-3c9588880b7cafaec325a104899fd8bbe27e7d72}"
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
HERMES_PYTHON="${HERMES_PYTHON:-/opt/hermes/venv/bin/python3}"
config="$HERMES_HOME/config.yaml"
original_config=""

if [[ ! "$AGENCY_AGENTS_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: AGENCY_AGENTS_SHA must be a full 40-character commit SHA" >&2
  exit 2
fi
if [[ ! -x "$HERMES_PYTHON" ]]; then
  echo "ERROR: Hermes Python not found at $HERMES_PYTHON" >&2
  exit 2
fi

tmp_dir="$(mktemp -d /tmp/agency-agents-install.XXXXXX)"
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT

# Preserve the pre-install plugin list. The upstream installer supports simple
# YAML lists, but Hermes commonly writes this field in flow style; restoring
# from the structured pre-install document avoids collapsing existing entries.
if [[ -f "$config" ]]; then
  original_config="$tmp_dir/config.before-agency.yaml"
  cp "$config" "$original_config"
fi

echo "==> Fetch Agency Agents @ $AGENCY_AGENTS_SHA"
curl -fsSL --retry 3 \
  "https://codeload.github.com/msitarzewski/agency-agents/tar.gz/${AGENCY_AGENTS_SHA}" \
  -o "$tmp_dir/source.tgz"
mkdir -p "$tmp_dir/source"
tar xzf "$tmp_dir/source.tgz" --strip-components=1 -C "$tmp_dir/source"

echo "==> Generate and validate Hermes lazy router"
(cd "$tmp_dir/source" && bash scripts/convert.sh --tool hermes)
(cd "$tmp_dir/source" && "$HERMES_PYTHON" scripts/check-hermes-plugin.py)
HOME="$(dirname "$HERMES_HOME")" HERMES_HOME="$HERMES_HOME" \
  bash "$tmp_dir/source/scripts/install.sh" --tool hermes

echo "==> Install AI Lab capability router"
plugin_root="$HERMES_HOME/plugins"
plugin_dest="$plugin_root/ai-lab-capabilities"
if [[ "$(basename "$plugin_dest")" != "ai-lab-capabilities" ]]; then
  echo "ERROR: unsafe plugin destination: $plugin_dest" >&2
  exit 2
fi
mkdir -p "$plugin_root"
rm -rf "$plugin_dest"
cp -R agency/hermes-plugins/ai-lab-capabilities "$plugin_dest"

backup="$config.bak.ai-lab-agency.$(date +%Y%m%d%H%M%S)"
[[ -f "$config" ]] && cp "$config" "$backup"
"$HERMES_PYTHON" - "$config" "$original_config" <<'PY'
from pathlib import Path
import os
import sys
import tempfile

import yaml

path = Path(sys.argv[1])
original = Path(sys.argv[2]) if sys.argv[2] else None
source = original if original and original.exists() else path
document = yaml.safe_load(source.read_text(encoding="utf-8")) if source.exists() else {}
if not isinstance(document, dict):
    raise SystemExit("ERROR: Hermes config root must be a mapping")
plugins = document.setdefault("plugins", {})
if not isinstance(plugins, dict):
    raise SystemExit("ERROR: Hermes plugins config must be a mapping")
enabled = plugins.get("enabled") or []
if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
    raise SystemExit("ERROR: Hermes plugins.enabled must be a string list")
for plugin in ("agency-agents-router", "ai-lab-capabilities"):
    if plugin not in enabled:
        enabled.append(plugin)
plugins["enabled"] = enabled

path.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(prefix="config.yaml.", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

echo "==> Agency/Hermes integration installed"
echo "    agency-agents-router: $HERMES_HOME/plugins/agency-agents-router"
echo "    ai-lab-capabilities:  $plugin_dest"

echo "==> Configure safe AI Lab web extraction"
"$HERMES_PYTHON" scripts/configure_hermes_web_extract.py \
  --hermes-home "$HERMES_HOME" \
  --plugin-source agency/hermes-plugins/ai-lab-capabilities \
  --backup-root "$HERMES_HOME/backups"
