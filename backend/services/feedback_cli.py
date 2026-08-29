"""Machine-readable feedback digest prepare/ack CLI for the local Mac worker."""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.services.feedback import acknowledge_feedback_digest, prepare_feedback_digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="feedback-digest")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    ack = sub.add_parser("ack")
    ack.add_argument("digest_id")
    ack.add_argument("payload_hash")
    return parser


async def _run(args: argparse.Namespace) -> dict:
    if args.command == "prepare":
        return await prepare_feedback_digest()
    return await acknowledge_feedback_digest(args.digest_id, args.payload_hash)


def main() -> int:
    args = _parser().parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if result.get("status") in {
        "prepared", "delivered", "empty", "too_early", "locked"
    }:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
