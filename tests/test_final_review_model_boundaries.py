# ruff: noqa: F811 -- imported pytest fixtures are injected by parameter name.
import json
import pytest
from test_wiki_retrieval_governance import wiki
from backend.api import knowledge_policy as gateway, subscriptions
from backend.db import SessionLocal
from backend.services import knowledge_catalog as catalog
from backend.services.knowledge_policy import resolve_policy, mint_capability
from backend.services.user_note_context import note_directory
from test_purpose_activity_disclosure import inference_fixture

@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['超聚变的IPD是什么', '超聚变的ipd是什么', '超聚变的薪资结构是什么'])
async def test_original_topic_gap(wiki, monkeypatch, query):
    import scripts.hermes_bridge as bridge
    wiki('超聚变', '仅介绍服务器产品，公司概况。没有流程资料。')
    policy = await policy_for('topic-reader')
    cap = mint_capability(policy, subject_id='audit', entry_point='chat', user_id='reader')
    result = await gateway.capability_search(gateway.GatewaySearchRequest(query=query, include_content=True),cap)
    monkeypatch.setattr(bridge, '_knowledge_gateway_search', lambda *a, **kw: result)
    monkeypatch.setattr(bridge._knowledge_tool_context, 'value', {'capability':cap, 'scopes':list(policy.effective_categories)})
    response = json.loads(bridge._knowledge_search_tool({'query':query}))
    print('TOPIC_GAP', query, response)
    assert response['retrieval_status'] != 'matched'

async def policy_for(tenant):
    async with SessionLocal() as db:
        return (await resolve_policy(db, tenant_key=tenant, catalog=catalog.compute_catalog()))[0]

@pytest.mark.asyncio
@pytest.mark.parametrize('controlled', [False, True])
async def test_selected_book_disclosure(wiki, tmp_path, controlled):
    wiki('IPD', '# IPD\n\nPRIVATE_DESIGN_SENTINEL', knowledge_level='K5', enforced_export_allowed=not controlled, book_publication_authorized=True, book_title='IPD', book_author='Editorial', book_summary='Reader summary')
    (tmp_path/'knowledge_catalog.json').write_text(json.dumps({'version':'2.0','packs':[], 'documents':[{'path':'wiki/IPD.md','pack_id':'knowledge/methodology/public','security_level':'green','classification_status':'approved','owner_tenant':'public','book_publication_authorized':True}]}))
    catalog.clear_knowledge_caches()
    policy = await policy_for('audit-reader')
    payload = {'tenant_key':'audit-reader', 'user_id':'reader', 'visible_categories':policy.effective_categories}
    books = await subscriptions._available_books(payload)
    assert books, 'fixture must have a real readable book'
    book_id = next(iter(books))
    _, book = await subscriptions._available_book_body(payload, book_id)
    assert 'PRIVATE_DESIGN_SENTINEL' in json.dumps(book), 'ordinary reader authorization retained'
    cap = mint_capability(policy, subject_id='audit', entry_point='chat', user_id='reader', book_scope={'book_id':book_id, 'content_version':book['content_version']})
    result = await gateway.capability_search(gateway.GatewaySearchRequest(query='IPD是什么，只披露目的与大致活动', book_id=book_id, content_version=book['content_version']), cap)
    print('SELECTED_BOOK', controlled, json.dumps(result,ensure_ascii=False))
    assert ('PRIVATE_DESIGN_SENTINEL' in json.dumps(result)) is not controlled

@pytest.mark.asyncio
@pytest.mark.parametrize('controlled', [False, True])
async def test_user_notes_disclosure(tmp_path, monkeypatch, controlled):
    monkeypatch.setenv('AI_LAB_HOME', str(tmp_path))
    monkeypatch.setenv('AI_LAB_USER_SYNC_ROOT', str(tmp_path/'notes'))
    catalog.clear_knowledge_caches()
    directory = note_directory('note-reader', 'reader')
    directory.mkdir(parents=True)
    header = 'title: IPD\n' + ('enforced_export_allowed: false\nenforced_external_publish_allowed: false\n' if controlled else '')
    (directory/'ipd.md').write_text('---\n'+header+'---\n# IPD\nPRIVATE_NOTE_DESIGN_SENTINEL')
    policy = await policy_for('note-reader')
    cap = mint_capability(policy, subject_id='audit', entry_point='chat', user_id='reader', sources=('user_notes',))
    result = await gateway.capability_search(gateway.GatewaySearchRequest(query='IPD', sources=['user_notes'], include_content=True),cap)
    print('USER_NOTES', controlled, json.dumps(result,ensure_ascii=False))
    assert ('PRIVATE_NOTE_DESIGN_SENTINEL' in json.dumps(result)) is not controlled


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['超聚变是什么', '超聚变的ipd是什么', '超聚变的薪资结构是什么'])
async def test_requested_topic_present(wiki, query):
    wiki('超聚变', '超聚变是服务器公司。ipd用于产品开发。薪资结构包含基本工资。')
    policy = await policy_for('present-reader')
    cap = mint_capability(policy, subject_id='audit', entry_point='chat', user_id='reader')
    result = await gateway.capability_search(gateway.GatewaySearchRequest(query=query, include_content=True), cap)
    assert result['query'] == query
    assert result['retrieval_status'] == 'matched'


@pytest.mark.parametrize('header', ['enforced_export_allowed: false', 'noexport: true',
    'enforced_external_publish_allowed: false', 'disclosure_granularity: summary\nnoexport: true\npurpose_publication_validated: true'])
