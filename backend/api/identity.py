"""身份话术规则引擎 —— YAML 配置驱动，命中即返回固定回答。

设计要点（按 Supervision 批复）：
- 支持三种匹配类型：exact / contains / regex（默认 contains）
- 基于文件 mtime 的热加载：修改 YAML 后下一次请求秒级生效，无需重启
- 命中即返回，不调 LLM；未命中返回 None，走原有 RAG + LLM 流程
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "identity_rules.yaml"

_cache: Optional[Dict[str, Any]] = None
_last_mtime: Optional[float] = None


def _load(force: bool = False) -> Dict[str, Any]:
    """加载/热加载配置：首次或文件 mtime 变化时重新读取。"""
    global _cache, _last_mtime
    try:
        stat = CONFIG_PATH.stat()
    except OSError:
        # 配置文件不存在时返回空规则，不阻塞主流程
        return {"rules": []}

    current_mtime = stat.st_mtime
    if _cache is None or force or _last_mtime != current_mtime:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _cache = data if isinstance(data, dict) else {"rules": []}
        _last_mtime = current_mtime
    return _cache


def _match_pattern(pattern: str, query: str, match_type: str) -> bool:
    """按 match_type 判断单条 pattern 是否命中 query。"""
    if match_type == "exact":
        return query.strip().lower() == pattern.strip().lower()
    if match_type == "regex":
        try:
            return bool(re.search(pattern, query, flags=re.IGNORECASE))
        except re.error:
            return False
    # default: contains
    return pattern.lower() in query.lower()


def match_identity_rule(question: str) -> Optional[str]:
    """命中身份规则返回固定回答，否则返回 None（走正常流程）。"""
    if not question:
        return None
    cfg = _load()
    rules: List[Dict[str, Any]] = cfg.get("rules") or []
    q = question
    for rule in rules:
        match_type = (rule.get("match_type") or "contains").lower()
        patterns = rule.get("patterns") or []
        for pat in patterns:
            if _match_pattern(str(pat), q, match_type):
                resp = rule.get("response") or ""
                return str(resp).strip()
    return None


def reload_config() -> None:
    """强制重新加载配置（供测试或运维调用）。"""
    _load(force=True)
