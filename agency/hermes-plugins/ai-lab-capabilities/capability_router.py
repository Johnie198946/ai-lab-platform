"""Adaptive capability routing layered on Hermes' existing disclosure tools.

This module deliberately does not register a new model-facing router.  It:

* uses Hermes' ``pre_llm_call`` hook to inject a bounded set of candidates;
* extends the existing ``tool_search`` response with the same candidates;
* leaves execution to ``skill_view``, ``agency_agents_load`` / ``delegate``,
  and the existing ``tool_describe`` / ``tool_call`` bridge; and
* learns lightweight success/latency priors from ``post_tool_call``.

The capability corpus stays outside the model context.  Newly installed
skills and Agency agents are discovered on every process cache refresh, so
Hermes keeps its self-growing behaviour without an ever-growing prompt.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Iterable


MAX_CANDIDATES = 5
MAX_INJECTED_CHARS = 2600
_INSTALLED = False
_STATS_LOCK = threading.Lock()

_LATIN_RE = re.compile(r"[a-z0-9][a-z0-9+.#_-]*", re.I)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")

# Small domain glossary, not a role catalog.  It fixes CJK recall while the
# actual inventory remains dynamic and comes from Hermes/Agency themselves.
_ALIASES: dict[str, tuple[str, ...]] = {
    "市场": ("market", "marketing"),
    "营销": ("marketing", "campaign", "growth"),
    "上市": ("go-to-market", "launch", "gtm"),
    "发布": ("go-to-market", "launch", "gtm"),
    "定价": ("pricing", "price"),
    "渠道": ("channel", "distribution", "sales"),
    "战略": ("strategy", "strategist", "strategic"),
    "管理层": ("executive", "management", "business"),
    "商业": ("business", "commercial"),
    "产品": ("product", "product-manager"),
    "增长": ("growth", "acquisition", "conversion"),
    "用户": ("user", "customer", "audience"),
    "客户": ("customer", "client", "audience"),
    "研究": ("research", "analysis", "analyst"),
    "分析": ("analysis", "analyst", "research"),
    "安全": ("security", "secure", "audit"),
    "代码": ("code", "software", "developer"),
    "架构": ("architecture", "architect", "system-design"),
    "测试": ("test", "testing", "quality", "qa"),
    "财务": ("finance", "financial"),
    "法律": ("legal", "compliance"),
    "内容": ("content", "copywriting", "editorial"),
    "设计": ("design", "designer", "ux", "ui"),
    "指标": ("metric", "metrics", "kpi", "measurement"),
    "风险": ("risk", "scenario", "assumption"),
    "方案": ("plan", "strategy", "roadmap"),
}

_DEEP_MARKERS = (
    "专业", "深入", "完整", "系统", "严谨", "管理层", "董事会", "评审",
    "可执行", "方案", "战略", "审计", "生产", "高质量", "expert",
    "professional", "comprehensive", "board", "audit", "production",
)
_FAST_MARKERS = (
    "快速", "简单", "简要", "一句话", "先看看", "随便", "大概",
    "quick", "brief", "simple", "roughly",
)
_PROFESSIONAL_WORDS = {
    "expert", "senior", "specialist", "professional", "strategist",
    "architect", "analyst", "audit", "production", "holistic",
}


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _stats_path() -> Path:
    return _hermes_home() / "state" / "capability-router-stats.json"


def _tokens(text: str) -> set[str]:
    lowered = (text or "").lower()
    tokens = {token.lower() for token in _LATIN_RE.findall(lowered)}
    for run in _CJK_RE.findall(lowered):
        tokens.add(run)
        tokens.update(run[i : i + 2] for i in range(max(0, len(run) - 1)))
    for source, aliases in _ALIASES.items():
        if source in lowered:
            tokens.update(aliases)
    if "gtm" in tokens:
        tokens.update(("go-to-market", "launch", "market"))
    if "go-to-market" in tokens:
        tokens.add("gtm")
    if "icp" in tokens:
        tokens.update(("customer", "segment", "audience", "positioning"))
    return {token for token in tokens if token}


def _task_depth(query: str) -> float:
    text = (query or "").lower()
    deep = sum(marker in text for marker in _DEEP_MARKERS)
    fast = sum(marker in text for marker in _FAST_MARKERS)
    depth = 0.5 + min(deep, 4) * 0.11 - min(fast, 3) * 0.14
    if len(text) > 180:
        depth += 0.08
    return min(1.0, max(0.1, depth))


def _load_stats(path: Path | None = None) -> dict[str, dict[str, Any]]:
    target = path or _stats_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_stats(stats: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    target = path or _stats_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(stats, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _agency_data_path() -> Path | None:
    candidates = [
        _hermes_home() / "plugins" / "agency-agents-router" / "data" / "agents.json",
        Path(__file__).resolve().parent.parent / "agency-agents-router" / "data" / "agents.json",
    ]
    return next((path for path in candidates if path.exists()), None)


def _agency_capabilities() -> list[dict[str, Any]]:
    path = _agency_data_path()
    if path is None:
        return []
    try:
        agents = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    capabilities = []
    for agent in agents if isinstance(agents, list) else []:
        slug = str(agent.get("slug") or "").strip()
        if not slug:
            continue
        capabilities.append({
            "id": f"agency:{slug}",
            "kind": "agency_agent",
            "name": str(agent.get("name") or slug),
            "description": str(agent.get("description") or "")[:600],
            # Search the specialist's actual standards outside model context;
            # only the short description is ever emitted in a candidate card.
            "_search_text": str(agent.get("body") or "")[:5000],
            "domain": str(agent.get("division") or "specialized"),
            "invoke_tool": "agency_agents_load",
            "invoke_args": {"agent": slug},
            "depth": 0.82,
            "cost": 0.10,
        })
    return capabilities


def _skill_capabilities() -> list[dict[str, Any]]:
    try:
        from tools.skills_tool import _find_all_skills

        skills = _find_all_skills()
    except Exception:
        return []
    capabilities = []
    for skill in skills:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        description = str(skill.get("description") or "")[:600]
        capabilities.append({
            "id": f"skill:{name}",
            "kind": "skill",
            "name": name,
            "description": description,
            "domain": str(skill.get("category") or "general"),
            "invoke_tool": "skill_view",
            "invoke_args": {"name": name},
            "depth": 0.62,
            "cost": 0.035,
        })
    return capabilities


def _direct_capability() -> dict[str, Any]:
    return {
        "id": "hermes:direct",
        "kind": "direct",
        "name": "Hermes direct response",
        "description": "Fast general-purpose response using current conversation context.",
        "domain": "general",
        "invoke_tool": "",
        "invoke_args": {},
        "depth": 0.24,
        "cost": 0.0,
    }


def _quality_prior(capability: dict[str, Any]) -> float:
    words = _tokens(
        f"{capability.get('name', '')} {capability.get('description', '')}"
    )
    professional = len(words & _PROFESSIONAL_WORDS)
    return min(0.92, 0.58 + professional * 0.07)


def _history_prior(capability_id: str, stats: dict[str, dict[str, Any]]) -> float:
    record = stats.get(capability_id) or {}
    calls = max(0, int(record.get("calls") or 0))
    successes = max(0, int(record.get("successes") or 0))
    # Bayesian smoothing prevents one early result from dominating ranking.
    return (successes + 2.0) / (calls + 4.0)


def _score_capability(
    capability: dict[str, Any],
    query: str,
    stats: dict[str, dict[str, Any]],
) -> tuple[float, dict[str, float]]:
    query_tokens = _tokens(query)
    search_text = (
        f"{capability.get('name', '')} {capability.get('description', '')} "
        f"{capability.get('domain', '')} {capability.get('_search_text', '')}"
    )
    capability_tokens = _tokens(search_text)
    overlap = query_tokens & capability_tokens
    lexical = len(overlap) / max(math.sqrt(len(query_tokens) * max(len(capability_tokens), 1)), 1.0)
    query_lower = query.lower()
    name_lower = str(capability.get("name") or "").lower()
    if name_lower and name_lower in query_lower:
        lexical += 0.25
    if capability["kind"] == "direct":
        lexical = 0.28
    else:
        lexical = min(1.0, lexical * 2.8)

    title_tokens = _tokens(str(capability.get("name") or "")) - _PROFESSIONAL_WORDS
    title_fit = len(query_tokens & title_tokens) / max(len(title_tokens), 1)
    title_fit = min(1.0, title_fit)

    depth_fit = 1.0 - abs(_task_depth(query) - float(capability.get("depth") or 0.5))
    quality = _quality_prior(capability)
    history = _history_prior(str(capability["id"]), stats)
    raw_cost = float(capability.get("cost") or 0.0)

    # Professional requests penalize underpowered candidates; quick requests
    # penalize heavyweight ones.  The source itself never receives a bonus.
    requested_depth = _task_depth(query)
    # A heavyweight specialist is expensive for a quick question, but that
    # penalty should mostly disappear when the user explicitly needs depth.
    cost = raw_cost * (1.0 - requested_depth * 0.75)
    mismatch = 0.0
    if requested_depth >= 0.72 and float(capability.get("depth") or 0.5) < 0.5:
        mismatch = 0.16
    elif requested_depth <= 0.35 and float(capability.get("depth") or 0.5) > 0.75:
        mismatch = 0.13

    score = (
        lexical * 0.43
        + depth_fit * 0.22
        + quality * 0.17
        + history * 0.10
        + title_fit * 0.10
        + 0.08
        - cost
        - mismatch
    )
    factors = {
        "task_fit": round(lexical, 3),
        "depth_fit": round(depth_fit, 3),
        "quality": round(quality, 3),
        "history": round(history, 3),
        "title_fit": round(title_fit, 3),
        "cost_penalty": round(cost, 3),
        "mismatch_penalty": round(mismatch, 3),
    }
    return max(0.0, min(1.0, score)), factors


def recommend(
    query: str,
    *,
    limit: int = MAX_CANDIDATES,
    capabilities: Iterable[dict[str, Any]] | None = None,
    stats: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Rank a bounded number of executable capability cards."""
    inventory = list(capabilities) if capabilities is not None else (
        [_direct_capability()] + _skill_capabilities() + _agency_capabilities()
    )
    history = stats if stats is not None else _load_stats()
    ranked: list[tuple[float, dict[str, Any], dict[str, float]]] = []
    for capability in inventory:
        score, factors = _score_capability(capability, query, history)
        if score > 0.12:
            ranked.append((score, capability, factors))
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))

    cards = []
    for score, capability, factors in ranked[: max(1, min(limit, MAX_CANDIDATES))]:
        cards.append({
            "id": capability["id"],
            "kind": capability["kind"],
            "name": capability["name"],
            "domain": capability.get("domain", "general"),
            "description": str(capability.get("description") or "")[:220],
            "fit": round(score * 100, 1),
            "confidence": round((0.55 + factors["history"] * 0.35) * 100, 1),
            "factors": factors,
            "invoke": {
                "tool": capability.get("invoke_tool") or None,
                "arguments": capability.get("invoke_args") or {},
            },
        })
    return cards


