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
import hashlib
import re
from functools import lru_cache, wraps
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException, Query, Depends

from backend.api.tenant import current_visibility
from backend.services.knowledge_catalog import (
    document_index, load_manifest, filter_database_live_documents,
    AUTHORIZED_DOCUMENT_PATHS, resolve_authorized_version,
    _apply_file_read_barrier, run_knowledge_read,
)

# Candidate metadata is request-local, not an authorization cache. Every target
# still passes the live file barrier, and HTTP boundaries recheck durable state.
_CANDIDATE_INDEX: ContextVar = ContextVar("knowledge_candidate_index", default=None)


def _candidate_documents(vault):
    scope = _CANDIDATE_INDEX.get()
    if scope is not None and scope[0] == vault.resolve():
        return scope[1]
    return document_index(vault)


@contextmanager
def _candidate_scope(vault, documents=None):
    scope = _CANDIDATE_INDEX.get()
    if documents is None and scope is not None and scope[0] == vault.resolve():
        yield
        return
    token = _CANDIDATE_INDEX.set((vault.resolve(),
        document_index(vault) if documents is None else documents))
    try:
        yield
    finally:
        _CANDIDATE_INDEX.reset(token)


def _with_candidates(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        vault = next((arg for arg in args if isinstance(arg, Path)), kwargs.get("vault", _vault()))
        with _candidate_scope(vault):
            return function(*args, **kwargs)
    return wrapped


async def _live_read_scope():
    vault = _vault()
    candidates = await run_knowledge_read(document_index, vault)
    documents = await filter_database_live_documents(list(candidates.values()), vault)
    token = AUTHORIZED_DOCUMENT_PATHS.set(frozenset(item["path"] for item in documents))
    with _candidate_scope(vault, {item["path"]: item for item in documents}):
        try:
            yield
        finally:
            AUTHORIZED_DOCUMENT_PATHS.reset(token)


def _read_endpoint(function):
    @wraps(function)
    async def endpoint(*args, **kwargs):
        result = await run_knowledge_read(function, *args, **kwargs)
        # Revoke the whole response on a mid-read change, including entity names
        # and link labels, rather than leaking a partially filtered projection.
        candidates = _candidate_documents(_vault())
        live = await filter_database_live_documents(list(candidates.values()), _vault())
        before_scope = {path for path, item in candidates.items()
                        if resolve_authorized_version(path, {path: item}, _visibility())}
        after_scope = {item["path"] for item in live if resolve_authorized_version(
            item["path"], {item["path"]: item}, _visibility())}
        if {item["path"] for item in live} != set(candidates) or before_scope != after_scope:
            raise HTTPException(status_code=409, detail="knowledge changed during read; retry")
        return result
    return endpoint


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"], dependencies=[Depends(_live_read_scope)])

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
    scope = _CANDIDATE_INDEX.get()
    vault = scope[0] if scope is not None else _vault()
    document = _candidate_documents(vault).get(rel)
    if document is not None:
        document = _apply_file_read_barrier(vault, document)
    if document is None:
        return False
    live_paths = AUTHORIZED_DOCUMENT_PATHS.get()
    if live_paths is not None and rel not in live_paths:
        return False
    if document.get("disclosure_granularity") == "summary" and live_paths is None:
        return False
    resolved = resolve_authorized_version(rel, {rel: document}, vis)
    return resolved is not None


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


def _markdown_links(text: str) -> list[tuple[str, str]]:
    """Use the already installed CommonMark parser, including reference links.

    Record exact source fragments instead of re-rendering the evidence body.
    Parsing permits every URI so unsafe schemes are identified and denied by
    our own authorization boundary, not left behind as unparsed literal text.
    """
    from markdown_it import MarkdownIt
    from markdown_it.rules_inline import autolink, image, link
    parser = MarkdownIt("commonmark")
    parser.validateLink = lambda url: True
    found: list[tuple[str, str]] = []

    def capture(rule):
        def wrapped(state, silent):
            start, count = state.pos, len(state.tokens)
            accepted = rule(state, silent)
            if accepted and not silent:
                for token in state.tokens[count:]:
                    if token.type in {"link_open", "image"}:
                        target = token.attrGet("href" if token.type == "link_open" else "src")
                        if target:
                            found.append((state.src[start:state.pos], target))
                            break
            return accepted
        return wrapped

    for name, rule in (("link", link), ("image", image), ("autolink", autolink)):
        parser.inline.ruler.at(name, capture(rule))
    env: dict = {}
    tokens = parser.parse(text, env)
    lines = text.splitlines(keepends=True)
    # Raw HTML is outside the Wiki/OKF link contract. Remove its entire block,
    # not just the tags, so private labels and attributes cannot survive.
    for token in tokens:
        has_html = token.type == "html_block" or any(
            child.type == "html_inline" for child in (token.children or [])
        )
        if has_html and token.map:
            found.append(("".join(lines[token.map[0]:token.map[1]]), ""))
    for definition in env.get("references", {}).values():
        start, end = definition["map"]
        found.append(("".join(lines[start:end]), definition["href"]))
    return sorted(found, key=lambda item: len(item[0]), reverse=True)



def _wikilinks(text: str) -> List[str]:
    """Extract Wiki and Markdown destinations; public URLs are not Wiki edges."""
    from urllib.parse import urlsplit
    links = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", text)
    links.extend(target for _, target in _markdown_links(text) if not urlsplit(target).scheme)
    return [link.split("#", 1)[0].strip() for link in links if link.split("#", 1)[0].strip()]


def _safe_vault_file(vault: Path, relative: str) -> Path | None:
    try:
        path = (vault / relative).resolve()
        return path if vault.resolve() in path.parents and path.is_file() else None
    except OSError:
        return None


def _resolve_wiki_target(target: str, vault: Path, source: str = "", *, markdown: bool = False) -> str | None:
    from urllib.parse import unquote, urlsplit
    import posixpath
    target = unquote(target).split("#", 1)[0].strip()
    if not target or urlsplit(target).scheme or target.startswith(("/", "\\")) or "\\" in target:
        return None
    target = target.removesuffix(".md")
    documents = _candidate_documents(vault)
    if "/" in target or markdown:
        if target.startswith("wiki/"):
            relative = posixpath.normpath(target) + ".md"
        elif source:
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(source), target)) + ".md"
            # Root-relative Obsidian folder paths remain compatible.
            if not markdown and not target.startswith(".") and relative not in documents:
                relative = posixpath.normpath("wiki/" + target) + ".md"
        else:
            relative = posixpath.normpath("wiki/" + target) + ".md"
        if not relative.startswith("wiki/") or relative not in documents:
            return None
        return relative if _rel_visible(relative, _visibility()) else None
    matches = []
    for path, meta in documents.items():
        if not path.startswith("wiki/"):
            continue
        aliases = meta.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        names = [Path(path).stem, str(meta.get("title") or ""), *aliases]
        if any(str(name).casefold() == target.casefold() for name in names) and _rel_visible(path, _visibility()):
            matches.append(path)
    return matches[0] if len(matches) == 1 else None


