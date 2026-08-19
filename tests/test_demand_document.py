from __future__ import annotations

import json

from backend.services.demand_document import (
    extract_demand_document,
    visible_demand_markdown,
)


SCREENSHOT_CONFIRMATION = """
## 《集团算力利用率提升 · 需求确认单（001）》

### 现状诊断（已确认事实）

| # | 事实 | 含义 |
|---|---|---|
| 1 | 算力综合利用率约 30%，七成闲置 | 供需错配，不是总量不足 |
| 2 | 高峰时段推理算力不够用 | 对抢占能力有要求 |

### 四维确认单

| 维度 | 内容 |
|---|---|
| **目标** | 集团综合利用率 3 个月内提升至 60%+ |
| **非目标** | 不对集团外提供算力运营；不做跨域同步 |
| **约束** | 数据物理不出厂区；推理负载为主 |
| **验收** | 利用率周报连续 4 周 ≥60%；推理 P99 达标 |

### 方案方向（初步）

| 层 | 组件 | 成熟度 |
|---|---|---|
| 运营控制面 | TokenOps 三账体系 | 标准商用 |
| 边缘执行面 | TokenBox 本地算力车间 | 标准商用 |
"""


def test_screenshot_confirmation_is_normalized() -> None:
    result = extract_demand_document(SCREENSHOT_CONFIRMATION)

    assert result["recognized"] is True
    assert result["demand_document"]["status"] == "draft"
    assert result["demand"]["target_metric"].startswith("集团综合利用率")
    assert result["demand"]["cycle"] == "3 个月"
    assert result["demand"]["non_goals"]
    assert result["demand"]["constraints"]
    assert result["demand"]["acceptance_criteria"]
    assert result["demand"]["solution_directions"]
    assert result["demand"]["completeness"] >= 70
    assert {section["type"] for section in result["demand_document"]["sections"]} >= {
        "facts",
        "solution_direction",
    }


def test_plain_chat_mention_does_not_create_document() -> None:
    result = extract_demand_document("我们后面会整理需求确认单，现在先聊聊业务背景。")

    assert result["recognized"] is False


def test_machine_envelope_is_used_but_hidden_from_chat() -> None:
    payload = json.dumps(
        {
            "title": "算力项目需求确认单",
            "summary": {
                "core_problem": "算力闲置",
                "target_metric": "利用率达到 60%",
            },
            "sections": [
                {
                    "type": "goal",
                    "title": "目标",
                    "items": ["利用率达到 60%"],
                    "body": "",
                },
                {
                    "type": "acceptance",
                    "title": "验收",
                    "items": ["连续四周达标"],
                    "body": "",
                },
            ],
        },
        ensure_ascii=False,
    )
    content = f"""
## 需求收敛确认单
### 目标
目标已经明确。
### 验收标准
按月验收。
<!-- AI_LAB_DEMAND_V1
{payload}
AI_LAB_DEMAND_V1 -->
"""

    result = extract_demand_document(content)

    assert result["recognized"] is True
    assert result["demand"]["core_problem"] == "算力闲置"
    assert "AI_LAB_DEMAND_V1" not in visible_demand_markdown(content)


def test_unknown_sections_are_preserved_for_generic_renderer() -> None:
    content = """
## 需求确认单
### 目标指标
| 维度 | 内容 |
|---|---|
| 目标 | 三个月完成首期验证 |
### 验收标准
| 维度 | 内容 |
|---|---|
| 验收 | 用户签字确认 |
### 特殊治理约定
必须保留原始审计记录。
"""
    result = extract_demand_document(content)

    assert result["recognized"] is True
    assert any(
        section["type"] == "unknown"
        for section in result["demand_document"]["sections"]
    )
    assert "必须保留原始审计记录" in result["demand_document"]["raw_markdown"]
