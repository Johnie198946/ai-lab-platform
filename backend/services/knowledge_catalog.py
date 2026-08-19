"""Vault-backed knowledge catalog discovery without HTTP-layer dependencies."""

from __future__ import annotations

import os
from pathlib import Path

PUBLIC_CATEGORIES: tuple[str, ...] = (
    "wiki", "raw", "研究系统", "竞品情报", "AI情报雷达", "产品设计",
    "客户画像", "任务记录", "决策记录",
)
INDUSTRY_KNOWLEDGE_PREFIX = "knowledge/行业知识"
CATEGORY_TITLES = {
    "研究系统": "研究报告与来源卡片", "wiki": "编译知识条目", "产品设计": "产品文档",
    "raw": "原始资料", "AI情报雷达": "情报日报", "竞品情报": "竞品分析",
    "客户画像": "客户资料", "任务记录": "项目任务记录", "决策记录": "决策记录",
}


def _vault() -> Path:
    default = Path(__file__).resolve().parent.parent.parent / "data" / "vault"
    return Path(os.environ.get("AI_LAB_HOME", str(default)))


def _doc_count(path: Path) -> int:
    return sum(1 for _ in path.rglob("*.md"))


def compute_catalog(vault: Path | None = None) -> list[dict]:
    vault = vault or _vault()
    if not vault.exists():
        return []
    catalog: list[dict] = []
    for name in PUBLIC_CATEGORIES:
        child = vault / name
        if child.is_dir():
            catalog.append({
                "category": name, "path_prefix": f"{name}/",
                "title": CATEGORY_TITLES.get(name, name),
                "doc_count": _doc_count(child), "open": True,
            })
    industry_root = vault / "knowledge" / "行业知识"
    if industry_root.is_dir():
        for domain in sorted(path for path in industry_root.iterdir() if path.is_dir()):
            category = f"{INDUSTRY_KNOWLEDGE_PREFIX}/{domain.name}"
            catalog.append({
                "category": category, "path_prefix": f"{category}/", "title": domain.name,
                "doc_count": _doc_count(domain), "open": True,
            })
    return catalog
