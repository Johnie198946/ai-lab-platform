from __future__ import annotations

import json
from pathlib import Path

from backend.services.visitor_insight import (
    extract_visitor_insight,
    persist_visitor_wiki,
)


def envelope(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False)
    return (
        "摘要\n<!-- AI_LAB_VISITOR_INSIGHT_V1 "
        f"{serialized} AI_LAB_VISITOR_INSIGHT_V1 -->"
    )


def test_extracts_versioned_visitor_insight_and_rejects_unsafe_urls() -> None:
    result = extract_visitor_insight(
        envelope(
            {
                "customer_positioning": ["算力基础设施企业"],
                "verified_facts": ["发布新一代产品"],
                "hypotheses": ["交付效率可能是关注点"],
                "sources": [
                    {
                        "title": "官网",
                        "url": "https://example.com/news",
                        "confidence": "high",
                    },
                    {"title": "危险链接", "url": "javascript:alert(1)"},
                ],
            }
        )
    )

    assert result["recognized"] is True
    assert result["summary"]["verified_facts"] == ["发布新一代产品"]
    assert result["sources"][0]["url"].startswith("https://")
    assert result["sources"][1]["url"] == ""


def test_wiki_separates_public_facts_from_private_visit_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    visitor = {
        "visit_id": "visit/../../unsafe",
        "customer_code": "C023",
        "company_name": "示例科技/集团",
        "visitors": [{"name": "张三", "title": "CTO"}],
        "purpose": "讨论未公开方案",
        "focus_topics": ["Agent 编排"],
    }
    insight = {
        "source_hash": "abc",
        "summary": {
            "customer_positioning": ["公开定位"],
            "verified_facts": ["公开事实"],
            "hypotheses": ["未验证痛点"],
            "reception_advice": ["现场建议"],
        },
        "sources": [
            {
                "title": "官网",
                "url": "https://example.com",
                "date": "2026-08-01",
                "confidence": "high",
            }
        ],
    }

    paths = persist_visitor_wiki(
        tenant_key="tenant/demo", visitor=visitor, insight=insight
    )
    public = (tmp_path / paths["public_wiki_slug"]).read_text(encoding="utf-8")
    private = (tmp_path / paths["private_record_path"]).read_text(encoding="utf-8")

    assert "张三" not in public
    assert "未验证痛点" not in public
    assert "公开事实" in public
    assert "张三" in private
    assert "未验证痛点" in private
    assert ".." not in paths["private_record_path"]


def test_without_sources_only_private_record_is_written(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    paths = persist_visitor_wiki(
        tenant_key="demo",
        visitor={
            "visit_id": "visit-1",
            "customer_code": "C001",
            "company_name": "无来源公司",
        },
        insight={
            "source_hash": "x",
            "summary": {"hypotheses": ["待验证"]},
            "sources": [],
        },
    )

    assert paths["public_wiki_slug"] == ""
    assert (tmp_path / paths["private_record_path"]).is_file()
