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


def test_hermes_knowledge_tool_uses_model_selected_query_and_capability_scope():
    import scripts.hermes_bridge as bridge

    bridge._knowledge_tool_context.value = {
        "capability": "signed-capability-token",
        "scopes": ["knowledge/company/green"],
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
                "category_scope": ["knowledge/company/green"],
            }))
    finally:
        bridge._knowledge_tool_context.value = None

    assert captured["query"] == "超聚变是做什么的？"
    assert captured["category_scope"] == ["knowledge/company/green"]
    assert captured["sources"] == ["tenant_knowledge"]
    assert payload["docs"][0]["path"] == "wiki/超聚变.md"
