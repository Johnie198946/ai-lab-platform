"""SYNTHETIC contract fixtures only; these are NOT actual editorial approvals.

`synthetic_fixture()` is the full executable legal-schema example for callers.
Pseudo-CJK content deliberately demonstrates that deterministic prerequisites
cannot certify semantic quality or authenticate a claimed independent reviewer.
"""
import copy
import random

import pytest

from backend.services.publication_editorial import (
    BOOK_CHECKS, CHAPTER_CHECKS, editorial_metrics, editorial_target_hash,
    make_editorial_contract, validate_editorial, validate_editorial_brief,
)


def synthetic_brief(genre="popular_science"):
    return {
        "genre": genre,
        "question": "为什么这个合成主题值得非技术读者现在投入时间理解？",
        "thesis": "合成测试论点只用于验证原创判断会与正文和来源共同绑定，不能代表真实编辑结论。",
        "reader_value": "读者可据此检查选题是否提供明确的新理解或下一步行动。",
        "novelty": "相对已有目录，本测试只新增合同结构与目标哈希绑定的验证。",
        "counterargument": "一种反方意见认为机械字段齐全并不能证明文章真的专业或有洞见。",
        "uncertainties": ["确定性验证器无法独立判断论点的新颖性与事实质量。"],
        "evidence_urls": ["https://example.com/source"],
        "selection_reason": "选择此题仅因为它能以最小样本覆盖新的主编选题合同。",
    }


def synthetic_fixture(format="book"):
    rng = random.Random(731)
    count, length = (8, 2600) if format == "book" else (1, 3200)
    parts = []
    for i in range(count):
        prose = "".join(chr(rng.randrange(0x4E00, 0x9FFF + 1)) for _ in range(length))
        parts.append(f"## 第{i + 1}章 合成测试\n\n### 机制与示例\n\n{prose}\n\n")
    body = "".join(parts)
    receipts = [{"source_url": "https://example.org/synthetic", "sha256": "a" * 64,
                 "kind": "synthetic-test-only"}]
    contract = make_editorial_contract(
        body, format=format, writer_sessions=["hermes:synthetic-writer"], revision=1,
        learning_objectives=["仅供合成测试验证契约结构，不代表真实内容质量"],
        editorial_brief=synthetic_brief(), research_gaps=[], source_receipts=receipts,
    )
    review = {
        "editorial_target_hash": contract["target_hash"],
        "reviewer_session": "hermes:synthetic-reviewer", "revision": 1,
        "decision": "approved", "research_gaps": [], "chapters": [],
        "book_checks": {name: {"decision": "approved", "finding":
            f"合成测试占位说明：{name}。此文本只检查格式长度，不能证明可读性与审稿独立性。"}
            for name in BOOK_CHECKS},
    }
    for c in editorial_metrics(body)["chapters"]:
        review["chapters"].append({"id": c["id"], "body_hash": c["body_hash"],
            "decision": "approved", "checks": {name: {
                "quote": c["paragraphs"][0][:30],
                "finding": f"合成测试占位说明：{name}。这是测试结构验证的说明而非真实审稿，不得作为出版批准。",
            } for name in CHAPTER_CHECKS}})
    return body, contract, review, receipts


@pytest.mark.parametrize("format", ["book", "chapter"])
def test_complete_synthetic_contract(format):
    assert validate_editorial(*synthetic_fixture(format)) == []


def test_only_ast_prose_counts_and_h3_rolls_up():
    body = """# 标题不计
## 第一章 不计标题

正文汉字。

### 子标题不计

[链接标签](https://example.org/目的地不计) `代码不计` ![图片不计](x)

> 引用不计
>
> ## 引用假章

```text
代码不计
```

    缩进代码不计

<div>HTML不计</div>

<!-- 注释不计 -->

<span>行内不计</span>保留文字。

### 参考文献

参考资料不计。

### 正文恢复

恢复正文。

## 附录

附录不计。
"""
    m = editorial_metrics(body)
    assert m["total_cjk"] == len("正文汉字链接标签保留文字恢复正文")
    assert len(m["chapters"]) == 1
    assert m["chapters"][0]["unique_cjk"] == m["unique_cjk"]
    assert "恢复正文。" in m["chapters"][0]["paragraphs"]


def test_duplicate_normalization_and_global_chapter_dedupe():
    m = editorial_metrics("## 一\n\n相同正文，例子１。\n\n## 二\n\n相 同 正 文！例子２。\n")
    assert m["total_cjk"] == 12
    assert m["unique_cjk"] == 6
    assert m["duplicate_ratio"] == 0.5
    assert m["chapters"][1]["unique_cjk"] == 0


