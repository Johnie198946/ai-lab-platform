"""
Harness 模板引擎 —— 把 Agent prompt 固化为可实例化 bundle

Harness Engineering 的"模板化"落地:
  每个 Agent = 一个模板 bundle (guides + sensors)
  模板可实例化: 换信源/换输出目录/换知识域 → 生成新 Agent

目录结构:
  harness_templates/
    <template_name>/
      template.md        # 模板本体 (占位符 {VAR})
      manifest.yaml      # 模板元数据 (变量定义·默认值·校验)

用法:
  from harness_templates.engine import render_template, list_templates

  render_template("competitor_intel", {
      "AGENT_NAME": "竞品情报",
      "SOURCE_PATHS": "/Users/.../raw/",
      "OUTPUT_DIR": "竞品情报/",
  })
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent

PLACEHOLDER_RE = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")


@dataclass
class HarnessTemplate:
    """一个可实例化的 Agent harness 模板"""

    name: str
    description: str
    variables: dict = field(default_factory=dict)  # var -> (default, desc)
    body: str = ""

    @classmethod
    def load(cls, name: str) -> "HarnessTemplate":
        """从目录加载模板 (template.md + manifest.yaml)"""
        tdir = TEMPLATES_DIR / name
        manifest_path = tdir / "manifest.yaml"
        body_path = tdir / "template.md"
        if not manifest_path.exists() or not body_path.exists():
            raise FileNotFoundError(f"模板不存在: {name}")
        with open(manifest_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        with open(body_path, encoding="utf-8") as f:
            body = f.read()
        return cls(
            name=name,
            description=meta.get("description", ""),
            variables=meta.get("variables", {}),
            body=body,
        )

    def render(self, overrides: dict) -> str:
        """实例化: 用变量替换占位符"""
        result = self.body
        missing = []
        for var, (default, _desc) in self.variables.items():
            value = overrides.get(var, default)
            if value is None:
                missing.append(var)
            result = result.replace("{" + var + "}", str(value or ""))
        # 检查未替换的占位符
        left = PLACEHOLDER_RE.findall(result)
        if left:
            raise ValueError(f"模板缺少变量: {left}")
        return result


def list_templates() -> list[HarnessTemplate]:
    """列出所有可用模板"""
    out = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        if d.is_dir() and (d / "template.md").exists():
            out.append(HarnessTemplate.load(d.name))
    return out


def render_template(name: str, overrides: dict) -> str:
    """便捷入口: 渲染模板"""
    return HarnessTemplate.load(name).render(overrides)
