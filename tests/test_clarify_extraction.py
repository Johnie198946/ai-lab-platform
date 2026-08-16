"""测试 clarify 工具调用提取与清洗。"""
import json
from backend.services.reasoning_extractor import (
    TOOL_WHITELIST,
    extract_steps,
    _tool_type,
)


def test_clarify_in_whitelist():
    assert "clarify" in TOOL_WHITELIST
    assert _tool_type("clarify") == "clarify"


def test_clarify_step_extraction():
    rows = [
        {
            "id": 1,
            "session_id": "test-session",
            "role": "assistant",
            "content": "请确认您的需求",
            "reasoning_content": "用户提出了模糊的电商需求，触发澄清卡片",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "clarify",
                        "arguments": json.dumps(
                            {
                                "question": "请选择您的电商平台模式",
                                "choices": ["B2C 单商户", "B2B2C 多商户", "B2B 批发分销"],
                                "multi_select": False,
                            }
                        ),
                    },
                }
            ],
        }
    ]

    steps = extract_steps(rows)
    assert len(steps) == 2
    # Step 1: thought
    assert steps[0].type == "thought"
    assert steps[0].title == "思考过程"
    assert "电商需求" in steps[0].detail

    # Step 2: clarify tool call
    assert steps[1].type == "clarify"
    assert "需求澄清: 请选择您的电商平台模式" in steps[1].title
    assert "B2C 单商户" in steps[1].detail
