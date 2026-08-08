#!/usr/bin/env python3
"""
drift_scan.py — 代码库漂移监测（OpenAI 式"垃圾回收"）

扫描 ai-lab-platform 找漂移/退化迹象，输出给 Agent 建议修复:
  1. 架构违规（复用 test_architecture 的规则）
  2. TODO/FIXME/HACK 遗留
  3. 未使用 import（粗略·AST）
  4. 文件大小异常（单体文件过大 = 可能过度膨胀）
  5. 测试覆盖率线索（有 api 文件无对应测试）

用法:
  python3 scripts/drift_scan.py            # 全量扫描
  python3 scripts/drift_scan.py --json     # JSON 输出（供 Agent 消费）
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
TESTS = REPO / "tests"

LAYERS = {
    "api": "backend.api",
    "services": "backend.services",
    "agents": "backend.agents",
    "models": "backend.models",
    "db": "backend.db",
}


def _py_files(root: Path):
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in str(p) or p.name == "__init__.py":
            continue
        yield p


def _imports(path: Path) -> list:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def _layer(module: str):
    for layer, prefix in LAYERS.items():
        if module == prefix or module.startswith(prefix + "."):
            return layer
    return None


def scan_architecture() -> list:
    """1. 架构违规"""
    issues = []
    for path in _py_files(BACKEND):
        parts = path.relative_to(BACKEND).parts
        file_layer = parts[0] if parts[0] in LAYERS else None
        if not file_layer:
            continue
        for imp in _imports(path):
            tgt = _layer(imp)
            if not tgt:
                continue
            bad = (
                (file_layer == "models" and tgt in ("api", "services", "agents"))
                or (file_layer == "db" and tgt not in ("models", "db"))
                or (file_layer in ("services", "agents") and tgt == "api")
            )
            if bad:
                issues.append({
                    "type": "architecture",
                    "file": str(path.relative_to(REPO)),
                    "detail": f"{file_layer} -> {tgt} 违规依赖",
                })
    return issues


def scan_todos() -> list:
    """2. TODO/FIXME/HACK 遗留"""
    issues = []
    for path in list(_py_files(BACKEND)) + list(_py_files(TESTS)):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for kw in ("TODO", "FIXME", "HACK", "XXX"):
                if kw in line:
                    issues.append({
                        "type": "todo",
                        "file": str(path.relative_to(REPO)),
                        "detail": f"L{i}: {line.strip()[:80]}",
                    })
                    break
    return issues


def scan_unused_imports() -> list:
    """3. 未使用 import（AST 粗查）"""
    issues = []
    for path in _py_files(BACKEND):
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (SyntaxError, OSError):
            continue
        names_used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = (alias.asname or alias.name).split(".")[0]
                    if local not in names_used and local != "annotations":
                        issues.append({
                            "type": "unused_import",
                            "file": str(path.relative_to(REPO)),
                            "detail": f"未使用: {alias.name} (L{node.lineno})",
                        })
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    local = alias.asname or alias.name
                    if local not in names_used and local != "annotations":
                        issues.append({
                            "type": "unused_import",
                            "file": str(path.relative_to(REPO)),
                            "detail": f"未使用: {alias.name} (L{node.lineno})",
                        })
    return issues


def scan_big_files() -> list:
    """4. 单体文件过大"""
    issues = []
    for path in _py_files(BACKEND):
        try:
            n = len(path.read_text(encoding="utf-8").splitlines())
        except OSError:
            continue
        if n > 500:
            issues.append({
                "type": "big_file",
                "file": str(path.relative_to(REPO)),
                "detail": f"{n} 行（>500 建议拆分）",
            })
    return issues


def scan_test_gaps() -> list:
    """5. 有 api 文件无对应测试（支持 test_<name>_api.py 命名）"""
    issues = []
    api_files = {
        p.stem
        for p in (BACKEND / "api").glob("*.py")
        if p.name != "__init__.py"
    }
    test_stems = set()
    for p in TESTS.glob("test_*.py"):
        # test_knowledge_api.py -> knowledge / knowledge_api
        s = p.stem[5:]  # 去 test_ 前缀
        test_stems.add(s)
        test_stems.add(s.removesuffix("_api"))
    for stem in sorted(api_files - test_stems):
        if stem in ("errors", "auth", "tenant", "me", "register", "__init__"):
            continue  # 基础/轻量模块跳过
        issues.append({
            "type": "test_gap",
            "file": f"backend/api/{stem}.py",
            "detail": f"无对应测试文件 tests/test_{stem}_api.py 或 test_{stem}.py",
        })
    return issues


def main():
    as_json = "--json" in sys.argv
    scanners = [
        ("架构违规", scan_architecture),
        ("TODO/FIXME 遗留", scan_todos),
        ("未使用 import", scan_unused_imports),
        ("大文件", scan_big_files),
        ("测试缺口", scan_test_gaps),
    ]
    all_issues = []
    for name, fn in scanners:
        found = fn()
        if found:
            all_issues.extend(found)
            if not as_json:
                print(f"## {name}（{len(found)}）")
                for i in found:
                    print(f"  [{i['type']}] {i['file']}: {i['detail']}")

    if as_json:
        print(json.dumps({"count": len(all_issues), "issues": all_issues},
                         ensure_ascii=False, indent=2))
    else:
        print(f"\n共 {len(all_issues)} 项漂移。用 --json 输出结构化结果给 Agent 消费。")


if __name__ == "__main__":
    main()