def test_inline_note_control(header):
    from types import SimpleNamespace
    from backend.services.user_note_context import normalize_inline_notes, render_local_note_context
    notes = normalize_inline_notes([SimpleNamespace(id='SECRET_TITLE', title='SECRET_TITLE',
        markdown='---\n' + header + '\n---\n# SECRET_TITLE\nSECRET_BODY')])
    assert notes[0]['content_status'] == 'disclosure_limited'
    assert 'SECRET' not in json.dumps(notes) + render_local_note_context(notes)


def test_private_red_note_is_not_export_control():
    from backend.services.user_note_context import model_note
    note = {'id': 'mine', 'title': 'Mine', 'markdown': '---\nsecurity_level: red\nowner_tenant: mine\n---\nPrivate text'}
    assert model_note(note) == note


@pytest.mark.asyncio
async def test_chat_blocks_controlled_toc_before_model(wiki, tmp_path):
    from backend.api import chat
    from fastapi import HTTPException
    wiki('IPD', '# SECRET_TOC\nSECRET_BODY', knowledge_level='K5', enforced_export_allowed=False,
         book_publication_authorized=True, book_title='SECRET_TITLE', book_author='Editorial', book_summary='Reader summary')
    (tmp_path/'knowledge_catalog.json').write_text(json.dumps({'version':'2.0','packs':[], 'documents':[
        {'path':'wiki/IPD.md','pack_id':'knowledge/methodology/public','security_level':'green',
         'classification_status':'approved','owner_tenant':'public','book_publication_authorized':True}]}))
    catalog.clear_knowledge_caches()
    policy = await policy_for('toc-reader')
    payload = {'tenant_key':'toc-reader', 'user_id':'reader', 'visible_categories':policy.effective_categories}
    book_id = next(iter(await subscriptions._available_books(payload)))
    with pytest.raises(HTTPException) as exc:
        await chat._resolve_source_context(scope=chat.ChatContextScope(mode='platform_only', selected_book_id=book_id),
            payload=payload, subject_id='toc-session', question='目的与活动', policy=policy)
    assert exc.value.detail == {'code': 'book_disclosure_insufficient'}


@pytest.mark.asyncio
async def test_book_projection_uses_real_pipeline_receipts(tmp_path, inference_fixture):
    from test_purpose_activity_disclosure import start, DRAFT, sanitized, privacy, BODY, DETAIL
    from backend.services.knowledge_pipeline import advance_completed
    _, _, store, _ = await start(tmp_path)
    for output in ({**DRAFT, 'title': DRAFT['title'] + ' book-boundary-fixture'}, sanitized(), privacy()):
        finished = await inference_fixture(store, output)
        assert finished['status'] == 'completed'
        result = await advance_completed(store, run_id=finished['run_id'], vault=tmp_path)
    assert result['status'] == 'published'
    live = await catalog.filter_database_live_documents(list(catalog.document_index(tmp_path).values()), tmp_path)
    item = next(d for d in live if d['path'] == result['artifact_ref'])
    book = {'book_id': 'component-test', 'content_version': 'reader-version',
            'title': 'PRIVATE_TITLE', 'sections': [{'id': 's', 'title': 'PRIVATE_TOC', 'markdown': DETAIL}]}
    projected = await gateway._model_book({'source_path': item['path'], 'purpose_publication_validated': True},
                                          book, frozenset([item['pack_id']]))
    encoded = json.dumps(projected, ensure_ascii=False)
    assert BODY in '\n'.join(s['markdown'] for s in projected['sections'])
    assert 'PRIVATE_' not in encoded and DETAIL not in encoded
    path = tmp_path / item['path']
    path.write_text(path.read_text() + '\n' + DETAIL)
    denied = await gateway._model_book({'source_path': item['path'], 'purpose_publication_validated': True},
                                       book, frozenset([item['pack_id']]))
    assert denied['content_status'] == 'disclosure_limited'
    assert 'PRIVATE_' not in json.dumps(denied) and DETAIL not in json.dumps(denied, ensure_ascii=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('controlled', [False, True])
async def test_private_snapshot_source_control(tmp_path, controlled):
    import hashlib
    import sqlite3
    from test_owner_private_bookshelf import _source_tree
    from backend.services.owner_private_bookshelf import OwnerPrivateBookshelfStore, export_follow_builders
    source = _source_tree(tmp_path / 'source', people=1, sources=2)
    markdown = ('---\nnoexport: true\n---\n' if controlled else '') + '# PRIVATE_TOC\nPRIVATE_BODY' + '\n来源正文。' * 100
    snapshot = source / 'data/raw/snapshots/controlled.md'
    snapshot.write_text(markdown)
    with sqlite3.connect(source / 'data/follow_builders.sqlite3') as db:
        db.execute('UPDATE source_versions SET snapshot_path=?,content_type=?,content_sha256=? WHERE id=1',
                   ('data/raw/snapshots/controlled.md', 'text/markdown', hashlib.sha256(markdown.encode()).hexdigest()))
    package = tmp_path / 'package'
    export_follow_builders(source, package, 'tenant', 'reader')
    store = OwnerPrivateBookshelfStore(tmp_path / 'store')
    store.import_package(package, 'tenant', 'reader', expected_current=None)
    book_id = json.loads((package / 'manifest.json').read_text())['sources'][0]['book_id']
    metadata, body = store.read_book('tenant', 'reader', book_id)
    assert 'PRIVATE_BODY' in json.dumps(body)
    assert metadata['_model_disclosure_controlled'] is controlled
    model = await gateway._model_book(metadata, body, frozenset())
    assert ('PRIVATE_BODY' in json.dumps(model)) is not controlled
