"""
知识引擎 API — 让镜像到服务器的知识库可查可用

数据源（容器内挂载 /app/data）:
- AI_LAB_HOME        = /app/data/vault        (本地 Obsidian 库镜像)
- knowledge_matrix   = /app/data/knowledge_matrix.json (矩阵 v2.0，服务器重建)

能力:
- GET /api/knowledge/matrix     全量知识矩阵
- GET /api/knowledge/stats      知识库统计
- GET /api/knowledge/search?q=  全文检索（标题/正文/实体）
- GET /api/knowledge/entities   实体索引查询
- GET /api/knowledge/wiki       wiki 条目列表
- GET /api/knowledge/wiki/{slug} 单条 wiki（含 wikilinks）
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException, Query

from backend.api.tenant import current_visibility

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "vault"
MATRIX_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_matrix.json"
)

SEARCH_LIMIT = 20
_SNIPPET_CHARS = 160


def _visibility():
    """当前可见范围: None=全部（超管/开发）；frozenset=已订阅分类集合。"""
    return current_visibility.get()


def _rel_visible(rel: str, vis: set[str] | frozenset[str] | None) -> bool:
    """文档相对路径是否对当前可见范围可见（支持多段类目前缀匹配）。

    - ``vis is None`` → 全部可见（超管 / 开发态）
    - 否则：rel 与任一已订类目相等，或以 ``类目/`` 为前缀即可见。
      单层类目零回归（如 ``wiki/条目.md`` 对 ``wiki``）；
      多段类目通过前缀对齐（如 ``knowledge/行业知识/金融/动态.md`` 对
      ``knowledge/行业知识/金融``）。
    """
    if vis is None:
        return True
    return any(rel == cat or rel.startswith(f"{cat}/") for cat in vis)


def _vault() -> Path:
    import os

    return Path(os.environ.get("AI_LAB_HOME", str(VAULT_ROOT)))


@lru_cache(maxsize=1)
def _matrix() -> Dict[str, Any]:
    for cand in (MATRIX_PATH, _vault() / "knowledge_matrix.json"):
        if cand.exists():
            with open(cand, encoding="utf-8") as fh:
                return json.load(fh)
    return {}


def _frontmatter(text: str) -> Dict[str, Any]:
    """解析 YAML frontmatter，失败返回空 dict。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def _wikilinks(text: str) -> List[str]:
    """提取 [[target]] 链接，去掉锚点和别名。"""
    links = re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]", text)
    return [link.strip() for link in links if link.strip()]


def _iter_md_files(vault: Path):
    vis = _visibility()
    for p in sorted(vault.rglob("*.md")):
        rel = p.relative_to(vault).as_posix()
        if rel.startswith((".obsidian", "_archive", "00_Inbox", "模板")):
            continue
        if not _rel_visible(rel, vis):
            continue
        yield p, rel


def _doc_title(text: str) -> str:
    """标题优先级: frontmatter.title → 首个 # 标题 → 首行。"""
    fm = _frontmatter(text)
    t = fm.get("title")
    if isinstance(t, str) and t.strip():
        return t.strip()
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    return first_line.lstrip("# ").strip() or Path("unknown").stem


def _tokenize_query(text: str) -> List[str]:
    """优先使用 jieba；缺失时退回轻量正则切词，避免本地依赖不全直接 500。"""
    normalized = text.lower()
    try:
        import jieba

        tokens = [t.strip() for t in jieba.cut(normalized)]
    except ModuleNotFoundError:
        tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", normalized)
    return [token for token in tokens if len(token) >= 2]