def _candidate_context(query: str) -> str | None:
    cards = recommend(query, limit=MAX_CANDIDATES)
    if not cards:
        return None
    compact = [
        {
            "id": card["id"],
            "kind": card["kind"],
            "fit": card["fit"],
            "confidence": card["confidence"],
            "reason": {
                "task": card["factors"]["task_fit"],
                "depth": card["factors"]["depth_fit"],
                "quality": card["factors"]["quality"],
            },
            "summary": card["description"][:120],
            "invoke": card["invoke"],
        }
        for card in cards
    ]
    prefix = (
        "[Hermes capability recommendations — internal routing metadata]\n"
        "Choose objectively; the user did not request a specific implementation. "
        "For a quick/general request, direct response may be best. For a professional "
        "request, prefer the highest-fit proven specialist. Load only the selected "
        "capability using invoke; do not expose internal capability names unless asked. "
        "If no candidate materially improves the answer, respond directly.\n"
        "Candidates: "
    )
    # Drop the weakest tail candidate rather than truncating JSON.  The model
    # always receives valid, actionable cards and context remains hard-bounded.
    while compact:
        payload = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        context = prefix + payload
        if len(context) <= MAX_INJECTED_CHARS:
            return context
        compact.pop()
    return None


def _pre_llm_call(user_message: str = "", **kwargs: Any) -> dict[str, str] | None:
    del kwargs
    context = _candidate_context(user_message)
    return {"context": context} if context else None


