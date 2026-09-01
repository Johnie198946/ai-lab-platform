#!/usr/bin/env python3
"""
平台契约审计

目的：
1. 校验 knowledge_matrix 是否满足机读契约
2. 校验 runtime/manifests 目录是否可用于 harness 执行
3. 为服务器更新后的健康检查提供可复用入口
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REQUIRED_MATRIX_KEYS = {
    "version",
    "generated_at",
    "categories",
    "entity_index",
    "stats",
}


def audit_matrix(matrix_path: Path) -> list[str]:
    """校验 knowledge_matrix 基础契约。"""
    issues: list[str] = []
    if not matrix_path.exists():
        return [f"matrix missing: {matrix_path}"]

    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"matrix invalid json: {exc}"]

    missing = REQUIRED_MATRIX_KEYS - set(matrix.keys())
    if missing:
        issues.append(f"matrix missing keys: {sorted(missing)}")

    version = str(matrix.get("version", ""))
    if version not in {"2.0", "2.1", "3.0-wiki-only"}:
        issues.append(f"unsupported matrix version: {version}")

    stats = matrix.get("stats") or {}
    if int(stats.get("total_documents", 0)) <= 0:
        issues.append("matrix total_documents must be > 0")
    if not isinstance(matrix.get("entity_index"), dict):
        issues.append("matrix entity_index must be dict")

    return issues


def audit_runtime_dirs(data_dir: Path) -> list[str]:
    """校验 harness 运行目录是否齐备。"""
    issues: list[str] = []
    manifests = data_dir / "manifests"
    runtime = data_dir / "runtime"

    if not manifests.exists():
        issues.append(f"runtime manifests dir missing: {manifests}")
    if not runtime.exists():
        issues.append(f"runtime ledger dir missing: {runtime}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="审计 AI Lab Platform 运行契约")
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parent.parent / "data"),
        help="平台 data 目录",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    matrix_path = data_dir / "knowledge_matrix.json"
    issues = audit_matrix(matrix_path)
    issues.extend(audit_runtime_dirs(data_dir))

    if issues:
        print("❌ runtime contract audit failed")
        for issue in issues:
            print(f" - {issue}")
        return 1

    print("✅ runtime contract audit passed")
    print(f" - data_dir: {data_dir}")
    print(f" - matrix: {matrix_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
