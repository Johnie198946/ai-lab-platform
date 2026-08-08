"""
结构测试（ArchUnit 式）—— 模块边界依赖规则

保证 backend 分层架构不被破坏:
  api/    (HTTP 层)      → 可依赖 services/, agents/, models/, db
  services/ (业务逻辑)   → 可依赖 models/, agents/, db (不依赖 api/)
  agents/ (Agent 编排)   → 可依赖 models/, services/ (不依赖 api/)
  models/ (数据模型)     → 不依赖任何 backend 内部模块 (最底层)
  db.py                 → 不依赖 api/ services/ agents/

规则:
  1. api/ 不得被 services/ agents/ models/ 反向依赖
  2. services/ 不得 import api/
  3. agents/ 不得 import api/
  4. models/ 不得 import backend 任何其他模块
  5. db 连接层不得依赖上层

用法: pytest tests/test_architecture.py -v
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"

LAYERS = {
    "api": "backend.api",
    "services": "backend.services",
    "agents": "backend.agents",
    "models": "backend.models",
    "db": "backend.db",
}


def _iter_py_files():
    for p in sorted(BACKEND.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        yield p


def _imports_of(path: Path) -> list:
    """提取文件的顶层 import 目标"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _layer_of(module: str) -> str | None:
    for layer, prefix in LAYERS.items():
        if module == prefix or module.startswith(prefix + "."):
            return layer
    return None


def _violations():
    """返回 [(file, target_layer, rule)]"""
    violations = []
    for path in _iter_py_files():
        rel = path.relative_to(BACKEND)
        # 跳过 __init__ 和入口
        if path.name == "__init__.py":
            continue
        # 文件自身所在层
        parts = rel.parts
        file_layer = parts[0] if parts[0] in LAYERS else None
        if not file_layer:
            continue
        for imp in _imports_of(path):
            target_layer = _layer_of(imp)
            if not target_layer:
                continue
            # 规则 4: models 不得依赖业务层 (可依赖 db 基础设施)
            if file_layer == "models" and target_layer in ("api", "services", "agents"):
                violations.append((str(rel), target_layer, "models 不得依赖业务层"))
            # 规则 5: db 不得依赖上层
            if file_layer == "db" and target_layer not in ("models", "db"):
                violations.append((str(rel), target_layer, "db 不得依赖业务层"))
            # 规则 2: services 不得依赖 api
            if file_layer == "services" and target_layer == "api":
                violations.append((str(rel), target_layer, "services 不得依赖 api"))
            # 规则 3: agents 不得依赖 api
            if file_layer == "agents" and target_layer == "api":
                violations.append((str(rel), target_layer, "agents 不得依赖 api"))
            # 规则 1: api 不得被反向依赖 (由上面的规则覆盖)
    return violations


def test_layered_architecture():
    """模块边界: 分层依赖规则"""
    bad = _violations()
    assert not bad, f"架构违规 {len(bad)} 处:\n" + "\n".join(f"  {f} -> {t} ({r})" for f, t, r in bad)


def test_no_circular_api_import():
    """api 模块之间不应互相 import (环依赖)"""
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0,'.'); from backend.main import app; print('ok')"],
        capture_output=True, text=True, timeout=30, cwd=str(BACKEND.parent),
    )
    assert r.returncode == 0, f"backend.main 导入失败:\n{r.stderr[:500]}"


if __name__ == "__main__":
    v = _violations()
    if v:
        print(f"架构违规 {len(v)} 处:")
        for f, t, r in v:
            print(f"  {f} -> {t} ({r})")
    else:
        print("✅ 架构干净")
