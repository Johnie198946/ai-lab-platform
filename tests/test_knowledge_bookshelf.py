from __future__ import annotations

import json

from backend.services.knowledge_catalog import bookshelf_catalog, clear_manifest_cache, reader_book_body


def test_bookshelf_only_exposes_public_and_owned_admitted_books(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "public.md").write_text(
        "---\ntitle: Public\nclassification_status: approved\nsecurity_level: green\n"
        "book_publication_authorized: true\nbook_title: Public Handbook\nbook_author: Editorial Team\n"
        "book_summary: A deliberately edited reader summary.\n---\n# Public\n\n"
        "A useful public summary with [[Evidence|a source]].\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "private.md").write_text(
        "---\nclassification_status: approved\nsecurity_level: red\nowner_tenant: tenant-a\n"
        "book_publication_authorized: true\nbook_title: Private Handbook\nbook_author: Private Team\n"
        "book_summary: Private approved summary.\n---\nPrivate body.", encoding="utf-8",
    )
    (tmp_path / "wiki" / "yellow.md").write_text(
        "---\nclassification_status: approved\nsecurity_level: yellow\nentitlement_key: knowledge/paid\n"
        "book_publication_authorized: true\nbook_title: Paid Handbook\nbook_author: Paid Team\n"
        "book_summary: Paid approved summary.\n---\nPaid body.", encoding="utf-8",
    )
    (tmp_path / "wiki" / "chat.md").write_text(
        "---\nclassification_status: approved\nsecurity_level: green\npublication_suitable: true\n"
        "book_publication_authorized: true\nbook_title: Chat\nbook_author: Bot\n"
        "book_summary: Generic green chat.\n---\nChat body.", encoding="utf-8",
    )
    (tmp_path / "wiki" / "spoof.md").write_text(
        "---\nclassification_status: approved\nsecurity_level: green\nsource_kind: publication\n"
        "book_title: Spoof\nbook_author: Attacker\nbook_summary: Metadata is not authority.\n---\nSpoof body.", encoding="utf-8",
    )
    (tmp_path / "knowledge_catalog.json").write_text(json.dumps({
        "version": "2.0",
        "packs": [{"category": "knowledge/public", "title": "Public shelf"}],
        "documents": [
            {
                "knowledge_id": "green", "path": "wiki/public.md", "title": "Public",
                "book_title": "Public Handbook", "book_author": "Editorial Team",
                "book_summary": "A deliberately edited reader summary.", "cover_theme": "methodology",
                "pack_id": "knowledge/public", "security_level": "green",
                "classification_status": "approved", "book_publication_authorized": True, "source_count": 2,
            },
            {"knowledge_id": "red", "path": "wiki/private.md", "pack_id": "knowledge/private", "security_level": "red", "classification_status": "approved", "book_publication_authorized": True, "owner_tenant": "tenant-a"},
            {"knowledge_id": "yellow", "path": "wiki/yellow.md", "pack_id": "knowledge/paid", "security_level": "yellow", "classification_status": "approved", "book_publication_authorized": True, "entitlement_key": "knowledge/paid"},
            {"knowledge_id": "chat", "path": "wiki/chat.md", "pack_id": "knowledge/public", "security_level": "green", "classification_status": "approved", "publication_suitable": True},
            {"knowledge_id": "spoof", "path": "wiki/spoof.md", "pack_id": "knowledge/public", "security_level": "green", "classification_status": "approved", "source_kind": "publication"},
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
    assert private["author"] == "Private Team"
    assert private["author_source"] == "editorial"
    assert private["summary"] == "Private approved summary."
    assert private["cover_theme"] == "private"
    assert {
        book["knowledge_id"] for shelf in bookshelf_catalog("tenant-b", tmp_path)
        for book in shelf["books"]
    } == {"green"}

    # Removing live publication approval revokes stale manifest admission.
    public_path = tmp_path / "wiki" / "public.md"
    public_path.write_text(
        public_path.read_text().replace("book_publication_authorized: true\n", "")
    )
    assert "green" not in {
        book["knowledge_id"] for shelf in bookshelf_catalog("tenant-a", tmp_path)
        for book in shelf["books"]
    }

    entitled = bookshelf_catalog(
        "tenant-a", tmp_path, frozenset({"knowledge/paid"})
    )
    assert {book["knowledge_id"] for shelf in entitled for book in shelf["books"]} == {
        "red", "yellow"
    }


def test_duplicate_declared_knowledge_ids_keep_distinct_book_identity(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    for name in ("a", "b"):
        (wiki / f"{name}.md").write_text(
            "---\nclassification_status: approved\nsecurity_level: green\n"
            f"book_publication_authorized: true\nbook_title: {name}\n"
            "book_author: Editorial\nbook_summary: Approved summary.\n---\n"
            f"# {name}\n", encoding="utf-8",
        )
    (tmp_path / "knowledge_catalog.json").write_text(json.dumps({
        "version": "2.0",
        "packs": [{"category": "knowledge/public", "title": "Public shelf"}],
        "documents": [
            {
                "knowledge_id": "duplicate-id", "path": f"wiki/{name}.md", "title": name,
                "pack_id": "knowledge/public", "security_level": "green",
                "classification_status": "approved", "book_publication_authorized": True,
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


def test_bookshelf_only_rechecks_explicit_admission_candidates(tmp_path, monkeypatch):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "admitted.md").write_text(
        "---\nclassification_status: approved\nsecurity_level: green\n"
        "book_publication_authorized: true\nbook_title: Admitted\n"
        "book_author: Editorial\nbook_summary: Approved summary.\n---\n# Admitted\n",
        encoding="utf-8",
    )
    (wiki / "blocked.md").write_text(
        "---\nclassification_status: approved\nsecurity_level: green\n"
        "publication_suitable: true\n---\n# Blocked\n", encoding="utf-8",
    )
    (tmp_path / "knowledge_catalog.json").write_text(json.dumps({
        "version": "2.0",
        "packs": [{"category": "knowledge/public", "title": "Public shelf"}],
        "documents": [
            {
                "knowledge_id": "admitted", "path": "wiki/admitted.md", "title": "Admitted",
                "pack_id": "knowledge/public", "security_level": "green",
                "classification_status": "approved", "book_publication_authorized": True,
            },
            {
                "knowledge_id": "blocked", "path": "wiki/blocked.md", "title": "Blocked",
                "pack_id": "knowledge/public", "security_level": "green",
                "classification_status": "approved",
            },
        ],
    }), encoding="utf-8")
    clear_manifest_cache()
    from backend.services import knowledge_catalog
    calls: list[str] = []
    original = knowledge_catalog._apply_file_read_barrier
    monkeypatch.setattr(
        knowledge_catalog, "_apply_file_read_barrier",
        lambda vault, item: calls.append(item["path"]) or original(vault, item),
    )

    books = [book for shelf in bookshelf_catalog("tenant-a", tmp_path) for book in shelf["books"]]

    assert [book["knowledge_id"] for book in books] == ["admitted"]
    assert calls == ["wiki/admitted.md"]


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
