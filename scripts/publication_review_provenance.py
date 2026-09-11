#!/usr/bin/env python3
"""Local trusted operator: attest an exact completed native Hermes review."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.publication_review_provenance import attest_native_review


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-key")
    init.add_argument("--private-key", type=Path, required=True)
    init.add_argument("--public-key", type=Path, required=True)
    attest = sub.add_parser("attest")
    attest.add_argument("--state-db", type=Path, default=Path.home() / ".hermes/state.db")
    attest.add_argument("--private-key", type=Path, required=True)
    attest.add_argument("--review-file", type=Path, required=True)
    attest.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.command == "init-key":
        # Never replace a pin silently. Rotation is a separate explicit action.
        if args.private_key.exists() or args.public_key.exists():
            p.error("key path already exists; refusing replacement")
        key = Ed25519PrivateKey.generate()
        private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        args.private_key.parent.mkdir(parents=True, exist_ok=True)
        args.public_key.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(args.private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(private)
        with args.public_key.open("xb") as f:
            f.write(public)
        print(json.dumps({"private_key_created": True, "public_key": str(args.public_key)}))
    else:
        if args.private_key.is_symlink() or args.private_key.stat().st_mode & 0o077:
            p.error("private key must be a non-symlink owner-only file")
        proof = attest_native_review(args.state_db, args.review_file, args.private_key.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as f:
            f.write(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"proof": str(args.output), "reviewer_session": proof["reviewer_session"],
                          "editorial_target_hash": proof["editorial_target_hash"]}))


if __name__ == "__main__":
    main()
