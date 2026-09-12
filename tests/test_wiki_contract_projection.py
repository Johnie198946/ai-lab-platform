import pytest

pytest_plugins = ("test_wiki_retrieval_governance",)


@pytest.mark.parametrize("markup", [
    '<a href="secret.md">PRIVATE_SENTINEL</a>',
    'prefix <a href="secret.md">PRIVATE_SENTINEL</a> suffix',
    '> <a href="secret.md">\n> PRIVATE_SENTINEL\n> </a>',
    '<span data-secret="PRIVATE_SENTINEL">label</span>',
    '<a href="secret.md">PRIVATE_SENTINEL',
])
def test_raw_html_cannot_preserve_private_labels(wiki, tmp_path, markup):
    from backend.api import knowledge as api
    path = wiki("public", "保留的公开内容。\n\n" + markup)
    result = api._model_text(path.read_text(), "wiki/public.md", tmp_path)
    assert "PRIVATE_SENTINEL" not in result
    assert "secret.md" not in result
    assert "保留的公开内容。" in result


def test_wiki_contract_does_not_require_matrix(wiki, monkeypatch):
    from backend.api import knowledge as api
    monkeypatch.setattr(api, "_matrix", lambda: {})
    contract = api.get_contract()
    assert contract["matrix_available"] is False
    assert contract["retrieval_interface"] == "wiki_entries_and_relevant_links"
    assert "not_truth_or_admission" in contract["matrix_role"]
    assert contract["machine_interface"] == "knowledge_catalog+knowledge_matrix"
    assert "knowledge_matrix.json（实体索引）" not in contract["source_of_truth"]["machine"]
