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
from backend.services.knowledge_catalog import document_index, load_manifest

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "vault"
MATRIX_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_matrix.json"
)

SEARCH_LIMIT = 20
# Wiki is an evidence store, not a list of finished articles.  Chat needs enough
# surrounding facts to reason over a hit; the old 160 character window often
# returned only a heading (and title hits returned an empty snippet entirely).
_SNIPPET_CHARS = 600

_QUERY_NOISE = (
    "请问", "帮我查一下", "帮我查询", "查询一下", "查一下", "介绍一下",
    "我想了解", "想了解", "关于", "是做什么的", "做什么的", "是什么",
    "有什么", "怎么样", "如何", "请介绍", "请", "一下",
)


def _visibility():
    """当前可见范围: None=全部（超管/开发）；frozenset=已订阅分类集合。"""
    return current_visibility.get()


def _rel_visible(rel: str, vis: set[str] | frozenset[str] | None) -> bool:
    """Authorize an approved K5 document by its compiled logical pack.

    A path absent from ``knowledge_catalog.json`` is always invisible, even to
    a developer/super-admin request. ``vis is None`` only bypasses tenant pack
    selection; it never bypasses governance admission.
    """
    document = document_index(_vault()).get(rel)
    if document is None:
        return False
    if vis is None:
        return True
    return str(document.get("pack_id") or "") in vis


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


def _visible_wikilinks(text: str, vault: Path) -> List[str]:
    """Return only links whose target is inside the current authorization scope."""
    vis = _visibility()
    visible: List[str] = []
    for link in _wikilinks(text):
        relative = f"wiki/{link}.md"
        if _rel_visible(relative, vis) and (vault / relative).exists():
            visible.append(link)
    return visible


def _filtered_entity_index(m: Dict[str, Any]) -> Dict[str, List[str]]:
    vis = _visibility()
    return {
        str(entity): [str(path) for path in paths if _rel_visible(str(path), vis)]
        for entity, paths in (m.get("entity_index") or {}).items()
        if any(_rel_visible(str(path), vis) for path in paths)
    }


def _iter_md_files(vault: Path):
    vis = _visibility()
    for rel in sorted(document_index(vault)):
        if not _rel_visible(rel, vis):
            continue
        p = vault / rel
        if p.is_file():
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
    """Extract entity-oriented lexical terms from a natural-language question.

    The Wiki is queried by entity names and aliases.  Keeping only the raw
    sentence (for example ``超聚变是做什么的``) makes title matching fail, so
    we also retain a question-stripped phrase before normal tokenization.
    """
    normalized = text.lower()
    cleaned = normalized
    for phrase in _QUERY_NOISE:
        cleaned = cleaned.replace(phrase, " ")
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", cleaned).strip()
    candidates: List[str] = []
    if 2 <= len(cleaned) <= 40:
        candidates.append(cleaned)
    try:
        import jieba

        tokens = [t.strip() for t in jieba.cut(normalized)]
    except ModuleNotFoundError:
        tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", normalized)
    candidates.extend(
        token for token in tokens
        if len(token) >= 2 and token not in _QUERY_NOISE
    )
    return list(dict.fromkeys(candidates))


def _aliases(text: str) -> List[str]:
    raw = _frontmatter(text).get("aliases") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(item).strip() for item in raw if str(item).strip()]


