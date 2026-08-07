"""
编译链引擎 —— Karpathy LLM Wiki v4.0 (完整实现)

两阶段编译:
  Wiki Writer (每2h):  raw → wiki (Ingest + Diff)
  Deep Compiler (02:00): wiki → synth → distill

存储模式:
  - filesystem (默认): 直接读写 wiki/ 目录 markdown 文件 (与 Hermes Agent 一致)
  - db: SQLAlchemy 模型 (产品化时启用)
"""

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

WIKI_ROOT = Path(os.environ.get("AI_LAB_WIKI", "wiki"))
ENTITY_TYPES = ["竞品", "产品", "战略信号", "方法论", "客户", "项目"]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]*)?(?:\|[^\]]*)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


class CompilerService:
    """知识库编译服务 (Karpathy v4.0)"""

    def __init__(self, llm_client=None, wiki_root: Optional[Path] = None):
        self.llm = llm_client
        self.wiki_root = Path(wiki_root) if wiki_root else WIKI_ROOT

    # ================= 文件系统辅助 =================

    def _entity_to_path(self, entity: str) -> Path:
        """实体名 → wiki 文件路径 (目录结构即索引)"""
        for t in ENTITY_TYPES:
            if entity.startswith(t) or f"{t}/" in entity:
                return self.wiki_root / entity.replace(t, t)
        # 按类型猜测: 未知实体放根目录
        return self.wiki_root / f"{entity}.md"

    def _load_wiki(self, path: Path) -> Optional[Dict]:
        """读取 wiki 条目 → dict"""
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        return {
            "path": str(path),
            "content": content,
            "hash": hashlib.md5(content.encode()).hexdigest()[:12],
        }

    def _save_wiki(self, path: Path, content: str) -> None:
        """写 wiki 条目"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _extract_wikilinks(self, content: str) -> List[str]:
        """从 markdown 提取 [[wikilinks]]"""
        return WIKILINK_RE.findall(content)

    def _is_stub(self, content: str) -> bool:
        """判断条目是否只有空壳 (无实质内容)"""
        body = re.sub(FRONTMATTER_RE, "", content)
        body = body.strip()
        return len(body) < 50 or body.count("#") == 0

    # ================= Wiki Writer: raw → wiki =================

    async def raw_to_wiki(self, article: Dict) -> Dict:
        """
        Ingest: raw/ → wiki 条目直接写入 (无来源卡片中间层)
        1. LLM 读 raw
        2. 识别实体
        3. 写/更新 wiki 条目
        4. 补全 wikilinks
        """
        content = article.get("content", "")
        if not content:
            return {"entities": [], "wikis_updated": 0, "error": "empty article"}

        entities = await self._extract_entities(content)
        results = []
        for entity in entities:
            wiki = self._find_or_create_wiki(entity)
            updated = await self._update_wiki_from_raw(wiki, article)
            results.append(updated)

        return {
            "entities": entities,
            "wikis_updated": len(results),
            "results": results,
        }

    async def _extract_entities(self, content: str) -> List[str]:
        """从 raw 内容提取实体名 (LLM 优先, 规则兜底)"""
        if self.llm is not None:
            resp = await self.llm(
                "从以下内容提取涉及的实体名称(竞品/产品/战略信号/方法论/客户)，"
                "用逗号分隔，每个实体不超过6个字:\n\n" + content[:3000]
            )
            assert resp is not None
            entities = [e.strip() for e in resp.split(",") if e.strip()]
            if entities:
                return entities[:10]

        # 规则兜底: 匹配已知实体类型 + 专有名词
        candidates = set()
        for t in ENTITY_TYPES:
            for m in re.finditer(
                rf"{t}[：:\s]*([\u4e00-\u9fffA-Za-z0-9]{{2,20}})", content
            ):
                candidates.add(m.group(1))
        # 匹配 [[wikilink]] 里的实体
        for link in WIKILINK_RE.findall(content):
            candidates.add(link.split("|")[0].split("/")[-1])
        return list(candidates)[:10] if candidates else ["未命名实体"]

    def _find_or_create_wiki(self, entity: str) -> Dict:
        """找已有 wiki 条目或新建"""
        path = self._entity_to_path(entity)
        wiki = self._load_wiki(path)
        if wiki is None:
            now = datetime.now().strftime("%Y-%m-%d")
            content = (
                f"---\ntitle: {entity}\ntype: 待分类\nupdated: {now}\n"
                f"aliases: [{entity}]\n---\n\n# {entity}\n\n"
            )
            self._save_wiki(path, content)
            wiki = self._load_wiki(path)
        assert wiki is not None, "wiki entry should exist after create"
        return wiki

    async def _update_wiki_from_raw(self, wiki: Dict, article: Dict) -> Dict:
        """从 raw 提取增量信息更新 wiki 条目 (Karpathy: 更新已有, 不堆新文件)"""
        path = Path(wiki["path"])
        old_content = wiki["content"]
        title = article.get("title", "新内容")
        source_kind = article.get("source_kind", "manual")
        date = datetime.now().strftime("%Y-%m-%d")

        # 新增"当前态势"段 (放在正文开头, Karpathy 原则: 最新在前)
        new_section = (
            f"## {date} 更新 ({source_kind})\n- {article.get('summary', title)}\n\n"
        )

        if self._is_stub(old_content):
            # 空壳条目 → 直接用新内容填充
            body = f"# {Path(path).stem}\n\n{new_section}## 关联\n"
            self._save_wiki(path, body)
        else:
            # 已有条目 → 插入新段到 ## 关联 之前
            if "## 关联" in old_content:
                new_content = old_content.replace("## 关联", new_section + "## 关联", 1)
            else:
                new_content = old_content.rstrip() + "\n\n" + new_section
            self._save_wiki(path, new_content)

        return {"entity": Path(path).stem, "path": str(path), "changed": True}

    # ================= Diff (每次 Wiki Writer 跑后) =================

    async def diff_wiki(self, wiki_id: Optional[int] = None) -> Dict:
        """
        Diff: 对比 wiki 条目新旧状态
        标记: strengthened / weakened / uncontested / new
        """
        if self.llm is not None:
            # LLM 模式: 交给 LLM 判断信号强度
            return await self._llm_diff(wiki_id)

        # 规则模式: 基于文件 mtime 和变更记录判断
        diffs = []
        for path in sorted(self.wiki_root.rglob("*.md")):
            mtime = path.stat().st_mtime
            age_hours = (datetime.now().timestamp() - mtime) / 3600
            if age_hours < 24:
                diffs.append(
                    {
                        "wiki_entry": str(path.relative_to(self.wiki_root)),
                        "status": "updated",
                        "change_summary": f"updated {age_hours:.1f}h ago",
                    }
                )
        return {"diffs": diffs, "count": len(diffs)}

    async def _llm_diff(self, wiki_id: Optional[int]) -> Dict:
        """LLM 判断 diff 信号强度"""
        paths = [str(p) for p in self.wiki_root.rglob("*.md")]
        prompt = (
            "对比以下 wiki 条目的最新更新段，判断每个条目的信号变化:\n"
            f"条目列表: {paths[:20]}\n"
            "输出格式: 条目路径|strengthened|一句话说明"
        )
        resp = await self.llm(prompt)
        assert resp is not None
        diffs = []
        for line in resp.strip().split("\n"):
            parts = line.split("|")
            if len(parts) >= 3:
                diffs.append(
                    {
                        "wiki_entry": parts[0],
                        "status": parts[1],
                        "change_summary": parts[2],
                    }
                )
        return {"diffs": diffs, "count": len(diffs)}

    # ================= Deep Compiler: wiki → synth → distill =================

    async def synth(self) -> Dict:
        """
        Synth: 跨条目交叉验证
        1. 读全部 wiki 条目
        2. 找矛盾、找强化、找缺口
        3. 补全 wikilinks
        """
        entries = {}
        for path in sorted(self.wiki_root.rglob("*.md")):
            if path.name in ("INDEX.md", "COMPILE_LOG.md", "WIKI_ARCHITECTURE.md"):
                continue
            wiki = self._load_wiki(path)
            if wiki:
                entries[str(path.relative_to(self.wiki_root))] = wiki

        # 1. 断链检测: wikilinks 指向不存在的条目
        broken_links = []
        all_names = set(entries.keys()) | {Path(p).stem for p in entries}
        for path, wiki in entries.items():
            for link in self._extract_wikilinks(wiki["content"]):
                target = link.split("/")[-1]
                if target not in all_names and target != Path(path).stem:
                    broken_links.append({"from": path, "to": target})

        # 2. 孤立条目: 没有任何 wikilink 指向它
        linked_to = set()
        for wiki in entries.values():
            for link in self._extract_wikilinks(wiki["content"]):
                linked_to.add(link.split("/")[-1])
        orphans = [
            p
            for p in entries
            if Path(p).stem not in linked_to and Path(p).stem != "INDEX"
        ]

        return {
            "entry_count": len(entries),
            "broken_links": broken_links,
            "orphan_entries": orphans,
            "suggestions": [
                f"修复断链 {len(broken_links)} 处",
                f"孤立条目 {len(orphans)} 个需要被引用",
            ],
        }

    async def distill(self, week: str) -> Dict:
        """
        Distill: wiki → 可用资产
        1. 七角色攻防话术
        2. 产品特性→客户利益对照表
        3. 竞品态势矩阵
        4. 综合洞察简报
        """
        entries = {}
        for path in sorted(self.wiki_root.rglob("*.md")):
            if path.name in ("INDEX.md", "COMPILE_LOG.md", "WIKI_ARCHITECTURE.md"):
                continue
            wiki = self._load_wiki(path)
            if wiki:
                entries[str(path.relative_to(self.wiki_root))] = wiki

        # 竞品条目
        competitor_entries = {
            p: w
            for p, w in entries.items()
            if "竞品" in p or "竞品" in w["content"][:200]
        }

        if self.llm is not None:
            prompt = (
                f"基于以下 wiki 条目，为超聚变 MO 生成 {week} 营销蒸馏:\n"
                "1. 七角色攻防话术(老板·高管·中层·技术·业务·运维·合规)各一条\n"
                "2. 产品特性→客户利益对照表(3行)\n"
                "3. 竞品态势矩阵(3家)\n\n"
                f"条目:\n"
                + "\n".join(f"[{p}]\n{w['content'][:500]}" for p, w in entries.items())
            )
            resp = await self.llm(prompt)
            assert resp is not None
            return {
                "week": week,
                "output_type": "talking_points",
                "content": resp,
                "source_wiki_ids": list(entries.keys())[:20],
            }

        # 规则兜底: 从竞品条目提取一句话态势
        competitor_matrix = []
        for p, w in competitor_entries.items():
            first_line = next(
                (
                    line
                    for line in w["content"].split("\n")
                    if line.strip().startswith("-")
                ),
                "暂无数据",
            )
            competitor_matrix.append(
                {"competitor": Path(p).stem, "headline": first_line.strip("- ")}
            )

        return {
            "week": week,
            "output_type": "talking_points",
            "content": {
                "competitor_matrix": competitor_matrix,
                "note": (
                    "LLM 未配置，使用规则蒸馏。接入 llm_client 后可生成完整七角色话术。"
                ),
            },
            "source_wiki_ids": list(competitor_entries.keys())[:20],
        }

    # ================= 对话处理 =================

    async def dialogue_to_wiki(self, dialogue_path: str) -> Dict:
        """
        对话 → wiki: 从对话 dump 提取实体和决策, 更新 wiki 条目
        """
        path = Path(dialogue_path)
        if not path.exists():
            return {"error": f"dialogue not found: {dialogue_path}"}

        content = path.read_text(encoding="utf-8")
        # 对话文件 → 伪 article 走 raw_to_wiki
        return await self.raw_to_wiki(
            {
                "title": path.stem,
                "content": content,
                "source_kind": "dialogue",
                "summary": f"对话资产 {path.stem}",
            }
        )