@_with_candidates
def _visible_wikilinks(text: str, vault: Path, source: str = "") -> List[str]:
    """Only authorized, unambiguous destinations; links never grant access."""
    visible: List[str] = []
    markdown_targets = {target.split("#", 1)[0] for _, target in _markdown_links(text)}
    for link in _wikilinks(text):
        relative = _resolve_wiki_target(link, vault, source, markdown=link in markdown_targets)
        if relative and _safe_vault_file(vault, relative):
            visible.append(relative.removeprefix("wiki/").removesuffix(".md"))
    return list(dict.fromkeys(visible))


@_with_candidates
def _filtered_entity_index(m: Dict[str, Any]) -> Dict[str, List[str]]:
    vis = _visibility()
    result = {}
    for entity, paths in (m.get("entity_index") or {}).items():
        visible = [str(path) for path in paths if _rel_visible(str(path), vis)]
        if visible:
            result[str(entity)] = visible
    return result


def _iter_md_files(vault: Path):
    documents = _candidate_documents(vault)
    vis = _visibility()
    for rel in sorted(documents):
        # Never leave a ContextVar token installed across a generator yield:
        # direct callers may stop iterating early or interleave other requests.
        with _candidate_scope(vault, documents):
            if not _rel_visible(rel, vis):
                continue
            p = _safe_vault_file(vault, rel)
        if p is not None:
            yield p, rel


