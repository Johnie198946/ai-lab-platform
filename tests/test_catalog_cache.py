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
