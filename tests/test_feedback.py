from __future__ import annotations

import asyncio
import hashlib
import inspect
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, delete, inspect as sa_inspect, select

from backend.db import SessionLocal, _migrate_feedback_digest_columns
from backend.models.feedback import FeedbackDigestRun, FeedbackEvent
from backend.services.feedback import (
    FeedbackReceipt,
    acknowledge_feedback_digest,
    capture_feedback,
    classify_feedback,
    prepare_feedback_digest,
    render_digest,
    sanitize_excerpt,
)


@pytest.mark.parametrize(
    "message",
    [
        "这个功能太难用了，每次都找不到入口",
        "我要反馈一个问题：上传文件后一直没反应",
        "为什么回答总是答非所问",
        "能不能支持导出 Excel，这里现在根本不能用",
    ],
)
def test_feedback_classifier_accepts_product_complaints(message):
    signal = classify_feedback(message)
    assert signal.matched is True
    assert signal.score >= 4


@pytest.mark.parametrize(
    "message",
    [
        "这个功能怎么用？",
        "这个功能没有不好用，只是我还不熟悉",
        "以前很慢，现在已经好了",
        "同事说这个功能很垃圾，但我觉得还可以",
        "请分析用户为什么会说‘这个功能太难用了’",
        "我今天有点烦",
        "我无法理解量子纠缠，请解释一下",
    ],
)
def test_feedback_classifier_rejects_nearby_non_complaints(message):
    assert classify_feedback(message).matched is False


def test_feedback_sanitizes_secrets_and_pii():
    token = "sk-" + "abcdefghijklmnop"
    aws_key = "AKIA" + "IOSFODNN7EXAMPLE"
    azure_key = "AbCdEf0123456789" + "+/=="
    value = sanitize_excerpt(
        f"太差了，联系 13812345678 或 a@example.com，token {token}，"
        "身份证 110101199001011234，银行卡 6222020202020202，https://x.test?a=secret，"
        f"AWS {aws_key}，IP 192.168.1.10，IPv6 2001:db8::1 和 fe80::a%en0，"
        f"微信 abc_123456，Azure密钥 {azure_key}"
    )
    assert "13812345678" not in value
    assert "a@example.com" not in value
    assert token not in value
    assert "110101199001011234" not in value
    assert "6222020202020202" not in value
    assert "a=secret" not in value
    assert aws_key not in value
    assert "192.168.1.10" not in value
    assert "2001:db8::1" not in value
    assert "fe80::a%en0" not in value
    assert "abc_123456" not in value
    assert azure_key not in value
    assert "已脱敏" in value


