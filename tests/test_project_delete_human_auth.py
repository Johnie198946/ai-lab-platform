from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.api.quantum_workspace import _require_interactive_human, _enforce_agent_lease_fence


@pytest.mark.parametrize(
    "payload",
    [
        {"principal_type": "human", "amr": ["pwd"], "auth_time": "now"},
        {"principal_type": "human", "amr": ["otp"], "auth_time": "now"},
        {"principal_type": "human", "amr": ["oauth"], "auth_time": "now"},
    ],
)
def test_delete_project_accepts_interactive_human_auth_methods(payload):
    payload["auth_time"] = int(datetime.now(timezone.utc).timestamp())
    _require_interactive_human(payload)


@pytest.mark.parametrize(
    "payload,detail",
    [
        ({"principal_type": "service", "amr": ["oauth"]}, "authenticated human principal required"),
        ({"principal_type": "human", "amr": ["service_token"]}, "interactive human authentication required"),
        ({"principal_type": "human", "amr": []}, "interactive human authentication required"),
        ({"principal_type": "human", "amr": ["test_interactive"], "auth_time": 1}, "interactive human authentication required"),
        ({"principal_type": "human", "amr": ["pwd"]}, "recent interactive authentication required"),
        ({"principal_type": "human", "amr": ["pwd"], "auth_time": 1}, "recent interactive authentication required"),
    ],
)
def test_delete_project_rejects_noninteractive_or_service_principals(payload, detail):
    with pytest.raises(HTTPException) as excinfo:
        _require_interactive_human(payload)
    assert excinfo.value.detail == detail


def test_agent_lease_fence_allows_interactive_human_principals_without_session():
    task = {}
    payload = {"principal_type": "human", "amr": ["otp"], "sub": "u1"}
    # Should return before requiring a session_id/lease when the principal is an interactive human.
    _enforce_agent_lease_fence(task, payload, session_id=None, lease_epoch=None)
