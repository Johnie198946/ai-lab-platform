"""HTTP/DTO continuity checks across the existing publication reader path."""
from backend.api.knowledge_publication import SerialBundle
from backend.api.subscriptions import _public_book
from backend.services.knowledge_catalog import publication_book
from backend.services.knowledge_publication_store import PublicationStore
from test_daily_publication import at, bundle, ready


def test_new_contract_survives_admin_dto_and_public_projection(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    parsed = SerialBundle.model_validate(value).model_dump(exclude_none=True)
    assert parsed['quality_contract'] == value['quality_contract']
    assert parsed['editorial_proof_sha256'] == value['editorial_proof_sha256']
    store.stage(parsed, now=at(10))
    store.release_due(now=at(12))
    items = store.published(now=at(12))
    assert len(items) == 1
    public = _public_book(publication_book(items[0]))
    assert public['publication_format'] == 'chapter'
    assert public['publication_type_label'] == '科普 · 连载章节'
    assert public['content_version'] == value['body_hash']
    assert public['test_serial'] is True


def test_optional_contract_absence_remains_absence_in_http_dto(tmp_path):
    value = ready(PublicationStore(tmp_path), bundle(), editorial=False)
    parsed = SerialBundle.model_validate(value).model_dump(exclude_none=True)
    assert 'quality_contract' not in parsed
    assert 'editorial_proof_file' not in parsed
    assert 'editorial_proof_sha256' not in parsed


def test_public_source_dto_does_not_lose_explicit_unreadable_state():
    value = {'id':'source-1','publication_format':'source','publication_type_label':'来源元数据',
             'readable':False,'content_status':'metadata_only','canonical_url':'https://example.org/source',
             'review_private_note':'never public'}
    projected = _public_book(value)
    assert projected['readable'] is False
    assert projected['publication_format'] == 'source'
    assert projected['canonical_url'] == value['canonical_url']
    assert 'review_private_note' not in projected
