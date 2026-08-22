import asyncio
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


def test_request_scoped_wiki_evidence_uses_raw_query_and_capability_scope():
    import scripts.hermes_bridge as bridge

    body = bridge.GoalRequest(
        goal="augmented prompt that must not be searched",
        session_id="tenant-session",
        knowledge_capability="signed-capability-token",
        knowledge_policy_version="policy-version-1",
        knowledge_query="超聚变是做什么的？",
    )
    captured = {}

    def fake_search(token, *, query, category_scope, limit):
        captured.update({
            "token": token,
            "query": query,
            "category_scope": category_scope,
            "limit": limit,
        })
        return [{
            "path": "wiki/超聚变.md",
            "title": "超聚变",
            "snippet": "超聚变提供服务器与算力基础设施产品。",
        }]

    with patch.object(bridge, "_knowledge_gateway_search", side_effect=fake_search):
        evidence = asyncio.run(
            bridge._request_scoped_wiki_evidence(
                body,
                {"scopes": ["knowledge/company/green"]},
            )
        )

    assert captured["query"] == "超聚变是做什么的？"
    assert captured["category_scope"] == ["knowledge/company/green"]
    assert "[[wiki/超聚变.md]]" in evidence
    assert "服务器与算力基础设施" in evidence
