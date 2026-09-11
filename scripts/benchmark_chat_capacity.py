#!/usr/bin/env python3
"""Run bounded, authenticated answer-level chat capacity batches."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import statistics
import time
import urllib.request
import uuid


def _one(url: str, token: str, timeout: float) -> dict[str, object]:
    request_id = f"capacity-{uuid.uuid4().hex}"
    body = json.dumps({
        "question": "只回答 CAPACITY_OK",
        "session_id": request_id,
        "request_id": request_id,
    }).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    first_event = None
    done = False
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw in response:
                if raw.startswith(b"data:"):
                    first_event = first_event or time.monotonic()
                    try:
                        done = json.loads(raw[5:]).get("type") == "done" or done
                    except (json.JSONDecodeError, AttributeError):
                        pass
        error = "" if done else "missing_done"
    except Exception as exc:
        error = type(exc).__name__
    ended = time.monotonic()
    return {
        "ok": not error,
        "error": error,
        "ttft_ms": round(((first_event or ended) - started) * 1000, 1),
        "total_ms": round((ended - started) * 1000, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--concurrency", default="1,4,8,16")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    tokens = [item for item in os.environ.get("QUANTUM_E2E_TOKENS", "").split(",") if item]
    if not tokens:
        parser.error("QUANTUM_E2E_TOKENS is required")
    report = []
    for count in (int(item) for item in args.concurrency.split(",")):
        with ThreadPoolExecutor(max_workers=count) as pool:
            results = list(pool.map(
                lambda index: _one(args.url, tokens[index % len(tokens)], args.timeout),
                range(count),
            ))
        totals = sorted(float(item["total_ms"]) for item in results)
        report.append({
            "concurrency": count,
            "succeeded": sum(bool(item["ok"]) for item in results),
            "failed": sum(not bool(item["ok"]) for item in results),
            "median_ms": round(statistics.median(totals), 1),
            "p95_ms": totals[min(len(totals) - 1, int(len(totals) * 0.95))],
            "errors": sorted({str(item["error"]) for item in results if item["error"]}),
        })
    print(json.dumps({"batches": report}, ensure_ascii=False, sort_keys=True))
    return 0 if all(not item["failed"] for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
