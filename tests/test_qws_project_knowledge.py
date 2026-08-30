from datetime import datetime, timezone

import pytest

from backend.services.qws_project_knowledge import (
    build_document_graph,
    decide_distillation_candidate,
    distill_project_events,
    merge_distillation_candidates,
    parse_source_ref,
    render_obsidian_markdown,
    upsert_project_document,
)


def test_document_revisions_are_immutable_obsidian_projections():
    process, first = upsert_project_document(
        {},
        document_id="project-brief",
        title="项目说明",
        content="# 项目说明\n\n参考 [[交付清单]]。",
        status="PUBLISHED",
        source_refs=["intake:intake-1@1"],
        tags=["project/qws"],
        actor_id="user:user-a",
        now=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    process, second = upsert_project_document(
        process,
        document_id="project-brief",
        title="项目说明",
        content="# 项目说明\n\n参考 [[交付清单]] 与 [[决策记录]]。",
        status="PUBLISHED",
        source_refs=["intake:intake-1@1", "decision:gate-1@2"],
        tags=["project/qws"],
        actor_id="user:user-a",
        now=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )

    assert first["revision"] == 1
    assert second["revision"] == 2
    assert process["document_revisions"][0]["content"] != second["content"]
    assert process["document_revisions"][0]["content_hash"] == first["content_hash"]
    rendered = render_obsidian_markdown(second)
    assert "document_id: \"project-brief\"" in rendered
    assert "source_refs:" in rendered
    assert "[[交付清单]]" in rendered


def test_published_document_requires_valid_source_ref():
    with pytest.raises(ValueError, match="published_document_requires_source_ref"):
        upsert_project_document(
            {}, document_id="brief", title="Brief", content="# Brief", status="PUBLISHED",
            source_refs=[], tags=[], actor_id="user:user-a",
        )
    with pytest.raises(ValueError, match="invalid_source_ref"):
        parse_source_ref("https://signed.example/token=secret")


def test_document_graph_reports_backlinks_and_broken_links():
    graph = build_document_graph([
        {"id": "a", "title": "A", "content": "See [[B]] and [[Missing]]."},
        {"id": "b", "title": "B", "content": "# B"},
    ])
    assert graph["backlinks"]["b"] == ["a"]
    assert graph["broken_links"] == [{"source_document_id": "a", "target_title": "Missing"}]


def test_distiller_is_cursor_based_deterministic_and_candidate_only():
    events = [
        {"sequence": 1, "id": "e1", "event_type": "task_updated", "payload": {}},
        {"sequence": 2, "id": "e2", "event_type": "gate_decided", "title": "批准方案", "payload": {"decision": "APPROVE"}},
        {"sequence": 3, "id": "e3", "event_type": "delivery_manifest_accepted", "title": "验收交付", "payload": {"manifest_id": "m1"}},
    ]
    first = distill_project_events(events, cursor=0)
    replay = distill_project_events(list(reversed(events)), cursor=0)
    assert first == replay
    assert first["next_cursor"] == 3
    assert [item["status"] for item in first["candidates"]] == ["CANDIDATE", "CANDIDATE"]
    assert first["candidates"][0]["source_refs"] == ["audit:e2"]

    process = merge_distillation_candidates({}, candidates=first["candidates"], next_cursor=3)
    process = merge_distillation_candidates(process, candidates=first["candidates"], next_cursor=3)
    assert len(process["distillation_candidates"]) == 2
    admitted_process, admitted = decide_distillation_candidate(
        process,
        candidate_id=first["candidates"][0]["id"],
        decision="ADMIT",
        actor_id="user:user-a",
        note="来源已核验",
    )
    assert admitted["status"] == "ADMITTED"
    assert admitted_process["distillation_cursor"] == 3


def test_distiller_cursor_does_not_skip_candidates_after_page_budget():
    events = [
        {"sequence": index, "id": f"e{index}", "event_type": "gate_decided", "payload": {}}
        for index in range(1, 4)
    ]
    first = distill_project_events(events, cursor=0, max_candidates=1)
    assert first["next_cursor"] == 1
    second = distill_project_events(events, cursor=first["next_cursor"], max_candidates=2)
    assert [item["event_sequence"] for item in second["candidates"]] == [2, 3]
