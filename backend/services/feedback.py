"""Deterministic, privacy-minimizing product complaint capture and digest."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from backend.db import SessionLocal
from backend.models.feedback import FeedbackDigestRun, FeedbackEvent

CST = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)
_LOCK_ID = 815_202_608

_EXPLICIT = re.compile(r"(?:投诉|吐槽|反馈(?:一个|下)?(?:问题)?|提个建议|我要建议|很不满意)", re.I)
_NEGATIVE = re.compile(
    r"(?:不好用|难用|反人类|鸡肋|没用|答非所问|不准确|太慢|很慢|卡住|卡死|"
    r"崩溃|闪退|失败|报错|打不开|无法|不能|没反应|找不到|丢失|麻烦|繁琐|"
    r"又坏了|一直|总是|每次|根本|体验差|有问题|bug)", re.I,
)
_TARGET = re.compile(
    r"(?:这个功能|这个页面|这里|这个按钮|这个入口|你们|产品|应用|app|ios|网页|回答|"
    r"上传|登录|注册|导出|下载|搜索|对话|消息|文件|页面|按钮|入口|功能)", re.I,
)
_SUGGEST = re.compile(r"(?:能不能|希望|建议|应该|最好|请改|改一下|优化|增加|支持)", re.I)
_INTENSITY = re.compile(r"(?:太|很|特别|非常|完全|根本|又|一直|总是|每次)", re.I)
_NEGATION = re.compile(r"(?:没有不好用|并不难用|不是不能|不算慢|没有问题|没问题)", re.I)
_RESOLVED = re.compile(r"(?:以前|之前).{0,16}(?:不好用|慢|失败|有问题).{0,20}(?:现在|如今).{0,10}(?:好了|正常|修复|解决)", re.I)
_QUOTED = re.compile(r"(?:别人|同事|用户|客户|他|她).{0,12}(?:说|反馈|抱怨|认为)|(?:分析|解释).{0,20}[‘'\"]", re.I)
_REVOKE = re.compile(r"^(?:请)?撤销(?:刚才|上一条|最近)?(?:的)?(?:反馈|投诉|抱怨)[。！! ]*$", re.I)

_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_TOKEN = re.compile(r"\b(?:sk|ghp|xox[baprs]|Bearer)[-_ A-Za-z0-9]{8,}\b", re.I)
_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_BANK_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
_URL = re.compile(r"https?://\S+", re.I)
_BIDI = re.compile("[\u202A-\u202E\u2066-\u2069]")
_CLOUD_CREDENTIAL = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)", re.I,
)
_IPV4 = re.compile(r"(?<!\d)(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?!\d)")
_IPV6 = re.compile(r"(?<![0-9A-Fa-f:])(?:[A-Fa-f0-9]{0,4}:){2,7}[A-Fa-f0-9]{0,4}(?:%[A-Za-z0-9_.-]+)?(?![0-9A-Fa-f:])")
_LABELED_IDENTIFIER = re.compile(
    r"(?:(?:微信|企业微信|账号|用户名|密码|密钥|secret|access[_ -]?key)\s*[:：=]?\s*)"
    r"[^\s,，;；]{5,}", re.I,
)


@dataclass(frozen=True)
class FeedbackSignal:
    matched: bool
    score: int
    signal_type: str = ""
    category: str = "other"
    severity: str = "low"
    matched_rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedbackReceipt:
    feedback_id: str
    signal_type: str
    message: str = "已作为产品改进反馈记录；输入“撤销刚才的反馈”可撤销"
    revocable: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "signal_type": self.signal_type,
            "message": self.message,
            "revocable": self.revocable,
        }


def classify_feedback(message: str) -> FeedbackSignal:
    value = " ".join(str(message or "").strip().split())
    if not value or _NEGATION.search(value) or _RESOLVED.search(value) or _QUOTED.search(value):
        return FeedbackSignal(False, 0)
    score = 0
    rules: list[str] = []
    for name, points, pattern in (
        ("explicit", 5, _EXPLICIT),
        ("negative", 4, _NEGATIVE),
        ("target", 2, _TARGET),
        ("suggestion", 1, _SUGGEST),
        ("intensity", 2, _INTENSITY),
    ):
        if pattern.search(value):
            score += points
            rules.append(name)
    if "negative" in rules and "explicit" not in rules and "target" not in rules:
        return FeedbackSignal(False, score, matched_rules=tuple(rules))
    if score < 4:
        return FeedbackSignal(False, score, matched_rules=tuple(rules))
    category = _category(value)
    severity = "high" if re.search(r"(?:崩溃|闪退|数据丢失|无法登录|完全不能|卡死)", value, re.I) else (
        "medium" if score >= 6 else "low"
    )
    return FeedbackSignal(
        True, score, "explicit" if "explicit" in rules else "inferred",
        category, severity, tuple(rules),
    )


def _category(value: str) -> str:
    if re.search(r"(?:崩溃|闪退|失败|报错|打不开|无法|不能|没反应|卡死|丢失|bug)", value, re.I):
        return "reliability"
    if re.search(r"(?:慢|卡住|延迟|响应)", value, re.I):
        return "performance"
    if re.search(r"(?:不准确|答非所问|没用|回答)", value, re.I):
        return "quality"
    if re.search(r"(?:希望|增加|支持|能不能)", value, re.I):
        return "missing_capability"
    if re.search(r"(?:不好用|难用|反人类|找不到|麻烦|繁琐|入口)", value, re.I):
        return "usability"
    return "other"


def sanitize_excerpt(message: str, limit: int = 2000) -> str:
    value = _BIDI.sub("", str(message or "")[:limit])
    value = _PHONE.sub("[手机号已脱敏]", value)
    value = _EMAIL.sub("[邮箱已脱敏]", value)
    value = _TOKEN.sub("[凭据已脱敏]", value)
    value = _ID_CARD.sub("[身份证已脱敏]", value)
    value = _BANK_CARD.sub("[银行卡号已脱敏]", value)
    value = _URL.sub("[链接已脱敏]", value)
    value = _CLOUD_CREDENTIAL.sub("[云凭据已脱敏]", value)
    value = _IPV4.sub("[IP地址已脱敏]", value)
    value = _IPV6.sub("[IP地址已脱敏]", value)
    value = _LABELED_IDENTIFIER.sub("[账号标识已脱敏]", value)
    return value


def _hmac_key() -> bytes:
    value = os.environ.get("FEEDBACK_HMAC_KEY") or os.environ.get("AUTHEN_JWT_SECRET")
    if not value:
        raise RuntimeError("feedback_hmac_key_missing")
    return value.encode()


def _ref(value: str) -> str:
    return hmac.new(_hmac_key(), value.encode(), hashlib.sha256).hexdigest()


def _content_digest(value: str) -> str:
    return hmac.new(_hmac_key(), value.encode(), hashlib.sha256).hexdigest()


async def capture_feedback(
    message: str,
    *,
    auth_payload: dict[str, Any],
    request_id: str | None,
    session_id: str | None,
    surface: str = "unknown",
    app_version: str = "",
) -> FeedbackReceipt | None:
    tenant_key = str(auth_payload.get("tenant_key") or "public")
    user_id = str(auth_payload.get("user_id") or auth_payload.get("sub") or "anonymous")
    try:
        user_ref = _ref(f"{tenant_key}\0{user_id}")
    except RuntimeError:
        logger.error("feedback capture disabled: HMAC key is missing")
        return None
    normalized = " ".join(str(message or "").strip().split())
    if _REVOKE.fullmatch(normalized):
        async with SessionLocal() as db:
            latest = (
                await db.execute(
                    select(FeedbackEvent).where(
                        FeedbackEvent.tenant_key == tenant_key,
                        FeedbackEvent.user_ref == user_ref,
                        FeedbackEvent.revoked_at.is_(None),
                    ).order_by(FeedbackEvent.created_at.desc(), FeedbackEvent.id.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if latest is None:
                return FeedbackReceipt("", "revoked", "没有可撤销的最近反馈", False)
            latest.revoked_at = datetime.now(timezone.utc)
            latest.status = "dismissed"
            await db.commit()
            return FeedbackReceipt(str(latest.id), "revoked", "已撤销最近一条产品反馈", False)
    signal = classify_feedback(message)
    if not signal.matched:
        return None
    effective_request_id = request_id or uuid.uuid4().hex
    content_hash = _content_digest(message)
    now = datetime.now(timezone.utc)
    event = FeedbackEvent(
        tenant_key=tenant_key,
        user_ref=user_ref,
        session_ref=_ref(f"{tenant_key}\0{user_id}\0{session_id or ''}"),
        request_id=effective_request_id,
        content_hash=content_hash,

        sanitized_excerpt=(
            sanitize_excerpt(message)
            if signal.signal_type == "explicit"
            else "[推断型抱怨信号；未保留用户原文]"
        ),
        signal_type=signal.signal_type,
        category=signal.category,
        severity=signal.severity,
        score=signal.score,
        matched_rules=list(signal.matched_rules),
        surface=surface[:24],
        app_version=app_version[:64],
    )
    try:
        async with SessionLocal() as db:
            async with db.begin():
                if db.bind and db.bind.dialect.name == "postgresql":
                    # Serialize all writes for one user so the 24h rate limit and
                    # dedupe check are atomic across API workers.
                    await db.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": int(user_ref[:15], 16)},
                    )
                existing = (
                    await db.execute(
                        select(FeedbackEvent).where(
                            FeedbackEvent.tenant_key == tenant_key,
                            FeedbackEvent.user_ref == event.user_ref,
                            FeedbackEvent.content_hash == content_hash,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.revoked_at is not None:
                        existing.revoked_at = None
                        existing.status = "new"
                        existing.created_at = now
                        existing.request_id = effective_request_id
                        existing.sanitized_excerpt = event.sanitized_excerpt
                    feedback_id = existing.id
                    feedback_type = existing.signal_type
                else:
                    recent_count = await db.scalar(
                        select(func.count(FeedbackEvent.id)).where(
                            FeedbackEvent.tenant_key == tenant_key,
                            FeedbackEvent.user_ref == event.user_ref,
                            FeedbackEvent.created_at >= now - timedelta(days=1),
                            FeedbackEvent.revoked_at.is_(None),
                        )
                    )
                    if int(recent_count or 0) >= 50:
                        return None
                    db.add(event)
                    await db.flush()
                    feedback_id = event.id
                    feedback_type = signal.signal_type
            return FeedbackReceipt(str(feedback_id), feedback_type)
    except IntegrityError:
        async with SessionLocal() as db:
            existing = (
                await db.execute(
                    select(FeedbackEvent).where(
                        FeedbackEvent.tenant_key == tenant_key,
                        FeedbackEvent.user_ref == event.user_ref,
                        FeedbackEvent.content_hash == content_hash,
                    )
                )
            ).scalar_one_or_none()
            return FeedbackReceipt(str(existing.id), existing.signal_type) if existing else None
    except Exception:
        # Feedback collection must never take down chat. Callers only expose a receipt
        # after a durable write succeeds.
        logger.exception("feedback capture failed without user content")
        return None


def render_digest(events: Sequence[FeedbackEvent], digest_date: str) -> str:
    categories = Counter(item.category for item in events)
    severities = Counter(item.severity for item in events)
    users = {item.user_ref for item in events}
    tenants = {item.tenant_key for item in events}
    names = {
        "reliability": "稳定性", "performance": "性能", "quality": "回答质量",
        "missing_capability": "缺失能力", "usability": "易用性", "other": "其他",
    }
    lines = [
        f"新增抱怨：{len(events)} 条",
        f"涉及用户：{len(users)} 人",
        f"涉及租户：{len(tenants)} 个",
        f"高严重度：{severities.get('high', 0)} 条",
        "",
    ]
    for category, count in categories.most_common():
        lines.append(f"【{names.get(category, category)}】{count} 条")
    lines.append("")
    lines.append("隐私边界：日报不包含任何用户原文；明细仅保留于受控数据库。")
    lines.append(f"统计周期：{digest_date}（确定性汇总，未调用模型）")
    return "\n".join(lines).strip()


async def run_feedback_digest(now: datetime | None = None) -> dict[str, Any]:
    """Deliver one logical digest per CST day.

    PostgreSQL keeps a transaction-scoped advisory lock while the webhook call is
    in flight, so every worker uses the same connection and the lock cannot leak
    into the pool. Webhook delivery is intentionally at-least-once: the stable
    digest ID/payload hash let the recipient identify a crash-window duplicate.
    """
    from backend.services.feishu import send_feishu_async

    current = (now or datetime.now(timezone.utc)).astimezone(CST)
    if current.hour < 9:
        return {"status": "too_early"}
    result: dict[str, Any]
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind and db.bind.dialect.name == "postgresql":
                acquired = bool(await db.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _LOCK_ID}
                ))
                if not acquired:
                    return {"status": "locked"}
            run = (
                await db.execute(
                    select(FeedbackDigestRun)
                    .where(FeedbackDigestRun.delivery_status == "failed")
                    .order_by(FeedbackDigestRun.digest_date.asc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            ).scalar_one_or_none()
            digest_date = run.digest_date if run else current.date()
            if run is None:
                run = await db.get(FeedbackDigestRun, digest_date, with_for_update=True)
            if run and run.delivery_status in {"delivered", "empty"}:
                return {"status": run.delivery_status, "event_count": run.event_count}
            cutoff_local = datetime.combine(
                digest_date, datetime.min.time().replace(hour=9), tzinfo=CST
            )
            period_end = run.period_end if run else cutoff_local.astimezone(timezone.utc)
            previous_end = await db.scalar(
                select(FeedbackDigestRun.period_end)
                .where(FeedbackDigestRun.delivery_status.in_(["delivered", "empty"]))
                .order_by(FeedbackDigestRun.period_end.desc())
                .limit(1)
            )
            period_start = run.period_start if run else (
                previous_end or (period_end - timedelta(days=1))
            )
            await db.execute(delete(FeedbackEvent).where(
                FeedbackEvent.created_at < period_end - timedelta(days=90)
            ))
            events = (
                await db.execute(
                    select(FeedbackEvent)
                    .where(
                        FeedbackEvent.created_at > period_start,
                        FeedbackEvent.created_at <= period_end,
                        FeedbackEvent.revoked_at.is_(None),
                        FeedbackEvent.status != "dismissed",
                    )
                    .order_by(FeedbackEvent.created_at.asc())
                )
            ).scalars().all()
            if run is None:
                run = FeedbackDigestRun(
                    digest_date=digest_date, period_start=period_start, period_end=period_end
                )
                db.add(run)
            run.period_start = period_start
            run.period_end = period_end
            run.event_count = len(events)
            run.unique_user_count = len({item.user_ref for item in events})
            run.attempts = int(run.attempts or 0) + 1
            if not events:
                run.delivery_status = "empty"
                run.last_error = ""
                result = {"status": "empty", "event_count": 0}
            else:
                content = render_digest(events, str(digest_date))
                digest_id = f"feedback-{digest_date}"
                content = f"Digest ID: {digest_id}\n\n{content}"
                run.payload_hash = hashlib.sha256(content.encode()).hexdigest()
                delivered = await send_feishu_async(
                    f"产品抱怨日报 · {digest_date}", content
                )
                run.delivery_status = "delivered" if delivered else "failed"
                run.last_error = (
                    "" if delivered else "feishu_not_configured_or_delivery_failed"
                )
                run.delivered_at = datetime.now(timezone.utc) if delivered else None
                result = {
                    "status": run.delivery_status,
                    "event_count": run.event_count,
                    "unique_user_count": run.unique_user_count,
                    "digest_id": digest_id,
                }
    return result