@pytest.mark.asyncio
async def test_capture_is_idempotent_and_tenant_scoped(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-test-key")
    async with SessionLocal() as db:
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    kwargs = {
        "auth_payload": {"tenant_key": "tenant-a", "user_id": "user-a"},
        "request_id": "request-fixed-001",
        "session_id": "session-a",
        "surface": "ios",
    }
    first = await capture_feedback("这个功能太难用了，每次都失败", **kwargs)
    second = await capture_feedback("这个功能太难用了，每次都失败", **kwargs)
    other = await capture_feedback(
        "这个功能太难用了，每次都失败",
        auth_payload={"tenant_key": "tenant-b", "user_id": "user-a"},
        request_id="request-fixed-001",
        session_id="session-a",
    )
    assert first and second and other
    assert first.feedback_id == second.feedback_id
    assert first.feedback_id != other.feedback_id
    async with SessionLocal() as db:
        rows = (await db.execute(select(FeedbackEvent))).scalars().all()
    assert len(rows) == 2
    assert {row.tenant_key for row in rows} == {"tenant-a", "tenant-b"}
    assert all("user-a" not in row.user_ref for row in rows)
    assert all(row.content_hash != hashlib.sha256("这个功能太难用了，每次都失败".encode()).hexdigest() for row in rows)


@pytest.mark.asyncio
async def test_capture_fails_closed_without_hmac_key(monkeypatch):
    monkeypatch.delenv("FEEDBACK_HMAC_KEY", raising=False)
    monkeypatch.delenv("AUTHEN_JWT_SECRET", raising=False)
    receipt = await capture_feedback(
        "我要反馈：这个功能总是报错",
        auth_payload={"tenant_key": "t", "sub": "u"},
        request_id="missing-key",
        session_id="s",
    )
    assert receipt is None


@pytest.mark.asyncio
async def test_capture_folds_same_content_with_new_request_id(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-fold-key")
    async with SessionLocal() as db:
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    payload = {"tenant_key": "feedback-fold", "sub": "user-fold"}
    first = await capture_feedback(
        "这个功能总是报错，真的很不好用",
        auth_payload=payload,
        request_id="fold-a",
        session_id="session-a",
    )
    second = await capture_feedback(
        "这个功能总是报错，真的很不好用",
        auth_payload=payload,
        request_id="fold-b",
        session_id="session-a",
    )
    assert first is not None and second is not None
    assert first.feedback_id == second.feedback_id


@pytest.mark.asyncio
async def test_capture_rate_limits_variant_spam_per_user(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-rate-key")
    async with SessionLocal() as db:
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    payload = {"tenant_key": "feedback-rate", "sub": "user-rate"}
    first = await capture_feedback(
        "这个功能总是报错，真的很不好用",
        auth_payload=payload,
        request_id="rate-0",
        session_id="session-rate",
    )
    assert first is not None
    async with SessionLocal() as db:
        anchor = await db.get(FeedbackEvent, int(first.feedback_id))
        assert anchor is not None
        for index in range(1, 50):
            db.add(FeedbackEvent(
                tenant_key=anchor.tenant_key,
                user_ref=anchor.user_ref,
                session_ref=anchor.session_ref,
                request_id=f"rate-{index}",
                content_hash=f"{index:064x}",
                sanitized_excerpt=f"变体 {index}",
                signal_type="inferred",
                category="reliability",
                severity="medium",
                score=6,
            ))
        await db.commit()
    blocked = await capture_feedback(
        "这个上传功能又报错了，还是很不好用",
        auth_payload=payload,
        request_id="rate-51",
        session_id="session-rate",
    )
    assert blocked is None


@pytest.mark.asyncio
async def test_concurrent_reconnects_collapse_at_database_boundary(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-race-key")
    async with SessionLocal() as db:
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    payload = {"tenant_key": "feedback-race", "sub": "user-race"}
    receipts = await asyncio.gather(*[
        capture_feedback(
            "我要反馈：上传功能每次都报错",
            auth_payload=payload,
            request_id=f"race-{index}",
            session_id="session-race",
        )
        for index in range(4)
    ])
    assert all(item is not None for item in receipts)
    assert len({item.feedback_id for item in receipts if item}) == 1


@pytest.mark.asyncio
async def test_inferred_feedback_drops_text_and_chat_command_revokes(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-revoke-key")
    async with SessionLocal() as db:
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    payload = {"tenant_key": "feedback-revoke", "sub": "user-revoke"}
    captured = await capture_feedback(
        "这个功能总是报错，真的很不好用",
        auth_payload=payload,
        request_id="revoke-1",
        session_id="session-revoke",
    )
    assert captured is not None and captured.revocable is True
    async with SessionLocal() as db:
        row = await db.get(FeedbackEvent, int(captured.feedback_id))
        assert row is not None
        assert row.sanitized_excerpt == "[推断型抱怨信号；未保留用户原文]"
    revoked = await capture_feedback(
        "撤销刚才的反馈",
        auth_payload=payload,
        request_id="revoke-2",
        session_id="session-revoke",
    )
    assert revoked is not None and revoked.signal_type == "revoked"
    async with SessionLocal() as db:
        row = await db.get(FeedbackEvent, int(captured.feedback_id))
        assert row is not None and row.revoked_at is not None


def test_digest_is_deterministic_and_reports_exact_counts():
    events = [
        FeedbackEvent(
            tenant_key="a", user_ref="u1", session_ref="s1", request_id="r1",
            content_hash="1" * 64, sanitized_excerpt="上传后一直没反应",
            signal_type="inferred", category="reliability", severity="high", score=8,
        ),
        FeedbackEvent(
            tenant_key="b", user_ref="u2", session_ref="s2", request_id="r2",
            content_hash="2" * 64, sanitized_excerpt="入口太难找",
            signal_type="inferred", category="usability", severity="medium", score=7,
        ),
    ]
    first = render_digest(events, "2026-08-29")
    assert first == render_digest(events, "2026-08-29")
    assert "新增抱怨：2 条" in first
    assert "涉及用户：2 人" in first
    assert "涉及租户：2 个" in first
    assert "未调用模型" in first
    assert "上传后一直没反应" not in first
    assert "日报不包含任何用户原文" in first


def test_postgres_digest_lock_is_transaction_scoped_contract():
    source = inspect.getsource(prepare_feedback_digest)
    assert "pg_try_advisory_xact_lock" in source
    assert "pg_try_advisory_lock" not in source.replace("pg_try_advisory_xact_lock", "")
    assert "async with db.begin()" in source


def test_feedback_digest_payload_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE feedback_digest_runs (digest_date DATE PRIMARY KEY, payload_hash VARCHAR(64))"
        )
        _migrate_feedback_digest_columns(connection)
        _migrate_feedback_digest_columns(connection)
        columns = {
            item["name"] for item in sa_inspect(connection).get_columns("feedback_digest_runs")
        }
        assert "payload_content" in columns


def test_postgres_startup_migration_serializes_and_is_idempotent():
    import backend.db as database

    init_source = inspect.getsource(database.init_db)
    migration_source = inspect.getsource(database._migrate_feedback_digest_columns)
    assert "pg_advisory_xact_lock" in init_source
    assert "ADD COLUMN IF NOT EXISTS payload_content" in migration_source


@pytest.mark.asyncio
async def test_daily_digest_freezes_until_local_delivery_ack(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-digest-key")

    async with SessionLocal() as db:
        await db.execute(delete(FeedbackDigestRun))
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    receipt = await capture_feedback(
        "我要反馈一个问题：这个功能总是失败",
        auth_payload={"tenant_key": "digest-tenant", "user_id": "digest-user"},
        request_id="digest-request-001",
        session_id="digest-session",
    )
    assert receipt is not None
    now = datetime.now(timezone.utc) + timedelta(days=1, minutes=1)
    first = await prepare_feedback_digest(now)
    second = await prepare_feedback_digest(now + timedelta(minutes=10))
    assert first["status"] == "prepared"
    assert first["event_count"] == 1
    assert second["status"] == "prepared"
    assert first["digest_id"] == second["digest_id"]
    assert first["payload_hash"] == second["payload_hash"]
    assert first["content"] == second["content"]
    assert "新增抱怨：1 条" in first["content"]
    mismatch = await acknowledge_feedback_digest(first["digest_id"], "0" * 64)
    assert mismatch["status"] == "payload_mismatch"
    ack = await acknowledge_feedback_digest(first["digest_id"], first["payload_hash"])
    assert ack["status"] == "delivered"
    after = await prepare_feedback_digest(now + timedelta(minutes=20))
    assert after["status"] == "delivered"


@pytest.mark.asyncio
async def test_unacked_digest_retries_oldest_batch_with_stable_id(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-retry-key")
    async with SessionLocal() as db:
        await db.execute(delete(FeedbackDigestRun))
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    assert await capture_feedback(
        "我要反馈：导出功能每次都报错",
        auth_payload={"tenant_key": "retry-tenant", "sub": "retry-user"},
        request_id="retry-event",
        session_id="retry-session",
    )
    first_now = datetime.now(timezone.utc) + timedelta(days=1)
    first = await prepare_feedback_digest(first_now)
    second = await prepare_feedback_digest(first_now + timedelta(days=1))
    assert first["status"] == "prepared"
    assert second["status"] == "prepared"
    assert first["digest_id"] == second["digest_id"]
    assert first["content"] == second["content"]
    assert first["payload_hash"] == second["payload_hash"]


@pytest.mark.asyncio
async def test_frozen_failed_digest_transitions_back_to_prepared_before_ack(monkeypatch):
    monkeypatch.setenv("FEEDBACK_HMAC_KEY", "feedback-failed-retry-key")
    async with SessionLocal() as db:
        await db.execute(delete(FeedbackDigestRun))
        await db.execute(delete(FeedbackEvent))
        await db.commit()
    assert await capture_feedback(
        "我要反馈：同步功能连续失败",
        auth_payload={"tenant_key": "failed-tenant", "sub": "failed-user"},
        request_id="failed-retry-event",
        session_id="failed-retry-session",
    )
    now = datetime.now(timezone.utc) + timedelta(days=1)
    first = await prepare_feedback_digest(now)
    digest_date = datetime.strptime(
        first["digest_id"].removeprefix("feedback-"), "%Y-%m-%d"
    ).date()
    async with SessionLocal() as db:
        run = await db.get(FeedbackDigestRun, digest_date)
        assert run is not None
        run.delivery_status = "failed"
        run.last_error = "simulated_transport_failure"
        await db.commit()
    retried = await prepare_feedback_digest(now + timedelta(minutes=10))
    assert retried["status"] == "prepared"
    assert retried["payload_hash"] == first["payload_hash"]
    ack = await acknowledge_feedback_digest(retried["digest_id"], retried["payload_hash"])
    assert ack["status"] == "delivered"


@pytest.mark.asyncio
async def test_chat_nonstream_returns_durable_feedback_receipt(monkeypatch):
    from backend.api import chat as chat_api

    async def fake_capture(*_args, **_kwargs):
        return FeedbackReceipt("42", "explicit")

    monkeypatch.setattr(chat_api, "capture_feedback", fake_capture)
    monkeypatch.setattr(chat_api, "match_identity_rule", lambda _q: "固定回答")
    response = await chat_api.chat(
        chat_api.ChatRequest(
            question="这个功能很差",
            request_id="request-123",
            session_id=None,
            quoted_context=None,
            agent_id=None,
            skill_id=None,
        ),
        payload={"tenant_key": "t", "user_id": "u"},
    )
    assert response.feedback_receipt == {
        "feedback_id": "42",
        "signal_type": "explicit",
        "message": "已作为产品改进反馈记录；输入“撤销刚才的反馈”可撤销",
        "revocable": True,
    }


@pytest.mark.asyncio
async def test_feedback_capture_timeout_never_blocks_chat(monkeypatch):
    from backend.api import chat as chat_api

    async def slow_capture(*_args, **_kwargs):
        await asyncio.sleep(2)

    monkeypatch.setattr(chat_api, "capture_feedback", slow_capture)
    started = time.monotonic()
    receipt = await chat_api._capture_feedback_safely("抱怨")
    assert receipt is None
    assert time.monotonic() - started < 1.0


@pytest.mark.asyncio
async def test_chat_stream_emits_feedback_receipt(monkeypatch):
    from backend.api import chat as chat_api

    async def fake_capture(*_args, **_kwargs):
        return FeedbackReceipt("43", "inferred")

    monkeypatch.setattr(chat_api, "capture_feedback", fake_capture)
    monkeypatch.setattr(chat_api, "match_identity_rule", lambda _q: "固定回答")
    response = await chat_api.stream_chat(
        chat_api.StreamRequest(
            question="这个功能很差",
            request_id="request-456",
            session_id=None,
            quoted_context=None,
            agent_id=None,
            skill_id=None,
        ),
        {"tenant_key": "t", "user_id": "u"},
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    body = "".join(chunks)
    assert '"type": "feedback_receipt"' in body
    assert '"feedback_id": "43"' in body
