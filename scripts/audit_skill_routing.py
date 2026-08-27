#!/usr/bin/env python3
"""Audit Hermes SKILL.md discovery metadata without modifying Skill files."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.services.skill_router import (  # noqa: E402
    apply_routing_overrides,
    legacy_routing_hints,
    legacy_skill_level,
    legacy_skill_path,
    load_routing_overrides,
    normalize_skill_record,
    rank_skill_candidates,
    routing_quality_issues,
)


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")[:32_000]
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) != 3:
        return {}
    try:
        parsed = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def audit(root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for skill_md in sorted(root.rglob("SKILL.md")):
        if skill_md.is_symlink():
            continue
        metadata = _frontmatter(skill_md)
        source = skill_md.read_text(encoding="utf-8", errors="replace")[:32_000]
        relative = skill_md.parent.relative_to(root)
        fallback_parts = relative.parts[:-1]
        category = fallback_parts[0] if fallback_parts else "uncategorized"
        fallback = legacy_skill_path(
            category,
            str(metadata.get("name") or skill_md.parent.name),
            str(metadata.get("description") or ""),
        )
        governance_raw = {
            **metadata,
            "name": metadata.get("name") or skill_md.parent.name,
            "skill_path": metadata.get("skill_path") or metadata.get("taxonomy") or "",
            "skill_level": metadata.get("skill_level") or metadata.get("level") or "",
        }
        inferred_triggers, inferred_negatives = legacy_routing_hints(source, metadata)
        raw = {
            **governance_raw,
            "skill_path": governance_raw["skill_path"] or fallback,
            "skill_level": governance_raw["skill_level"] or legacy_skill_level(
                str(metadata.get("name") or skill_md.parent.name),
                str(metadata.get("description") or ""),
            ),
            "trigger_phrases": (
                metadata.get("trigger_phrases") or metadata.get("triggers")
                or inferred_triggers
            ),
            "negative_phrases": (
                metadata.get("negative_phrases") or metadata.get("exclusions")
                or inferred_negatives
            ),
        }
        normalized = normalize_skill_record(raw)
        issues = routing_quality_issues(governance_raw)
        issue_counts.update(issues)
        buckets[(normalized["skill_path"], normalized["skill_level"])].append(
            normalized["name"]
        )
        records.append({
            "name": normalized["name"],
            "file": str(skill_md),
            "skill_path": normalized["skill_path"],
            "skill_level": normalized["skill_level"],
            "description": normalized["description"],
            "trigger_phrases": normalized["trigger_phrases"],
            "negative_phrases": normalized["negative_phrases"],
            "issues": issues,
            "routing_issues": issues,
        })
    collisions = [
        {"skill_path": path, "skill_level": level, "skills": sorted(names)}
        for (path, level), names in buckets.items()
        if len(names) > 1
    ]
    collisions.sort(key=lambda item: (-len(item["skills"]), item["skill_path"]))
    compliant = sum(not record["issues"] for record in records)
    return {
        "root": str(root),
        "total": len(records),
        "compliant": compliant,
        "noncompliant": len(records) - compliant,
        "issue_counts": dict(sorted(issue_counts.items())),
        "collision_groups": collisions,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--query")
    parser.add_argument("--overrides", type=Path)
    args = parser.parse_args()
    result = audit(args.root.expanduser().resolve())
    routed_records = result["records"]
    if args.overrides:
        routed_records = apply_routing_overrides(
            routed_records,
            load_routing_overrides(str(args.overrides.expanduser().resolve())),
        )
        result["effective_compliant"] = sum(
            not record.get("routing_issues") for record in routed_records
        )
    if args.query:
        result["candidates"] = rank_skill_candidates(
            args.query, routed_records, limit=5
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"root={result['root']}")
        print(f"total={result['total']}")
        print(f"compliant={result['compliant']}")
        print(f"noncompliant={result['noncompliant']}")
        for issue, count in result["issue_counts"].items():
            print(f"issue.{issue}={count}")
        print(f"collision_groups={len(result['collision_groups'])}")
        if "effective_compliant" in result:
            print(f"effective_compliant={result['effective_compliant']}")
        for index, candidate in enumerate(result.get("candidates") or [], start=1):
            print(
                f"candidate.{index}={candidate['name']}"
                f" score={candidate['score']} path={candidate['skill_path']}"
                f" level={candidate['skill_level']}"
            )
    return 1 if args.strict and result["noncompliant"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
