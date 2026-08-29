from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import importlib.util


REPO = Path(__file__).resolve().parents[1]
HERMES_SOURCE = Path.home() / ".hermes" / "hermes-agent"
HERMES_SITE_PACKAGES = HERMES_SOURCE / "venv" / "lib" / "python3.11" / "site-packages"


def test_bridge_bootstrap_resolves_tools_registry_from_hermes() -> None:
    env = os.environ.copy()
    env["HERMES_HOME"] = str(Path.home() / ".hermes")
    env["PYTHONPATH"] = os.pathsep.join(
        (str(HERMES_SOURCE), str(HERMES_SITE_PACKAGES), str(REPO))
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import scripts.hermes_bridge; "
                "import tools; "
                "from tools.registry import registry; "
                f"assert Path(tools.__file__).resolve().is_relative_to(Path({str(HERMES_SOURCE)!r}).resolve())"
            ),
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert probe.returncode == 0, probe.stderr


def _load_capability_router():
    path = (
        REPO
        / "agency"
        / "hermes-plugins"
        / "ai-lab-capabilities"
        / "capability_router.py"
    )
    spec = importlib.util.spec_from_file_location("agent_os_acceptance_router", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_professional_agency_router_skips_unrelated_candidate() -> None:
    router = _load_capability_router()
    bilibili = {
        "id": "agency:bilibili-content-strategist",
        "kind": "agency_agent",
        "name": "Bilibili Content Strategist",
        "description": (
            "Plans Bilibili video content, audience growth, and branded content strategy."
        ),
        "_search_text": "product research roadmap user story solution design",
        "domain": "media",
        "depth": 0.82,
        "cost": 0.10,
    }

    context = router._candidate_context(
        "设计制造业AI质量异常闭环产品，给出目标客户、MVP、路线图和验收指标",
        capabilities=[bilibili],
        professional_only=True,
    )

    assert context is None


def test_tenant_skill_read_records_selected_skill(tmp_path: Path) -> None:
    import json

    from backend.services.tenant_hermes_sandbox import ensure_tenant_sandbox
    import scripts.hermes_bridge as bridge

    template_root = tmp_path / "templates"
    skill_dir = template_root / "article-research-summary"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: article-research-summary\n"
        "description: Use when researching an article; do not use for code.\n---\n"
        "# Research\nVerify the original source.\n",
        encoding="utf-8",
    )
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a",
        user_id="user-a",
        root=tmp_path / "sandboxes",
        template_root=template_root,
    )
    route = {
        "enforced": True,
        "allowed": ["article-research-summary"],
        "decision": None,
    }
    bridge._sandbox_tool_context.value = sandbox
    bridge._skill_route_context.value = route
    try:
        result = json.loads(
            bridge._tenant_skill_read_tool({"name": "article-research-summary"})
        )
    finally:
        bridge._sandbox_tool_context.value = None
        bridge._skill_route_context.value = None

    assert result["success"] is True
    assert route["decision"] == {
        "status": "selected",
        "requested_skill": "article-research-summary",
        "loaded_skill": "article-research-summary",
    }


def test_tenant_base_toolsets_do_not_implicitly_enable_host_memory() -> None:
    import scripts.hermes_bridge as bridge

    assert bridge._tenant_base_toolsets({"skill_load", "delegate_task"}) == {"clarify"}
    assert bridge._tenant_base_toolsets(
        {"memory", "session_search", "delegate_task"}
    ) == {"clarify", "memory", "session_search"}


def test_receipt_accepts_verified_deferred_agency_load(monkeypatch) -> None:
    import queue

    import scripts.hermes_bridge as bridge

    monkeypatch.setattr(
        bridge,
        "_verified_delegation_transcript",
        lambda _value: ("deleg_1234abcd", "research-synthesist"),
    )
    stream_q: queue.Queue = queue.Queue()
    bridge._emit_delegate_receipt(
        stream_q,
        "delegate_task",
        {
            "context": (
                "AI_LAB_AGENCY_SPECIALIST=research-synthesist\n"
                "Use the specialist for source synthesis."
            )
        },
        {
            "delegation_id": "deleg_1234abcd",
            "results": [
                {
                    "status": "completed",
                    "exit_reason": "completed",
                    "summary": "Verified synthesis with sources.",
                    "live_transcript": "/bounded/deleg_1234abcd/task-0.log",
                    "tool_trace": [
                        {
                            "tool": "tool_call",
                            "status": "ok",
                            "input_summary": {
                                "argument_keys": ["arguments", "name"],
                                "targets": {},
                            },
                        }
                    ],
                }
            ],
        },
    )

    receipt = stream_q.get_nowait()
    assert receipt["agency_loaded"] is True
    assert receipt["verifier"] == "pass"
    assert receipt["verification_source"] == "deferred_trace+transcript"


def test_skill_candidate_prompt_requires_decision_before_delegation() -> None:
    from backend.services.skill_router import candidate_prompt

    prompt = candidate_prompt(
        [
            {
                "name": "article-research-summary",
                "description": (
                    "Use when researching an article; do not use for code changes."
                ),
                "skill_path": "research/article",
                "skill_level": "professional",
                "trigger_phrases": ["研究这篇文章"],
                "negative_phrases": ["修改代码"],
                "score": 0.9,
            }
        ]
    )

    assert "在回答或调用 delegate_task 前" in prompt
    assert "tenant_skill_read" in prompt


def test_professional_agency_router_excludes_skill_cards() -> None:
    router = _load_capability_router()
    skill = {
        "id": "skill:ipd-04-architecture",
        "kind": "skill",
        "name": "Product Architecture Planning Expert",
        "description": "Professional product planning architecture roadmap MVP expert.",
        "_search_text": "product roadmap MVP user story manufacturing acceptance product",
        "domain": "product",
        "depth": 0.99,
        "cost": 0.0,
        "skill_level": "professional",
    }
    product_manager = {
        "id": "agency:product-manager",
        "kind": "agency_agent",
        "name": "Product Manager",
        "description": "Owns product discovery, MVP roadmap, and outcome measurement.",
        "_search_text": "product MVP roadmap",
        "domain": "product",
        "depth": 0.79,
        "cost": 0.1,
    }

    context = router._candidate_context(
        "设计制造业AI质量异常闭环产品，给出MVP、路线图和验收指标",
        capabilities=[skill, product_manager],
        professional_only=True,
    )

    assert context is not None
    assert "AI_LAB_AGENCY_SPECIALIST=product-manager" in context
    assert "AI_LAB_AGENCY_SPECIALIST=skill:" not in context
