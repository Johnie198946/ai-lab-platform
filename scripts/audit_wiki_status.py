#!/usr/bin/env python3
"""
wiki 状态字段审计脚本
扫描 wiki/ 所有条目，检查 status 字段：
  1. 缺失 → 报错（必须补）
  2. 非法值 → 报错（枚举外）
  3. 输出统计

用法: python3 scripts/audit_wiki_status.py [--fix-missing concept]
"""
import re
import sys
from pathlib import Path

# wiki 根目录: 优先环境变量 AI_LAB_VAULT, 否则产品仓库(测试用)
import os as _os

_DEFAULT_VAULT = "/Users/dengzhaoyu/Desktop/AI Lab/AI Lab"
WIKI_ROOT = Path(
    _os.environ.get("AI_LAB_VAULT", _DEFAULT_VAULT)
) / "wiki"
VALID_STATUS = {"concept", "planned", "live", "production", "archived"}
# 说明型文档允许缺失（不是实体条目）
SKIP_PATTERNS = ("INDEX", "COMPILE_LOG", "WIKI_ARCHITECTURE", "MIGRATION")

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def audit() -> list:
    """返回 [(path, issue, current)]"""
    problems = []
    for path in sorted(WIKI_ROOT.rglob("*.md")):
        if any(s in path.name for s in SKIP_PATTERNS):
            continue
        content = path.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.search(content)
        if not m:
            problems.append((str(path), "no_frontmatter", ""))
            continue
        fm = m.group(1)
        status_m = re.search(r"^status:\s*(.+)$", fm, re.MULTILINE)
        if not status_m:
            problems.append((str(path), "missing", ""))
        else:
            val = status_m.group(1).strip().strip('"\'')
            if val not in VALID_STATUS:
                problems.append((str(path), f"invalid({val})", val))
    return problems


def fix_missing(default: str = "concept") -> int:
    """给缺失 status 的条目补默认值"""
    problems = audit()
    fixed = 0
    for path, issue, _ in problems:
        if issue != "missing":
            continue
        p = Path(path)
        content = p.read_text(encoding="utf-8")
        # 在 frontmatter 的 type 行后插入 status
        m = FRONTMATTER_RE.search(content)
        assert m is not None, f"no frontmatter: {path}"
        fm = m.group(1)
        if re.search(r"^status:", fm, re.MULTILINE):
            continue
        # 插到 updated 行后（或任意位置）
        if re.search(r"^updated:", fm, re.MULTILINE):
            new_fm = re.sub(
                r"(^updated:.*$)",
                lambda mm: mm.group(1) + f"\nstatus: {default}",
                fm,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            new_fm = fm.rstrip() + f"\nstatus: {default}\n"
        content = content[: m.start()] + "---\n" + new_fm + "\n---" + content[m.end():]
        p.write_text(content, encoding="utf-8")
        print(f"  +{default}: {path}")
        fixed += 1
    return fixed


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "audit":
        problems = audit()
        if not problems:
            print("✅ 全部条目 status 字段合规")
        else:
            print(f"⚠️  {len(problems)} 个问题:")
            for path, issue, val in problems:
                print(f"  {issue:12s} {path}")
            sys.exit(1)
    elif cmd == "fix":
        default = sys.argv[2] if len(sys.argv) > 2 else "concept"
        n = fix_missing(default)
        print(f"\n已修复 {n} 个条目（默认 {default}）")
