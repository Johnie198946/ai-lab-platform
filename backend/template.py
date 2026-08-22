from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


class TemplateError(RuntimeError):
    pass


@dataclass(frozen=True)
class HermesTemplate:
    template_id: str
    version: str
    root: Path
    agent_ids: tuple[str, ...]
    skill_roots: tuple[Path, ...]
    allowed_skills: frozenset[str]
    config_allowlist: tuple[str, ...]
    fingerprint: str


class TemplateRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def load(self, template_id: str = "hermes-main", version: str = "v1") -> HermesTemplate:
        template_root = (self.root / template_id / version).resolve()
        if not (template_root / "manifest.yaml").is_file() and (self.root / "manifest.yaml").is_file():
            template_root = self.root
        manifest_path = template_root / "manifest.yaml"
        if not manifest_path.is_file():
            raise TemplateError("Hermes template manifest is missing")
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise TemplateError("Hermes template manifest is invalid") from exc
        if manifest.get("template_id") != template_id or manifest.get("version") != version:
            raise TemplateError("Hermes template identity mismatch")
        agent_ids = tuple(str(x) for x in manifest.get("agent_ids", []))
        skill_roots = tuple((template_root / str(x)).resolve() for x in manifest.get("skill_roots", []))
        if any(not root.is_dir() or not self._inside(root, template_root) for root in skill_roots):
            raise TemplateError("Hermes template skill root is invalid")
        allowed_skills = frozenset(self._skill_names(skill_roots))
        fingerprint = self._fingerprint(template_root)
        return HermesTemplate(
            template_id=template_id,
            version=version,
            root=template_root,
            agent_ids=agent_ids,
            skill_roots=skill_roots,
            allowed_skills=allowed_skills,
            config_allowlist=tuple(str(x) for x in manifest.get("config_allowlist", [])),
            fingerprint=fingerprint,
        )

    @staticmethod
    def _skill_names(roots: tuple[Path, ...]) -> list[str]:
        names: list[str] = []
        for root in roots:
            for skill_file in root.rglob("SKILL.md"):
                names.append(skill_file.parent.name)
        return sorted(set(names))

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _fingerprint(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()
