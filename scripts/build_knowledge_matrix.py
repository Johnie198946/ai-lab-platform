#!/usr/bin/env python3
"""
AI Lab 全局知识地图矩阵生成器 v2.0 (Knowledge Matrix Builder)

根治 main Agent 知识遗漏问题：
- 递归扫描 AI Lab 知识库下 ALL Markdown 文件（不再遗漏任何目录）
- 提取 YAML Frontmatter、WikiLinks、标签、核心摘要、实体关键词
- 构建 entity_index 支持模糊回退检索（按实体名/关键词反查文档）
- 生成极简、高浓度的 knowledge_matrix.json，作为 Agent 的全局上下文地图

v2.0 变更：
- 全库递归扫描（排除 .obsidian/.git/.claudian/_archive）
- 摘要从 250 字扩展到 500 字，确保关键实体不被截断
- 新增 entity_index：实体名 → 文档路径映射，支持模糊回退
- 新增 category 自动推断（基于目录路径）
- 使用 AI_LAB_HOME 环境变量，消除硬编码路径
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Set
from datetime import datetime


# 排除的目录（不扫描）
EXCLUDED_DIRS = {
    ".obsidian", ".git", ".claudian", "_archive", "node_modules",
    ".hermes", "__pycache__", ".cursor"
}

# 目录 → 分类映射（用于自动推断 category）
CATEGORY_RULES = [
    ("研究系统/专题档案", "topics"),
    ("研究系统/来源卡片", "source_cards"),
    ("研究系统/综合报告", "reports"),
    ("研究系统/蒸馏", "distillations"),
    ("研究系统/模板", "templates_research"),
    ("客户画像", "customer_personas"),
    ("竞品情报", "competitors"),
    ("决策记录", "decisions"),
    ("AI情报雷达", "radar"),
    ("wiki", "wiki"),
    ("产品设计", "product_design"),
    ("raw/articles", "raw_articles"),
    ("raw/dialogues", "raw_dialogues"),
    ("raw/reports", "raw_reports"),
    ("raw/horizon", "raw_horizon"),
    ("任务记录", "task_records"),
    ("模板", "templates"),
]

# 中文实体关键词库（用于 entity_index 构建）
ENTITY_PATTERNS = [
    # 竞品公司
    "字节跳动", "ByteDance", "豆包", "Doubao",
    "华为", "Huawei", "昇腾", "Ascend",
    "联想", "Lenovo",
    "阿里", "Alibaba", "Qwen", "千问", "通义",
    "腾讯", "Tencent", "混元", "Hy3", "WorkBuddy",
    "DeepSeek",
    "OpenAI", "Anthropic", "Claude",
    "Google", "Gemini", "DeepMind",
    "NVIDIA", "英伟达",
    "DELL", "Dell",
    "HPE",
    "Meta",
    "Microsoft", "微软",
    "AWS",
    "趋动科技", "VirtAI", "OrionX",
    "浪潮", "中兴", "新华三", "曙光",
    "宝德", "安擎",
    "VMware", "Broadcom",
    "飞致云", "MaxKB",
    "深言未来",
    # 内部产品/概念
    "TokenBox", "TokenOps", "AgentCare", "ATM",
    "FusionOne", "Token Factory", "Token工厂",
    "AI4MKT", "MOR",
    "WATT", "FLOPS", "TOKENS", "AGENTS", "VALUES",
    "LLM Wiki",
    # 关键人物
    "Brockman", "Sam Altman", "张一鸣",
    "Jeff Dean", "Demis Hassabis",
    "马斯克", "Musk",
    # 关键技术/事件
    "DRA", "Dynamo", "MIG",
    "Agent安全", "Agent治理",
    "知识检索", "knowledge_matrix",
]


def extract_frontmatter_and_content(file_path: Path) -> tuple[Dict[str, Any], str]:
    """提取 Markdown 文件的 YAML Frontmatter 和正文"""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}, ""

    frontmatter = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2]
            # Parse YAML-like frontmatter
            current_key = None
            current_list = None
            for line in fm_text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                # Handle list items under a key
                if (
                    stripped.startswith("- ")
                    and current_key
                    and current_list is not None
                ):
                    current_list.append(stripped[2:].strip().strip('"').strip("'"))
                    continue
                # If we were building a list, save it
                if current_list is not None and current_key:
                    frontmatter[current_key] = current_list
                    current_list = None
                    current_key = None
                # New key-value pair
                if ":" in stripped:
                    key, val = stripped.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    # Check if value is a list start
                    if val.startswith("[") and val.endswith("]"):
                        # Inline list
                        items = [
                            x.strip().strip('"').strip("'")
                            for x in val[1:-1].split(",")
                            if x.strip()
                        ]
                        frontmatter[key] = items
                    elif val == "":
                        # Could be a multi-line list
                        current_key = key
                        current_list = []
                    else:
                        frontmatter[key] = val.strip('"').strip("'")
            # Save any pending list
            if current_list is not None and current_key:
                frontmatter[current_key] = current_list

    return frontmatter, body.strip()


def extract_wikilinks(text: str) -> List[str]:
    """提取 Markdown 中的 [[wikilinks]]"""
    matches = re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]", text)
    return list(set(matches))


def infer_category(rel_path: str) -> str:
    """根据文件相对路径推断分类"""
    for prefix, cat_key in CATEGORY_RULES:
        if rel_path.startswith(prefix + "/") or rel_path.startswith(prefix + os.sep):
            return cat_key
    return "other"


def extract_entities(text: str) -> List[str]:
    """从文本中提取已知实体关键词"""
    found = set()
    for entity in ENTITY_PATTERNS:
        if entity in text:
            found.add(entity)
    return sorted(found)


def build_matrix(vault_dir: Path) -> Dict[str, Any]:
    """递归扫描整个 Vault，构建实体矩阵"""
    matrix = {
        "version": "2.0",
        "generated_at": "",
        "vault_root": str(vault_dir),
        "categories": {},
        "entity_index": {},  # 实体名 → [文档路径, ...]
        "stats": {
            "total_documents": 0,
            "total_wikilinks": 0,
            "total_entities_indexed": 0,
            "categories_count": 0
        }
    }

    total_docs = 0
    total_links = 0
    entity_index: Dict[str, List[str]] = {}
    category_counts: Dict[str, int] = {}

    # 递归扫描所有 .md 文件
    for root, dirs, files in os.walk(vault_dir):
        # 排除不需要的目录
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file in files:
            if not file.endswith(".md"):
                continue

            full_path = Path(root) / file
            try:
                rel_file_path = full_path.relative_to(vault_dir)
            except ValueError:
                continue

            rel_str = str(rel_file_path)

            # 跳过 matrix 自身和编译日志
            if file in ("knowledge_matrix.json",):
                continue

            fm, body = extract_frontmatter_and_content(full_path)
            wikilinks = extract_wikilinks(body)

            # 提取前 500 字作为摘要（v1.0 是 250 字，太短导致实体丢失）
            clean_body = re.sub(r"#+\s+", "", body)
            clean_body = re.sub(r"\[\[.*?\]\]", "", clean_body)
            clean_body = re.sub(r"\|", " ", clean_body)  # 表格分隔符替换
            clean_body = re.sub(r"\s+", " ", clean_body)
            summary = clean_body[:500].strip()

            # 提取实体
            full_text = body  # 用完整正文提取实体
            entities = extract_entities(full_text)

            # 推断分类
            category = infer_category(rel_str)

            # 构建文档条目
            doc_entry = {
                "path": rel_str,
                "title": fm.get("title", file.replace(".md", "")),
                "tags": fm.get("tags", []),
                "created": fm.get(
                    "created",
                    fm.get("date", fm.get("published_at", "")),
                ),
                "wikilinks": wikilinks,
                "entities": entities,
                "summary": summary,
                "category": category
            }

            # 添加到分类
            if category not in matrix["categories"]:
                matrix["categories"][category] = {}
            doc_key = file.replace(".md", "")
            # 避免 key 冲突：如果同名文件在不同子目录
            if doc_key in matrix["categories"][category]:
                # 用路径前缀做区分
                doc_key = rel_str.replace("/", "_").replace(".md", "")
            matrix["categories"][category][doc_key] = doc_entry

            # 更新 entity_index
            for entity in entities:
                if entity not in entity_index:
                    entity_index[entity] = []
                entity_index[entity].append(rel_str)

            # 统计
            category_counts[category] = category_counts.get(category, 0) + 1
            total_docs += 1
            total_links += len(wikilinks)

    # 写入 entity_index（去重 + 排序）
    for entity in entity_index:
        entity_index[entity] = sorted(set(entity_index[entity]))
    matrix["entity_index"] = entity_index

    matrix["stats"]["total_documents"] = total_docs
    matrix["stats"]["total_wikilinks"] = total_links
    matrix["stats"]["total_entities_indexed"] = len(entity_index)
    matrix["stats"]["categories_count"] = len(category_counts)
    matrix["generated_at"] = datetime.now().isoformat()

    return matrix


def main():
    parser = argparse.ArgumentParser(description="AI Lab Knowledge Matrix Builder v2.0")
    parser.add_argument(
        "--vault-dir",
        type=str,
        default=None,
        help="Path to the Obsidian Vault directory (overrides AI_LAB_HOME env var)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for knowledge_matrix.json (in addition to default locations)",
    )
    args = parser.parse_args()

    # 使用 AI_LAB_HOME 环境变量或 CLI 参数，消除硬编码路径
    vault_dir = Path(
        args.vault_dir
        or os.environ.get("AI_LAB_HOME", "/Users/dengzhaoyu/Desktop/AI Lab/AI Lab")
    )
    if not vault_dir.exists():
        print(f"Error: Vault dir not found at {vault_dir}")
        sys.exit(1)

    print(f"Scanning AI Lab Vault at {vault_dir}...")
    print(f"Excluding dirs: {EXCLUDED_DIRS}")
    matrix = build_matrix(vault_dir)

    # 输出到 AI Lab 根目录
    out_file1 = vault_dir / "knowledge_matrix.json"
    with open(out_file1, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)

    # 输出到 ai-lab-platform/data/
    platform_data = Path(__file__).parent.parent / "data"
    platform_data.mkdir(parents=True, exist_ok=True)
    out_file2 = platform_data / "knowledge_matrix.json"
    with open(out_file2, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)

    # 如果指定了 --output，额外输出到指定路径
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(matrix, f, ensure_ascii=False, indent=2)
        print(f"   - Saved to: {out_path}")

    print("✅ Knowledge Matrix v2.0 successfully built!")
    print(f"   - Total Documents: {matrix['stats']['total_documents']}")
    print(f"   - Total WikiLinks: {matrix['stats']['total_wikilinks']}")
    print(f"   - Total Entities Indexed: {matrix['stats']['total_entities_indexed']}")
    print(f"   - Categories: {matrix['stats']['categories_count']}")
    print("   - Category breakdown:")
    for cat_name, cat_data in sorted(matrix["categories"].items()):
        print(f"       {cat_name}: {len(cat_data)} docs")
    print(f"   - Saved to: {out_file1}")
    print(f"   - Saved to: {out_file2}")

    # 验证关键实体覆盖
    print("\n🔍 Entity coverage verification:")
    critical_entities = [
        "字节跳动",
        "ByteDance",
        "张一鸣",
        "DeepSeek",
        "华为",
        "联想",
        "Qwen",
        "Anthropic",
    ]
    for entity in critical_entities:
        if entity in matrix["entity_index"]:
            docs = matrix["entity_index"][entity]
            print(f"   ✅ {entity}: found in {len(docs)} docs")
        else:
            print(f"   ❌ {entity}: NOT FOUND in any doc!")


if __name__ == "__main__":
    main()
