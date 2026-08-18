import pytest
from fastapi import HTTPException

from backend.api import chat


def test_validate_chat_skill_allows_demand_architect() -> None:
    assert (
        chat.validate_chat_skill("solution-consultant-persona")
        == "solution-consultant-persona"
    )
    assert chat.validate_chat_skill(None) is None


def test_validate_chat_skill_rejects_non_allowlisted_skill() -> None:
    with pytest.raises(HTTPException) as error:
        chat.validate_chat_skill("../../secret")
    assert error.value.status_code == 400
