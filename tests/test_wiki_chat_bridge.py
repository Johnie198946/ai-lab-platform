import json
from unittest.mock import patch


def test_dynamic_chat_tools_include_delegation_when_platform_supports_it():
    import scripts.hermes_bridge as bridge

    with patch.object(
        bridge,
        "_get_cached_tools",
        return_value=["clarify", "skills", "web", "delegation"],
    ):
        resolved = bridge._resolve_dynamic_toolsets("洞察超聚变的竞争优势", {})
    assert "delegation" in resolved


def test_hermes_knowledge_tool_uses_query_and_capability_default_scope():
    import scripts.hermes_bridge as bridge

    bridge._knowledge_tool_context.value = {
        "capability": "signed-capability-token",
        "scopes": ["knowledge/company/public"],
        "sources": ["tenant_knowledge"],
    }
    captured = {}

    def fake_search(token, *, query, category_scope, sources, limit):
        captured.update({
            "token": token,
            "query": query,
            "category_scope": category_scope,
            "sources": sources,
            "limit": limit,
        })
        return [{
            "path": "wiki/超聚变.md",
            "title": "超聚变",
            "snippet": "超聚变提供服务器与算力基础设施产品。",
        }]

    try:
        with patch.object(bridge, "_knowledge_gateway_search", side_effect=fake_search):
            payload = json.loads(bridge._knowledge_search_tool({
                "query": "超聚变是做什么的？",
                "category_scope": ["green"],
            }))
    finally:
        bridge._knowledge_tool_context.value = None

    assert captured["query"] == "超聚变是做什么的？"
    assert captured["category_scope"] is None
    assert captured["sources"] == ["tenant_knowledge"]
    assert payload["docs"][0]["path"] == "wiki/超聚变.md"


def test_zero_local_results_recommend_public_web_fallback():
    import scripts.hermes_bridge as bridge

    bridge._knowledge_tool_context.value = {
        "capability": "signed-capability-token",
        "scopes": ["knowledge/product/public"],
        "sources": ["tenant_knowledge"],
    }
    try:
        with patch.object(bridge, "_knowledge_gateway_search", return_value=[]):
            payload = json.loads(bridge._knowledge_search_tool({"query": "Token Factory"}))
    finally:
        bridge._knowledge_tool_context.value = None

    assert payload["success"] is True
    assert payload["docs"] == []
    assert payload["fallback_recommended"] is True
    assert payload["fallback_source"] == "public_web"


def test_retrieval_prompt_requires_web_fallback_without_bypassing_restricted_data():
    import scripts.hermes_bridge as bridge

    prompt = bridge.KB_RETRIEVAL_DISCIPLINE
    assert "默认只传 query" in prompt
    assert "必须继续调用 web_search" in prompt
    assert "不得借联网推测或重构" in prompt
