from __future__ import annotations

import json

from backend.services.knowledge_catalog import bookshelf_catalog, clear_manifest_cache, reader_book_body


def test_bookshelf_only_exposes_public_and_owned_admitted_books(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "public.md").write_text(
        "---\ntitle: Public\nbook_title: Public Handbook\nbook_author: Editorial Team\n"
        "book_summary: A deliberately edited reader summary.\n---\n# Public\n\n"
        "A useful public summary with [[Evidence|a source]].\n",
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
    assert {book["knowledge_id"] for book in books} == {"green", "red"}
    assert len({book["id"] for book in books}) == 2
    public = next(book for book in books if book["knowledge_id"] == "green")
    private = next(book for book in books if book["knowledge_id"] == "red")
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

    # Removing source metadata must revoke it without rebuilding the catalog.
    (tmp_path / "wiki" / "public.md").write_text("# Public\n\nSafe replacement.\n")
    refreshed = next(
        book for shelf in bookshelf_catalog("tenant-a", tmp_path)
        for book in shelf["books"] if book["knowledge_id"] == "green"
    )
    assert refreshed["summary"] == "Safe replacement."
    assert refreshed["title"] != "Public Handbook"
    assert refreshed["author"] != "Editorial Team"

    entitled = bookshelf_catalog(
        "tenant-a", tmp_path, frozenset({"knowledge/paid"})
    )
    assert {book["knowledge_id"] for shelf in entitled for book in shelf["books"]} == {
        "green", "red", "yellow"
    }


def test_duplicate_declared_knowledge_ids_keep_distinct_book_identity(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    for name in ("a", "b"):
        (wiki / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    (tmp_path / "knowledge_catalog.json").write_text(json.dumps({
        "version": "2.0",
        "packs": [{"category": "knowledge/public", "title": "Public shelf"}],
        "documents": [
            {
                "knowledge_id": "duplicate-id", "path": f"wiki/{name}.md", "title": name,
                "pack_id": "knowledge/public", "security_level": "green",
                "classification_status": "approved",
            }
            for name in ("a", "b")
        ],
    }), encoding="utf-8")
    clear_manifest_cache()

    books = [
        book
        for shelf in bookshelf_catalog("tenant-a", tmp_path)
        for book in shelf["books"]
    ]

    assert [book["knowledge_id"] for book in books] == ["duplicate-id", "duplicate-id"]
    assert len({book["id"] for book in books}) == 2
    assert {book["source_path"] for book in books} == {"wiki/a.md", "wiki/b.md"}


def test_reader_sections_preserve_empty_headings_and_ignore_fenced_hashes():
    result = reader_book_body(
        {"id": "book-1", "title": "Book", "author": "Author"},
        {
            "version": "a" * 64,
            "citation": "knowledge:wiki/book.md",
            "content": "# Parent\n## Child\nFacts [source](https://example.com/x).\n```\n# code\n```",
        },
    )

    assert result is not None
    assert [section["title"] for section in result["sections"]] == ["Parent", "Child"]
    assert result["sections"][0]["markdown"] == ""
    assert "# code" in result["sections"][1]["markdown"]
    assert "https://" not in result["sections"][1]["markdown"]
    assert "Facts source." in result["sections"][1]["markdown"]
