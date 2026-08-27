from __future__ import annotations

import json
from pathlib import Path

from backend.services.tenant_hermes_sandbox import ensure_tenant_sandbox
from scripts import hermes_bridge as bridge


def test_automatic_skill_read_is_limited_to_backend_shortlist(tmp_path: Path):
    template = tmp_path / "templates"
    for name in ("allowed-skill", "blocked-skill"):
        skill_md = template / "research" / name / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(f"---\nname: {name}\n---\n{name} body", encoding="utf-8")
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant", user_id="user",
        root=tmp_path / "sandboxes", template_root=template,
    )

    bridge._sandbox_tool_context.value = sandbox
    bridge._skill_route_context.value = {
        "enforced": True,
        "allowed": ["allowed-skill"],
    }
    try:
        allowed = json.loads(bridge._tenant_skill_read_tool({"name": "allowed-skill"}))
        blocked = json.loads(bridge._tenant_skill_read_tool({"name": "blocked-skill"}))
    finally:
        bridge._sandbox_tool_context.value = None
        bridge._skill_route_context.value = None

    assert allowed["success"] is True
    assert blocked == {
        "success": False,
        "error": "skill_not_shortlisted",
        "allowed_candidates": ["allowed-skill"],
    }