def _capability_id_for_call(tool_name: str, args: dict[str, Any]) -> str | None:
    if tool_name == "skill_view":
        name = str(args.get("name") or "").strip()
        return f"skill:{name}" if name else None
    if tool_name in {"agency_agents_load", "agency_agents_delegate"}:
        name = str(args.get("agent") or args.get("slug") or "").strip()
        return f"agency:{name}" if name else None
    return None


def _result_succeeded(result: str) -> bool:
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError):
        return not str(result).startswith("[TOOL_ERROR]")
    if not isinstance(parsed, dict):
        return True
    return not bool(parsed.get("error")) and parsed.get("success", True) is not False


def _post_tool_call(
    tool_name: str,
    args: dict[str, Any],
    result: str,
    duration_ms: int = 0,
    **kwargs: Any,
) -> None:
    del kwargs
    capability_id = _capability_id_for_call(tool_name, args or {})
    if not capability_id:
        return
    with _STATS_LOCK:
        stats = _load_stats()
        record = stats.setdefault(capability_id, {})
        calls = int(record.get("calls") or 0) + 1
        successes = int(record.get("successes") or 0) + int(_result_succeeded(result))
        previous_latency = float(record.get("avg_latency_ms") or 0.0)
        record.update({
            "calls": calls,
            "successes": successes,
            "avg_latency_ms": round(previous_latency + (float(duration_ms) - previous_latency) / calls, 2),
        })
        _write_stats(stats)


