from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api import subscriptions
from backend.db import Base
from backend.models.tenant import KnowledgeBookSubscription, KnowledgeSeriesSubscription


AUTH = {
    "tenant_key": "tenant-a",
    "user_id": "reader-1",
    "visible_categories": frozenset({"knowledge/product/public"}),
}
BOOK = {
    "id": "wiki/product/ai-map",
    "title": "AI 产品全景图",
    "author": "Quantum 研究团队",
    "summary": "理解 AI 产品的完整结构。",
    "cover_theme": "product",
    "cover_variant": 1,
    "cover_version": 1,
    "security_level": "green",
    "knowledge_level": "K5",
    "freshness": "current",
    "source_count": 18,
}
VERSION = "a" * 64
BODY = {
    "book_id": BOOK["id"], "title": BOOK["title"], "author": BOOK["author"],
    "content_version": VERSION, "edition": 1, "citation": "knowledge:wiki/product.md",
    "sections": [{"id": "section-1", "title": "正文", "level": 1, "markdown": "内容"}],
}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def book_db(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'books.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    run(setup())
    monkeypatch.setattr(subscriptions, "SessionLocal", maker)
    monkeypatch.setattr(
        subscriptions,
        "bookshelf_catalog",
        lambda *_args, **_kwargs: [{
            "id": "knowledge/product/public",
            "title": "产品与方案",
            "security_level": "green",
            "book_count": 1,
            "books": [BOOK],
        }],
    )
    async def available_body(_payload, _book_id):
        book = (await subscriptions._available_books(_payload)).get(_book_id)
        if book is None:
            raise subscriptions._error(
                404, code="book_not_found", message="unavailable",
                action="refresh_catalog", retryable=True,
            )
        return book, BODY
    monkeypatch.setattr(subscriptions, "_available_book_body", available_body)
    yield
    run(engine.dispose())


def test_book_subscription_lifecycle_is_user_scoped(book_db):
    body = subscriptions.BookSubscriptionWrite(book_id=BOOK["id"])
    first = run(subscriptions.subscribe_book(body, AUTH))
    duplicate = run(subscriptions.subscribe_book(body, AUTH))
    mine = run(subscriptions.my_book_subscriptions(AUTH))
    other = run(subscriptions.my_book_subscriptions({**AUTH, "user_id": "reader-2"}))
    progressed = run(subscriptions.update_book_progress(
        subscriptions.BookProgressWrite(
            book_id=BOOK["id"], progress=0.42, content_version=VERSION
        ), AUTH
    ))
    removed = run(subscriptions.unsubscribe_book(body, AUTH))

    assert first["book"]["title"] == "AI 产品全景图"
    assert duplicate["book"]["id"] == BOOK["id"]
    assert len(mine["subscriptions"]) == 1
    assert other["subscriptions"] == []
    assert progressed["progress"] == pytest.approx(0.42)
    assert removed == {"book_id": BOOK["id"], "deleted": True}
    assert run(subscriptions.my_book_subscriptions(AUTH))["subscriptions"] == []


def test_concurrent_duplicate_puts_are_idempotent(book_db):
    body = subscriptions.BookSubscriptionWrite(book_id=BOOK["id"])

    async def race():
        return await asyncio.gather(
            *(subscriptions.subscribe_book(body, AUTH) for _ in range(20))
        )

    results = run(race())

    async def count_rows():
        async with subscriptions.SessionLocal() as db:
            return await db.scalar(select(func.count()).select_from(KnowledgeBookSubscription))

    assert len(results) == 20
    assert all(item["book"]["id"] == BOOK["id"] for item in results)
    assert run(count_rows()) == 1


def test_edition_change_resets_old_progress(book_db, monkeypatch):
    body = subscriptions.BookSubscriptionWrite(book_id=BOOK["id"])
    run(subscriptions.subscribe_book(body, AUTH))
    run(subscriptions.update_book_progress(subscriptions.BookProgressWrite(
        book_id=BOOK["id"], progress=0.8, content_version=VERSION
    ), AUTH))
    changed = {**BODY, "content_version": "b" * 64}

    async def changed_body(_payload, _book_id):
        return BOOK, changed
    monkeypatch.setattr(subscriptions, "_available_book_body", changed_body)

    refreshed = run(subscriptions.subscribe_book(body, AUTH))
    assert refreshed["edition"] == 2
    assert refreshed["progress"] == 0


def test_unavailable_book_cannot_be_subscribed(book_db, monkeypatch):
    monkeypatch.setattr(subscriptions, "bookshelf_catalog", lambda *_args, **_kwargs: [])

    with pytest.raises(HTTPException) as error:
        run(subscriptions.subscribe_book(
            subscriptions.BookSubscriptionWrite(book_id="restricted-book"), AUTH
        ))

    assert error.value.status_code == 404
    assert error.value.detail["code"] == "book_not_found"


def test_series_subscription_automatically_projects_latest_daily_issue(book_db, monkeypatch):
    first = {**BOOK, "id": "publication-day-1", "series_id": "ai-history",
             "issue_date": "2026-09-08", "content_version": "a" * 64}
    second = {**BOOK, "id": "publication-day-2", "series_id": "ai-history",
              "issue_date": "2026-09-09", "content_version": "b" * 64}
    current = [first]
    monkeypatch.setattr(subscriptions, "bookshelf_catalog", lambda *_args, **_kwargs: [{
        "id": "knowledge/publication/public", "title": "每日连载", "security_level": "green",
        "book_count": 1, "books": current,
    }])

    async def body(_payload, book_id):
        book = next(item for item in current if item["id"] == book_id)
        return book, {**BODY, "book_id": book_id, "content_version": book["content_version"]}
    monkeypatch.setattr(subscriptions, "_available_book_body", body)

    run(subscriptions.subscribe_book(subscriptions.BookSubscriptionWrite(book_id=first["id"]), AUTH))
    run(subscriptions.update_book_progress(subscriptions.BookProgressWrite(
        book_id=first["id"], progress=0.8, content_version="a" * 64
    ), AUTH))
    current[:] = [first, second]
    latest = run(subscriptions.my_book_subscriptions(AUTH))["subscriptions"][0]
    assert latest["book"]["id"] == second["id"]
    assert latest["edition"] == 1
    assert latest["progress"] == 0
    updated = run(subscriptions.update_book_progress(subscriptions.BookProgressWrite(
        book_id=second["id"], progress=0.25, content_version="b" * 64
    ), AUTH))
    assert updated["book"]["id"] == second["id"]
    assert updated["content_version"] == "b" * 64
    assert updated["progress"] == pytest.approx(0.25)

    async def checkpoints():
        async with subscriptions.SessionLocal() as db:
            rows = (await db.execute(select(KnowledgeBookSubscription))).scalars().all()
            follows = (await db.execute(select(KnowledgeSeriesSubscription))).scalars().all()
            return {row.book_id: row.progress for row in rows}, follows

    progress, follows = run(checkpoints())
    assert progress == {first["id"]: pytest.approx(0.8), second["id"]: pytest.approx(0.25)}
    assert len(follows) == 1


def test_concurrent_different_issue_subscriptions_keep_two_progress_rows_one_follow(book_db, monkeypatch):
    books = [
        {**BOOK, "id": "publication-day-1", "series_id": "ai-history", "issue_date": "2026-09-08", "content_version": "a" * 64},
        {**BOOK, "id": "publication-day-2", "series_id": "ai-history", "issue_date": "2026-09-09", "content_version": "b" * 64},
    ]
    monkeypatch.setattr(subscriptions, "bookshelf_catalog", lambda *_args, **_kwargs: [{
        "id": "knowledge/publication/public", "title": "每日连载", "security_level": "green", "book_count": 2, "books": books,
    }])

    async def body(_payload, book_id):
        book = next(item for item in books if item["id"] == book_id)
        return book, {**BODY, "book_id": book_id, "content_version": book["content_version"]}
    monkeypatch.setattr(subscriptions, "_available_book_body", body)

    async def race():
        return await asyncio.gather(*(subscriptions.subscribe_book(subscriptions.BookSubscriptionWrite(book_id=item["id"]), AUTH) for item in books))
    run(race())

    async def counts():
        async with subscriptions.SessionLocal() as db:
            return (
                await db.scalar(select(func.count()).select_from(KnowledgeBookSubscription)),
                await db.scalar(select(func.count()).select_from(KnowledgeSeriesSubscription)),
            )
    assert run(counts()) == (2, 1)

    books[:] = [books[1]]  # first issue was withdrawn; its row still identifies the followed series.
    assert run(subscriptions.unsubscribe_book(subscriptions.BookSubscriptionWrite(book_id="publication-day-1"), AUTH))["deleted"] is True
    assert run(subscriptions.my_book_subscriptions(AUTH))["subscriptions"] == []


def _unread_latest(monkeypatch):
    first = {**BOOK, "id": "publication-test-first", "series_id": "ai-history",
             "issue_date": "2026-09-07", "content_version": "a" * 64}
    second = {**BOOK, "id": "publication-test-second", "series_id": "ai-history",
              "issue_date": "2026-09-08", "content_version": "b" * 64}
    current = [first]
    monkeypatch.setattr(subscriptions, "bookshelf_catalog", lambda *_args, **_kwargs: [{
        "id": "knowledge/publication/public", "title": "每日连载", "security_level": "green",
        "book_count": len(current), "books": current,
    }])

    async def body(_payload, book_id):
        book = next(item for item in current if item["id"] == book_id)
        return book, {**BODY, "book_id": book_id, "content_version": book["content_version"]}

    monkeypatch.setattr(subscriptions, "_available_book_body", body)
    return first, second, current


def test_unsubscribe_unread_latest_issue_removes_follow_but_keeps_issue_progress(book_db, monkeypatch):
    first, second, current = _unread_latest(monkeypatch)
    run(subscriptions.subscribe_book(subscriptions.BookSubscriptionWrite(book_id=first["id"]), AUTH))
    current.append(second)

    removed = run(subscriptions.unsubscribe_book(
        subscriptions.BookSubscriptionWrite(book_id=second["id"]), AUTH
    ))

    async def rows():
        async with subscriptions.SessionLocal() as db:
            return (
                (await db.execute(select(KnowledgeBookSubscription))).scalars().all(),
                (await db.execute(select(KnowledgeSeriesSubscription))).scalars().all(),
            )

    progress, follows = run(rows())
    assert removed == {"book_id": second["id"], "deleted": True}
    assert run(subscriptions.my_book_subscriptions(AUTH))["subscriptions"] == []
    assert [row.book_id for row in progress] == [first["id"]]
    assert follows == []


def test_unsubscribe_withdrawn_unread_latest_uses_stored_publication_metadata(book_db, monkeypatch):
    first, second, current = _unread_latest(monkeypatch)
    run(subscriptions.subscribe_book(subscriptions.BookSubscriptionWrite(book_id=first["id"]), AUTH))
    current[:] = [first]

    class Store:
        def status(self, publication_id):
            return ([{"publication_id": second["id"], "series_id": "ai-history", "state": "withdrawn"}]
                    if publication_id == second["id"] else [])

    monkeypatch.setattr(subscriptions, "PublicationStore", Store)
    assert run(subscriptions.unsubscribe_book(
        subscriptions.BookSubscriptionWrite(book_id="publication-unknown"), AUTH
    ))["deleted"] is False
    assert len(run(subscriptions.my_book_subscriptions(AUTH))["subscriptions"]) == 1
    assert run(subscriptions.unsubscribe_book(
        subscriptions.BookSubscriptionWrite(book_id=second["id"]), AUTH
    ))["deleted"] is True
    assert run(subscriptions.my_book_subscriptions(AUTH))["subscriptions"] == []


def test_unsubscribe_unread_latest_issue_is_user_scoped(book_db, monkeypatch):
    first, second, current = _unread_latest(monkeypatch)
    other = {**AUTH, "user_id": "reader-2"}
    body = subscriptions.BookSubscriptionWrite(book_id=first["id"])
    run(subscriptions.subscribe_book(body, AUTH))
    run(subscriptions.subscribe_book(body, other))
    current.append(second)

    assert run(subscriptions.unsubscribe_book(
        subscriptions.BookSubscriptionWrite(book_id=second["id"]), AUTH
    ))["deleted"] is True
    assert run(subscriptions.my_book_subscriptions(AUTH))["subscriptions"] == []
    assert run(subscriptions.my_book_subscriptions(other))["subscriptions"][0]["book"]["id"] == second["id"]
