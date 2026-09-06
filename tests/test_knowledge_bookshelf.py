from __future__ import annotations

import json

from backend.services.knowledge_catalog import bookshelf_catalog, clear_manifest_cache


def test_bookshelf_only_exposes_public_and_owned_admitted_books(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "public.md").write_text(
        "---\ntitle: Public\n---\n# Public\n\nA useful public summary with [[Evidence|a source]].\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "private.md").write_text("Private summary.", encoding="utf-8")
    (tmp_path / "wiki" / "yellow.md").write_text("Paid secret.", encoding="utf-8")
    (tmp_path / "knowledge_catalog.json").write_text(json.dumps({
        "version": "2.0",
        "packs": [{"category": "knowledge/public", "title": "Public shelf"}],
        "documents": [
            {
                "knowledge_id": "green", "path": "wiki/public.md", "title": "Public",
                "book_title": "Public Handbook", "book_author": "Editorial Team",
                "book_summary": "A deliberately edited reader summary.", "cover_theme": "methodology",
                "pack_id": "knowledge/public", "security_level": "green",
                "classification_status": "approved", "source_count": 2,
            },
            {"knowledge_id": "red", "path": "wiki/private.md", "title": "Private", "cover_theme": "../evil", "pack_id": "knowledge/private", "security_level": "red", "classification_status": "approved", "owner_tenant": "tenant-a"},
            {"knowledge_id": "yellow", "path": "wiki/yellow.md", "title": "Paid", "pack_id": "knowledge/paid", "security_level": "yellow", "classification_status": "approved"},
        ],
    }), encoding="utf-8")
    clear_manifest_cache()

    shelves = bookshelf_catalog("tenant-a", tmp_path)

    books = [book for shelf in shelves for book in shelf["books"]]
    assert {book["id"] for book in books} == {"green", "red"}
    public = next(book for book in books if book["id"] == "green")
    private = next(book for book in books if book["id"] == "red")
    assert public["title"] == "Public Handbook"
    assert public["author"] == "Editorial Team"
    assert public["summary"] == "A deliberately edited reader summary."
    assert public["cover_theme"] == "methodology"
    assert public["cover_version"] == 1
    assert 0 <= public["cover_variant"] < 6
    assert private["author"] == "Quantum 研究团队"
    assert private["author_source"] == "fallback"
    assert private["summary"] == "Private summary."
    assert private["cover_theme"] == "general"

    entitled = bookshelf_catalog(
        "tenant-a", tmp_path, frozenset({"knowledge/paid"})
    )
    assert {book["id"] for shelf in entitled for book in shelf["books"]} == {
        "green", "red", "yellow"
    }
