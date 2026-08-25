#!/usr/bin/env bash
# Install the pinned Agency Agents lazy router plus the AI Lab capability router.
set -euo pipefail

cd "$(dirname "$0")/.."

AGENCY_AGENTS_SHA="${AGENCY_AGENTS_SHA:-ebe9c99acb5c96f9468de368d8bead775387d1a7}"
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
HERMES_PYTHON="${HERMES_PYTHON:-/opt/hermes/venv/bin/python3}"

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

config="$HERMES_HOME/config.yaml"
backup="$config.bak.ai-lab-agency.$(date +%Y%m%d%H%M%S)"
[[ -f "$config" ]] && cp "$config" "$backup"
"$HERMES_PYTHON" - "$config" "ai-lab-capabilities" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
plugin = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

in_plugins = False
in_enabled = False
for line in lines:
    if line.startswith("plugins:"):
        in_plugins, in_enabled = True, False
        continue
    if in_plugins and line and not line.startswith((" ", "\t")):
        in_plugins, in_enabled = False, False
    if in_plugins and line.strip() == "enabled:":
        in_enabled = True
        continue
    if in_enabled and line.strip().startswith("-"):
        if line.strip()[1:].strip().strip("\"'") == plugin:
            raise SystemExit(0)

if not lines:
    lines = ["plugins:", "  enabled:", f"  - {plugin}"]
elif not any(line.startswith("plugins:") for line in lines):
    lines.extend(["", "plugins:", "  enabled:", f"  - {plugin}"])
else:
    output = []
    in_plugins = False
    inserted = False
    saw_enabled = False
    for line in lines:
        if line.startswith("plugins:"):
            in_plugins = True
            output.append(line)
            continue
        if in_plugins and line and not line.startswith((" ", "\t")):
            if not saw_enabled and not inserted:
                output.extend(["  enabled:", f"  - {plugin}"])
                inserted = True
            in_plugins = False
        if in_plugins and line.strip().startswith("enabled:") and "[]" in line:
            saw_enabled = True
            output.extend(["  enabled:", f"  - {plugin}"])
            inserted = True
            continue
        if in_plugins and line.strip() == "enabled:":
            saw_enabled = True
            output.extend([line, f"  - {plugin}"])
            inserted = True
            continue
        output.append(line)
    if in_plugins and not saw_enabled and not inserted:
        output.extend(["  enabled:", f"  - {plugin}"])
    lines = output
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "==> Agency/Hermes integration installed"
echo "    agency-agents-router: $HERMES_HOME/plugins/agency-agents-router"
echo "    ai-lab-capabilities:  $plugin_dest"
