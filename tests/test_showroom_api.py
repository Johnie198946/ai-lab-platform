from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt

from backend.api.showroom import (
    ReviewSubmission,
    ShowroomCommand,
    _validate_websocket_token,
    apply_showroom_command,
    hub,
    submit_showroom_review,
)


def auth_token() -> str:
    return jwt.encode(
        {"sub": "showroom-user", "username": "guide"},
        "test-secret",
        algorithm="HS256",
    )


def payload() -> dict[str, str]:
    return {"sub": "showroom-user", "username": "guide", "tenant_key": "demo"}


def reset_state() -> None:
    hub.state.update(
        {
            "epoch": 0,
            "stage": "station-1",
            "payload": {},
            "reviews": {},
        }
    )
    hub.ready_sessions.clear()


def test_showroom_prepare_commit_and_stale_epoch() -> None:
    reset_state()
    prepared = asyncio.run(
        apply_showroom_command(
            ShowroomCommand(
                type="PREPARE",
                epoch=100,
                stage="station-4",
                payload={"demand": "换模"},
            ),
            payload(),
        )
    )
    assert prepared["stage"] == "station-1"

    committed = asyncio.run(
        apply_showroom_command(
            ShowroomCommand(
                type="COMMIT",
                epoch=100,
                stage="station-4",
                payload={"demand": "换模"},
            ),
            payload(),
        )
    )
    assert committed["stage"] == "station-4"
    assert committed["payload"]["demand"] == "换模"

    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            apply_showroom_command(
                ShowroomCommand(type="COMMIT", epoch=99, stage="station-2"),
                payload(),
            )
        )
    assert stale.value.status_code == 409


def test_review_requires_comment_for_non_approval() -> None:
    reset_state()
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(
            submit_showroom_review(
                "TR1",
                ReviewSubmission(decision="changes", comment="", phase="概念"),
                payload(),
            )
        )
    assert rejected.value.status_code == 422

    accepted = asyncio.run(
        submit_showroom_review(
            "TR1",
            ReviewSubmission(decision="approved", comment="", phase="概念"),
            payload(),
        )
    )
    assert accepted["reviews"]["TR1"]["decision"] == "approved"


def test_websocket_token_validation() -> None:
    assert _validate_websocket_token(auth_token())["username"] == "guide"
    with pytest.raises(JWTError):
        _validate_websocket_token("not-a-token")
