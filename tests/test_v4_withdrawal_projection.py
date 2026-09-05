"""V4 lifecycle states must never become public catalog entries."""
import pytest
from backend.services.knowledge_color_projection import (
    approved_color_documents, clear_color_projection_cache,
)


@pytest.mark.parametrize('state', [
    'archived', 'deleted', 'superseded', 'stale', 'quarantined',
    'withdraw_pending', 'withdrawing', 'withdrawn',
])
def test_inactive_approved_green_is_not_projected(tmp_path, state):
    wiki = tmp_path / 'wiki'
    wiki.mkdir()
    (wiki / 'example.md').write_text(
        '---\ntitle: Example\nsecurity_level: green\n'
        'classification_status: approved\nowner_tenant: public\n'
        f'status: {state}\n---\nExample\n', encoding='utf-8',
    )
    clear_color_projection_cache()
    assert approved_color_documents(tmp_path) == []
