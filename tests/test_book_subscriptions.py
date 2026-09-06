from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api import subscriptions
from backend.db import Base
from backend.models.tenant import KnowledgeBookSubscription


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


def run(coro):
    return asyncio.run(coro)


def test_book_writes_accept_build_16_camel_case_payloads():
    subscription = subscriptions.BookSubscriptionWrite.model_validate(
        {"bookId": BOOK["id"], "edition": 2}
    )
    progress = subscriptions.BookProgressWrite.model_validate(
        {"bookId": BOOK["id"], "progress": 0.42}
    )

    assert subscription.book_id == BOOK["id"]
    assert subscription.edition == 2
    assert progress.book_id == BOOK["id"]


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
    yield
    run(engine.dispose())


def test_book_subscription_lifecycle_is_user_scoped(book_db):
    body = subscriptions.BookSubscriptionWrite(book_id=BOOK["id"])
    first = run(subscriptions.subscribe_book(body, AUTH))
    duplicate = run(subscriptions.subscribe_book(body, AUTH))
    mine = run(subscriptions.my_book_subscriptions(AUTH))
    other = run(subscriptions.my_book_subscriptions({**AUTH, "user_id": "reader-2"}))
    progressed = run(subscriptions.update_book_progress(
        subscriptions.BookProgressWrite(book_id=BOOK["id"], progress=0.42), AUTH
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


def test_unavailable_book_cannot_be_subscribed(book_db, monkeypatch):
    monkeypatch.setattr(subscriptions, "bookshelf_catalog", lambda *_args, **_kwargs: [])

    with pytest.raises(HTTPException) as error:
        run(subscriptions.subscribe_book(
            subscriptions.BookSubscriptionWrite(book_id="restricted-book"), AUTH
        ))

    assert error.value.status_code == 404
    assert error.value.detail["code"] == "book_not_found"