@_with_candidates
def _model_text(text: str, relative: str, vault: Path) -> str:
    """Disclosure metadata contains private lineage; it is not model evidence."""
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)
    # Omit unauthorized link labels and targets as well as links_out metadata.
    def link(match):
        target = match.group(1).split("|")[0].split("#")[0].strip()
        return match.group(0) if _resolve_wiki_target(target, vault, relative) else ""
    body = re.sub(r"\[\[([^\]]+)\]\]", link, body)
    from urllib.parse import urlsplit
    for fragment, target in _markdown_links(body):
        if urlsplit(target).scheme.lower() not in {"http", "https"} and not _resolve_wiki_target(target, vault, relative, markdown=True):
            body = body.replace(fragment, "")
    return body


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

        tokens = [t.strip() for t in jieba.cut(cleaned)]
    except ModuleNotFoundError:
        tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", cleaned)
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


def _term_in(term: str, text: str) -> bool:
    """Literal topic matching, not semantic inference or an authorization rule."""
    term, text = term.strip().casefold(), text.casefold()
    if not term:
        return False
    if re.fullmatch(r"[a-z0-9_.-]+", term):
        return re.search(r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])", text) is not None
    return term in text


@_with_candidates
def _search_docs(vault: Path, q: str, limit: int, *, entities: list[str] | None = None,
                 topics: list[str] | None = None, paths: list[str] | None = None) -> List[Dict[str, Any]]:
    """Locate authorized Wiki evidence; Hermes supplies intent and chooses links.

    Entities are entry hints, topics are required literal terms (including live
    aliases). Explicit paths select subsequent reads, never grant access. Matrix
    and links cannot manufacture relevance or add evidence to a result set.
    """
    qtokens = _tokenize_query(q)
    terms: list[str] = list(dict.fromkeys([*(entities or []), *(topics or []), *qtokens]))
    vis = _visibility()
    scored: Dict[str, Dict[str, Any]] = {}
    selected = set(paths or [])
    # Legacy matrix callers retain locator recall, never additive relevance.
    try:
        matrix = _matrix()
    except (OSError, ValueError):
        matrix = {}  # Optional locator failure cannot disable live Wiki reads.
    located = {str(path) for entity, targets in (matrix.get("entity_index") or {}).items()
               if any(_term_in(term, str(entity)) for term in terms)
               for path in targets}
    for path, rel in _iter_md_files(vault):
        if selected and rel not in selected:
            continue
        text = path.read_text(encoding="utf-8")
        title = _doc_title(text)
        names = "\n".join([title, path.stem, *_aliases(text)])
        body = _model_text(text, rel, vault)
        is_summary = _candidate_documents(vault)[rel].get("disclosure_granularity") == "summary"
        if is_summary:
            # Only the published body is hash-bound by the existing review.
            # Unreviewed frontmatter titles/aliases/links cannot become evidence.
            title = _doc_title(body)[:200]
            names = title
        # Metadata/lineage and unauthorized link labels are never search evidence.
        lexical_body = re.sub(r"\[\[[^\]]+\]\]", "", body)
        for fragment, _ in _markdown_links(body):
            lexical_body = lexical_body.replace(fragment, "")
        searchable = names + "\n" + lexical_body
        if topics and not all(_term_in(topic, searchable) for topic in topics):
            continue
        name_hits = sum(_term_in(term, names) for term in terms)
        body_hits = sum(_term_in(term, lexical_body) for term in terms)
        if not selected and not name_hits and not body_hits and rel not in located:
            continue
        # Check the residual question against this entry, not other entities.
        # Tokenize only after removing matched entry names: compound names must
        # not be mistaken for missing topics, nor erase an unrequested topic.
        residual = q.casefold()
        for name in sorted(names.splitlines(), key=len, reverse=True):
            if name.strip():
                residual = residual.replace(name.casefold(), " ")
        residual_terms = _tokenize_query(residual)
        atomic_terms = [t for t in residual_terms if not any(
            other != t and other in t for other in residual_terms)]
        topic_gap = not topics and not selected and name_hits and any(
            not _term_in(t, searchable) for t in atomic_terms)
        scored[rel] = {
            "path": rel, "title": title,
            "score": name_hits * 6 + body_hits,
            "snippet": _snippet(body, terms),
            "match_basis": "topic_gap" if topic_gap else "selected_path" if selected else "entry" if name_hits else "body" if body_hits else "index_only",
            "wikilinks": _visible_wikilinks(body if is_summary else text, vault, rel),
        }

    documents = _candidate_documents(vault)
    ranked = sorted(
        (item for item in scored.values() if _safe_vault_file(vault, item["path"])
         and _rel_visible(item["path"], vis)),
        key=lambda d: (not d["path"].startswith("wiki/"), d.get("match_basis") not in {"entry", "selected_path"}, -d["score"], d["path"]),
    )[:limit]
    for item in ranked:
        meta = documents.get(item["path"], {})
        # Search snippets obey the same link/body boundary, never index lineage.
        safe_text = _model_text((vault / item["path"]).read_text(encoding="utf-8"), item["path"], vault)
        item["snippet"] = _snippet(safe_text, qtokens)
        try:
            raw = (vault / item["path"]).read_bytes()
        except OSError:
            raw = b""
        item.update({
            "knowledge_id": meta.get("knowledge_id") or hashlib.sha256(
                item["path"].encode()
            ).hexdigest()[:24],
            "category": meta.get("pack_id", ""),
            "knowledge_level": meta.get("knowledge_level", "K5"),
            "classification_status": meta.get("classification_status", "approved"),
            "security_level": meta.get("security_level", ""),
            "freshness": meta.get("freshness", "unknown"),
            "confidence": meta.get("confidence", "unknown"),
            "quality_status": meta.get("quality_status", "unrated"),
            "disclosure_granularity": meta.get("disclosure_granularity", "detail"),
            "source_count": int(meta.get("source_count") or 0),
            "version": hashlib.sha256(raw).hexdigest(),
            "source_kind": meta.get("source_kind") or "governed_wiki",
            "citation": f"knowledge:{item['path']}",
            "conditions": meta.get("conditions") or [],
            "effective_at": meta.get("effective_at") or meta.get("updated_at"),
        })
    return ranked[:limit]