def _snippet(text: str, terms: List[str]) -> str:
    """Return a useful factual window rather than an empty title-only hit."""
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)
    body = re.sub(r"^#\s+.*$", "", body, count=1, flags=re.MULTILINE).strip()
    low = body.lower()
    positions = [low.find(term) for term in terms if term and low.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 80)
    value = body[start : start + _SNIPPET_CHARS]
    return re.sub(r"\s+", " ", value).strip()


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
    wiki_targets: Dict[str, str] = {}
    if wiki_root.exists():
        for wf, rel in _iter_md_files(vault):
            if not rel.startswith("wiki/"):
                continue
            text = wf.read_text(encoding="utf-8", errors="ignore")
            title = _doc_title(text)
            aliases = _aliases(text)
            title_low = title.lower()
            searchable_names = [
                title_low,
                wf.stem.lower(),
                *[alias.lower() for alias in aliases],
            ]
            for name in searchable_names:
                wiki_targets.setdefault(name, rel)
            logical_path = rel.removeprefix("wiki/").removesuffix(".md").lower()
            wiki_targets.setdefault(logical_path, rel)
            wscore = 0
            for t in qtokens:
                if any(t in name or name in t for name in searchable_names):
                    wscore += 6  # wiki 命中高权重
            if any(ql in name or name in ql for name in searchable_names):
                wscore += 4
            if wscore > 0:
                scored[rel] = {
                    "path": rel,
                    "title": title,
                    "score": wscore,
                    "snippet": _snippet(text, qtokens),
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
            target = link.split("|")[0].split("#")[0].strip()
            rel = wiki_targets.get(target.lower())
            if rel is None:
                continue
            if not _rel_visible(rel, vis):
                continue
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
            "snippet": text[max(0, idx - 40) : idx + _SNIPPET_CHARS].replace("\n", " "),
        }

    documents = document_index(vault)
    ranked = sorted(scored.values(), key=lambda d: (-d["score"], d["path"]))
    for item in ranked:
        meta = documents.get(item["path"], {})
        if not item.get("snippet"):
            try:
                item["snippet"] = _snippet(
                    (vault / item["path"]).read_text(encoding="utf-8", errors="ignore"),
                    qtokens,
                )
            except OSError:
                item["snippet"] = ""
        item.update({
            "category": meta.get("pack_id", ""),
            "knowledge_level": meta.get("knowledge_level", "K5"),
            "classification_status": meta.get("classification_status", "approved"),
            "security_level": meta.get("security_level", ""),
            "freshness": meta.get("freshness", "unknown"),
            "source_count": int(meta.get("source_count") or 0),
        })
    return ranked[:limit]


@router.get("/matrix")
def get_matrix() -> Dict[str, Any]:
    m = _matrix()
    if not m:
        raise HTTPException(status_code=404, detail="knowledge_matrix.json not found")
    vis = _visibility()
    # 矩阵始终按治理 Catalog 过滤；超管也不能读取未批准文档。
    filtered = dict(m)
    cats: Dict[str, Any] = {}
    for cat, entries in (m.get("categories") or {}).items():
        if isinstance(entries, dict):
            sub = {
                k: v
                for k, v in entries.items()
                if isinstance(v, dict) and _rel_visible(str(v.get("path", k)), vis)
            }
            if sub:
                cats[cat] = sub
        elif isinstance(entries, list):
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
        "machine_interface": "knowledge_catalog+knowledge_matrix",
        "matrix_version": m.get("version", "unknown"),
        "generated_at": m.get("generated_at"),
        "source_of_truth": {
            "human": "wiki/ 已批准 K5 frontmatter",
            "machine": "knowledge_catalog.json（权限投影）+ knowledge_matrix.json（实体索引）",
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
        "categories_count": len(load_manifest(_vault()).get("packs") or []),
        "entity_count": len(_filtered_entity_index(m)),
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
        "matrix": {
            "total_documents": len(md_files),
            "categories_count": 0,
            "total_entities_indexed": len(_filtered_entity_index(m)),
        },
    }
    documents = document_index(vault)
    for _, rel in md_files:
        cat = str(documents.get(rel, {}).get("pack_id") or "unknown")
        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
    stats["matrix"]["categories_count"] = len(stats["categories"])
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
    filtered_entities = _filtered_entity_index(m)
    if filtered_entities:
        for ent in filtered_entities:
            if q.lower() in ent.lower():
                entities.append(ent)

    return {"query": q, "total": len(docs), "docs": docs, "entity_hits": entities}


@router.get("/entities")
def entities(
    q: Optional[str] = Query(None, max_length=100),
) -> Dict[str, Any]:
    m = _matrix()
    idx = _filtered_entity_index(m)
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
        entries.append(
            {
                "slug": p.relative_to(wiki_dir).with_suffix("").as_posix(),
                "title": fm.get("title", p.stem),
                "status": fm.get("status", "unknown"),
                "tags": fm.get("tags", []),
                "links_out": _visible_wikilinks(text, vault),
            }
        )
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
        "wikilinks": _visible_wikilinks(text, vault),
        "content": body,
    }
