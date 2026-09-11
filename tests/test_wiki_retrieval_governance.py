"""Wiki intent selectors and live governance; never commit private Vault bodies."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from backend.api import knowledge as k
from backend.api import knowledge_policy as gateway
from backend.api.tenant import current_visibility
from backend.services import knowledge_catalog as catalog


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(k, "_matrix", lambda: {})
    catalog.clear_knowledge_caches()
    token = current_visibility.set(frozenset({"knowledge/methodology/public"}))

    def write(name, body="Synthetic evidence.", **labels):
        path = tmp_path / "wiki" / (name + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {"title": name, "type": "methodology", "confidence": "medium",
                    "owner_tenant": "public", "classification_status": "approved",
                    "security_level": "green", "status": "active", **labels}
        path.write_text("---\n" + yaml.safe_dump(metadata, allow_unicode=True) + "---\n" + body)
        catalog.clear_knowledge_caches()
        return path

    yield write
    current_visibility.reset(token)
    catalog.clear_knowledge_caches()


@pytest.mark.parametrize("confidence", ["high", "medium", "low", "unknown"])
def test_legacy_quality_is_not_permission(wiki, tmp_path, confidence):
    wiki("IPD", confidence=confidence)
    docs = k._search_docs(tmp_path, "IPD", 5)
    assert len(docs) == 1
    assert docs[0]["confidence"] == confidence
    assert docs[0]["quality_status"] == ("unrated" if confidence == "unknown" else "legacy_label")
    assert not catalog._assertion_admitted({"confidence": confidence}, require_confidence=True)


@pytest.mark.parametrize("confidence", [0, None, True, 2, -1, "nan", "infinity", "not-a-rating"])
def test_invalid_and_generated_quality_gates_remain(wiki, tmp_path, confidence):
    wiki("IPD", confidence=confidence)
    assert not k._search_docs(tmp_path, "IPD", 5)


@pytest.mark.parametrize("owner", [None, "", "tenant-a"])
def test_green_owner_is_not_invented(wiki, tmp_path, owner):
    wiki("IPD", owner_tenant=owner)
    assert not catalog.document_index(tmp_path)


def test_topics_aliases_and_explicit_link_read_no_matrix_dominance(wiki, tmp_path, monkeypatch):
    wiki("流程", "Synthetic process evidence. [[阶段]] [[Apple]] [[secret|HIDDEN]]",
         aliases=["IPD", "集成产品开发"])
    wiki("阶段", "Synthetic stage activities.")
    wiki("Apple", "Unrelated devices.")
    wiki("超聚变", "Servers; [[流程|IPD]] is only a link.")
    monkeypatch.setattr(k, "_matrix", lambda: {"entity_index": {"IPD": ["wiki/Apple.md"]},
        "categories": {"anything": {"apple": {"path": "wiki/Apple.md", "title": "IPD 超聚变 华为", "entities": ["IPD"] * 100}}}})
    query = "超聚变 华为 IPD 集成产品开发 流程 阶段 决策评审 PDT"
    docs = k._search_docs(tmp_path, query, 5, entities=["超聚变", "华为"], topics=["IPD"])
    assert [d["path"] for d in docs] == ["wiki/流程.md"]
    assert docs[0]["match_basis"] == "entry"
    assert docs[0]["wikilinks"] == ["阶段", "Apple"]
    assert "HIDDEN" not in json.dumps(docs)
    assert k._search_docs(tmp_path, "集成产品开发", 5)[0]["path"] == "wiki/流程.md"
    followed = k._search_docs(tmp_path, "read relevant stage", 5, paths=["wiki/阶段.md"])
    assert [d["path"] for d in followed] == ["wiki/阶段.md"]
    assert followed[0]["match_basis"] == "selected_path"
    assert not k._search_docs(tmp_path, query, 5, topics=["IPD", "uncovered topic"])
    assert not k._term_in("IPD", "SHIPDesign")


def test_selected_paths_never_cross_scope_or_escape(wiki, tmp_path):
    wiki("IPD-secret", "PRIVATE", security_level="red", owner_tenant="tenant-a")
    assert not k._search_docs(tmp_path, "IPD", 5, paths=["wiki/IPD-secret.md", "../secret.md"])
    token = current_visibility.set(frozenset({"knowledge/methodology/private/tenant-a"}))
    try:
        assert k._search_docs(tmp_path, "IPD", 5, paths=["wiki/IPD-secret.md"])
    finally:
        current_visibility.reset(token)


def test_explicit_no_cross_tenant_overrides_public_label_and_cached_scope(wiki, tmp_path):
    path = wiki("IPD", "PRIVATE DESIGN ACCEPTANCE DELIVERABLES")
    candidates = catalog.document_index(tmp_path)
    with k._candidate_scope(tmp_path, candidates):
        assert k._search_docs(tmp_path, "IPD", 5)
        path.write_text(path.read_text().replace("status: active", "status: active\neffective_actions: {cross_tenant: false}"))
        assert not k._search_docs(tmp_path, "IPD", 5)
    token = current_visibility.set(None)  # Existing internal admin audit scope only.
    try:
        assert k._search_docs(tmp_path, "IPD", 5)
    finally:
        current_visibility.reset(token)


@pytest.mark.parametrize("change", ["status: withdrawn", "status: withdraw_pending", "status: recompile_required", "enforced_searchable: false"])
def test_withdrawal_invalidates_cached_candidates_and_locators(wiki, tmp_path, monkeypatch, change):
    path = wiki("IPD")
    candidates = catalog.document_index(tmp_path)
    monkeypatch.setattr(k, "_matrix", lambda: {"entity_index": {"IPD": ["wiki/IPD.md"]}})
    with k._candidate_scope(tmp_path, candidates):
        assert k._search_docs(tmp_path, "IPD", 5)
        path.write_text(path.read_text().replace("status: active", change))
        assert not k._search_docs(tmp_path, "IPD", 5, paths=["wiki/IPD.md"])


def test_unbound_summary_cannot_bypass_raw_authorization(wiki, tmp_path):
    wiki("IPD", "PRIVATE", security_level="red", owner_tenant="tenant-a")
    wiki("summary", "Purpose and broad activity only.", disclosure_granularity="summary",
         summary_of="wiki/IPD.md", derivation_permitted=True, publication_audience=["public"])
    assert not k._search_docs(tmp_path, "IPD", 5)


@pytest.mark.asyncio
async def test_gateway_selectors_reach_shared_search_and_status(wiki, tmp_path, monkeypatch):
    wiki("IPD", "Synthetic concept and activity.")
    wiki("Apple", "Unrelated.")
    claims = {"tenant_key": "selector-test", "user_id": "reader", "policy_version": "v1",
              "scopes": ["knowledge/methodology/public"], "sources": ["tenant_knowledge"]}
    monkeypatch.setattr(gateway, "verify_capability", lambda _: claims)
    async def policy(*args, **kwargs):
        return SimpleNamespace(policy_version="v1"), None
    monkeypatch.setattr(gateway, "resolve_policy", policy)
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query="超聚变 Apple IPD", topics=["IPD"], entities=["超聚变"], include_content=True), "signed")
    assert [d["title"] for d in result["docs"]] == ["IPD"]
    assert result["retrieval_status"] == "matched"
    assert result["evidence_sufficiency"] == "not_assessed"
    empty = await gateway.capability_search(gateway.GatewaySearchRequest(query="missing", topics=["missing"]), "signed")
    assert empty["retrieval_status"] == "no_match"


@pytest.mark.parametrize("outcome,status,success", [([], "no_match", True),
    ([{"path": "wiki/IPD.md", "match_basis": "body"}], "insufficient", True),
    ([{"path": "wiki/IPD.md", "match_basis": "entry", "content_status": "complete"}], "matched", True),
    (RuntimeError("offline"), "error", False)])
def test_bridge_outcomes_and_selector_forwarding(monkeypatch, outcome, status, success):
    import scripts.hermes_bridge as bridge
    bridge._knowledge_tool_context.value = {"capability": "signed", "scopes": ["knowledge/methodology/public"]}
    mock = Mock(side_effect=outcome if isinstance(outcome, Exception) else None,
                return_value=outcome)
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", mock)
    try:
        result = json.loads(bridge._knowledge_search_tool({"query": "IPD", "topics": ["IPD"]}))
    finally:
        bridge._knowledge_tool_context.value = None
    assert result["retrieval_status"] == status
    assert result["success"] is success
    assert result["fallback_recommended"] is (status != "matched")
    assert mock.call_args.kwargs["wiki_request"] == {"topics": ["IPD"]}


def test_malformed_gateway_is_error_not_empty(monkeypatch):
    import scripts.hermes_bridge as bridge
    response = Mock(status_code=200)
    response.json.return_value = {"unexpected": "payload"}
    monkeypatch.setattr(bridge.httpx, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match="invalid knowledge gateway response"):
        bridge._knowledge_gateway_search("signed", query="IPD")


@pytest.mark.parametrize("goal,network,tools,allowed", [
    ("超聚变的IPD是什么？", True, ["web_search"], True),
    ("超聚变的IPD是什么？", False, ["web_search"], False),
    ("超聚变的IPD是什么？", True, [], False),
    ("仅内部材料解释IPD", True, ["web_search"], False),
    ("不要联网解释IPD", True, ["web_search"], False),
    ("Only my notes: explain IPD", True, ["web_search"], False),
])
def test_existing_public_web_tool_retained_only_when_authorized(goal, network, tools, allowed):
    from scripts.hermes_bridge import _knowledge_public_fallback_allowed, _apply_triage_toolset_policy
    from backend.services.chat_triage import classify_request
    triage = classify_request(goal).as_dict()
    grant = _knowledge_public_fallback_allowed(goal, {"allow_network": network, "allowed_tools": tools}, triage)
    assert grant is allowed
    selected = _apply_triage_toolset_policy(["knowledge_gateway", "web"], triage, public_knowledge_fallback=grant)
    assert ("web" in selected) is allowed


def test_alias_link_is_locator_not_automatically_read_evidence(wiki, tmp_path):
    wiki("entry", "Evidence [[gate alias]]", related=["[[gate alias]]"])
    wiki("methods/gate", "Stage purpose.", aliases=["gate alias"])
    docs = k._search_docs(tmp_path, "entry", 5)
    assert [d["path"] for d in docs] == ["wiki/entry.md"]
    assert docs[0]["wikilinks"] == ["methods/gate"]
    followed = k._search_docs(tmp_path, "read gate", 5, paths=["wiki/methods/gate.md"])
    assert [d["path"] for d in followed] == ["wiki/methods/gate.md"]


@pytest.mark.asyncio
async def test_authorization_database_failure_is_error_not_no_match(wiki, tmp_path, monkeypatch):
    import backend.db as db
    from fastapi import HTTPException
    wiki("IPD")
    candidates = list(catalog.document_index(tmp_path).values())
    monkeypatch.setattr(db, "SessionLocal", Mock(side_effect=RuntimeError("database offline")))
    with pytest.raises(HTTPException) as error:
        await catalog.filter_database_live_documents(candidates, tmp_path)
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_mid_read_cross_tenant_tightening_revokes_response(wiki, tmp_path, monkeypatch):
    from fastapi import HTTPException
    path = wiki("IPD", "PRIVATE DETAILS")
    claims = {"tenant_key": "race-test", "user_id": "reader", "policy_version": "v1",
              "scopes": ["knowledge/methodology/public"], "sources": ["tenant_knowledge"]}
    monkeypatch.setattr(gateway, "verify_capability", lambda _: claims)
    async def policy(*args, **kwargs):
        return SimpleNamespace(policy_version="v1"), None
    monkeypatch.setattr(gateway, "resolve_policy", policy)
    original = gateway._read_model_content
    def tighten(*args, **kwargs):
        result = original(*args, **kwargs)
        path.write_text(path.read_text().replace("status: active", "status: active\neffective_actions: {cross_tenant: false}"))
        return result
    monkeypatch.setattr(gateway, "_read_model_content", tighten)
    with pytest.raises(HTTPException) as error:
        await gateway.capability_search(gateway.GatewaySearchRequest(
            query="IPD", include_content=True), "signed")
    assert error.value.status_code == 409


@pytest.mark.parametrize("syntax", [
    "[PRIVATE_SENTINEL](../岗位/secret.md)", "[PRIVATE_SENTINEL](../岗位/secret)",
    "![PRIVATE_SENTINEL](../岗位/secret.md)", "[[../岗位/secret.md#验收|PRIVATE_SENTINEL]]",
    "[PRIVATE_SENTINEL](%2e%2e/%e5%b2%97%e4%bd%8d/secret.md#x)",
    "[PRIVATE_SENTINEL](../../../../outside.md)", "[PRIVATE_SENTINEL](file:///private/secret.md)",
])
def test_unauthorized_markdown_and_wiki_links_never_reach_snippets(wiki, tmp_path, syntax):
    wiki("方法论/entry", "Public purpose. " + syntax)
    wiki("岗位/secret", "PRIVATE", security_level="red", owner_tenant="other")
    docs = k._search_docs(tmp_path, "entry", 5)
    assert "PRIVATE_SENTINEL" not in json.dumps(docs)
    assert not docs[0]["wikilinks"]
    text = (tmp_path / "wiki/方法论/entry.md").read_text()
    assert "PRIVATE_SENTINEL" not in k._model_text(text, "wiki/方法论/entry.md", tmp_path)


def test_source_relative_encoded_links_and_ambiguous_basename(wiki, tmp_path):
    wiki("方法论/entry", "Entry [stage](../阶段/IPD.md#%E7%9B%AE%E7%9A%84) [[IPD#目的]]")
    wiki("阶段/IPD", "Purpose and activity.")
    docs = k._search_docs(tmp_path, "entry", 5)
    assert docs[0]["wikilinks"] == ["阶段/IPD"]
    wiki("other/IPD", "Another meaning.")
    with k._candidate_scope(tmp_path):
        assert k._resolve_wiki_target("IPD", tmp_path) is None
        assert k._resolve_wiki_target("../阶段/IPD.md#目的", tmp_path, "wiki/方法论/entry.md") == "wiki/阶段/IPD.md"
    target = tmp_path / "wiki/阶段/IPD.md"
    target.write_text(target.read_text().replace("status: active", "status: withdrawn"))
    docs = k._search_docs(tmp_path, "entry", 5)
    assert "[stage]" not in docs[0]["snippet"]


@pytest.mark.asyncio
@pytest.mark.parametrize("control", [{"security_level": "red", "owner_tenant": "owner"},
    {"enforced_export_allowed": False}, {"enforced_external_publish_allowed": False}])
async def test_model_gateway_never_receives_controlled_detail_even_owner(wiki, tmp_path, monkeypatch, control):
    wiki("IPD", "PRIVATE_ROLE PRIVATE_DESIGN PRIVATE_ACCEPTANCE PRIVATE_DELIVERABLE", **control)
    scope = "knowledge/methodology/private/owner" if control.get("security_level") == "red" else "knowledge/methodology/public"
    monkeypatch.setattr(gateway, "verify_capability", lambda _: {"tenant_key": "owner", "user_id": "owner",
        "policy_version": "v1", "scopes": [scope], "sources": ["tenant_knowledge"]})
    async def policy(*args, **kwargs):
        return SimpleNamespace(policy_version="v1"), None
    monkeypatch.setattr(gateway, "resolve_policy", policy)
    token = current_visibility.set(frozenset({scope}))
    try:
        assert k._search_docs(tmp_path, "IPD", 5)  # Internal authorized discovery remains.
    finally:
        current_visibility.reset(token)
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query="IPD", paths=["wiki/IPD.md"], include_content=True), "signed")
    assert result["docs"] == []
    assert "PRIVATE_" not in json.dumps(result)


from test_purpose_activity_disclosure import inference_fixture as inference_fixture  # noqa: E402 -- real worker fixture


@pytest.mark.asyncio
async def test_owner_gets_hash_reviewed_summary_not_detail_in_tool_payload(tmp_path, monkeypatch, inference_fixture):
    import test_purpose_activity_disclosure as fixture
    from backend.db import SessionLocal
    from backend.services.knowledge_policy import mint_capability, resolve_policy
    import scripts.hermes_bridge as bridge
    tenant, event, store, run = await fixture.start(tmp_path)
    for output in (fixture.DRAFT, fixture.sanitized(), fixture.privacy()):
        finished = await inference_fixture(store, output)
        assert finished["status"] == "completed"
        green = await fixture.advance_completed(store, run_id=finished["run_id"], vault=tmp_path)
    assert green["status"] == "published"
    live = await catalog.filter_database_live_documents(list(catalog.document_index(tmp_path).values()), tmp_path)
    summary = next(d for d in live if d["path"] == green["artifact_ref"])
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(db, tenant_key=tenant, catalog=catalog.compute_catalog(tmp_path))
    capability = mint_capability(policy, subject_id="model", entry_point="chat")
    # Explicitly requesting an owned private path still resolves to reviewed summary.
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query="IPD", paths=[summary["summary_of"]], include_content=True), capability)
    assert [d["path"] for d in result["docs"]] == [summary["path"]]
    assert result["docs"][0]["markdown"].strip() == fixture.BODY
    assert fixture.DETAIL not in json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *a, **kw: result["docs"])
    bridge._knowledge_tool_context.value = {"capability": capability, "scopes": list(policy.effective_categories)}
    try:
        payload = bridge._knowledge_search_tool({"query": "IPD", "paths": [summary["path"]]})
    finally:
        bridge._knowledge_tool_context.value = None
    assert fixture.DETAIL not in payload
    assert fixture.PURPOSE in payload
    # Purpose review binds title as well as body; tampering denies the artifact.
    path = tmp_path / summary["path"]
    text = path.read_text()
    metadata = yaml.safe_load(text.split("---", 2)[1])
    metadata.update(title="PRIVATE_SENTINEL", aliases=["PRIVATE_SENTINEL"], source_kind="PRIVATE_SENTINEL")
    path.write_text("---\n" + yaml.safe_dump(metadata) + "---\n" + fixture.BODY)
    catalog.clear_knowledge_caches()
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query="IPD", include_content=True), capability)
    assert result["docs"] == []
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    path.write_text(path.read_text() + "\nPRIVATE_SENTINEL")
    assert not (await gateway.capability_search(gateway.GatewaySearchRequest(
        query="IPD", include_content=True), capability))["docs"]


def test_mac_capability_wrapper_propagates_missing_tool_failure(monkeypatch):
    from test_agency_integration import load_capability_plugin, FakePluginContext
    plugin = load_capability_plugin()
    context = FakePluginContext()
    plugin.register(context)
    monkeypatch.setattr(context, "dispatch_tool", lambda *args: json.dumps({
        "success": False, "error": "tool_not_found", "retrieval_status": "error",
        "fallback_recommended": True, "fallback_source": "public_web"}))
    result = json.loads(context.tools["ai_lab_execute"]["handler"]({
        "capability": "knowledge_search", "inputs": {"query": "IPD", "topics": ["IPD"]}}))
    assert result["success"] is False
    assert result["error"] == "tool_not_found"
    assert result["retrieval_status"] == "error"
    assert result["fallback_recommended"] is True


def test_real_ipd_local_fixture_readonly(tmp_path, monkeypatch):
    root = os.environ.get("AI_LAB_REAL_IPD_FIXTURE_ROOT")
    if not root:
        pytest.skip("opt-in local real Vault fixture; private bodies must not enter Git")
    source = Path(root)
    expected = {
        "超聚变IPD产品开发流程.md": "e798e4c1226ebe86d7edfbb8647ea87e7d2d268af114d0739b72288740f1f3b7",
        "超聚变IPD节点Agent定义与对外口径.md": "75233c86321a4e82410c4c90b491a270cf197722d31363c548aaaa74b89f2d21",
    }
    before = {name: (source / name).read_bytes() for name in expected}
    assert {name: hashlib.sha256(raw).hexdigest() for name, raw in before.items()} == expected
    target = tmp_path / "wiki/方法论"
    target.mkdir(parents=True)
    for name, raw in before.items():
        (target / name).write_bytes(raw)
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(k, "_matrix", lambda: {})
    catalog.clear_knowledge_caches()
    token = current_visibility.set(None)
    try:
        docs = k._search_docs(tmp_path, "超聚变 华为 IPD 集成产品开发 流程 阶段 决策评审 PDT", 5, topics=["IPD"])
        assert [d["title"] for d in docs] == ["超聚变IPD节点Agent定义与对外口径"]
        assert docs[0]["confidence"] == "medium"
        # Ownerless unknown file stays quarantined; do not invent public ownership.
        assert not any("产品开发流程.md" in d["path"] for d in docs)
    finally:
        current_visibility.reset(token)
    token = current_visibility.set(frozenset({"knowledge/methodology/public"}))
    try:
        assert not k._search_docs(tmp_path, "IPD", 5, topics=["IPD"])
    finally:
        current_visibility.reset(token)
        catalog.clear_knowledge_caches()
    assert {name: (source / name).read_bytes() for name in expected} == before
