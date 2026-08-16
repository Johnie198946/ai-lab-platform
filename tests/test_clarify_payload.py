"""测试后端 clarify 载荷提取（chat.py → ChatResponse.clarify）。"""
import json

from backend.api.chat import extract_clarify_payload
from backend.services.reasoning_extractor import ReasoningStep, extract_steps


def _clarify_step_detail(question: str, choices: list[str], multi_select: bool = False) -> str:
    return json.dumps(
        {"question": question, "choices": choices, "multi_select": multi_select},
        ensure_ascii=False,
    )


def test_extract_clarify_payload_from_step():
    step = ReasoningStep(
        type="clarify",
        title="需求澄清: 请选择您的电商平台模式",
        detail=_clarify_step_detail("请选择您的电商平台模式", ["B2C 单商户", "B2B2C 多商户", "B2B 批发分销"]),
    )
    payload = extract_clarify_payload([step])
    assert payload is not None
    assert payload.question == "请选择您的电商平台模式"
    assert payload.choices == ["B2C 单商户", "B2B2C 多商户", "B2B 批发分销"]
    assert payload.multi_select is False


def test_extract_clarify_payload_multi_select():
    step = ReasoningStep(
        type="clarify",
        title="需求澄清: MVP 侧重",
        detail=_clarify_step_detail("首期 MVP 核心侧重", ["商品管理", "订单支付", "分销裂变"], multi_select=True),
    )
    payload = extract_clarify_payload([step])
    assert payload is not None
    assert payload.multi_select is True
    assert len(payload.choices) == 3


def test_extract_clarify_payload_picks_last():
    """多条 clarify 步骤时取最后一条（最新一轮提问）。"""
    steps = [
        ReasoningStep(type="clarify", title="第一轮", detail=_clarify_step_detail("第一轮问题", ["A"])),
        ReasoningStep(type="clarify", title="第二轮", detail=_clarify_step_detail("第二轮问题", ["X", "Y"])),
    ]
    payload = extract_clarify_payload(steps)
    assert payload.question == "第二轮问题"
    assert payload.choices == ["X", "Y"]


def test_extract_clarify_payload_none_when_missing():
    assert extract_clarify_payload([]) is None
    assert extract_clarify_payload([ReasoningStep(type="thought", title="思考")]) is None


def test_extract_clarify_payload_invalid_json():
    step = ReasoningStep(type="clarify", title="需求澄清", detail="not-json{{{")
    assert extract_clarify_payload([step]) is None


def test_extract_clarify_payload_missing_question():
    step = ReasoningStep(
        type="clarify", title="需求澄清", detail=json.dumps({"choices": ["A"]})
    )
    assert extract_clarify_payload([step]) is None


def test_extract_clarify_payload_string_choices():
    step = ReasoningStep(
        type="clarify",
        title="需求澄清",
        detail=json.dumps({"question": "Q", "choices": "B2C 单商户"}),
    )
    payload = extract_clarify_payload([step])
    assert payload is not None
    assert payload.choices == ["B2C 单商户"]


def test_full_pipeline_from_state_rows():
    """端到端：state.db 行 → extract_steps → extract_clarify_payload。"""
    rows = [
        {
            "id": 1,
            "session_id": "s",
            "role": "assistant",
            "content": "",
            "reasoning_content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "clarify",
                        "arguments": json.dumps(
                            {
                                "question": "请选择您的电商平台模式",
                                "choices": ["B2C 单商户", "B2B2C 多商户"],
                                "multi_select": False,
                            }
                        ),
                    },
                }
            ],
        }
    ]
    steps = extract_steps(rows)
    payload = extract_clarify_payload(steps)
    assert payload is not None
    assert payload.question == "请选择您的电商平台模式"
    assert payload.choices == ["B2C 单商户", "B2B2C 多商户"]
