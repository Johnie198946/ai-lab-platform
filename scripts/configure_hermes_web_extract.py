#!/usr/bin/env python3
"""Atomically deploy AI Lab's Hermes plugin and select its extract provider."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import tempfile

import yaml


PLUGIN_NAME = "ai-lab-capabilities"
EXTRACT_BACKEND = "ai-lab-native"
SEARCH_BACKEND = "ddgs"


def _document(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Hermes config root must be a mapping: {path}")
    return payload


def _atomic_yaml(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(hermes_home: Path, plugin_source: Path, backup_root: Path) -> dict[str, str]:
    required = {
        "plugin.yaml", "__init__.py", "capability_router.py",
        "native_extract_provider.py", "skill-routing-overrides.yaml",
    }
    missing = sorted(name for name in required if not (plugin_source / name).is_file())
    if missing:
        raise ValueError("Plugin source is incomplete: " + ", ".join(missing))

    config_path = hermes_home / "config.yaml"
    plugin_root = hermes_home / "plugins"
    destination = plugin_root / PLUGIN_NAME
    if destination.name != PLUGIN_NAME:
        raise ValueError(f"Unsafe plugin destination: {destination}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_root / f"hermes-web-extract-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    if config_path.exists():
        shutil.copy2(config_path, backup / "config.yaml")
    if destination.exists():
        shutil.copytree(destination, backup / PLUGIN_NAME)

    plugin_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=PLUGIN_NAME + ".", dir=plugin_root))
    previous = plugin_root / f".{PLUGIN_NAME}.previous-{os.getpid()}"
    try:
        shutil.copytree(
            plugin_source,
            temporary,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        if destination.exists():
            os.replace(destination, previous)
        os.replace(temporary, destination)
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        if not destination.exists() and previous.exists():
            os.replace(previous, destination)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    document = _document(config_path)
    plugins = document.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        raise ValueError("Hermes plugins config must be a mapping")
    enabled = plugins.get("enabled") or []
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise ValueError("Hermes plugins.enabled must be a string list")
    if PLUGIN_NAME not in enabled:
        enabled.append(PLUGIN_NAME)
    plugins["enabled"] = enabled

    web = document.setdefault("web", {})
    if not isinstance(web, dict):
        raise ValueError("Hermes web config must be a mapping")
    web["search_backend"] = SEARCH_BACKEND
    web["extract_backend"] = EXTRACT_BACKEND
    # The Bridge never grants terminal to iOS tenant agents.  Keep Hermes on
    # its built-in task-isolated browser tools by leaving the backend unset;
    # ``backend: off`` disables browser_navigate as well and silently defeats
    # the narrow WeChat verification-page fallback.
    browser = document.setdefault("browser", {})
    if not isinstance(browser, dict):
        raise ValueError("Hermes browser config must be a mapping")
    browser.pop("backend", None)
    _atomic_yaml(config_path, document)
    return {
        "backup": str(backup),
        "plugin": str(destination),
        "config": str(config_path),
        "search_backend": SEARCH_BACKEND,
        "extract_backend": EXTRACT_BACKEND,
        "browser_backend": "builtin",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-home", type=Path, required=True)
    parser.add_argument("--plugin-source", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    args = parser.parse_args()
    result = configure(
        args.hermes_home.expanduser().resolve(),
        args.plugin_source.expanduser().resolve(),
        args.backup_root.expanduser().resolve(),
    )
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