@_with_candidates
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


@_with_candidates
def get_contract() -> Dict[str, Any]:
    """暴露当前机读知识接口契约，明确已实现边界。"""
    m = _matrix()
    return {
        # Keep the legacy identifier for clients; the role fields below are the
        # current authority. Matrix presence is not a prerequisite for Wiki reads.
        "machine_interface": "knowledge_catalog+knowledge_matrix",
        "retrieval_interface": "wiki_entries_and_relevant_links",
        "matrix_role": "rebuildable_compatibility_projection_not_truth_or_admission",
        "matrix_available": bool(m),
        "matrix_version": m.get("version", "unknown"),
        "generated_at": m.get("generated_at"),
        "source_of_truth": {
            "human": "Wiki正文与元数据；原始资料保留来源真值",
            "machine": "既有授权与治理记录；目录和实体索引是Wiki的可重建投影",
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


@_with_candidates
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
    documents = _candidate_documents(vault)
    for _, rel in md_files:
        cat = str(documents.get(rel, {}).get("pack_id") or "unknown")
        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
    stats["matrix"]["categories_count"] = len(stats["categories"])
    return stats


@_with_candidates
def search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(SEARCH_LIMIT, ge=1, le=50),
) -> Dict[str, Any]:
    vault = _vault()
    if not vault.exists():
        raise HTTPException(status_code=404, detail=f"vault not found: {vault}")
    docs = _search_docs(vault, q, limit)
    from backend.services.knowledge_publication_store import PUBLICATION_CATEGORY, PublicationStore
    store = PublicationStore()
    vis = _visibility()
    known = {item["path"] for item in docs}
    docs.extend(item for item in store.search(q, limit, public_metadata_only=True) if item["path"] not in known)
    if vis is None or PUBLICATION_CATEGORY in vis:
        known = {item["path"] for item in docs}
        docs.extend(item for item in store.search(q, limit) if item["path"] not in known)
    docs = sorted(docs, key=lambda item: (-item["score"], item["path"]))[:limit]

    # 实体命中（矩阵 entity_index）
    entities: List[str] = []
    m = _matrix()
    filtered_entities = _filtered_entity_index(m)
    if filtered_entities:
        for ent in filtered_entities:
            if q.lower() in ent.lower():
                entities.append(ent)

    return {"query": q, "total": len(docs), "docs": docs, "entity_hits": entities}


@_with_candidates
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


@_with_candidates
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
                "links_out": _visible_wikilinks(text, vault, rel),
            }
        )
    return {"total": len(entries), "entries": entries}


