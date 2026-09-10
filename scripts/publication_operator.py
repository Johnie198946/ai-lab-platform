#!/usr/bin/env python3
"""Trusted, deterministic operator interface for Quantumn serial editions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backend.services.knowledge_publication_store import PublicationError, PublicationStore, receipt_set_hash
from backend.services.follow_builders_publication import load_candidate


def _file(value: str) -> tuple[str, Path]:
    try:
        kind, path = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected KIND=/absolute/path") from exc
    return kind, Path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate frozen Quantumn publication editions")
    parser.add_argument("--root", type=Path, help="publication runtime directory")
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("bundle", type=Path)
    stage.add_argument("--body-file", type=Path, help="reviewed body bytes; never stored in the bundle path")
    stage.add_argument("--source-file", action="append", type=_file, default=[])
    stage.add_argument("--rights-file", action="append", type=_file, default=[])
    stage.add_argument("--review-file", type=Path)
    stage.add_argument("--execution-file", action="append", type=_file, default=[])
    source_index = commands.add_parser("stage-source-index")
    source_index.add_argument("package", type=Path)
    source_index.add_argument("--review-file", type=Path)
    status = commands.add_parser("status")
    status.add_argument("--publication-id")
    commands.add_parser("release-due")
    withdraw = commands.add_parser("withdraw")
    withdraw.add_argument("publication_id")
    args = parser.parse_args()
    store = PublicationStore(args.root)
    try:
        if args.command == "stage-source-index":
            bundle, body_file, record_files = load_candidate(args.package)
            bundle["body"] = body_file.read_text(encoding="utf-8")
            bundle["body_receipt"] = store.ingest_file(body_file, "publication_body")
            bundle["source_receipts"] = [store.ingest_file(path, kind) for kind, path in record_files]
            bundle["source_snapshot_hash"] = receipt_set_hash(bundle["source_receipts"])
            if args.review_file:
                review = json.loads(args.review_file.read_text(encoding="utf-8"))
                bundle["review"] = {**review, "receipt": store.ingest_file(args.review_file, "content_review")}
            vault = Path(os.environ.get("AI_LAB_HOME", Path(__file__).resolve().parent.parent / "data" / "vault"))
            result = store.stage(bundle, vault=vault)
        elif args.command == "stage":
            bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
            if args.body_file:
                bundle["body"] = args.body_file.read_text(encoding="utf-8")
                bundle["body_receipt"] = store.ingest_file(args.body_file, "publication_body")
                bundle["body_hash"] = bundle["body_receipt"]["sha256"]
            if args.source_file:
                bundle["source_receipts"] = [store.ingest_file(path, kind) for kind, path in args.source_file]
                bundle["source_snapshot_hash"] = receipt_set_hash(bundle["source_receipts"])
            if args.rights_file:
                bundle["rights_evidence"] = [store.ingest_file(path, kind) for kind, path in args.rights_file]
            if args.execution_file:
                bundle["execution_evidence"] = [store.ingest_file(path, kind) for kind, path in args.execution_file]
            if args.review_file:
                bundle["review"]["receipt"] = store.ingest_file(args.review_file, "content_review")
            vault = Path(os.environ.get("AI_LAB_HOME", Path(__file__).resolve().parent.parent / "data" / "vault"))
            result = store.stage(bundle, vault=vault)
        elif args.command == "status":
            result = store.status_report(args.publication_id)
        elif args.command == "release-due":
            result = store.release_due()
        else:
            result = store.withdraw(args.publication_id)
    except (OSError, json.JSONDecodeError, PublicationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    ok = args.command != "release-due" or result["status"] == "ok"
    print(json.dumps({"ok": ok, "result": result}, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
