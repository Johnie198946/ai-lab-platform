from __future__ import annotations

import atexit
import asyncio
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from tempfile import gettempdir

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

_existing_sqlite_url = os.environ.get("DATABASE_URL", "")
if _existing_sqlite_url.startswith("sqlite+aiosqlite:///"):
    # The legacy API module may already have initialized backend.db in a combined
    # regression run. Inspect the same database instead of silently switching the
    # environment after SQLAlchemy's engine has been created.
    TEST_DB = Path(_existing_sqlite_url.removeprefix("sqlite+aiosqlite:///"))
else:
    TEST_DB = Path(gettempdir()) / f"quantum_workspace_m05a_test_{os.getpid()}.db"
    TEST_DB.unlink(missing_ok=True)
    atexit.register(lambda owned=TEST_DB: owned.unlink(missing_ok=True))
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB}"
os.environ.setdefault("AUTHEN_DEV_MODE", "true")

from backend.api.auth import require_auth  # noqa: E402
from backend.db import engine as app_engine  # noqa: E402
from backend.main import app  # noqa: E402

# Other test modules can import backend.db before this module and then mutate
# DATABASE_URL during collection. SQLAlchemy's already-created engine remains
# authoritative, so direct SQLite assertions must inspect that engine's file.
_engine_database = app_engine.url.database
assert _engine_database is not None
TEST_DB = Path(_engine_database)


@pytest.fixture
def client():
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a",
        "user_id": "owner-a",
        "sub": "owner-a",
        "principal_type": "human",
        "amr": ["pwd"],
        "auth_time": int(datetime.now(timezone.utc).timestamp()),
        "is_super_admin": False,
    }
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _project(client: TestClient, suffix: str) -> str:
    response = client.post(
        "/api/v1/project-templates/ipd-product-development/instantiate",
        json={
            "request_id": f"m05a-project-{suffix}",
            "name": "M0.5A",
            "goal": "normalized facts",
            "desired_outputs": ["facts"],
            "truth_mode": "PLANNED",
        },
    )
    assert response.status_code == 201
    return response.json()["project_id"]


def _applied_project(client: TestClient, suffix: str) -> str:
    project_id = _project(client, suffix)
    intake = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={
            "request_id": f"m05a-intake-{suffix}",
            "business_goal": "deliver",
            "customers_and_scenarios": "team",
            "product_scope": "new",
            "product_form": "software",
            "innovation_level": "new_product",
            "tailoring_level": "standard",
            "requirements_and_evidence": "evidence",
            "desired_deliverables": ["package"],
            "target_finish_at": "2027-08-31T00:00:00Z",
        },
    ).json()
    draft = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/generate",
        json={
            "request_id": f"m05a-draft-{suffix}",
            "business_intake_id": intake["id"],
            "process_template_id": "ipd-product-development",
            "process_template_version": "1.0.0",
            "catalog_revision": "catalog-current",
        },
    ).json()
    applied = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/{draft['id']}/apply",
        json={
            "request_id": f"m05a-apply-{suffix}",
            "expected_revision": 0,
            "draft_revision": draft["revision"],
        },
    )
    assert applied.status_code == 200
    return project_id


def test_apply_persists_canonical_immutable_process_facts(client):
    project_id = _applied_project(client, "facts")
    process_v1 = client.get(f"/api/v1/projects/{project_id}/process").json()

    assert process_v1["config_revision"] == 1
    assert len(process_v1["canonical_hash"]) == 64

    with sqlite3.connect(TEST_DB) as connection:
        revision = connection.execute(
            "SELECT id, canonical_hash FROM workspace_process_revisions "
            "WHERE project_id = ? AND revision = 1",
            (project_id,),
        ).fetchone()
        assert revision and revision[1] == process_v1["canonical_hash"]
        revision_id = revision[0]
        counts = {
            table: connection.execute(
                f"SELECT count(*) FROM {table} WHERE process_revision_id = ?",
                (revision_id,),
            ).fetchone()[0]
            for table in (
                "workspace_stages",
                "workspace_task_revisions",
                "workspace_gates",
                "workspace_task_dependencies",
            )
        }
    assert counts == {
        "workspace_stages": len(process_v1["stages"]),
        "workspace_task_revisions": len(process_v1["tasks"]),
        "workspace_gates": len(process_v1["gates"]),
        "workspace_task_dependencies": len(process_v1["dependencies"]),
    }

    task_id = process_v1["tasks"][0]["id"]
    changed = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 1, "status": "IN_PROGRESS"},
    )
    assert changed.status_code == 200
    with sqlite3.connect(TEST_DB) as connection:
        revisions = connection.execute(
            "SELECT revision, canonical_hash FROM workspace_process_revisions "
            "WHERE project_id = ? ORDER BY revision",
            (project_id,),
        ).fetchall()
    assert len(revisions) == 2
    assert revisions[0] == (1, process_v1["canonical_hash"])
    assert revisions[1][0] == 2
    assert revisions[1][1] != revisions[0][1]