def test_short_padding_and_no_subheading_chapter_inflation():
    body = "## 正文\n\n短文。\n\n" + ("### 标题汉字\n\n" * 50) + "```\n" + "填充" * 20000 + "\n```\n"
    c = make_editorial_contract(body, format="book", writer_sessions=["writer"], revision=1,
                                learning_objectives=["理解此合成测试的限制与目标"], editorial_brief=synthetic_brief())
    reasons = validate_editorial(body, c)
    assert {"quality.chapter_count", "quality.effective_cjk", "review.required"} <= set(reasons)
    assert len(editorial_metrics(body)["chapters"]) == 1


def test_missing_chapter_short_chapter_and_duplicate_reject():
    body, c, r, receipts = synthetic_fixture()
    c["chapters"].pop()
    assert "contract.chapters" in validate_editorial(body, c, r, receipts)

    # Entire-paragraph dedupe cannot detect paraphrases/repeated fragments.
    repeated = "## 第一章\n\n" + ("重复正文。\n\n" * 1000)
    c2 = make_editorial_contract(repeated, format="chapter", writer_sessions=["writer"], revision=1,
                                 learning_objectives=["理解此合成测试的限制与目标"], editorial_brief=synthetic_brief())
    assert "quality.duplicate_ratio" in validate_editorial(repeated, c2)
    assert "quality.chapter_length:chapter-001" in validate_editorial(repeated, c2)


@pytest.mark.parametrize("field,value,reason", [
    ("format", "article", "contract.format"),
    ("version", "editorial-v1", "contract.version"),
    ("revision", True, "contract.revision"),
    ("revision", 1.0, "contract.revision"),
    ("previous_body_hash", "SHA256:bad", "contract.previous_body_hash"),
    ("writer_sessions", [False], "contract.writer_sessions"),
    ("learning_objectives", [], "contract.learning_objectives"),
])
def test_invalid_contract_schema(field, value, reason):
    body, c, r, receipts = synthetic_fixture("chapter")
    c[field] = value
    reasons = validate_editorial(body, c, r, receipts)
    assert reason in reasons
    assert "contract.target_hash" in reasons
    assert reasons == sorted(set(reasons))


def test_hash_binds_format_body_objectives_chapters_and_receipts():
    body, c, r, receipts = synthetic_fixture("chapter")
    for field, value in [("format", "book"), ("learning_objectives", ["新的学习目标内容必须重新审稿"]),
                         ("chapters", []), ("target_hash", "A" * 64)]:
        altered = {**c, field: value}
        assert "contract.target_hash" in validate_editorial(body, altered, r, receipts)
    assert "contract.target_hash" in validate_editorial(body + "\n", c, r, receipts)
    assert "contract.target_hash" in validate_editorial(body, c, r, [{"different": True}])
    assert editorial_target_hash(body, c, receipts * 2) == c["target_hash"]
    assert editorial_target_hash(body, {**c, "target_hash": "ignored"}, receipts) == c["target_hash"]
    altered = {**c, "format": "book"}
    altered["target_hash"] = editorial_target_hash(body, altered, receipts)
    assert "review.target_hash" in validate_editorial(body, altered, r, receipts)


def test_editorial_brief_is_required_hash_bound_and_structured():
    body, contract, review, receipts = synthetic_fixture("chapter")
    assert validate_editorial_brief(contract["editorial_brief"]) == []
    for mutation, reason in [
        ({"genre": "summary"}, "contract.editorial_brief"),
        ({**synthetic_brief(), "genre": "summary"}, "contract.editorial_brief.genre"),
        ({**synthetic_brief(), "thesis": "摘要"}, "contract.editorial_brief.thesis"),
        ({**synthetic_brief(), "uncertainties": []}, "contract.editorial_brief.uncertainties"),
        ({**synthetic_brief(), "evidence_urls": ["http://example.org"]}, "contract.editorial_brief.evidence_urls"),
    ]:
        changed = {**contract, "editorial_brief": mutation}
        reasons = validate_editorial(body, changed, review, receipts)
        assert reason in reasons and "contract.target_hash" in reasons


@pytest.mark.parametrize("session", ["hermes:synthetic-writer", "other:reviewer", "hermes:", True])
def test_self_review_and_non_hermes_rejected(session):
    body, c, r, receipts = synthetic_fixture("chapter")
    r["reviewer_session"] = session
    assert "review.independence" in validate_editorial(body, c, r, receipts)


def test_open_gap_and_resolved_gap_schema():
    body, c, r, receipts = synthetic_fixture("chapter")
    gap = {"id": "gap-1", "question": "证据是否足以支持这一机制解释？", "state": "open",
           "resolution": "", "source_urls": []}
    c["research_gaps"] = [gap]
    assert "research_gaps.open" in validate_editorial(body, c, r, receipts)
    gap.update(state="resolved", resolution="这是合成测试的解释字段，仅测试明确说明和引用链接的契约格式，不表示已核实真实来源。",
               source_urls=["https://example.org/source"])
    c["target_hash"] = editorial_target_hash(body, c, receipts)
    r["editorial_target_hash"] = c["target_hash"]
    assert validate_editorial(body, c, r, receipts) == []
    gap["source_urls"] = ["http://example.org/source"]
    assert "contract.research_gaps" in validate_editorial(body, c, r, receipts)


