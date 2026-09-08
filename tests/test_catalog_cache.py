from types import SimpleNamespace

from sqlalchemy import URL

from backend.api import catalog as catalog_api


def test_compute_catalog_caches_by_vault_version(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(catalog_api.knowledge, "_vault", lambda: tmp_path)
    monkeypatch.setattr(
        catalog_api,
        "_compute_catalog",
        lambda vault: calls.append(vault) or [{"category": "wiki", "revision": len(calls)}],
    )
    monkeypatch.setattr(catalog_api, "_catalog_cache", None)

    first = catalog_api.compute_catalog()
    second = catalog_api.compute_catalog()

    assert first == second
    assert len(calls) == 1

    (tmp_path / "knowledge_matrix.json").write_text('{"version": 2}', encoding="utf-8")
    third = catalog_api.compute_catalog()

    assert third[0]["revision"] == 2
    assert len(calls) == 2


def test_projection_sync_forwards_unredacted_database_url_object(monkeypatch):
    import backend.db as db
    import backend.services.knowledge_catalog as catalog
    import sqlalchemy.ext.asyncio as sqlalchemy_asyncio

    url = URL.create(
        "postgresql+asyncpg", username="catalog", password="opaque-test-value",
        host="database.invalid", database="knowledge",
    )
    forwarded = []

    def intercept(value, **_kwargs):
        forwarded.append(value)
        raise RuntimeError("network disabled by test")

    monkeypatch.setattr(db, "engine", SimpleNamespace(url=url))
    monkeypatch.setattr(sqlalchemy_asyncio, "create_async_engine", intercept)
    assert catalog._projection_rows_sync([]) is None
    assert forwarded == [url]
    assert forwarded[0].password == url.password
