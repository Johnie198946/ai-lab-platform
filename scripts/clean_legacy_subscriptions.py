#!/usr/bin/env python3
"""一次性存量清理脚本：删除订阅了 knowledge / tenants 根目录的旧订阅行。

背景：订阅制 v6 白名单后，`knowledge` 根与 `tenants` 根不可订阅；
历史数据中可能存在早先误订阅这两类根目录的脏行，本脚本一键清理。

用法:
    python scripts/clean_legacy_subscriptions.py --dry-run   # 预览，不删除
    python scripts/clean_legacy_subscriptions.py             # 实际删除

依赖 DATABASE_URL 环境变量（缺省指向本地 Postgres，见 backend/db.py）。
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.tenant import KnowledgeSubscription

# 需要清理的旧根目录订阅（v6 白名单后物理不可订阅）
LEGACY_ROOT_CATEGORIES = ("knowledge", "tenants")


async def find_legacy_rows():
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(KnowledgeSubscription).where(
                    KnowledgeSubscription.category.in_(LEGACY_ROOT_CATEGORIES)
                )
            )
        ).scalars().all()
        return list(rows)


async def delete_legacy_rows(rows) -> int:
    async with SessionLocal() as db:
        for row in rows:
            await db.delete(row)
        await db.commit()
    return len(rows)


async def clean(dry_run: bool) -> int:
    rows = await find_legacy_rows()
    if not rows:
        print("未发现订阅 knowledge/tenants 根目录的旧行，无需清理。")
        return 0
    for row in rows:
        print(
            f"{'[dry-run] 将删除' if dry_run else '删除'}: "
            f"tenant_key={row.tenant_key} category={row.category}"
        )
    if dry_run:
        print(f"[dry-run] 共 {len(rows)} 行待清理（未实际删除）。")
        return len(rows)
    count = await delete_legacy_rows(rows)
    print(f"清理完成，共删除 {count} 行。")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="清理订阅了 knowledge/tenants 根目录的旧行")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览待删除行，不实际执行删除",
    )
    args = parser.parse_args()
    asyncio.run(clean(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