def _matrix_doc_entries(m: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """把矩阵 categories 展平为 path → 文档条目（兼容 dict 与 list 两种形状）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for cat in m.get("categories", {}).values():
        if not isinstance(cat, dict):
            continue
        for entry in cat.values():
            if isinstance(entry, dict) and entry.get("path"):
                out[entry["path"]] = entry
    return out


def _search_docs(vault: Path, q: str, limit: int) -> List[Dict[str, Any]]:
    """检索 v4 —— wiki 优先（对齐 Karpathy：wiki 是唯一真理源）。

    检索顺序：
    1. wiki/ 目录定位: 实体名 → wiki/ 下对应条目（标题/文件名匹配优先）
    2. wikilinks 追读: 命中条目的 [[wikilinks]] 关联条目计入候选
    3. 矩阵辅助: knowledge_matrix 实体反查补充（仅索引层，不主导）
    4. 内容兜底: 未收录文档按 jieba 词项扫描（raw/ 等）
    上下文片段优先取 wiki 条目正文。
    """
    ql = q.lower()
    qtokens = _tokenize_query(ql)
    m = _matrix()
    entries = _matrix_doc_entries(m)
    scored: Dict[str, Dict[str, Any]] = {}

    # 1) wiki/ 优先: 实体名 → wiki/ 目录定位（wiki 是唯一真理源）
    vis = _visibility()
    wiki_root = vault / "wiki"
    if wiki_root.exists():
        for wf in sorted(wiki_root.rglob("*.md")):
            rel = wf.relative_to(vault).as_posix()
            if not _rel_visible(rel, vis):
                continue
            title = _doc_title(wf.read_text(encoding="utf-8", errors="ignore"))
            title_low = title.lower()
            wscore = 0
            for t in qtokens:
                if t in title_low or t in wf.stem.lower():
                    wscore += 6  # wiki 命中高权重
            if ql in title_low or ql in wf.stem.lower():
                wscore += 4
            if wscore > 0:
                scored[rel] = {
                    "path": rel,
                    "title": title,
                    "score": wscore,
                    "snippet": "",
                }

    # 1.5) wikilinks 追读: 命中 wiki 条目的关联条目计入候选（Karpathy 知识网）
    import re
    hit_paths = [p for p, e in scored.items() if p.startswith("wiki/")]
    for hp in hit_paths:
        try:
            htext = (vault / hp).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for link in re.findall(r"\[\[([^\]]+)\]\]", htext):
            target = link.split("|")[0].strip()
            # 目标可能是 "竞品/DeepSeek" 或 "DeepSeek" → 定位到 wiki/ 下
            tpath = (vault / "wiki" / f"{target}.md").as_posix()
            if not (vault / tpath).exists():
                continue
            rel = tpath
            if rel in scored:
                scored[rel]["score"] += 3  # wikilinks 关联加分
            else:
                scored[rel] = {
                    "path": rel,
                    "title": _doc_title(
                        (vault / rel).read_text(encoding="utf-8", errors="ignore")
                    ),
                    "score": 3,
                    "snippet": "",
                }

    # 2) 矩阵打分（辅助: 补 wiki 未覆盖的分类/文档）
    for path, e in entries.items():
        if not _rel_visible(path, vis):
            continue
        title_low = (e.get("title") or "").lower()
        ents = [str(x).lower() for x in (e.get("entities") or [])]
        tags = [str(x).lower() for x in (e.get("tags") or [])]
        score = 0
        for t in qtokens:
            if t in title_low:
                score += 2  # 矩阵命中降权（wiki 为主）
        for t in qtokens:
            if any(t in ent or ent in t for ent in ents):
                score += 1
        for t in qtokens:
            if any(t in tag for tag in tags):
                score += 1
        if ql in title_low:
            score += 2
        if score <= 0:
            continue
        if path in scored:
            scored[path]["score"] += score  # 合并加分
        else:
            scored[path] = {
                "path": path,
                "title": e.get("title") or path,
                "score": score,
                "snippet": (e.get("summary") or "")[:_SNIPPET_CHARS],
            }

    # 2) entity_index 反查
    ei = m.get("entity_index", {})
    for ent, paths in ei.items():
        ent_low = str(ent).lower()
        if ent_low in ql or any(ent_low in t or t in ent_low for t in qtokens):
            for p in paths:
                if not _rel_visible(p, vis):
                    continue
                if p not in scored:
                    scored[p] = {
                        "path": p,
                        "title": p,
                        "score": 1,
                        "snippet": "",
                    }

    # 3) 内容兜底（矩阵未收录的文档，如 raw/）
    for p, rel in _iter_md_files(vault):
        if rel in scored:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        low = text.lower()
        matched = [t for t in qtokens if t in low]
        if not matched:
            continue
        title = _doc_title(text)
        score = len(matched) * 2
        if any(t in title.lower() for t in matched):
            score += 4
        idx = low.find(matched[0])
        scored[rel] = {
            "path": rel,
            "title": title,
            "score": score,
            "snippet": text[max(0, idx - 40): idx + _SNIPPET_CHARS].replace("\n", " "),
        }

    ranked = sorted(scored.values(), key=lambda d: (-d["score"], d["path"]))
    return ranked[:limit]


@router.get("/matrix")
def get_matrix() -> Dict[str, Any]:
    m = _matrix()
    if not m:
        raise HTTPException(status_code=404, detail="knowledge_matrix.json not found")
    vis = _visibility()
    if vis is None:
        return m
    # 订阅制: 返回过滤后的矩阵（只含可见分类/条目）
    filtered = dict(m)
    cats: Dict[str, Any] = {}
    for cat, entries in (m.get("categories") or {}).items():
        if isinstance(entries, dict):
            if cat in vis:
                cats[cat] = entries
            else:
                sub = {
                    k: v
                    for k, v in entries.items()
                    if isinstance(v, dict) and _rel_visible(str(v.get("path", k)), vis)
                }
                if sub:
                    cats[cat] = sub
        elif isinstance(entries, list):
            if cat in vis:
                cats[cat] = entries
            else:
                sub = [p for p in entries if _rel_visible(str(p), vis)]
                if sub:
                    cats[cat] = sub
    filtered["categories"] = cats
    ei = m.get("entity_index", {})
    filtered["entity_index"] = {
        k: [p for p in v if _rel_visible(p, vis)] for k, v in ei.items()
    }
    return filtered


@router.get("/contract")
def get_contract() -> Dict[str, Any]:
    """暴露当前机读知识接口契约，明确已实现边界。"""
    m = _matrix()
    if not m:
        raise HTTPException(status_code=404, detail="knowledge_matrix.json not found")
    return {
        "machine_interface": "knowledge_matrix",
        "matrix_version": m.get("version", "unknown"),
        "generated_at": m.get("generated_at"),
        "source_of_truth": {
            "human": "编译后的知识层（研究系统 / wiki 兼容视图）",
            "machine": "knowledge_matrix.json",
        },
        "implemented": [
            "matrix",
            "stats",
            "search",
            "entities",
            "wiki_list",
            "wiki_detail",
            "chat",
        ],
        "planned": [
            "task_replay",
            "runtime_audit_dashboard",
            "policy-driven compile orchestration",
        ],
        "categories_count": m.get("stats", {}).get("categories_count", 0),
        "entity_count": m.get("stats", {}).get("total_entities_indexed", 0),
    }


@router.get("/stats")
def get_stats() -> Dict[str, Any]:
    vault = _vault()
    if not vault.exists():
        raise HTTPException(status_code=404, detail=f"vault not found: {vault}")
    md_files = list(_iter_md_files(vault))
    m = _matrix()
    stats = {
        "vault": str(vault),
        "total_md_files": len(md_files),
        "categories": {},
        "matrix": m.get("stats", {}),
    }
    for _, rel in md_files:
        cat = rel.split("/")[0]
        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
    return stats


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(SEARCH_LIMIT, ge=1, le=50),
) -> Dict[str, Any]:
    vault = _vault()
    if not vault.exists():
        raise HTTPException(status_code=404, detail=f"vault not found: {vault}")
    docs = _search_docs(vault, q, limit)

    # 实体命中（矩阵 entity_index）
    entities: List[str] = []
    m = _matrix()
    if m.get("entity_index"):
        for ent in m["entity_index"]:
            if q.lower() in ent.lower():
                entities.append(ent)

    return {"query": q, "total": len(docs), "docs": docs, "entity_hits": entities}


@router.get("/entities")
def entities(
    q: Optional[str] = Query(None, max_length=100),
) -> Dict[str, Any]:
    m = _matrix()
    idx = m.get("entity_index", {})
    if not idx:
        raise HTTPException(status_code=404, detail="entity_index not found")
    if q:
        hits = {k: v for k, v in idx.items() if q.lower() in k.lower()}
        return {"query": q, "total": len(hits), "entities": hits}
    return {"total": len(idx), "entities": idx}


@router.get("/wiki")
def list_wiki() -> Dict[str, Any]:
    vault = _vault()
    vis = _visibility()
    wiki_dir = vault / "wiki"
    if not wiki_dir.exists():
        raise HTTPException(status_code=404, detail="wiki dir not found")
    entries: List[Dict[str, Any]] = []
    for p in sorted(wiki_dir.rglob("*.md")):
        rel = p.relative_to(vault).as_posix()
        if not _rel_visible(rel, vis):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        fm = _frontmatter(text)
        entries.append({
            "slug": p.relative_to(wiki_dir).with_suffix("").as_posix(),
            "title": fm.get("title", p.stem),
            "status": fm.get("status", "unknown"),
            "tags": fm.get("tags", []),
            "links_out": _wikilinks(text),
        })
    return {"total": len(entries), "entries": entries}


@router.get("/wiki/{slug:path}")
def get_wiki(slug: str) -> Dict[str, Any]:
    vault = _vault()
    wiki_dir = vault / "wiki"
    if not wiki_dir.exists():
        raise HTTPException(status_code=404, detail="wiki dir not found")
    # 防路径穿越（统一 resolve 根，避免 macOS /private 符号链接不一致）
    wiki_root = wiki_dir.resolve()
    target = (wiki_dir / f"{slug}.md").resolve()
    if not str(target).startswith(str(wiki_root)):
        raise HTTPException(status_code=403, detail="invalid slug")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"wiki entry not found: {slug}")
    rel = target.relative_to(wiki_root).as_posix()
    rel = f"wiki/{rel}"
    if not _rel_visible(rel, _visibility()):
        raise HTTPException(status_code=404, detail=f"wiki entry not found: {slug}")
    text = target.read_text(encoding="utf-8", errors="ignore")
    fm = _frontmatter(text)
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, flags=re.DOTALL).strip()
    return {
        "slug": slug,
        "title": fm.get("title", target.stem),
        "status": fm.get("status", "unknown"),
        "tags": fm.get("tags", []),
        "frontmatter": fm,
        "wikilinks": _wikilinks(text),
        "content": body,
    }