@pytest.mark.parametrize("mutation,reason", [
    (lambda r: r.update(revision=True), "review.revision"),
    (lambda r: r.update(decision="revise"), "review.decision"),
    (lambda r: r.update(research_gaps=["open"]), "review.research_gaps"),
    (lambda r: r.update(chapters=[]), "review.chapters"),
    (lambda r: r["chapters"][0].update(body_hash="0" * 64), "review.chapter:chapter-001"),
    (lambda r: r["chapters"][0].update(checks={"score": 100}), "review.check:chapter-001:mechanism"),
    (lambda r: r["chapters"][0]["checks"]["mechanism"].update(quote="伪造的引用" * 10), "review.check:chapter-001:mechanism"),
    (lambda r: r["chapters"][0]["checks"]["mechanism"].update(finding="好"), "review.check:chapter-001:mechanism"),
    (lambda r: r.update(book_checks={"score": 100}), "review.book_check:coherence"),
])
def test_review_is_evidence_not_scores(mutation, reason):
    body, c, r, receipts = synthetic_fixture("chapter")
    mutation(r)
    assert reason in validate_editorial(body, c, r, receipts)


def test_chapter_identity_and_hash_exactness():
    body, c, r, receipts = synthetic_fixture()
    r["chapters"][1] = copy.deepcopy(r["chapters"][0])
    assert "review.chapters" in validate_editorial(body, c, r, receipts)
    before = editorial_metrics(body)["chapters"]
    after = editorial_metrics(body.replace("### 机制与示例", "### 修订后的机制", 1))["chapters"]
    assert [x["id"] for x in before] == [x["id"] for x in after]
    assert before[0]["body_hash"] != after[0]["body_hash"]
    assert before[1]["body_hash"] == after[1]["body_hash"]


@pytest.mark.parametrize("value", [None, True, 12, "invalid", [], {"bad": []}])
def test_malformed_inputs_do_not_crash(value):
    body, c, r, receipts = synthetic_fixture("chapter")
    assert validate_editorial(body, value, r, receipts)
    assert validate_editorial(body, c, value, receipts)
    for field in ("writer_sessions", "chapters", "research_gaps", "revision"):
        if field == "research_gaps" and value == []:
            continue  # Empty gaps are valid, not malformed.
        assert validate_editorial(body, {**c, field: value}, r, receipts)
    if value is not None and value != []:
        assert "contract.target_hash" in validate_editorial(body, c, r, value)


def test_cross_chapter_quote_and_missing_checks_fail():
    body, c, r, receipts = synthetic_fixture()
    r["chapters"][0]["checks"]["evidence"]["quote"] = r["chapters"][1]["checks"]["evidence"]["quote"]
    del r["chapters"][0]["checks"]["limits"]
    reasons = validate_editorial(body, c, r, receipts)
    assert "review.check:chapter-001:evidence" in reasons
    assert "review.check:chapter-001:limits" in reasons


def test_front_matter_cannot_satisfy_chapter_length():
    body, _, _, _ = synthetic_fixture("chapter")
    prose = editorial_metrics(body)["chapters"][0]["paragraphs"][0]
    body = f"{prose}\n\n## 正文章\n\n少量正文。\n\n## **参考文献**\n\n{prose}\n"
    c = make_editorial_contract(body, format="chapter", writer_sessions=["writer"], revision=1,
                                learning_objectives=["理解此合成测试的限制与目标"], editorial_brief=synthetic_brief())
    metrics = editorial_metrics(body)
    assert len(metrics["chapters"]) == 1
    assert metrics["total_cjk"] == len(prose) + 4
    assert "quality.effective_cjk" in validate_editorial(body, c)


def test_minimums_are_constants_and_not_environment(monkeypatch):
    monkeypatch.setenv("BOOK_MIN_CJK", "1")
    monkeypatch.setenv("CHAPTER_MIN_CJK", "1")
    body, c, r, receipts = synthetic_fixture("chapter")
    prose = editorial_metrics(body)["chapters"][0]["paragraphs"][0]
    body = body.replace(prose, prose[:2999])
    c = make_editorial_contract(body, format="chapter", writer_sessions=["writer"], revision=1,
                                learning_objectives=["理解此合成测试的限制与目标"], editorial_brief=synthetic_brief())
    assert "quality.chapter_length:chapter-001" in validate_editorial(body, c)


def test_receipts_order_canonicalization_and_non_json_fail_closed():
    body, c, r, receipts = synthetic_fixture("chapter")
    other = {"source_url": "https://example.org/other", "sha256": "b" * 64}
    assert editorial_target_hash(body, c, receipts + [other]) == editorial_target_hash(body, c, [other] + receipts)
    assert "contract.target_hash" in validate_editorial(body, c, r, [{"not_json": float("nan")}])
