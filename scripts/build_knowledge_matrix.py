#!/usr/bin/env python3
"""
AI Lab 全局知识地图矩阵生成器 (Knowledge Matrix Builder)

解决 main Agent 知识遗漏问题的顶层方案：
读取 AI Lab 知识库下的专题档案、来源卡片、客户画像、竞品情报、决策记录，
抽取其 YAML Frontmatter、WikiLinks 依赖、标签与核心摘要，
生成极简、高浓度的 knowledge_matrix.json，作为 Agent 的全局上下文地图。
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any


def extract_frontmatter_and_content(file_path: Path) -> tuple[Dict[str, Any], str]:
    """提取 Markdown 文件的 YAML Frontmatter 和正文摘要"""
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
            for line in fm_text.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if val.startswith("[") and val.endswith("]"):
                        # 简单解析列表
                        val = [
                            x.strip().strip('"').strip("'")
                            for x in val[1:-1].split(",")
                            if x.strip()
                        ]
                    frontmatter[key] = val

    return frontmatter, body.strip()


def extract_wikilinks(text: str) -> List[str]:
    """提取 Markdown 中的 [[wikilinks]]"""
    matches = re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]", text)
    return list(set(matches))


def build_matrix(vault_dir: Path) -> Dict[str, Any]:
    """扫描整个 Vault，构建实体矩阵"""
    matrix = {
        "version": "1.0",
        "generated_at": "",
        "categories": {
            "topics": {},          # 专题档案 (SSOT)
            "source_cards": {},    # 来源卡片 (原子凭证)
            "reports": {},         # 综合报告
            "customer_personas": {},# 客户画像
            "competitors": {},     # 竞品情报
            "decisions": {},       # 决策记录 (ADR)
            "radar": {}            # AI情报雷达
        },
        "stats": {
            "total_documents": 0,
            "total_wikilinks": 0
        }
    }

    category_mappings = {
        "研究系统/专题档案": "topics",
        "研究系统/来源卡片": "source_cards",
        "研究系统/综合报告": "reports",
        "客户画像": "customer_personas",
        "竞品情报": "competitors",
        "决策记录": "decisions",
        "AI情报雷达": "radar"
    }

    total_docs = 0
    total_links = 0

    for rel_path, cat_key in category_mappings.items():
        target_dir = vault_dir / rel_path
        if not target_dir.exists():
            continue

        for root, _, files in os.walk(target_dir):
            for file in files:
                if not file.endswith(".md"):
                    continue

                full_path = Path(root) / file
                rel_file_path = full_path.relative_to(vault_dir)
                fm, body = extract_frontmatter_and_content(full_path)
                wikilinks = extract_wikilinks(body)

                # 提取前 250 字作为极简摘要
                clean_body = re.sub(r"#+\s+", "", body)
                clean_body = re.sub(r"\[\[.*?\]\]", "", clean_body)
                summary = clean_body[:250].replace("\n", " ").strip()

                doc_entry = {
                    "path": str(rel_file_path),
                    "title": fm.get("title", file.replace(".md", "")),
                    "tags": fm.get("tags", []),
                    "created": fm.get("created", ""),
                    "wikilinks": wikilinks,
                    "summary": summary
                }

                matrix["categories"][cat_key][file.replace(".md", "")] = doc_entry
                total_docs += 1
                total_links += len(wikilinks)

    matrix["stats"]["total_documents"] = total_docs
    matrix["stats"]["total_wikilinks"] = total_links
    from datetime import datetime
    matrix["generated_at"] = datetime.now().isoformat()

    return matrix


def main():
    vault_dir = Path("/Users/dengzhaoyu/Desktop/AI Lab/AI Lab")
    if not vault_dir.exists():
        print(f"Error: Vault dir not found at {vault_dir}")
        return

    print(f"Scanning AI Lab Vault at {vault_dir}...")
    matrix = build_matrix(vault_dir)

    # 输出到 AI Lab 根目录
    out_file1 = vault_dir / "knowledge_matrix.json"
    with open(out_file1, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)

    # 输出到 ai-lab-platform/data/
    platform_data = Path("/Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform/data")
    platform_data.mkdir(parents=True, exist_ok=True)
    out_file2 = platform_data / "knowledge_matrix.json"
    with open(out_file2, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)

    print("✅ Knowledge Matrix successfully built!")
    print(f"   - Total Documents: {matrix['stats']['total_documents']}")
    print(f"   - Total WikiLinks: {matrix['stats']['total_wikilinks']}")
    print(f"   - Saved to: {out_file1}")
    print(f"   - Saved to: {out_file2}")


if __name__ == "__main__":
    main()