def _legacy_database(path: Path, *, include_orphan: bool = True) -> None:
    snapshot = {
        "process_instance_id": "proc_legacy",
        "stages": [{"id": "stage-1", "name": "concept", "order": 0}],
        "tasks": [
            {
                "id": "task-1",
                "stage_id": "stage-1",
                "title": "legacy task",
                "status": "TODO",
            }
        ],
        "gates": [{"id": "gate-1", "stage_id": "stage-1", "name": "TR1"}],
        "dependencies": [],
        "graphs": {},
    }
    import json

    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE workspace_projects (
                id VARCHAR(40) PRIMARY KEY,
                tenant_key VARCHAR(64) NOT NULL,
                owner_user_id VARCHAR(64) NOT NULL,
                name VARCHAR(160) NOT NULL,
                goal TEXT NOT NULL,
                desired_outputs JSON NOT NULL,
                template_id VARCHAR(80),
                template_version VARCHAR(32),
                truth_mode VARCHAR(20) NOT NULL,
                process_revision INTEGER NOT NULL,
                process_snapshot JSON NOT NULL
            );
            CREATE TABLE workspace_task_conversations (
                id VARCHAR(40) PRIMARY KEY,
                project_id VARCHAR(40) NOT NULL,
                task_id VARCHAR(40) NOT NULL
            );
            CREATE TABLE workflows (id VARCHAR(48) PRIMARY KEY);
            CREATE TABLE workflow_executions (id VARCHAR(48) PRIMARY KEY);
            """
        )
        connection.execute(
            "INSERT INTO workspace_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "project-legacy",
                "tenant-a",
                "owner-a",
                "legacy",
                "goal",
                "[]",
                "ipd-product-development",
                "1.0.0",
                "PLANNED",
                1,
                json.dumps(snapshot),
            ),
        )
        conversations = [("conv-valid", "project-legacy", "task-1")]
        if include_orphan:
            conversations.append(("conv-orphan", "project-legacy", "missing-task"))
        connection.executemany(
            "INSERT INTO workspace_task_conversations VALUES (?, ?, ?)",
            conversations,
        )


def test_migration_dry_run_backfills_deterministically_and_rolls_back(tmp_path):
    from sqlalchemy import create_engine

    from backend.services.workspace_migration import migrate_workspace_schema

    database = tmp_path / "legacy.db"
    _legacy_database(database)
    engine = create_engine(f"sqlite:///{database}")

    with engine.begin() as connection:
        dry_run = migrate_workspace_schema(connection, dry_run=True)
    assert dry_run == {
        "dry_run": True,
        "projects_scanned": 1,
        "projects_to_backfill": 1,
        "orphan_conversation_ids": ["conv-orphan"],
        "orphan_conversation_references": [],
        "revisions_written": 0,
    }
    with sqlite3.connect(database) as connection:
        assert "workspace_process_revisions" not in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    with pytest.raises(RuntimeError, match="orphan task conversations"):
        with engine.begin() as connection:
            migrate_workspace_schema(connection)
    with sqlite3.connect(database) as connection:
        assert "workspace_process_revisions" not in {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    clean_database = tmp_path / "clean.db"
    _legacy_database(clean_database, include_orphan=False)
    clean_engine = create_engine(f"sqlite:///{clean_database}")
    with clean_engine.begin() as connection:
        migrated = migrate_workspace_schema(connection)
    assert migrated["revisions_written"] == 1
    assert migrated["orphan_conversation_ids"] == []
    with sqlite3.connect(clean_database) as connection:
        first = connection.execute(
            "SELECT canonical_hash, legacy_snapshot FROM workspace_process_revisions"
        ).fetchone()
    assert first is not None

    with clean_engine.begin() as connection:
        repeated = migrate_workspace_schema(connection)
    assert repeated["revisions_written"] == 0
    with sqlite3.connect(clean_database) as connection:
        assert connection.execute(
            "SELECT canonical_hash, legacy_snapshot FROM workspace_process_revisions"
        ).fetchone() == first

    rollback_db = tmp_path / "rollback.db"
    _legacy_database(rollback_db, include_orphan=False)
    rollback_engine = create_engine(f"sqlite:///{rollback_db}")
    with pytest.raises(RuntimeError, match="injected migration failure"):
        with rollback_engine.begin() as connection:
            migrate_workspace_schema(connection, fail_after_backfill=True)
    with sqlite3.connect(rollback_db) as connection:
        assert connection.execute(
            "SELECT count(*) FROM workspace_process_revisions"
        ).fetchone()[0] == 0


def _auth(user_id: str, tenant: str = "tenant-a") -> None:
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": tenant,
        "user_id": user_id,
        "sub": user_id,
        "principal_type": "human",
        "amr": ["pwd"],
        "auth_time": int(datetime.now(timezone.utc).timestamp()),
        "is_super_admin": False,
    }


def test_gate_approval_chain_is_fail_closed_and_idempotent(client):
    project_id = _applied_project(client, "approval")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    gate_id = process["gates"][0]["id"]

    owner_self_review = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/decisions",
        json={
            "request_id": "decision-owner-self",
            "expected_process_revision": 1,
            "decision": "APPROVED",
            "comment": "self review",
        },
    )
    assert owner_self_review.status_code == 403

    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "request_id": "member-approver-001",
            "user_id": "approver-a",
            "role": "reviewer",
            "scopes": ["project:read", "gate:approve"],
        },
    )
    assert member.status_code == 201
    appointed = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/approvers",
        json={"request_id": "appoint-approver-001", "user_id": "approver-a"},
    )
    assert appointed.status_code == 201

    _auth("member-without-chain")
    denied = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/decisions",
        json={
            "request_id": "decision-denied-001",
            "expected_process_revision": 1,
            "decision": "APPROVED",
        },
    )
    assert denied.status_code == 403

    _auth("approver-a")
    request = {
        "request_id": "decision-approver-001",
        "expected_process_revision": 1,
        "decision": "APPROVED",
        "comment": "evidence accepted",
    }
    first = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/decisions", json=request
    )
    replay = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/decisions", json=request
    )
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == first.json()

    drift = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/decisions",
        json={**request, "decision": "REJECTED"},
    )
    assert drift.status_code == 409

    with sqlite3.connect(TEST_DB) as connection:
        assert connection.execute(
            "SELECT count(*) FROM workspace_approval_decisions WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0] == 1
        event_types = {
            row[0]
            for row in connection.execute(
                "SELECT event_type FROM workspace_audit_events WHERE project_id = ?",
                (project_id,),
            )
        }
    assert {"MEMBER_ADDED", "GATE_APPROVER_APPOINTED", "GATE_DECIDED"} <= event_types


def test_approval_rejects_cross_tenant_even_with_matching_ids(client):
    project_id = _applied_project(client, "cross-tenant")
    gate_id = client.get(f"/api/v1/projects/{project_id}/process").json()["gates"][0]["id"]
    _auth("intruder", tenant="tenant-b")
    response = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/decisions",
        json={
            "request_id": "cross-tenant-decision",
            "expected_process_revision": 1,
            "decision": "APPROVED",
        },
    )
    assert response.status_code == 404


def test_concurrent_duplicate_approval_replays_without_500(client, monkeypatch):
    from backend.models.workspace import WorkspaceApprovalDecision

    project_id = _applied_project(client, "approval-race")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    gate_id = process["gates"][0]["id"]
    assert client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "request_id": "member-race-approver",
            "user_id": "approver-race",
            "role": "reviewer",
            "scopes": ["gate:approve"],
        },
    ).status_code == 201
    assert client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/approvers",
        json={"request_id": "appoint-race-approver", "user_id": "approver-race"},
    ).status_code == 201
    _auth("approver-race")

    original_commit = AsyncSession.commit
    reached = 0
    release = asyncio.Event()

    async def synchronized_commit(session):
        nonlocal reached
        if any(isinstance(item, WorkspaceApprovalDecision) for item in session.new):
            reached += 1
            if reached == 2:
                release.set()
            else:
                await release.wait()
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", synchronized_commit)
    request = {
        "request_id": "concurrent-decision-request",
        "expected_process_revision": 1,
        "decision": "APPROVED",
        "comment": "same payload",
    }

    async def race():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
            url = f"/api/v1/projects/{project_id}/gates/{gate_id}/decisions"
            return await asyncio.gather(
                async_client.post(url, json=request),
                async_client.post(url, json=request),
            )

    responses = asyncio.run(race())
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["id"] for response in responses}) == 1


def test_normalized_projection_detects_legacy_snapshot_drift(client):
    project_id = _applied_project(client, "projection-drift")
    before = client.get(f"/api/v1/projects/{project_id}/process").json()
    with sqlite3.connect(TEST_DB) as connection:
        snapshot = json.loads(
            connection.execute(
                "SELECT process_snapshot FROM workspace_projects WHERE id=?", (project_id,)
            ).fetchone()[0]
        )
        snapshot["tasks"][0]["title"] = "tampered legacy cache"
        connection.execute(
            "UPDATE workspace_projects SET process_snapshot=? WHERE id=?",
            (json.dumps(snapshot), project_id),
        )
    drift = client.get(f"/api/v1/projects/{project_id}/process")
    assert drift.status_code == 409
    assert drift.json()["detail"]["error"] == "normalized_projection_drift"
    assert before["tasks"][0]["title"] != "tampered legacy cache"


def test_project_scopes_authorize_read_write_and_keep_admin_owner_only(client):
    project_id = _applied_project(client, "rbac")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task_id = process["tasks"][0]["id"]
    for request_id, member_id, scopes in (
        ("member-read-scope", "reader", ["project:read"]),
        ("member-write-scope", "writer", ["project:write"]),
        ("member-no-scope-00", "noscope", []),
        ("member-inactive-0", "inactive", ["project:read", "project:write"]),
    ):
        assert client.post(
            f"/api/v1/projects/{project_id}/members",
            json={"request_id": request_id, "user_id": member_id, "role": "member", "scopes": scopes},
        ).status_code == 201
    with sqlite3.connect(TEST_DB) as connection:
        connection.execute(
            "UPDATE workspace_project_members SET status='INACTIVE' "
            "WHERE project_id=? AND user_id='inactive'",
            (project_id,),
        )

    _auth("reader")
    assert project_id in {item["id"] for item in client.get("/api/v1/projects").json()}
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/tasks/{task_id}").status_code == 200
    assert client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 1, "status": "IN_PROGRESS"},
    ).status_code == 403
    assert client.post(
        "/api/v1/task-conversations",
        json={"project_id": project_id, "task_id": task_id, "agent_version": "reader"},
    ).status_code == 403

    _auth("writer")
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 200
    assert client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 1, "status": "IN_PROGRESS"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "request_id": "writer-must-not-admin",
            "user_id": "another",
            "role": "member",
            "scopes": ["project:read"],
        },
    ).status_code == 404

    for blocked_user in ("noscope", "inactive"):
        _auth(blocked_user)
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 403
        assert project_id not in {item["id"] for item in client.get("/api/v1/projects").json()}
    _auth("writer", tenant="tenant-b")
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_concurrent_decision_request_id_drift_across_gates_returns_conflict(client, monkeypatch):
    from backend.models.workspace import WorkspaceApprovalDecision

    project_id = _applied_project(client, "decision-drift-race")
    gates = client.get(f"/api/v1/projects/{project_id}/process").json()["gates"][:2]
    assert client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "request_id": "member-drift-race",
            "user_id": "race-reviewer",
            "role": "reviewer",
            "scopes": ["gate:approve"],
        },
    ).status_code == 201
    for index, gate in enumerate(gates):
        assert client.post(
            f"/api/v1/projects/{project_id}/gates/{gate['id']}/approvers",
            json={"request_id": f"appoint-drift-{index}", "user_id": "race-reviewer"},
        ).status_code == 201
    _auth("race-reviewer")
    original_commit = AsyncSession.commit
    reached = 0
    release = asyncio.Event()

    async def synchronized_commit(session):
        nonlocal reached
        if any(isinstance(item, WorkspaceApprovalDecision) for item in session.new):
            reached += 1
            if reached == 2:
                release.set()
            else:
                await release.wait()
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", synchronized_commit)

    async def race():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
            payload = {
                "request_id": "same-key-different-gate",
                "expected_process_revision": 1,
                "decision": "APPROVED",
                "comment": "same",
            }
            return await asyncio.gather(*[
                async_client.post(
                    f"/api/v1/projects/{project_id}/gates/{gate['id']}/decisions",
                    json=payload,
                )
                for gate in gates
            ])

    responses = asyncio.run(race())
    assert sorted(response.status_code for response in responses) == [201, 409]


def test_concurrent_member_and_appointment_same_payload_replay_200(client, monkeypatch):
    from backend.models.workspace import WorkspaceGateApprover, WorkspaceProjectMember

    project_id = _applied_project(client, "member-appoint-race")
    gate_id = client.get(f"/api/v1/projects/{project_id}/process").json()["gates"][0]["id"]
    original_commit = AsyncSession.commit
    state = {"model": WorkspaceProjectMember, "count": 0, "release": asyncio.Event()}

    async def synchronized_commit(session):
        if any(isinstance(item, state["model"]) for item in session.new):
            state["count"] += 1
            if state["count"] == 2:
                state["release"].set()
            else:
                await state["release"].wait()
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", synchronized_commit)

    async def post_twice(url, body):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
            return await asyncio.gather(async_client.post(url, json=body), async_client.post(url, json=body))

    member_body = {
        "request_id": "concurrent-member-key",
        "user_id": "concurrent-reviewer",
        "role": "reviewer",
        "scopes": ["gate:approve"],
    }
    member_responses = asyncio.run(post_twice(f"/api/v1/projects/{project_id}/members", member_body))
    assert sorted(item.status_code for item in member_responses) == [200, 201]
    state.update({"model": WorkspaceGateApprover, "count": 0, "release": asyncio.Event()})
    appointment_responses = asyncio.run(post_twice(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/approvers",
        {"request_id": "concurrent-appoint-key", "user_id": "concurrent-reviewer"},
    ))
    assert sorted(item.status_code for item in appointment_responses) == [200, 201]


def test_member_and_appointment_payloads_are_complete_and_replay_identically(client):
    project_id = _applied_project(client, "complete-payload")
    gate_id = client.get(f"/api/v1/projects/{project_id}/process").json()["gates"][0]["id"]
    member_request = {
        "request_id": "complete-member-request",
        "user_id": "complete-approver",
        "role": "reviewer",
        "scopes": ["project:read", "gate:approve"],
    }

    member = client.post(f"/api/v1/projects/{project_id}/members", json=member_request)
    member_replay = client.post(
        f"/api/v1/projects/{project_id}/members", json=member_request
    )
    assert member.status_code == 201
    assert member_replay.status_code == 200
    assert member_replay.json() == member.json()
    member_payload = member.json()
    assert member_payload == {
        "id": member_payload["id"],
        "project_id": project_id,
        "tenant_id": "tenant-a",
        "user_id": "complete-approver",
        "request_id": "complete-member-request",
        "role": "reviewer",
        "scopes": ["project:read", "gate:approve"],
        "status": "ACTIVE",
        "appointed_by": "owner-a",
        "approver_id": None,
    }

    appointment_request = {
        "request_id": "complete-appointment-request",
        "user_id": "complete-approver",
    }
    appointment = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/approvers",
        json=appointment_request,
    )
    appointment_replay = client.post(
        f"/api/v1/projects/{project_id}/gates/{gate_id}/approvers",
        json=appointment_request,
    )
    assert appointment.status_code == 201
    assert appointment_replay.status_code == 200
    assert appointment_replay.json() == appointment.json()
    appointment_payload = appointment.json()
    assert appointment_payload == {
        "id": appointment_payload["id"],
        "project_id": project_id,
        "tenant_id": "tenant-a",
        "gate_id": gate_id,
        "user_id": "complete-approver",
        "request_id": "complete-appointment-request",
        "status": "ACTIVE",
        "appointed_by": "owner-a",
        "member_id": member_payload["id"],
        "project_approver_id": appointment_payload["project_approver_id"],
    }


def test_project_write_member_edits_task_and_persists_normalized_revision(client):
    project_id = _applied_project(client, "member-edit")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task = process["tasks"][0]
    stage = process["stages"][0]
    member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={
            "request_id": "member-edit-request",
            "user_id": "writer-a",
            "role": "editor",
            "scopes": ["project:read", "project:write"],
        },
    )
    assert member.status_code == 201

    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a",
        "user_id": "writer-a",
        "sub": "writer-a",
        "principal_type": "human",
        "amr": ["pwd"],
        "auth_time": int(datetime.now(timezone.utc).timestamp()),
        "is_super_admin": False,
    }
    edited = client.put(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}",
        json={
            "expected_revision": 1,
            "stage_id": stage["id"],
            "title": "Member edited title",
            "summary": "Member edited summary",
            "assignee_role": "Editor",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["process_revision"] == 2

    projected = client.get(f"/api/v1/projects/{project_id}/process")
    assert projected.status_code == 200, projected.text
    assert projected.json()["process_revision"] == 2
    assert next(
        item for item in projected.json()["tasks"] if item["id"] == task["id"]
    )["title"] == "Member edited title"
