"""Build a review candidate for the existing publication store; never publish it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from backend.services.knowledge_publication_store import (
    PublicationError, public_source_index_review_hash, render_public_source_index, validate_public_source_index,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _json(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise PublicationError(f"invalid evidence file: {path}")
    data = path.read_bytes()
    try:
        value = json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"invalid evidence JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PublicationError(f"evidence must be an object: {path}")
    return value, _hash(data)


def load_candidate(package: Path) -> tuple[dict[str, Any], Path, list[tuple[str, Path]]]:
    if package.is_symlink() or not package.is_dir():
        raise PublicationError("invalid public candidate package")
    package = package.resolve()
    manifest, _ = _json(package / "manifest.json")
    if (manifest.get("schema_version") != "follow-builders.public-candidate.v1"
            or manifest.get("state") != "pending_independent_content_review"):
        raise PublicationError("invalid public candidate manifest")
    bundle_path = (package / str(manifest.get("bundle") or "")).resolve()
    if package not in bundle_path.parents:
        raise PublicationError("public candidate bundle escaped its package")
    bundle, bundle_hash = _json(bundle_path)
    if bundle_hash != manifest.get("bundle_sha256"):
        raise PublicationError("public candidate bundle changed")
    body = (package / str(manifest.get("body") or "")).resolve()
    if package not in body.parents or body.is_symlink() or not body.is_file() or _hash(body.read_bytes()) != manifest.get("body_sha256"):
        raise PublicationError("public candidate body is missing, escaped, or changed")
    review_request = (package / str(manifest.get("review_request") or "")).resolve()
    if (package not in review_request.parents or review_request.is_symlink() or not review_request.is_file()
            or _hash(review_request.read_bytes()) != manifest.get("review_request_sha256")):
        raise PublicationError("public candidate review request is missing, escaped, or changed")
    records = []
    for receipt in manifest.get("record_receipts") or []:
        if not isinstance(receipt, dict) or set(receipt) != {"path", "kind", "sha256"}:
            raise PublicationError("invalid public candidate record receipt")
        path = (package / receipt["path"]).resolve()
        if (package not in path.parents or path.is_symlink() or not path.is_file()
                or receipt["kind"] not in {"public_source_metadata", "public_roster_metadata"}
                or _hash(path.read_bytes()) != receipt["sha256"]):
            raise PublicationError("public candidate record is missing, escaped, or changed")
        records.append((receipt["kind"], path))
    expected = bundle.get("source_index", {}).get("expected_sources", 0) + bundle.get("source_index", {}).get("expected_authorities", 0)
    if len(records) != expected:
        raise PublicationError("public candidate record count mismatch")
    return bundle, body, records


def build_candidate(source_root: Path, output: Path, admission_path: Path, source_audit_path: Path,
                    scope_path: Path, *, expected_sources: int, expected_authorities: int) -> dict[str, Any]:
    source_root = source_root.resolve()
    db_path = source_root / "data/follow_builders.sqlite3"
    if source_root.is_symlink() or db_path.is_symlink() or not db_path.is_file():
        raise PublicationError("invalid Follow Builders source database")
    admission, admission_hash = _json(admission_path)
    source_audit, source_audit_hash = _json(source_audit_path)
    scope, scope_hash = _json(scope_path)
    if (admission.get("decision") != "CONDITIONAL_PUBLIC_METADATA_INDEX_ONLY_NOT_FINAL_PUBLICATION_APPROVAL"
            or admission.get("input_evidence", {}).get("source_audit", {}).get("sha256") != source_audit_hash
            or source_audit.get("schema_version") != "follow-builders.source-audit.v1"):
        raise PublicationError("public admission evidence is missing or unbound")
    admitted_sources = {item.get("source_id"): item for item in admission.get("sources", []) if isinstance(item, dict)}
    admitted_roster = {item.get("roster_id"): item for item in admission.get("roster", []) if isinstance(item, dict)}
    scoped_sources, scoped_people = scope.get("sources"), scope.get("people")
    if (not isinstance(scoped_sources, list) or len(scoped_sources) != expected_sources
            or not isinstance(scoped_people, list) or len(scoped_people) != expected_authorities
            or set(admitted_sources) != {item.get("id") for item in scoped_sources}
            or set(admitted_roster) != {item.get("id") for item in scoped_people}):
        raise PublicationError("explicit public candidate scope cardinality mismatch")

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        source_ids = [item["id"] for item in scoped_sources]
        roster_ids = [item["id"] for item in scoped_people]
        source_rows = {row["id"]: dict(row) for row in connection.execute(
            f"SELECT id,canonical_url,title,author,published,kind FROM sources WHERE id IN ({','.join('?' * len(source_ids))})",
            source_ids,
        )}
        people_rows = {row["id"]: dict(row) for row in connection.execute(
            f"SELECT id,handle,display_name,organization_or_role,official_entry FROM people WHERE id IN ({','.join('?' * len(roster_ids))})",
            roster_ids,
        )}
        live_source_ids = [row[0] for row in connection.execute("SELECT id FROM sources ORDER BY id")]
        live_authority_ids = [row[0] for row in connection.execute("SELECT id FROM people ORDER BY id")]
    finally:
        connection.close()
    if source_rows != {item["id"]: item for item in scoped_sources}:
        raise PublicationError("source database no longer matches frozen source scope")
    if any(any(people_rows[item["id"]].get(key) != item.get(key) for key in ("id", "handle", "display_name", "organization_or_role"))
           for item in scoped_people):
        raise PublicationError("source database no longer matches frozen roster scope")

    excluded_source_ids = [item for item in live_source_ids if item not in set(source_ids)]
    excluded_authority_ids = [item for item in live_authority_ids if item not in set(roster_ids)]
    counts = admission.get("counts", {})
    if (excluded_source_ids != counts.get("out_of_scope_live_source_ids")
            or len(live_source_ids) != counts.get("live_database_source_count")
            or len(live_authority_ids) != counts.get("live_database_roster_count")):
        raise PublicationError("live database no longer matches admission audit scope")

    sources = []
    for scoped in scoped_sources:
        admitted = admitted_sources[scoped["id"]]
        candidate = admitted["public_metadata_candidate"]
        if _hash(candidate) != admitted.get("evidence_binding", {}).get("metadata_sha256"):
            raise PublicationError(f"admission source hash mismatch: {scoped['id']}")
        record = {
            **candidate,
            "book_id": "follow-builders-public-source-" + hashlib.sha256(candidate["literal_url"].encode()).hexdigest()[:24],
            "admission_status": admitted["admission_status"],
            "specific_qualifications": admitted.get("specific_qualifications") or [],
            "admission_metadata_sha256": admitted["evidence_binding"]["metadata_sha256"],
        }
        record["metadata_sha256"] = _hash({key: value for key, value in record.items() if key not in {"book_id", "metadata_sha256"}})
        sources.append(record)
    authorities = []
    for scoped in scoped_people:
        admitted = admitted_roster[scoped["id"]]
        candidate = admitted["public_metadata_candidate"]
        if _hash(candidate) != admitted.get("evidence_binding", {}).get("metadata_sha256"):
            raise PublicationError(f"admission roster hash mismatch: {scoped['id']}")
        record = {**candidate, "admission_status": admitted["admission_status"],
                  "specific_qualifications": admitted.get("specific_qualifications") or [],
                  "admission_metadata_sha256": admitted["evidence_binding"]["metadata_sha256"]}
        record["metadata_sha256"] = _hash({key: value for key, value in record.items() if key != "metadata_sha256"})
        authorities.append(record)
    selection_scope = {
        "observed_at": admission["audited_at"],
        "selection_basis": "frozen_explicit_scope_not_latest_live_database",
        "selected_source_ids": source_ids, "selected_authority_ids": roster_ids,
        "excluded_live_source_ids": excluded_source_ids, "excluded_live_authority_ids": excluded_authority_ids,
    }
    selection_scope["selection_scope_sha256"] = _hash(selection_scope)
    index = validate_public_source_index({
        "collection_id": "follow-builders-public", "collection_title": "Follow Builders 公开来源索引",
        "admission_decision": admission["decision"], "audit_sha256": admission_hash,
        "expected_sources": expected_sources, "expected_authorities": expected_authorities,
        "selection_scope": selection_scope,
        "sources": sources, "authorities": authorities,
    })
    body = render_public_source_index(index)
    body_hash = _hash(body.encode())
    review_hash = public_source_index_review_hash(body_hash, index)
    bundle = {
        "series_id": "follow-builders-sources", "source_publication_id": "follow-builders-public-v1",
        "issue_date": admission["audited_at"][:10], "title": index["collection_title"],
        "summary": f"{expected_sources} 条外部来源元数据与 {expected_authorities} 条未核验关注名册；不含第三方全文。",
        "author": "As-stored source metadata", "institution": "Follow Builders",
        "authored_by": "source_metadata", "content_kind": "source_index", "rights_scope": "metadata_link_only",
        "rights_reference": "", "rights_valid_until": None, "rights_perpetual": False,
        "rights_evidence": [], "rights_evidence_status": "not_applicable_metadata_only", "owner_policy_id": "",
        "release_at": admission["audited_at"], "state": "staged", "is_test": False,
        "source_snapshot_hash": "", "source_receipts": [], "body_hash": body_hash, "body_receipt": {},
        "references": [{"title": item["recorded_title"], "url": item["literal_url"]} for item in sources],
        "wiki_references": [], "assets": [], "completeness": "metadata_only",
        "review": {"content_hash": "", "decision": "pending", "reviewed_by": "", "reviewed_at": "", "receipt": None},
        "execution_claim": "not_run", "execution_evidence": [],
        "warnings": ["metadata index only; no full-text redistribution approval", "roster identities are not independently verified"],
        "source_index": index, "source_index_review_hash": review_hash,
    }
    files = [(f"records/source-{item['source_id']:03d}.json", "public_source_metadata", item) for item in sources]
    files += [(f"records/roster-{item['roster_id']:03d}.json", "public_roster_metadata", item) for item in authorities]
    categories = [item.get("local_evidence_category") for item in admission.get("sources", [])]
    bundle_bytes = _canonical(bundle) + b"\n"
    review_request_bytes = _canonical({"content_hash": review_hash, "decision": "pending"}) + b"\n"
    manifest = {"schema_version": "follow-builders.public-candidate.v1", "state": "pending_independent_content_review",
                "bundle": "bundle.json", "body": "body.md", "review_request": "review-request.json",
                "bundle_sha256": _hash(bundle_bytes), "body_sha256": body_hash,
                "review_request_sha256": _hash(review_request_bytes), "source_index_review_hash": review_hash,
                "source_audit_sha256": source_audit_hash, "scope_sha256": scope_hash,
                "content_boundary": {"public_fulltext_approvals": admission.get("counts", {}).get("fulltext_approvals"),
                                     "local_snapshot_inventory_not_public_content": {
                                         "apparent_html_articles": categories.count("readable_article_snapshot"),
                                         "pdf_reports": categories.count("readable_report_pdf"),
                                         "landing_pages": sum(categories.count(name) for name in (
                                             "course_landing_index", "course_series_landing", "course_unreadable_summary")),
                                     }, "complete_course_verified": False,
                                     "fulltext_gap": "all records are metadata/link only pending real redistribution-rights evidence"},
                "record_receipts": [{"path": path, "kind": kind, "sha256": item["metadata_sha256"]} for path, kind, item in files]}
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        (temporary / "records").mkdir()
        (temporary / "body.md").write_text(body, encoding="utf-8")
        (temporary / "bundle.json").write_bytes(bundle_bytes)
        (temporary / "review-request.json").write_bytes(review_request_bytes)
        for path, _, item in files:
            (temporary / path).write_bytes(_canonical({key: value for key, value in item.items() if key not in {"book_id", "metadata_sha256"}}))
        (temporary / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
        if output.exists():
            if output.is_symlink() or not output.is_dir() or (output / "manifest.json").read_bytes() != (temporary / "manifest.json").read_bytes():
                raise PublicationError("candidate output already exists with different content")
            load_candidate(output)
            shutil.rmtree(temporary)
        else:
            os.replace(temporary, output)
            temporary = None
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
    return {"output": str(output), "sources": len(sources), "authorities": len(authorities),
            "body_sha256": body_hash, "state": manifest["state"], "record_receipts": len(files)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a pending Follow Builders public metadata-index candidate")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--admission-audit", type=Path, required=True)
    parser.add_argument("--source-audit", type=Path, required=True)
    parser.add_argument("--scope-file", type=Path, required=True)
    parser.add_argument("--expected-sources", type=int, required=True)
    parser.add_argument("--expected-authorities", type=int, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_candidate(args.source_root, args.output, args.admission_audit, args.source_audit,
                                     args.scope_file, expected_sources=args.expected_sources,
                                     expected_authorities=args.expected_authorities), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
