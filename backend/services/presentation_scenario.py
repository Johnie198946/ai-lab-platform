"""Existing Workflow scenario contract for private document-to-presentation runs."""

from __future__ import annotations

import re
from typing import Any

SCENARIO_ID = "document-to-presentation"
SCENARIO_VERSION = "2.0.0"
DEFAULT_THEME = {
    "colors": {
        "primary": "#8057E8",
        "text": "#191521",
        "muted": "#686275",
        "pale": "#F1EEFA",
        "background": "#FFFFFF",
        "inverse": "#FFFFFF",
    },
    "fonts": {"title": "Aptos", "body": "Aptos"},
}


def validate_theme(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict) or set(raw) != {"colors", "fonts"}:
        raise ValueError("theme contains unsupported or missing fields")
    colors, fonts = raw.get("colors"), raw.get("fonts")
    if not isinstance(colors, dict) or set(colors) != set(DEFAULT_THEME["colors"]):
        raise ValueError("theme colors are incomplete or unsupported")
    if not isinstance(fonts, dict) or set(fonts) != set(DEFAULT_THEME["fonts"]):
        raise ValueError("theme fonts are incomplete or unsupported")
    if any(
        not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
        for color in colors.values()
    ):
        raise ValueError("theme colors must use #RRGGBB")
    if any(
        not isinstance(font, str)
        or not font.strip()
        or len(font) > 80
        or any(ord(character) < 32 for character in font)
        for font in fonts.values()
    ):
        raise ValueError("theme font names are invalid")
    return {
        "colors": {key: color.upper() for key, color in colors.items()},
        "fonts": {key: font.strip() for key, font in fonts.items()},
    }


def is_presentation_workflow(workflow) -> bool:
    return (workflow.requirements_snapshot or {}).get("scenario_id") == SCENARIO_ID


def build_presentation_plan(
    workflow, *, plan_id: str, knowledge_scope: list[str]
) -> dict[str, Any] | None:
    if not is_presentation_workflow(workflow):
        return None
    source = (workflow.requirements_snapshot or {}).get("source_document") or {}
    common = {
        "scenario_id": SCENARIO_ID,
        "scenario_version": SCENARIO_VERSION,
        "knowledge_scope": knowledge_scope,
        "allow_network": False,
    }
    nodes = [
        {
            "id": "presentation_analysis",
            "node_type": "LLM_INFERENCE",
            "name": "分析文档与提炼证据",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "markdown",
                "instruction": "通读私有源文档，形成演示简报：受众目标、核心结论、关键事实、可用数据、内容缺口与不得推断项。只保留源文档可支持的信息。",
                "max_tokens": 5000,
            },
        },
        {
            "id": "presentation_outline",
            "node_type": "LLM_INFERENCE",
            "name": "生成演示文稿大纲",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "presentation_outline",
                "approval_gate": "outline",
                "instruction": "基于文档分析和已确认需求设计逐页故事线。每页写明标题、页面作用、核心要点、证据依据与建议视觉；标题直接说明主题或有证据支持的结论，不得补造事实。",
                "max_tokens": 8000,
            },
        },
        {
            "id": "presentation_design",
            "node_type": "LLM_INFERENCE",
            "name": "生成代表页设计样稿",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "presentation_design",
                "approval_gate": "design",
                "instruction": "基于已批准大纲生成 3 至 5 张带真实内容的代表页，覆盖封面、关键正文以及适用的数据或结论页；同时给出完整配色与字体。不得使用空占位符，不得虚构数据。",
                "max_tokens": 7000,
            },
        },
        {
            "id": "presentation_deck",
            "node_type": "OUTPUT_FORMAT",
            "name": "生成可编辑演示文稿",
            "parameters": {
                **common,
                "agent_id": "main_agent",
                "output_format": "presentation",
                "instruction": "严格按已批准的大纲逐页填入内容，并沿用已批准代表页的设计系统。优先删减内容而不是缩小字号；标题直接、文字自然，图表只使用源文档中可核验的数据。",
                "max_tokens": 16000,
            },
        },
    ]
    return {
        "plan_id": plan_id,
        "name": workflow.title,
        "version": SCENARIO_VERSION,
        "scenario_id": SCENARIO_ID,
        "source_document": source,
        "nodes": nodes,
        "edges": [
            {"source": "presentation_analysis", "target": "presentation_outline"},
            {"source": "presentation_analysis", "target": "presentation_design"},
            {"source": "presentation_outline", "target": "presentation_design"},
            {"source": "presentation_outline", "target": "presentation_deck"},
            {"source": "presentation_design", "target": "presentation_deck"},
        ],
    }
