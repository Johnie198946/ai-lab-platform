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
PHASE_RE = re.compile(r"^### (P[0-3])：(.+)$", re.MULTILINE)
BULLET_RE = re.compile(r"^- (.+?)[；。]?$|^\d+\. (.+?)[；。]?$", re.MULTILINE)


def slug(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"work_{digest}"


def compile_plan(markdown: str) -> dict:
    phase_matches = list(PHASE_RE.finditer(markdown))
    if len(phase_matches) != 4:
        raise ValueError(f"expected P0-P3, found {len(phase_matches)} phases")

    phases = []
    previous_phase = None
    for index, match in enumerate(phase_matches):
        end = phase_matches[index + 1].start() if index + 1 < len(phase_matches) else markdown.find("## 14.", match.end())
        section = markdown[match.end():end]
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

    decision_start = markdown.find("## 14.")
    decisions = []
    if decision_start >= 0:
        for bullet in BULLET_RE.finditer(markdown[decision_start:]):
            title = next(group for group in bullet.groups() if group)
            decisions.append({"id": slug(f"decision:{title}"), "question": title, "status": "APPROVED_BY_IMPLEMENTATION_DIRECTIVE"})
    if len(decisions) != 6:
        raise ValueError(f"expected 6 product decisions, found {len(decisions)}")

    return {
        "schema_version": "1.0",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "compile_status": "READY",
        "strategy": "P0_TO_P3",
        "phase_count": len(phases),
        "task_count": sum(len(phase["tasks"]) for phase in phases),
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
