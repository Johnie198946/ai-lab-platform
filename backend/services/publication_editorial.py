"""Pure, fail-closed editorial prerequisites, NOT proof of literary quality.

No runtime, IO, DB or model calls. Operator must independently authenticate native
Hermes writer/reviewer receipts: a caller-supplied session string proves nothing.
`make_editorial_contract` creates a draft contract, NEVER an approved review.
Source receipts are JSON-object lists; their complete canonical hashes are bound
as a sorted set. Existing publication/source provenance gates remain mandatory.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

BOOK_MIN_CJK = 20_000
BOOK_MIN_CHAPTERS = 8
BOOK_CHAPTER_MIN_CJK = 1_000
CHAPTER_MIN_CJK = 3_000
MAX_DUPLICATE_RATIO = 0.15
MIN_QUOTE_LENGTH = 20
MIN_FINDING_LENGTH = 30
CHAPTER_CHECKS = ("mechanism", "worked_example", "limits", "reader_questions", "evidence")
BOOK_CHECKS = ("coherence", "non_redundancy", "novice_readability")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_NON_BODY = re.compile(r"^(?:前言|序言|序|目录|来源|参考(?:资料|文献)?|引用|附录|致谢|preface|contents|references|sources|bibliography|appendix)(?:\s|[:：、.\-]|$)", re.I)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(value, minimum=1):
    return isinstance(value, str) and len(value.strip()) >= minimum


def _inline(token):
    """Visible prose only: no inline code, images, HTML or HTML contents."""
    output, depth = [], 0
    for child in token.children or []:
        if child.type == "html_inline":
            tag = child.content.strip()
            if tag.startswith("</"):
                depth = max(0, depth - 1)
            elif re.match(r"<[A-Za-z]", tag) and not re.match(r"<(?:br|hr|img|input|meta|link|wbr)\b", tag, re.I) and not tag.endswith("/>"):
                depth += 1
        elif not depth and child.type == "text":
            output.append(child.content)
        elif not depth and child.type in {"softbreak", "hardbreak"}:
            output.append("\n")
    return "".join(output)


def editorial_metrics(body: str) -> dict:
    """H2 chapters include all their H3+ prose. Counts dedupe CJK paragraphs
    globally (NFKC, punctuation/spacing/Latin/numbers ignored). Chapter IDs are
    positional and stable across body-only edits; hashes bind exact raw spans.
    All heading levels may start excluded reference sections. Only paragraph
    AST nodes count; headings, code, quotes, HTML and link destinations do not.
    """
    if not isinstance(body, str):
        raise ValueError("body must be a string")
    tokens = MarkdownIt("commonmark", {"html": True}).parse(body)
    lines = body.splitlines(keepends=True)
    chapters, paragraphs, seen = [], [], set()
    current, blocked_level, quote_depth = None, None, 0
    total = unique = 0
    for i, token in enumerate(tokens):
        if token.type == "blockquote_open":
            quote_depth += 1
        elif token.type == "blockquote_close":
            quote_depth -= 1
        if quote_depth:
            continue
        if token.type == "heading_open" and token.map is not None:
            level = int(token.tag[1:])
            title = tokens[i + 1].content
            if level <= 2 and current is not None:
                current["_end"] = token.map[0]
                current = None
            if blocked_level is not None and level <= blocked_level:
                blocked_level = None
            if _NON_BODY.match(unicodedata.normalize("NFKC", _inline(tokens[i + 1])).strip()):
                blocked_level = level if blocked_level is None else min(level, blocked_level)
            if level == 2 and blocked_level is None:
                current = {"id": f"chapter-{len(chapters) + 1:03d}", "title": title,
                           "total_cjk": 0, "unique_cjk": 0, "paragraphs": [],
                           "_start": token.map[0], "_end": len(lines)}
                chapters.append(current)
        if token.type != "paragraph_open" or blocked_level is not None:
            continue
        text = _inline(tokens[i + 1])
        key = "".join(_CJK.findall(unicodedata.normalize("NFKC", text)))
        count = len(key)
        fresh = count if key not in seen else 0
        seen.add(key)
        total += count
        unique += fresh
        paragraphs.append(text)
        if current is not None:
            current["total_cjk"] += count
            current["unique_cjk"] += fresh
            current["paragraphs"].append(text)
    for chapter in chapters:
        raw = "".join(lines[chapter.pop("_start"):chapter.pop("_end")])
        chapter["body"] = raw
        chapter["body_hash"] = _hash(raw)
    return {"total_cjk": total, "unique_cjk": unique,
            "duplicate_ratio": (total - unique) / total if total else 0.0,
            "chapters": chapters}


def editorial_target_hash(body: str, contract: dict, source_receipts=None) -> str:
    """Bind exact body, entire contract except target_hash, and receipt hash set.
    Invalid/non-JSON receipt objects raise ValueError/TypeError (validator catches).
    """
    receipts = [] if source_receipts is None else source_receipts
    if not isinstance(body, str) or not isinstance(contract, dict):
        raise ValueError("invalid target inputs")
    if not isinstance(receipts, list) or any(not isinstance(r, dict) or not r for r in receipts):
        raise ValueError("source_receipts must be nonempty JSON objects in a list")
    return _hash(_canonical({"body_hash": _hash(body),
        "contract": {k: v for k, v in contract.items() if k != "target_hash"},
        "source_receipt_hashes": sorted({_hash(_canonical(r)) for r in receipts})}))


def make_editorial_contract(body: str, *, format: str, writer_sessions: list[str],
                            revision: int, learning_objectives: list[str],
                            research_gaps=None, previous_body_hash=None,
                            source_receipts=None, issue_id=None, attempt_id=None) -> dict:
    """Generate a hash-bound DRAFT, including every measured chapter.
    Validate after generation; this helper intentionally does not manufacture
    review findings, approvals, source receipts or authenticated session IDs.
    """
    contract = {"version": "editorial-v1", "format": format,
                "writer_sessions": writer_sessions, "revision": revision,
                "learning_objectives": learning_objectives,
                "chapters": [{k: c[k] for k in ("id", "title", "body_hash")}
                             for c in editorial_metrics(body)["chapters"]],
                "research_gaps": [] if research_gaps is None else research_gaps}
    if issue_id is not None:
        contract["issue_id"] = issue_id
    if attempt_id is not None:
        contract["attempt_id"] = attempt_id
    if previous_body_hash is not None:
        contract["previous_body_hash"] = previous_body_hash
    contract["target_hash"] = editorial_target_hash(body, contract, source_receipts)
    return contract


def _https(value):
    if not _text(value) or re.search(r"[\s\x00-\x1f\x7f]", value):
        return False
    try:
        url = urlsplit(value)
        return url.scheme == "https" and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


def validate_editorial(body, contract, review=None, source_receipts=None) -> list[str]:
    """Sorted unique reason codes; [] means prerequisites only, NOT publication
    authorization. Requires a review, but cannot authenticate its claimed author.
    Existing review envelope fields are allowed for upstream receipt validation.
    """
    reasons = set()
    if not isinstance(body, str):
        return ["body.invalid"]
    metrics = editorial_metrics(body)
    if not isinstance(contract, dict):
        return ["contract.invalid"]
    required = {"version", "format", "writer_sessions", "revision", "learning_objectives", "chapters", "research_gaps", "target_hash"}
    if not required <= contract.keys() or contract.keys() - required - {"previous_body_hash", "issue_id", "attempt_id"}:
        reasons.add("contract.fields")
    for field in ("issue_id", "attempt_id"):
        if field in contract and not _text(contract[field]):
            reasons.add(f"contract.{field}")
    if contract.get("version") != "editorial-v1":
        reasons.add("contract.version")
    fmt = contract.get("format")
    if fmt not in ("book", "chapter"):
        reasons.add("contract.format")
    revision = contract.get("revision")
    if type(revision) is not int or revision < 1:
        reasons.add("contract.revision")
    previous = contract.get("previous_body_hash")
    if "previous_body_hash" in contract and (not isinstance(previous, str) or not _HASH.fullmatch(previous)):
        reasons.add("contract.previous_body_hash")
    writers = contract.get("writer_sessions")
    if (not isinstance(writers, list) or not writers or any(not _text(w) or w != w.strip() for w in writers)
            or (all(isinstance(w, str) for w in writers) and len(set(writers)) != len(writers))):
        reasons.add("contract.writer_sessions")
        writers = []
    objectives = contract.get("learning_objectives")
    if not isinstance(objectives, list) or not objectives or any(not _text(o, 10) for o in objectives):
        reasons.add("contract.learning_objectives")
    chapters = metrics["chapters"]
    expected = [{k: c[k] for k in ("id", "title", "body_hash")} for c in chapters]
    if contract.get("chapters") != expected:
        reasons.add("contract.chapters")
    if len(chapters) < (BOOK_MIN_CHAPTERS if fmt == "book" else 1):
        reasons.add("quality.chapter_count")
    if sum(c["unique_cjk"] for c in chapters) < (BOOK_MIN_CJK if fmt == "book" else CHAPTER_MIN_CJK):
        reasons.add("quality.effective_cjk")
    for c in chapters:
        if c["unique_cjk"] < (BOOK_CHAPTER_MIN_CJK if fmt == "book" else CHAPTER_MIN_CJK):
            reasons.add(f"quality.chapter_length:{c['id']}")
    if metrics["duplicate_ratio"] > MAX_DUPLICATE_RATIO:
        reasons.add("quality.duplicate_ratio")
    gaps = contract.get("research_gaps")
    gap_ids = set()
    if not isinstance(gaps, list):
        reasons.add("contract.research_gaps")
    else:
        for gap in gaps:
            if not isinstance(gap, dict):
                reasons.add("contract.research_gaps")
                continue
            gid = gap.get("id")
            if not _text(gid) or gid in gap_ids:
                reasons.add("contract.research_gaps")
            else:
                gap_ids.add(gid)
            if gap.get("state") == "open":
                reasons.add("research_gaps.open")
            if (set(gap) != {"id", "question", "state", "resolution", "source_urls"}
                    or not _text(gap.get("question"), 10) or gap.get("state") != "resolved"
                    or not _text(gap.get("resolution"), MIN_FINDING_LENGTH)
                    or not isinstance(gap.get("source_urls"), list) or not gap["source_urls"]
                    or any(not _https(u) for u in gap["source_urls"])):
                reasons.add("contract.research_gaps")
    try:
        target = editorial_target_hash(body, contract, source_receipts)
        if contract.get("target_hash") != target:
            reasons.add("contract.target_hash")
    except (ValueError, TypeError, OverflowError):
        reasons.add("contract.target_hash")
        target = None
    if not isinstance(review, dict):
        reasons.add("review.required")
        return sorted(reasons)
    if target is None or review.get("editorial_target_hash") != target:
        reasons.add("review.target_hash")
    reviewer = review.get("reviewer_session")
    if (not isinstance(reviewer, str) or not reviewer.startswith("hermes:") or not reviewer[7:].strip()
            or reviewer != reviewer.strip() or reviewer in writers):
        reasons.add("review.independence")
    if type(review.get("revision")) is not int or review.get("revision") != revision:
        reasons.add("review.revision")
    if review.get("decision") != "approved":
        reasons.add("review.decision")
    if review.get("research_gaps") != []:
        reasons.add("review.research_gaps")
    reviewed = review.get("chapters")
    if (not isinstance(reviewed, list) or len(reviewed) != len(chapters)
            or any(not isinstance(r, dict) for r in reviewed)):
        reasons.add("review.chapters")
        reviewed = []
    by_id = {c["id"]: c for c in chapters}
    used = set()
    for r in reviewed:
        rid = r.get("id")
        if not isinstance(rid, str) or rid not in by_id or rid in used:
            reasons.add("review.chapters")
            continue
        used.add(rid)
        c = by_id[rid]
        if r.get("body_hash") != c["body_hash"] or r.get("decision") != "approved":
            reasons.add(f"review.chapter:{rid}")
        checks = r.get("checks")
        for name in CHAPTER_CHECKS:
            item = checks.get(name) if isinstance(checks, dict) else None
            if not isinstance(item, dict):
                reasons.add(f"review.check:{rid}:{name}")
                continue
            quote = item.get("quote")
            if (not _text(quote, MIN_QUOTE_LENGTH) or quote not in c["body"]
                    or not any(quote in p for p in c["paragraphs"])
                    or not _text(item.get("finding"), MIN_FINDING_LENGTH)):
                reasons.add(f"review.check:{rid}:{name}")
    if used != set(by_id):
        reasons.add("review.chapters")
    book_checks = review.get("book_checks")
    for name in BOOK_CHECKS:
        check = book_checks.get(name) if isinstance(book_checks, dict) else None
        if not isinstance(check, dict) or check.get("decision") != "approved" or not _text(check.get("finding"), MIN_FINDING_LENGTH):
            reasons.add(f"review.book_check:{name}")
    return sorted(reasons)
