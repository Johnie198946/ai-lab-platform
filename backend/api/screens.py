"""
9 块分屏配置接口

GET /api/screens          — 列出所有屏
GET /api/screens/{id}     — 获取单屏配置 (含 data_bindings)
数据来源: config/screens/screen-01.yaml ~ screen-09.yaml
启动时加载到内存缓存，零数据库依赖。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/screens", tags=["screens"])

SCREENS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "screens"

_cache: dict[str, dict[str, Any]] = {}


def _load_all() -> dict[str, dict[str, Any]]:
    """启动时从 YAML 文件加载全部屏配置到内存缓存。"""
    screens: dict[str, dict[str, Any]] = {}
    if not SCREENS_DIR.is_dir():
        return screens
    for yaml_path in sorted(SCREENS_DIR.glob("screen-*.yaml")):
        if not re.fullmatch(r"screen-\d{2}\.yaml", yaml_path.name):
            continue
        with open(yaml_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            if data and "screen_id" in data:
                screens[data["screen_id"]] = data
    return screens


_cache = _load_all()


def _reload() -> dict[str, dict[str, Any]]:
    """强制刷新缓存（dev / hot-reload 场景）。"""
    global _cache
    _cache = _load_all()
    return _cache


@router.get("")
async def list_screens() -> list[dict[str, Any]]:
    """列出全部 9 块屏的基础信息。"""
    return [
        {
            "screen_id": v["screen_id"],
            "title": v.get("title", ""),
            "role": v.get("role", ""),
            "layout": v.get("layout", ""),
            "theme": v.get("theme", "dark"),
        }
        for v in _cache.values()
    ]


@router.get("/{screen_id}")
async def get_screen(screen_id: str) -> dict[str, Any]:
    """获取单屏完整配置，包含 data_bindings 和 refresh 策略。"""
    screen = _cache.get(screen_id)
    if screen is None:
        raise HTTPException(status_code=404, detail=f"screen not found: {screen_id}")
    return screen
