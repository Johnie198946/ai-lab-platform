import pytest

from backend.services.workflow_executor import contiguous_bridge_events


def test_bridge_events_are_sorted_deduplicated_and_contiguous():
    events = [
        {"seq": 3, "event_id": "run:3"},
        {"seq": 2, "event_id": "run:2"},
        {"seq": 2, "event_id": "run:2"},
        {"seq": 1, "event_id": "run:1"},
    ]
    assert [event["seq"] for event in contiguous_bridge_events(events, 0)] == [1, 2, 3]
    assert [event["seq"] for event in contiguous_bridge_events(events, 1)] == [2, 3]


def test_bridge_event_gap_is_not_projected():
    with pytest.raises(RuntimeError, match="event gap"):
        contiguous_bridge_events(
            [{"seq": 4, "event_id": "run:4"}],
            2,
        )
