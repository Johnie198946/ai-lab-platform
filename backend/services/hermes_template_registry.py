"""Read-only registry for versioned Hermes runtime templates.

The registry deliberately does not provision or mutate templates.  Provisioning
belongs to the tenant sandbox manager in the next migration phase.  This module
only proves that a template is complete, confined to its root, and internally
consistent before another component is allowed to use it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml


class TemplateValidationError(ValueError):
    """Raised when a Hermes template is unsafe or incomplete."""


_REQUIRED_MANIFEST_FIELDS = {
    "template_id",
    "version",
    "agent_ids",
    "skill_roots",
    "config_allowlist",
    "excluded_paths",
    "integrity",
}
_DEFAULT_EXCLUDED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "auth.json",
    "state.db",
    "sessions",
    "memory",
}


@dataclass(frozen=True)
class HermesTemplate:
    """Validated immutable view of one template version."""

    template_id: str
    version: str
    root: Path
    manifest: dict[str, Any]
    files: dict[str, str]
    fingerprint: str


class HermesTemplateRegistry:
    """Load and validate Hermes templates without writing to them."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve()

    def load(self, template_id: str, version: str) -> HermesTemplate:
        self._validate_component(template_id, "template_id")
        self._validate_component(version, "version")
        template_root = (self.root / template_id / version).resolve()
        self._ensure_inside(template_root, self.root)
        if not template_root.is_dir():
            raise TemplateValidationError("template directory does not exist")

        manifest_path = template_root / "manifest.yaml"
        if not manifest_path.is_file():
            raise TemplateValidationError("manifest.yaml is required")
        if manifest_path.is_symlink():
            raise TemplateValidationError("manifest.yaml cannot be a symlink")
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise TemplateValidationError(f"invalid manifest.yaml: {exc}") from exc
        self._validate_manifest(manifest, template_id, version)
        for field in ("skill_roots", "config_allowlist", "excluded_paths"):
            for relative in manifest[field]:
                declared_path = self._validate_declared_path(
                    relative, template_root, field
                )
                if field != "excluded_paths" and not declared_path.exists():
                    raise TemplateValidationError(
                        f"declared {field} is missing: {relative}"
                    )

        files: dict[str, str] = {}
        for path in sorted(template_root.rglob("*")):
            if path.is_symlink():
                raise TemplateValidationError(
                    f"symlink is not allowed: {path.relative_to(template_root)}"
                )
            if not path.is_file():
                continue
            relative = path.relative_to(template_root).as_posix()
            self._validate_relative_path(
                relative, template_root, self._excluded_paths(manifest)
            )
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise TemplateValidationError(
                    f"cannot read template file {relative}: {exc}"
                ) from exc
            files[relative] = digest

        declared = manifest["integrity"].get("files", {})
        if not isinstance(declared, Mapping):
            raise TemplateValidationError("integrity.files must be a mapping")
        for relative, expected in declared.items():
            if relative not in files:
                raise TemplateValidationError(
                    f"declared integrity file is missing: {relative}"
                )
            if files[relative] != str(expected):
                raise TemplateValidationError(f"hash mismatch: {relative}")

        fingerprint = self._fingerprint(files, manifest)
        return HermesTemplate(
            template_id=template_id,
            version=version,
            root=template_root,
            manifest=dict(manifest),
            files=files,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _validate_component(value: str, field: str) -> None:
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise TemplateValidationError(f"invalid {field}")

    @classmethod
    def _validate_manifest(cls, manifest: Any, template_id: str, version: str) -> None:
        if not isinstance(manifest, dict):
            raise TemplateValidationError("manifest.yaml must contain a mapping")
        missing = sorted(_REQUIRED_MANIFEST_FIELDS - set(manifest))
        if missing:
            raise TemplateValidationError(
                f"missing manifest fields: {', '.join(missing)}"
            )
        if manifest["template_id"] != template_id or manifest["version"] != version:
            raise TemplateValidationError(
                "manifest identity does not match template path"
            )
        for field in ("agent_ids", "skill_roots", "config_allowlist", "excluded_paths"):
            if not isinstance(manifest[field], list) or not all(
                isinstance(x, str) for x in manifest[field]
            ):
                raise TemplateValidationError(f"{field} must be a list of strings")
        integrity = manifest["integrity"]
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
            raise TemplateValidationError("integrity.algorithm must be sha256")
        if not manifest["agent_ids"]:
            raise TemplateValidationError("agent_ids cannot be empty")

    @staticmethod
    def _excluded_paths(manifest: Mapping[str, Any]) -> set[str]:
        excluded = set(_DEFAULT_EXCLUDED_NAMES)
        excluded.update(str(value).strip("/") for value in manifest["excluded_paths"])
        return {value for value in excluded if value}

    @classmethod
    def _validate_declared_path(
        cls, relative: str, template_root: Path, field: str
    ) -> Path:
        if not isinstance(relative, str) or not relative.strip():
            raise TemplateValidationError(f"{field} contains an empty path")
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts:
            raise TemplateValidationError(
                f"{field} path is outside template root: {relative}"
            )
        resolved = (template_root / relative).resolve()
        cls._ensure_inside(resolved, template_root)
        return resolved

    @classmethod
    def _validate_relative_path(
        cls, relative: str, template_root: Path, excluded: set[str]
    ) -> None:
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts:
            raise TemplateValidationError(f"path escapes template root: {relative}")
        if any(part in excluded or part.startswith(".env") for part in path.parts):
            raise TemplateValidationError(f"excluded path in template: {relative}")
        cls._ensure_inside((template_root / relative).resolve(), template_root)

    @staticmethod
    def _ensure_inside(path: Path, root: Path) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise TemplateValidationError(
                f"path is outside template root: {path}"
            ) from exc

    @staticmethod
    def _fingerprint(files: Mapping[str, str], manifest: Mapping[str, Any]) -> str:
        digest = hashlib.sha256()
        digest.update(yaml.safe_dump(dict(manifest), sort_keys=True).encode("utf-8"))
        for relative in sorted(files):
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(files[relative].encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()
