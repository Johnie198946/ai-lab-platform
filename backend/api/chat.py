"""
问答 API — 基于知识库的 RAG 回答

流程: 问题 → 知识引擎检索（复用 knowledge.py）→ 组装上下文
      → deepseek 生成 → 返回答案+来源

环境变量: DEEPSEEK_API_KEY（compose 从 .env 注入）
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# 通过模块引用，保证与 knowledge.py 的 monkeypatch 兼容（测试用）
from backend.api import knowledge
from backend.api.auth import require_auth

router = APIRouter(prefix="/api/chat", tags=["chat"])

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
SYSTEM_PROMPT = (
    "你是 AI Lab 知识库助手。只能基于「参考资料」回答，不要编造。"
    "回答中标注引用来源（用 [1][2] 对应参考编号）。"
    "如果资料不足，明确说『知识库中没有足够信息』，不要猜测。"
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(6, ge=1, le=15)  # 检索上下文条数
    model: str = Field(DEFAULT_MODEL, max_length=50)


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]]
    model: str


def _resolve_wiki_entries(vault: Path, q: str, limit: int) -> List[str]:
    """实体解析 —— Karpathy 原则: 目录结构即索引。

    优先在 wiki/ 目录内按 标题/别名/文件名/目录类型 打分；
    matrix entity_index 仅作实体反查补充。
    """
    ql = q.lower()
    qtokens = knowledge._tokenize_query(ql)
    vis = knowledge._visibility()
    wiki_dir = vault / "wiki"
    scored: Dict[str, int] = {}
    if wiki_dir.exists():
        for p in wiki_dir.rglob("*.md"):
            rel = p.relative_to(vault).as_posix()
            if not knowledge._rel_visible(rel, vis):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            fm = knowledge._frontmatter(text)
            title = str(fm.get("title") or p.stem)
            aliases = [str(a).lower() for a in (fm.get("aliases") or [])]
            title_low = title.lower()
            stem_low = p.stem.lower()
            dir_low = p.parent.name.lower()
            score = 0
            for t in qtokens:
                if t in title_low:
                    score += 6
                if any(t in a for a in aliases):
                    score += 4
                if t in stem_low:
                    score += 2
                if t in dir_low:
                    score += 1
            if ql in title_low:
                score += 8
            if score > 0:
                scored[rel] = max(scored.get(rel, 0), score)
    # matrix 实体反查补充（实体出现在问题里 → 直接收录其路径）
    m = knowledge._matrix()
    for ent, paths in m.get("entity_index", {}).items():
        ent_low = str(ent).lower()
        if ent_low in ql or any(ent_low in t or t in ent_low for t in qtokens):
            for path in paths:
                if not knowledge._rel_visible(path, vis):
                    continue
                if path not in scored:
                    scored[path] = 2
    return sorted(scored, key=lambda p: -scored[p])[:limit]


def _resolve_wiki_link(vault: Path, link: str) -> Optional[str]:
    """把 [[链接]] 文本解析为 wiki 文件相对路径（按标题/文件名匹配）。"""
    link = link.strip().split("|")[0].strip()
    if not link:
        return None
    vis = knowledge._visibility()
    wiki_dir = vault / "wiki"
    if not wiki_dir.exists():
        return None
    for p in wiki_dir.rglob("*.md"):
        try:
            fm = knowledge._frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        title = str(fm.get("title") or p.stem)
        alias_list = [str(a) for a in (fm.get("aliases") or [])]
        if title == link or p.stem == link or link in alias_list:
            rel = p.relative_to(vault).as_posix()
            if not knowledge._rel_visible(rel, vis):
                continue
            return rel
    return None


def _build_context(question: str, limit: int) -> List[Dict[str, Any]]:
    """Karpathy 检索: 实体解析 → wiki 条目 + 1 跳 wikilinks 展开 → 跨条目上下文。

    与本地 Mac 的方法一致: 读多个 wiki 条目（及其链接条目）后由 LLM 合成答案。
    """
    vault = knowledge._vault()
    resolved = _resolve_wiki_entries(vault, question, limit)
    entries: List[Dict[str, Any]] = []
    seen: set = set()
    for rel in resolved:
        if rel in seen:
            continue
        p = vault / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        fm = knowledge._frontmatter(text)
        body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, flags=re.DOTALL).strip()
        links = knowledge._wikilinks(text)
        entries.append({
            "path": rel,
            "title": str(fm.get("title") or p.stem),
            "content": body[:1000],
            "links": links,
            "score": 5,
        })
        seen.add(rel)
        # 1 跳 wikilinks 展开（wiki 即知识图谱）
        for link in links[:6]:
            if len(entries) >= limit:
                break
            target = _resolve_wiki_link(vault, link)
            if not target or target in seen:
                continue
            tp = vault / target
            if not tp.exists():
                continue
            ttext = tp.read_text(encoding="utf-8", errors="ignore")
            tfm = knowledge._frontmatter(ttext)
            tbody = re.sub(
                r"^---\s*\n.*?\n---\s*\n?", "", ttext, flags=re.DOTALL
            ).strip()
            entries.append({
                "path": target,
                "title": str(tfm.get("title") or tp.stem),
                "content": tbody[:800],
                "links": knowledge._wikilinks(ttext),
                "score": 3,
            })
            seen.add(target)
    return entries[:limit]


def _call_llm(system: str, user: str, model: str) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="DEEPSEEK_API_KEY not configured")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                DEEPSEEK_URL,
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}") from e


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, payload=Depends(require_auth)) -> ChatResponse:
    import asyncio

    if not knowledge._vault().exists():
        raise HTTPException(status_code=404, detail="vault not found")
    sources = await asyncio.to_thread(_build_context, req.question, req.limit)
    if not sources:
        answer = "知识库中没有检索到相关资料，无法回答。"
        await _record_session(payload["tenant_key"], req.question, answer, [])
        return ChatResponse(
            question=req.question,
            answer=answer,
            sources=[],
            model=req.model,
        )
    ctx_lines = []
    for i, s in enumerate(sources, 1):
        ctx_lines.append(
            f"[{i}] 来源: {s['path']}\n标题: {s['title']}\n内容: {s['content']}"
        )
    user_prompt = (
        f"参考资料:\n{chr(10).join(ctx_lines)}\n\n"
        f"问题: {req.question}\n\n请基于参考资料回答，并标注引用 [1][2]…"
    )
    answer = await asyncio.to_thread(_call_llm, SYSTEM_PROMPT, user_prompt, req.model)
    out_sources = [
        {"path": s["path"], "title": s["title"], "score": s["score"]}
        for s in sources
    ]
    await _record_session(payload["tenant_key"], req.question, answer, out_sources)
    return ChatResponse(
        question=req.question,
        answer=answer,
        sources=out_sources,
        model=req.model,
    )


async def _record_session(
    tenant_key: str, question: str, answer: str, sources: list
) -> None:
    """问答会话历史 + 用量（租户维，逻辑隔离落点）。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import TenantSession, TenantUsage

    try:
        async with SessionLocal() as db:
            db.add(
                TenantSession(
                    tenant_key=tenant_key,
                    question=question,
                    answer=answer,
                    sources=sources or None,
                )
            )
            usage = (
                await db.execute(
                    select(TenantUsage).where(TenantUsage.tenant_key == tenant_key)
                )
            ).scalar_one_or_none()
            if usage is None:
                db.add(
                    TenantUsage(
                        tenant_key=tenant_key,
                        chat_calls=1,
                        token_used=len(answer),
                    )
                )
            else:
                usage.chat_calls += 1
                usage.token_used += len(answer)
            await db.commit()
    except Exception:
        # 会话记录失败不影响问答主流程
        pass
