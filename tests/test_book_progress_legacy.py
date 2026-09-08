"""HTTP regression for the pre-version Swift book_id/progress payload."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.api import subscriptions
from backend.db import _migrate_book_subscription_version
from test_book_subscriptions import AUTH, BODY, BOOK, VERSION, run

pytest_plugins = ("test_book_subscriptions",)


@pytest.fixture
def client(book_db):
    app = FastAPI()
    app.include_router(subscriptions.router)
    app.dependency_overrides[subscriptions.require_auth] = lambda: AUTH
    with TestClient(app) as client:
        yield client


def subscribe(client):
    response = client.put('/api/v1/me/book-subscriptions', json={'book_id': BOOK['id'], 'edition': 9})
    assert response.status_code == 200
    return response.json()


def save(client, progress, **extra):
    return client.patch('/api/v1/me/book-subscriptions/progress', json={
        'book_id': BOOK['id'], 'progress': progress, **extra,
    })


def current(client):
    return client.get('/api/v1/me/book-subscriptions').json()['subscriptions'][0]


def test_actual_old_swift_payload_persists_without_relabelling(client):
    subscribe(client)
    assert save(client, .6, content_version=VERSION).status_code == 200
    before = current(client)
    response = save(client, .42)
    assert response.status_code == 200
    saved = response.json()
    # All fields decoded by the old KnowledgeBookSubscriptionDTO remain present.
    assert {'book', 'edition', 'progress', 'subscribed_at', 'last_read_at'} <= saved.keys()
    assert saved['progress'] == .42
    assert saved['content_version'] == ''
    assert saved['progress_scope'] == 'legacy_unversioned'
    assert saved['canonical_progress'] == .6
    after = current(client)
    for field in ['progress', 'edition', 'content_version', 'last_read_at']:
        assert after[field] == before[field]
    assert after['legacy_progress'] == .42
    assert after['legacy_last_read_at']
    # Backwards reading is legitimate, do not apply a synthetic max().
    assert save(client, .2).json()['progress'] == .2
    assert save(client, .8, content_version=VERSION).status_code == 200
    assert current(client)['legacy_progress'] == .2
    assert current(client)['progress'] == .8


def test_old_offline_edition_never_overwrites_new_position(client, monkeypatch):
    subscribe(client)
    assert save(client, .7).status_code == 200

    async def changed(*_):
        return BOOK, {**BODY, 'content_version': 'b' * 64}
    monkeypatch.setattr(subscriptions, '_available_book_body', changed)
    assert subscribe(client)['edition'] == 2
    assert save(client, .3, content_version='b' * 64).status_code == 200
    before = current(client)
    assert save(client, .95).status_code == 200
    after = current(client)
    assert after['legacy_progress'] == .95
    assert all(after[k] == before[k] for k in ['progress', 'edition', 'content_version', 'last_read_at'])
    assert save(client, .9, content_version=VERSION).status_code == 409


@pytest.mark.parametrize('extra', [{'content_version': None}, {'content_version': ''}, {'content_version': 'G' * 64}, {'content_version': 'a' * 63}])
def test_explicit_bad_version_is_not_treated_as_legacy(client, extra):
    subscribe(client)
    assert save(client, .4, **extra).status_code == 422
    assert current(client)['legacy_progress'] is None


@pytest.mark.parametrize('progress', [-.1, 1.1])
def test_legacy_range_is_still_validated(client, progress):
    subscribe(client)
    assert save(client, progress).status_code == 422


def test_legacy_unsubscribed_and_revoked_fail_closed(client, monkeypatch):
    assert save(client, .5).status_code == 404
    subscribe(client)
    monkeypatch.setattr(subscriptions, 'bookshelf_catalog', lambda *_, **__: [])
    assert save(client, .5).status_code == 404


@pytest.mark.parametrize('identity', [{**AUTH, 'user_id': 'reader-2'}, {**AUTH, 'tenant_key': 'tenant-b'}])
def test_legacy_identity_cannot_write_someone_elses_checkpoint(client, identity):
    subscribe(client)
    client.app.dependency_overrides[subscriptions.require_auth] = lambda: identity
    assert save(client, .9).status_code == 404
    client.app.dependency_overrides[subscriptions.require_auth] = lambda: AUTH
    assert current(client)['legacy_progress'] is None


def test_additive_migration_preserves_unversioned_position_idempotently(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE knowledge_book_subscriptions (book_id TEXT PRIMARY KEY, progress REAL, last_read_at DATETIME)')
        connection.exec_driver_sql("INSERT INTO knowledge_book_subscriptions VALUES ('old', 0.7, '2026-01-01 00:00:00')")
        _migrate_book_subscription_version(connection)
        _migrate_book_subscription_version(connection)
        row = connection.execute(text('SELECT * FROM knowledge_book_subscriptions')).mappings().one()
        assert row['progress'] == row['legacy_progress'] == .7
        assert row['content_version'] == ''
        assert row['legacy_last_read_at'] == row['last_read_at']
        connection.exec_driver_sql("UPDATE knowledge_book_subscriptions SET content_version = 'a', progress = .1")
        _migrate_book_subscription_version(connection)
        assert connection.exec_driver_sql('SELECT legacy_progress FROM knowledge_book_subscriptions').scalar() == .7
    engine.dispose()
