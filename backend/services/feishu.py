"""飞书通知发送器 — Agent 汇报通道(站内 + 飞书)。

配置: 环境变量 FEISHU_WEBHOOK_URL(飞书自定义机器人 webhook)。
未配置时静默跳过(站内通知不受影响)。
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

FEISHU_WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")


def send_feishu(title: str, content: str, webhook_url: str | None = None) -> bool:
    """推送一条飞书消息(自定义机器人 · 富文本)。

    返回是否推送成功; 未配置 webhook 时返回 False 但不抛错。
    """
    url = webhook_url or FEISHU_WEBHOOK_URL
    if not url:
        logger.info("飞书 webhook 未配置, 跳过推送")
        return False
    try:
        text = f"**【{title}】**\n{content[:3500]}"
        r = httpx.post(
            url,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=15,
        )
        ok = r.status_code == 200 and r.json().get("code", 1) == 0
        if not ok:
            logger.warning("飞书推送失败 | HTTP %s | %s", r.status_code, r.text[:200])
        return ok
    except Exception as e:
        logger.warning("飞书推送异常: %s", e)
        return False


async def send_feishu_async(
    title: str, content: str, webhook_url: str | None = None
) -> bool:
    """异步包装(调度器内使用)。"""
    import asyncio

    return await asyncio.to_thread(send_feishu, title, content, webhook_url)
