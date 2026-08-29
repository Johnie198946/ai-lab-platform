from __future__ import annotations

from pathlib import Path

import pytest

from scripts import hermes_bridge


def _write_transcript(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cache" / "delegation" / "live" / "deleg_abcd1234" / "task-0.log"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("body", "expected_slug"),
    [
        (
            "20:32:14 tool     | -> agency_agents_load({'agent': 'product-manager'})\n"
            "20:32:14 result   | agency_agents_load ok 0.0s: "
            '{ "success": true, "agent": { "slug": "product-manager" } }\n',
            "product-manager",
        ),
        (
            "20:32:14 tool     | -> agency_agents_load({'agent': 'product-manager'})\n",
            None,
        ),
        (
            "20:32:14 tool     | -> agency_agents_load({'agent': 'product-manager'})\n"
            "20:32:14 result   | agency_agents_load ok 0.0s: "
            '{ "success": true, "agent": { "slug": "pricing-analyst" } }\n',
            None,
        ),
        (
            "20:32:14 tool     | -> agency_agents_load({})\n"
            "20:32:14 result   | agency_agents_load ok 0.0s: "
            '{ "success": true, "agent": { "slug": "product-manager" } }\n',
            None,
        ),
        (
            "20:32:14 tool     | -> agency_agents_load({'agent': 'product-manager'})\n"
            "20:32:14 result   | agency_agents_load ok 0.0s: "
            '{ "success": false, "agent": { "slug": "product-manager" } }\n',
            None,
        ),
        (
            "20:32:14 tool     | -> unrelated_tool({'name': 'agency_agents_load'})\n"
            "20:32:14 result   | unrelated_tool ok 0.0s: "
            '{ "success": true, "agent": { "slug": "product-manager" } }\n',
            None,
        ),
    ],
)
def test_verified_transcript_binds_effective_load_call_and_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    expected_slug: str | None,
) -> None:
    path = _write_transcript(tmp_path, body)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    delegation_id, loaded_slug = hermes_bridge._verified_delegation_transcript(path)

    assert delegation_id == "deleg_abcd1234"
    assert loaded_slug == expected_slug
