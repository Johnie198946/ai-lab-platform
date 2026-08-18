from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.api import chat


def test_expand_chat_skill_uses_hermes_scaffolding(tmp_path: Path, monkeypatch) -> None:
    skill_file = tmp_path / "productivity" / "solution-consultant-persona" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: solution-consultant-persona\n---\n# 架构师", encoding="utf-8"
    )
    monkeypatch.setattr(chat, "HERMES_SKILLS_DIR", tmp_path)

    expanded = chat.expand_chat_skill(
        "solution-consultant-persona", "我们要缩短换模时间"
    )

    assert expanded.startswith(
        '[IMPORTANT: The user has invoked the "solution-consultant-persona" skill'
    )
    assert "# 架构师" in expanded
    assert "The user has provided the following instruction" in expanded
    assert expanded.endswith("我们要缩短换模时间")


def test_expand_chat_skill_rejects_non_allowlisted_skill() -> None:
    with pytest.raises(HTTPException) as error:
        chat.expand_chat_skill("../../secret", "test")
    assert error.value.status_code == 400
