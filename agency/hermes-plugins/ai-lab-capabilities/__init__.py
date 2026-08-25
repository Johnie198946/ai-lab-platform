"""Hermes plugin exposing AI Lab as a small, auditable capability surface."""
from __future__ import annotations

import json
from typing import Any


CAPABILITIES = {
    "knowledge_search": {
        "description": "Search tenant-authorized AI Lab knowledge.",
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
    def list_capabilities(args: dict[str, Any], **kwargs) -> str:
        del args, kwargs
        return _json({
            "success": True,
            "provider": "ai-lab",
            "capabilities": [
                {"id": key, **value} for key, value in CAPABILITIES.items()
            ],
        })

    def execute(args: dict[str, Any], **kwargs) -> str:
        del kwargs
        capability_id = str(args.get("capability") or "").strip()
        capability = CAPABILITIES.get(capability_id)
        if not capability:
            return _json({
                "success": False,
                "error": "unsupported_capability",
                "capability": capability_id,
            })
        inputs = args.get("inputs") or {}
        if not isinstance(inputs, dict):
            return _json({"success": False, "error": "inputs_must_be_object"})
        missing = [key for key in capability["required"] if not inputs.get(key)]
        if missing:
            return _json({
                "success": False,
                "error": "missing_required_inputs",
                "missing": missing,
            })
        try:
            result = ctx.dispatch_tool(capability["underlying_tool"], inputs)
        except Exception as exc:  # pragma: no cover - depends on Hermes runtime
            return _json({
                "success": False,
                "capability": capability_id,
                "error": "execution_failed",
                "detail": str(exc),
            })
        return _json({
            "success": True,
            "provider": "ai-lab",
            "capability": capability_id,
            "result": result,
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
                        "enum": sorted(CAPABILITIES),
                    },
                    "inputs": {"type": "object"},
                },
                "required": ["capability", "inputs"],
            },
        },
        handler=execute,
        description="Execute one server-approved AI Lab capability.",
    )
