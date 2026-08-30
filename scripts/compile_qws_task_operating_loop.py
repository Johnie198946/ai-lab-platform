#!/usr/bin/env python3
"""Compile the QWS task operating-loop design into an executable phase plan."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "qws-task-operating-loop-v1.md"
OUTPUT = ROOT / "docs" / "qws-task-operating-loop-v1.compiled.json"
STATUS = ROOT / "docs" / "qws-task-operating-loop-v1.status.json"
PHASE_RE = re.compile(r"^### (P[0-3])：(.+)$", re.MULTILINE)
BULLET_RE = re.compile(r"^- (.+?)[；。]?$|^\d+\. (.+?)[；。]?$", re.MULTILINE)
IMPLEMENTATION_HEADING = "## 13. 分阶段实施"
DECISION_HEADING = "## 14. 需要产品拍板的 6 个问题"
NEXT_HEADING = "## 15."


def slug(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"work_{digest}"


def compile_plan(markdown: str) -> dict:
    implementation_start = markdown.find(IMPLEMENTATION_HEADING)
    decision_start = markdown.find(DECISION_HEADING)
    if implementation_start < 0 or decision_start < 0 or implementation_start >= decision_start:
        raise ValueError("implementation_or_decision_section_missing")
    implementation = markdown[implementation_start:decision_start]
    phase_matches = list(PHASE_RE.finditer(implementation))
    if len(phase_matches) != 4:
        raise ValueError(f"expected P0-P3, found {len(phase_matches)} phases")

    phases = []
    previous_phase = None
    for index, match in enumerate(phase_matches):
        end = phase_matches[index + 1].start() if index + 1 < len(phase_matches) else len(implementation)
        section = implementation[match.end():end]
        tasks = []
        for bullet in BULLET_RE.finditer(section):
            title = next(group for group in bullet.groups() if group)
            tasks.append({
                "id": slug(f"{match.group(1)}:{title}"),
                "title": title,
                "status": "TODO",
                "acceptance": [f"{title}具备可验证的主路径与证据"],
            })
        phase = {
            "id": match.group(1),
            "name": match.group(2).strip(),
            "depends_on": [previous_phase] if previous_phase else [],
            "tasks": tasks,
        }
        phases.append(phase)
        previous_phase = phase["id"]

    decision_end = markdown.find(NEXT_HEADING, decision_start)
    if decision_end < 0:
        decision_end = len(markdown)
    decisions = []
    for bullet in BULLET_RE.finditer(markdown[decision_start:decision_end]):
        title = next(group for group in bullet.groups() if group)
        decisions.append({"id": slug(f"decision:{title}"), "question": title, "status": "APPROVED_BY_IMPLEMENTATION_DIRECTIVE"})
    if len(decisions) != 6:
        raise ValueError(f"expected 6 product decisions, found {len(decisions)}")

    status_overlay = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    task_statuses = status_overlay.get("tasks") or {}
    known_task_ids = {task["id"] for phase in phases for task in phase["tasks"]}
    unknown_task_ids = sorted(set(task_statuses) - known_task_ids)
    if unknown_task_ids:
        raise ValueError(f"status_overlay_unknown_tasks:{','.join(unknown_task_ids)}")
    for phase in phases:
        for task in phase["tasks"]:
            overlay = task_statuses.get(task["id"])
            if overlay:
                task["status"] = str(overlay["status"])
                task["evidence"] = list(overlay.get("evidence") or [])

    return {
        "schema_version": "1.0",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "compile_status": "READY",
        "strategy": "P0_TO_P3",
        "phase_count": len(phases),
        "task_count": sum(len(phase["tasks"]) for phase in phases),
        "execution_status_source": str(STATUS.relative_to(ROOT)) if STATUS.exists() else None,
        "phases": phases,
        "product_decisions": decisions,
    }


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8")
    plan = compile_plan(markdown)
    OUTPUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)),
        "source_sha256": plan["source_sha256"],
        "phases": plan["phase_count"],
        "tasks": plan["task_count"],
        "decisions": len(plan["product_decisions"]),
        "status": plan["compile_status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