def _compact_skills_prompt(*args: Any, **kwargs: Any) -> str:
    del args, kwargs
    skills = _skill_capabilities()
    categories = sorted({str(item.get("domain") or "general") for item in skills})
    category_text = ", ".join(categories[:24])
    if len(categories) > 24:
        category_text += f", +{len(categories) - 24} more"
    return (
        "## Skills (on demand)\n"
        f"Hermes currently has {len(skills)} dynamically indexed skills across: {category_text}. "
        "Do not load the full inventory. Each user turn receives a bounded capability recommendation; "
        "load only a selected skill with skill_view(name). Use the existing tool_search when the "
        "recommended candidates are insufficient. Newly installed skills are indexed automatically."
    )


def _extend_tool_search() -> None:
    try:
        from tools import tool_search as module
    except Exception:
        return
    if getattr(module, "_ai_lab_capability_router", False):
        return

    original_dispatch = module.dispatch_tool_search
    original_schemas = module.bridge_tool_schemas

    def dispatch(args: dict[str, Any], **kwargs: Any) -> str:
        raw = original_dispatch(args, **kwargs)
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return raw
        query = str(args.get("query") or "").strip()
        try:
            requested = int(args.get("limit") or MAX_CANDIDATES)
        except (TypeError, ValueError):
            requested = MAX_CANDIDATES
        payload["capability_matches"] = recommend(query, limit=requested)
        payload["routing_hint"] = (
            "Capability matches are lightweight cards. Invoke only the selected skill/agent; "
            "ordinary tool matches keep the existing describe/call flow."
        )
        return json.dumps(payload, ensure_ascii=False)

    def schemas(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        definitions = original_schemas(*args, **kwargs)
        search = next(
            (item.get("function") for item in definitions if item.get("function", {}).get("name") == "tool_search"),
            None,
        )
        if search is not None:
            search["description"] = (
                "Search deferred tools plus dynamically indexed Hermes skills and Agency specialists. "
                "Use it when injected candidates are insufficient; only a bounded result set is returned.\n\n"
                + str(search.get("description") or "")
            )
        return definitions

    module.dispatch_tool_search = dispatch
    module.bridge_tool_schemas = schemas
    module._ai_lab_capability_router = True


def _compact_skill_manifest() -> None:
    # Hermes' system prompt resolver intentionally reaches through run_agent;
    # patch both references so this works in CLI and gateway construction.
    try:
        import agent.prompt_builder as prompt_builder

        prompt_builder.build_skills_system_prompt = _compact_skills_prompt
    except Exception:
        pass
    try:
        import run_agent

        run_agent.build_skills_system_prompt = _compact_skills_prompt
    except Exception:
        pass


def install(ctx: Any) -> None:
    """Attach the router to Hermes' existing search, prompt, and hook lifecycle."""
    global _INSTALLED
    if _INSTALLED:
        return
    _extend_tool_search()
    _compact_skill_manifest()
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    _INSTALLED = True
