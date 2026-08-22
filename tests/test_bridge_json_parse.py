import pytest

from scripts.hermes_bridge import _extract_json_object


def test_extract_json_object_accepts_strict_json():
    assert _extract_json_object('prefix {"nodes": [], "edges": []} suffix') == {
        "nodes": [],
        "edges": [],
    }


def test_extract_json_object_accepts_python_literal_fallback_for_model_output():
    raw = "```json\n{'nodes': [], 'edges': [],}\n```"
    assert _extract_json_object(raw) == {"nodes": [], "edges": []}


def test_extract_json_object_rejects_non_object_literal():
    with pytest.raises(ValueError, match="JSON 计划"):
        _extract_json_object("['not', 'an', 'object']")
