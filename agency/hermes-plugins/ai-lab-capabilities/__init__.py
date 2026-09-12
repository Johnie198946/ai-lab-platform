"""Hermes plugin exposing AI Lab as a small, auditable capability surface."""
from __future__ import annotations

import json
from typing import Any

from .capability_router import install as install_capability_router
from .research_deposit import ResearchDeposit

# Host lifecycle adapters can retain the registered instance, without model authority.
research_deposition = None


CAPABILITIES = {
    "research_deposit": {
        "description": "Deposit parent-adopted research into the authorized existing-sync user Vault. Inputs: title, FULL adopted research body or analysis (not the brief user-facing summary), source_urls, confidence (null if unreviewed), source_kind=research_analysis. Body requires >=800 characters, substantive Markdown headings ## 事实, ## 分析, ## 启示 with actual newlines (not literal backslash-n), >=20 characters per section and source URLs in body. One task supports multiple items: call once per item, keep primary source URL first and stable for corrections; quality rejection without durable raw permits corrected resubmission. Or action=status/recover with known session_id/turn_id/task_id and optional item_id from status. Status stays discoverable while writing is disabled but requires local-owner authorization. Batch status supports limit=1..20 and cursor=next_cursor; recover selects at most 3 actionable items, with 3 lifetime attempts per item. Inspect recoverable/recovery_blocked_reason, actionable_total/blocked_total; has_more is pagination, not task completion. Finalizer only verifies: explicitly hand off adopted body; it never saves the final answer automatically. Writer control cannot create research items (research_task_association_required). No-save cannot be lifted by text or model inputs without a supported verified same-material host consent association. Completion requires all known items. Local owner default profile only; not a Wiki compilation receipt.",
        "required": [],
    },
    "knowledge_search": {
        "description": "Search tenant-authorized Wiki using query plus optional entities/topics; read chosen links with paths. No private-file fallback. Inspect retrieval_status and use authorized public web for gaps. Selected-book full text/TOC uses book_id, content_version, operation, section and page. Follow next until truncated=false.",
        "underlying_tool": "knowledge_search",
        "required": ["query"],
    },
    "web_research": {
        "description": "Search the web through the server-approved provider.",
        "underlying_tool": "web_search",
        "required": ["query"],
    },
    "web_extract": {
        "description": "Extract a source page for evidence-backed work.",
        "underlying_tool": "web_extract",
        "required": ["url"],
    },
    "specialist_execution": {
        "description": "Delegate a bounded execution task through Hermes.",
        "underlying_tool": "delegate_task",
        "required": ["goal"],
    },
}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def register(ctx):
    global research_deposition
    deposition = ResearchDeposit(ctx)
    research_deposition = deposition
    deposition.install()
    # Stable schema; authorization and write-enable are checked on every call.
    capabilities = CAPABILITIES
    if hasattr(ctx, "register_web_search_provider"):
        from .native_extract_provider import build_provider

        ctx.register_web_search_provider(build_provider())
    # Reuse Hermes' existing progressive disclosure and lifecycle hooks.  This
    # does not add another model-facing navigation tool.
    install_capability_router(ctx, deposition=deposition)

    def list_capabilities(args: dict[str, Any], **kwargs) -> str:
        del args, kwargs
        return _json({
            "success": True,
            "provider": "ai-lab",
            "capabilities": [
                {"id": key, **value} for key, value in capabilities.items()
            ],
        })

    def execute(args: dict[str, Any], **kwargs) -> str:
        capability_id = str(args.get("capability") or "").strip()
        capability = capabilities.get(capability_id)
        if not capability:
            return _json({
                "success": False,
                "error": "unsupported_capability",
                "capability": capability_id,
            })
        inputs = args.get("inputs") or {}
        if not isinstance(inputs, dict):
            return _json({"success": False, "error": "inputs_must_be_object"})
        if capability_id == "research_deposit":
            return _json(deposition.execute(inputs, **kwargs))
        missing = [key for key in capability["required"] if not inputs.get(key)]
        if missing:
            return _json({
                "success": False,
                "error": "missing_required_inputs",
                "missing": missing,
            })
        try:
            result = ctx.dispatch_tool(capability["underlying_tool"], inputs, **kwargs)
        except Exception as exc:  # pragma: no cover - depends on Hermes runtime
            return _json({
                "success": False,
                "capability": capability_id,
                "error": "execution_failed",
                "detail": str(exc),
            })
        inner = result
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                inner = None
        # Dispatch completion is not knowledge retrieval success. Preserve the
        # underlying result contract, but propagate failures and fallback state.
        status = {key: inner[key] for key in (
            "error", "retrieval_status", "fallback_recommended", "fallback_source", "fallback_instruction"
        ) if isinstance(inner, dict) and key in inner} if capability_id == "knowledge_search" else {}
        return _json({
            "success": not (isinstance(inner, dict) and (inner.get("success") is False or inner.get("error"))),
            "provider": "ai-lab",
            "capability": capability_id,
            "result": result,
            **status,
        })

    ctx.register_tool(
        name="ai_lab_capabilities",
        toolset="ai_lab",
        schema={
            "name": "ai_lab_capabilities",
            "description": "List capabilities currently exposed by AI Lab.",
            "parameters": {"type": "object", "properties": {}},
        },
        handler=list_capabilities,
        description="List capabilities currently exposed by AI Lab.",
    )
    ctx.register_tool(
        name="ai_lab_execute",
        toolset="ai_lab",
        schema={
            "name": "ai_lab_execute",
            "description": (
                "Execute one server-approved AI Lab capability. Use this for "
                "knowledge, research, source extraction, and bounded delegation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "capability": {
                        "type": "string",
                        "enum": sorted(capabilities),
                    },
                    "inputs": {"type": "object"},
                },
                "required": ["capability", "inputs"],
            },
        },
        handler=execute,
        description="Execute one server-approved AI Lab capability.",
    )
