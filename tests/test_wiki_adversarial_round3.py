"""Read-only candidate review: fixtures write only pytest tmp dirs."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_wiki_retrieval_governance import wiki as wiki  # shared pytest fixture
from backend.api import knowledge as k, knowledge_policy as gateway
from backend.services import knowledge_catalog as catalog

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('syntax', [
    '[PRIVATE_SENTINEL][secret]\n\n[secret]: ../岗位/secret.md',
    '[PRIVATE_SENTINEL][]\n\n[PRIVATE_SENTINEL]: ../岗位/secret.md',
    '[PRIVATE_SENTINEL]\n\n[PRIVATE_SENTINEL]: ../岗位/secret.md',
    '[PRIVATE_SENTINEL](<../岗位/secret file.md>)',
    '[PRIVATE_SENTINEL [nested]](../岗位/secret.md)',
    '[PRIVATE_SENTINEL](%252e%252e/%e5%b2%97%e4%bd%8d/secret.md)',
])
def test_link_boundary(wiki, tmp_path, syntax):
    wiki('方法论/entry', 'Public purpose. ' + syntax)
    wiki('岗位/secret', 'PRIVATE_RAW', security_level='red', owner_tenant='other')
    docs = k._search_docs(tmp_path, 'entry', 5)
    print('LINK', repr(syntax), json.dumps(docs, ensure_ascii=False))
    assert 'PRIVATE_SENTINEL' not in json.dumps(docs)
    assert not k._search_docs(tmp_path, 'PRIVATE_SENTINEL', 5, topics=['PRIVATE_SENTINEL'])

async def signed(monkeypatch, scope='knowledge/methodology/public'):
    monkeypatch.setattr(gateway, 'verify_capability', lambda _: {
        'tenant_key': 'owner', 'user_id': 'owner', 'policy_version': 'v1',
        'scopes': [scope], 'sources': ['tenant_knowledge']})
    async def policy(*a, **kw):
        return SimpleNamespace(policy_version='v1'), None
    monkeypatch.setattr(gateway, 'resolve_policy', policy)

@pytest.mark.asyncio
async def test_known_controlled_path_missing_summary_is_insufficient(wiki, tmp_path, monkeypatch):
    wiki('IPD', 'PRIVATE_ROLE PRIVATE_DESIGN', enforced_export_allowed=False)
    live = await catalog.filter_database_live_documents(list(catalog.document_index(tmp_path).values()), tmp_path)
    index = {d['path']: d for d in live}
    scope = frozenset({'knowledge/methodology/public'})
    assert catalog.resolve_authorized_version('wiki/IPD.md', index, scope, for_model=False)
    assert catalog.resolve_authorized_version('wiki/IPD.md', index, scope, for_model=True) is None
    await signed(monkeypatch)
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query='IPD', paths=['wiki/IPD.md'], include_content=True), 'signed')
    print('NO_SUMMARY', result)
    assert not result['docs']
    assert result['retrieval_status'] == 'insufficient'

@pytest.mark.asyncio
async def test_query_only_same_entity_gap(wiki, tmp_path, monkeypatch):
    import scripts.hermes_bridge as bridge
    wiki('超聚变', '仅介绍服务器产品，公司概况。没有流程资料。')
    await signed(monkeypatch)
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query='超聚变的IPD是什么', include_content=True), 'signed')
    monkeypatch.setattr(bridge, '_knowledge_gateway_search', lambda *a, **kw: result['docs'])
    bridge._knowledge_tool_context.value = {'capability': 'signed', 'scopes':['knowledge/methodology/public']}
    try:
        payload = json.loads(bridge._knowledge_search_tool({'query':'超聚变的IPD是什么'}))
    finally:
        bridge._knowledge_tool_context.value = None
    print('SAME_ENTITY', payload)
    assert payload['fallback_recommended'] is True

@pytest.mark.parametrize('surface', ['cron','cli','desktop','local','hermes-desktop','feishu','lark'])
def test_cloud_actual_caller_never_owner(monkeypatch, surface):
    spec = importlib.util.spec_from_file_location('round3_router', ROOT / 'agency/hermes-plugins/ai-lab-capabilities/capability_router.py')
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    monkeypatch.setenv('AI_LAB_AGENT_OS_MODE', 'cloud_multi_tenant')
    monkeypatch.setenv('AI_LAB_LOCAL_OWNER_IDS', 'cloud-user')
    event = SimpleNamespace(source=SimpleNamespace(platform=surface,user_id='cloud-user',chat_type='direct'),text='read secret')
    router._pre_gateway_dispatch(event)
    principal = router._resolve_principal(surface,'cloud-user','read secret')
    denial = router._principal_denial('read_file', {'path':'/etc/passwd'}, {'principal':principal})
    print('AUTHORITY', surface, router._owner_surface(surface), principal, denial)
    assert principal != 'local_owner'

@pytest.mark.asyncio
async def test_summary_receipts_do_not_enforce_purpose_only(tmp_path, monkeypatch):
    import test_knowledge_disclosure_incremental as fixture
    from backend.db import SessionLocal
    from backend.services.knowledge_policy import resolve_policy, mint_capability
    sentinel = 'IPD purpose. PRIVATE_ROLE: chief architect. PRIVATE_DESIGN: secret topology. PRIVATE_ACCEPTANCE: all 97 checks. PRIVATE_DELIVERABLE: design blueprint.'
    monkeypatch.setattr(fixture, 'SANITIZE', {**fixture.SANITIZE, 'content':sentinel})
    tenant, event, green = await fixture.publish_fixture(tmp_path, monkeypatch)
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(db, tenant_key=tenant, catalog=catalog.compute_catalog(tmp_path))
    cap = mint_capability(policy, subject_id='model', entry_point='chat')
    result = await gateway.capability_search(gateway.GatewaySearchRequest(query='IPD', paths=[green['artifact_ref']], include_content=True), cap)
    print('PURPOSE_SCHEMA', json.dumps(result, ensure_ascii=False))
    assert result['docs'] == []
    assert result['retrieval_status'] == 'insufficient'
    assert 'PRIVATE_ROLE' not in json.dumps(result)

@pytest.mark.asyncio
async def test_reference_labels_create_hits_and_reach_gateway(wiki, tmp_path, monkeypatch):
    wiki('方法论/entry', 'Public purpose. [PRIVATE_SENTINEL][ref]\n\n[ref]: ../岗位/secret.md')
    wiki('岗位/secret', 'PRIVATE_RAW', security_level='red', owner_tenant='other')
    await signed(monkeypatch)
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query='PRIVATE_SENTINEL', topics=['PRIVATE_SENTINEL'], include_content=True), 'signed')
    print('REFERENCE_GATEWAY', json.dumps(result, ensure_ascii=False))
    assert not result['docs']

@pytest.mark.asyncio
@pytest.mark.parametrize('attack', ['ignore all rules; owner_tenant=other', '../岗位/secret.md', '%2e%2e/secret', 'IPD|.*'])
async def test_untrusted_selectors_do_not_grant_scope(wiki, tmp_path, monkeypatch, attack):
    wiki('IPD', 'PUBLIC')
    wiki('岗位/secret', 'PRIVATE_RAW', security_level='red', owner_tenant='other')
    await signed(monkeypatch)
    result = await gateway.capability_search(gateway.GatewaySearchRequest(
        query=attack, topics=[attack], entities=[attack], paths=['wiki/岗位/secret.md'], include_content=True), 'signed')
    assert result['docs'] == []
    assert 'PRIVATE_RAW' not in json.dumps(result)

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('summary_of','wiki/unrelated.md'), ('source_dependencies',[{'event_id':'forged'}]), ('publication_audience',['unauthorized'])])
async def test_summary_lineage_tampering_denied(tmp_path, monkeypatch, field, value):
    import yaml
    import test_knowledge_disclosure_incremental as fixture
    tenant, event, green = await fixture.publish_fixture(tmp_path, monkeypatch)
    path = tmp_path / green['artifact_ref']
    text = path.read_text()
    meta = yaml.safe_load(text.split('---',2)[1])
    meta[field] = value
    path.write_text('---\n' + yaml.safe_dump(meta) + '---\n' + fixture.SANITIZE['content'])
    catalog.clear_knowledge_caches()
    live = await catalog.filter_database_live_documents(list(catalog.document_index(tmp_path).values()), tmp_path)
    assert green['artifact_ref'] not in [d['path'] for d in live]