@_with_candidates
def get_wiki(slug: str) -> Dict[str, Any]:
    vault = _vault()
    wiki_dir = vault / "wiki"
    if not wiki_dir.exists():
        raise HTTPException(status_code=404, detail="wiki dir not found")
    # 防路径穿越（统一 resolve 根，避免 macOS /private 符号链接不一致）
    wiki_root = wiki_dir.resolve()
    target = (wiki_dir / f"{slug}.md").resolve()
    if wiki_root not in target.parents:
        raise HTTPException(status_code=403, detail="invalid slug")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"wiki entry not found: {slug}")
    rel = target.relative_to(wiki_root).as_posix()
    rel = f"wiki/{rel}"
    if not _rel_visible(rel, _visibility()):
        live_paths = AUTHORIZED_DOCUMENT_PATHS.get() or frozenset()
        resolved = resolve_authorized_version(rel, {
            key: value for key, value in _candidate_documents(vault).items()
            if key in live_paths and _rel_visible(key, _visibility())
        }, _visibility())
        if resolved is None:
            raise HTTPException(status_code=404, detail="wiki entry unavailable")
        rel = resolved["path"]
        target = vault / rel
        slug = rel.removeprefix("wiki/").removesuffix(".md")
    text = target.read_text(encoding="utf-8", errors="ignore")
    fm = _frontmatter(text)
    return {
        "slug": slug,
        "title": fm.get("title", target.stem),
        "status": fm.get("status", "unknown"),
        "tags": fm.get("tags", []),
        "frontmatter": {key: fm[key] for key in ("title", "status", "tags", "knowledge_level",
            "disclosure_granularity", "conditions", "effective_at") if key in fm},
        "citation": f"knowledge:{rel}",
        "version": hashlib.sha256(text.encode()).hexdigest(),
        "wikilinks": _visible_wikilinks(text, vault, rel),
        "content": _model_text(text, rel, vault),
    }


async def read_wiki_live(slug: str) -> Dict[str, Any]:
    """Reuse the HTTP Wiki read scope and its post-read revocation check."""
    scope = _live_read_scope()
    await scope.__anext__()
    try:
        return await _read_endpoint(get_wiki)(slug)
    finally:
        await scope.aclose()


for _route, _handler in (
    ("/matrix", get_matrix), ("/contract", get_contract), ("/stats", get_stats),
    ("/search", search), ("/entities", entities), ("/wiki", list_wiki),
    ("/wiki/{slug:path}", get_wiki),
):
    router.add_api_route(_route, _read_endpoint(_handler), methods=["GET"])
