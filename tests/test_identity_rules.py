"""身份话术规则引擎测试 —— 覆盖正向命中 + 反向防误杀。"""
from __future__ import annotations

import pytest

from backend.api.identity import match_identity_rule, reload_config


@pytest.fixture(autouse=True)
def _reload():
    """每条测试前强制重新加载配置，避免 mtime 缓存干扰。"""
    reload_config()


# ---------- 正向命中：应返回固定回答 ----------

@pytest.mark.parametrize("question", [
    "你是谁",
    "你是谁？",
    "你叫什么",
    "你叫什么名字",
    "自我介绍",
    "介绍一下你自己",
    "你是谁!",
    "你是哪个平台",
    "你是哪个系统？",
])
def test_positive_match_zh(question: str) -> None:
    resp = match_identity_rule(question)
    assert resp is not None, f"should match: {question!r}"
    assert "超聚变AI Lab" in resp
    assert "自生长" in resp or "知识体系" in resp


@pytest.mark.parametrize("question", [
    "who are you",
    "Who are you?",
    "what is your name",
    "introduce yourself",
    "WHO ARE YOU!!",
])
def test_positive_match_en(question: str) -> None:
    resp = match_identity_rule(question)
    assert resp is not None, f"should match: {question!r}"
    assert "xFusion AI Lab" in resp


# ---------- 反向防误杀：不应命中身份规则（应返回 None，走 LLM） ----------

@pytest.mark.parametrize("question", [
    "你是什么架构",
    "你是什么架构？",
    "请自我介绍一下这个项目",
    "请自我介绍一下这个系统",
    "介绍一下这个平台",
    "你是谁开发的",
    "你是什么技术栈",
    "what is the architecture",
    "introduce this project please",
])
def test_negative_no_match(question: str) -> None:
    resp = match_identity_rule(question)
    assert resp is None, f"should NOT match: {question!r}, got {resp!r}"


# ---------- 边界情况 ----------

def test_empty_and_whitespace() -> None:
    assert match_identity_rule("") is None
    assert match_identity_rule("   ") is None


def test_none_question() -> None:
    # 防御性：传 None 不应抛异常
    assert match_identity_rule(None) is None


# ---------- 铁律：AI Lab 禁提「展厅」 ----------

@pytest.mark.parametrize("question", [
    "AI Lab 展厅叫什么?",
    "展厅在哪里?",
    "以后 AI Lab 别叫展厅,叫共创体验中心,铁律",
    "AI Lab 对外怎么称呼?",
    "请记住 AI Lab 不叫展厅",
    "固化规则:AI Lab 只能说共创体验中心",
])
def test_showroom_ban_positive(question: str) -> None:
    """含「展厅」或询问 AI Lab 称呼 → 命中且自然表述(不宣告铁律本身)。"""
    resp = match_identity_rule(question)
    assert resp is not None, f"should match: {question!r}"
    assert "共创体验中心" in resp
    # 铁律内化: 回复自然表述, 不宣告「铁律/已遵守/绝不允许」等规则元信息
    assert "铁律" not in resp, resp
    assert "已遵守" not in resp and "绝不允许" not in resp, resp


@pytest.mark.parametrize("question", [
    "帮我做一个 AI Lab 项目",
    "AI Lab 知识库有哪些内容?",
    "今天有什么新闻?",
    "AI Lab 平台怎么部署?",
    "介绍一下 AI Lab 的对外定位",  # 业务性提问,不含违禁词,不触发
])
def test_showroom_ban_negative(question: str) -> None:
    """普通业务提问不应被铁律拦截(防误杀)。"""
    resp = match_identity_rule(question)
    assert resp is None, f"should NOT match: {question!r}, got {resp!r}"
