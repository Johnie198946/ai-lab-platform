#!/usr/bin/env python3
"""Explicit file-only relay for the existing writer/reviewer/no-agent issuer.

No model calls, scheduler, session writes, SCP, or release operation. Manifests
must be named draft-manifest.json or *.manifest.json for root discovery. Initial items use `prepared`;
all input hashes are required (bundle_sha256 is added when initially absent).
Files are limited to 2 MiB each (24 KiB transport chunks), 64 evidence files/item
and 64 items/manifest. The server independently enforces its body size policy.
Transport and signing credentials are operator-owned, never manifest fields.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sqlite3
import sys
import uuid

try:
    from scripts import publication_release_remote as transport
except ImportError:
    import publication_release_remote as transport

VERSION = "editorial-workflow-v2"
LIMIT = 2 * 1024 * 1024
CHUNK = 24 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {"bundle_file", "bundle_sha256", "body_file", "body_sha256", "source_files",
          "rights_files", "execution_files", "review_file", "proof_file", "status",
          "batch", "quality_contract", "receipt", "error"}
STATES = {"prepared", "await_review", "staged", "rejected", "blocked"}
GROUPS = {"source_files": "--source-file", "rights_files": "--rights-file", "execution_files": "--execution-file"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def local_path(base, value, *, output=False):
    if not isinstance(value, str) or not value:
        raise ValueError("explicit local path required")
    path = Path(value).expanduser()
    path = path if path.is_absolute() else base / path
    if ".." in path.parts or not path.is_relative_to(base):
        raise ValueError("file escapes manifest directory")
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError("symlink forbidden")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("regular unlinked-alias-free file required")
        if info.st_size > LIMIT:
            raise ValueError("file exceeds 2 MiB limit")
    elif not output or not path.parent.is_dir():
        raise ValueError("file missing")
    return path


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("regular file required")
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("file exceeds 2 MiB limit")
    return raw


def save(path, value):
    raw = encoded(value)
    if len(raw) > LIMIT:
        raise ValueError("JSON exceeds 2 MiB limit")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_manifest(path):
    path = Path(path).expanduser().absolute()
    if path.name != "draft-manifest.json" and not path.name.endswith(".manifest.json"):
        raise ValueError("manifest must be draft-manifest.json or *.manifest.json")
    local_path(path.parent, str(path))
    value = json.loads(read(path))
    if not isinstance(value, dict) or set(value) != {"version", "items"} or value["version"] != VERSION:
        raise ValueError("explicit editorial-workflow-v2 manifest required")
    if not isinstance(value["items"], list) or not 1 <= len(value["items"]) <= 64:
        raise ValueError("invalid manifest items")
    paths = set()
    outputs = set()
    for item in value["items"]:
        if not isinstance(item, dict) or set(item) - FIELDS or item.get("status") not in STATES:
            raise ValueError("unknown manifest fields or invalid status")
        inputs = [(item.get("bundle_file"), item.get("bundle_sha256")),
                  (item.get("body_file"), item.get("body_sha256"))]
        for group in GROUPS:
            entries = item.get(group)
            if not isinstance(entries, list) or len(entries) > 64:
                raise ValueError("explicit bounded evidence lists required")
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {"kind", "path", "sha256"} or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", entry.get("kind", "")):
                    raise ValueError("invalid evidence entry")
                inputs.append((entry["path"], entry["sha256"]))
        for index, (name, digest) in enumerate(inputs):
            file = local_path(path.parent, name)
            if index == 0 and digest is None and item["status"] == "prepared":
                digest = item["bundle_sha256"] = sha(read(file))
            if not isinstance(digest, str) or not HASH.fullmatch(digest) or sha(read(file)) != digest:
                raise ValueError("input hash mismatch or missing hash")
            if file == path or file in outputs:
                raise ValueError("input overlaps manifest or another output")
            paths.add(file)
        for field in ("review_file", "proof_file"):
            output = local_path(path.parent, item.get(field), output=True)
            if output == path or output in paths:
                raise ValueError("review/proof output overlaps input or other output")
            if item["status"] == "prepared" and output.exists():
                raise ValueError("review/proof must be fresh output paths")
            paths.add(output)
            outputs.add(output)
        if item.get("batch") and not re.fullmatch(r"[0-9a-f]{32}", item["batch"]):
            raise ValueError("invalid intake batch")
        bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
        if bundle.get("body_hash") != item["body_sha256"]:
            raise ValueError("bundle body hash mismatch")
        if item["status"] != "prepared" and bundle.get("quality_contract") != item.get("quality_contract"):
            raise ValueError("immutable contract mismatch")
    return path, value


# Uploaded bytes are immutable and confined to a unique private intake batch.
# Existing matching content is an idempotent retry, conflicting bytes fail closed.
UPLOAD = '''import os,sys,base64,hashlib,json,stat,tempfile
from pathlib import Path
batch,digest,ext,mode,payload=sys.argv[1:]
def valid(s,n):
 return isinstance(s,str) and len(s)==n and all(c in '0123456789abcdef' for c in s)
assert valid(batch,32) and valid(digest,64)
assert ext in ('.json','.md','.bin')
base=Path('/app/data/runtime/publication-intake')
for p in [*reversed(base.parents),base,base/batch]:
 if not p.exists(): p.mkdir(mode=0o700)
 assert not p.is_symlink() and p.is_dir()
def read(p,limit):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno())
  assert stat.S_ISREG(s.st_mode) and s.st_nlink==1,'intake conflict'
  raw=f.read(limit+1)
 assert len(raw)<=limit
 return raw
if mode=='bytes':
 raw=base64.b64decode(payload,validate=True)
 assert len(raw)<=24576
else:
 assert mode=='chunks'
 chunks=json.loads(payload)
 assert isinstance(chunks,list) and 1<=len(chunks)<=86
 parts=[]
 for h in chunks:
  assert valid(h,64)
  part=read(base/batch/(h+'.bin'),24576)
  assert hashlib.sha256(part).hexdigest()==h
  parts.append(part)
 raw=b''.join(parts)
assert len(raw)<=2097152 and hashlib.sha256(raw).hexdigest()==digest
p=base/batch/(digest+ext)
fd,tmp=tempfile.mkstemp(prefix='.upload-',dir=base/batch)
try:
 with os.fdopen(fd,'wb') as f:
  f.write(raw);f.flush();os.fsync(f.fileno())
 try: os.link(tmp,p,follow_symlinks=False)
 except FileExistsError: pass
finally:
 os.unlink(tmp)
assert read(p,2097152)==raw,'intake conflict'
print(json.dumps({'ok':True,'result':{'path':str(p),'sha256':digest}}))
'''


class Remote:
    def __init__(self, identity, known_hosts):
        self.identity, self.known_hosts = identity, known_hosts

    def call(self, words):
        result = transport._ssh(self.identity, self.known_hosts, shlex.join(words))
        if result.returncode:
            raise ValueError(f"remote command failed (exit {result.returncode})")
        ok, value = transport._json(result.stdout, "editorial")
        if ok is not True:
            raise ValueError("remote editorial admission failed")
        return value

    def operator(self, *args):
        return self.call([*transport.OPERATOR, *map(str, args)])

    def upload(self, batch, raw, ext):
        digest = sha(raw)
        if len(raw) > LIMIT:
            raise ValueError("upload exceeds limit")
        if len(raw) > CHUNK:
            chunks = []
            for offset in range(0, len(raw), CHUNK):
                chunk = raw[offset:offset + CHUNK]
                self.upload(batch, chunk, ".bin")
                chunks.append(sha(chunk))
            mode, payload = "chunks", json.dumps(chunks)
        else:
            mode, payload = "bytes", base64.b64encode(raw).decode()
        value = self.call([*transport.OPERATOR[:12], "-c", UPLOAD, batch, digest, ext, mode, payload])
        expected = f"/app/data/runtime/publication-intake/{batch}/{digest}{ext}"
        if value != {"path": expected, "sha256": digest}:
            raise ValueError("upload readback mismatch")
        return expected


def arguments(remote, base, item, bundle, review=None, proof=None):
    batch = item["batch"]
    args = [remote.upload(batch, encoded(bundle), ".json"), "--body-file",
            remote.upload(batch, read(local_path(base, item["body_file"])), ".md")]
    for group, flag in GROUPS.items():
        for entry in item[group]:
            args += [flag, entry["kind"] + "=" + remote.upload(batch, read(local_path(base, entry["path"])), ".bin")]
    if review is not None:
        args += ["--review-file", remote.upload(batch, review, ".json")]
    if proof is not None:
        args += ["--proof-file", remote.upload(batch, encoded(proof), ".json")]
    return args


def attempt(remote, contract, states):
    status = remote.operator("status")
    rows = status.get("editorial_attempts")
    if not isinstance(rows, list):
        raise ValueError("status lacks editorial attempts")
    rows = [r for r in rows if r.get("issue_id") == contract["issue_id"]]
    if not rows:
        raise ValueError("attempt readback missing")
    latest = max(rows, key=lambda r: r["revision"])
    if (latest.get("quality_contract") != contract or latest.get("attempt_id") != contract["attempt_id"]
            or latest.get("revision") != contract["revision"] or latest.get("target_hash") != contract["target_hash"]
            or latest.get("state") not in states):
        raise ValueError("attempt ID/hash/state readback mismatch")
    return latest


def prepare(path, remote):
    path, value = load_manifest(path)
    for item in value["items"]:
        if item["status"] != "prepared":
            continue
        item.setdefault("batch", uuid.uuid4().hex)
        save(path, value)  # Stable upload namespace even after transport interruption.
        bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
        result = remote.operator("prepare-editorial", *arguments(remote, path.parent, item, bundle))
        contract = result.get("quality_contract")
        if not isinstance(contract, dict) or any(key not in contract for key in ("issue_id", "revision", "attempt_id", "target_hash", "writer_sessions")):
            raise ValueError("server contract missing")
        receipt = attempt(remote, contract, {"await_review"})
        # The operator's ingest receipt IDs are deterministic. Reconstruct only
        # after successful intake, then verify the exact server target binding.
        for group, field in (("source_files", "source_receipts"), ("rights_files", "rights_evidence"), ("execution_files", "execution_evidence")):
            if item[group]:
                bundle[field] = [{"artifact_id": f"receipt-{e['kind']}-{e['sha256']}", "sha256": e["sha256"], "kind": e["kind"]} for e in item[group]]
        bundle["source_snapshot_hash"] = sha("\n".join(sorted(e["sha256"] for e in bundle.get("source_receipts", []))).encode())
        bundle["quality_contract"] = contract
        verify_target(bundle, read(local_path(path.parent, item["body_file"])).decode())
        # Publish a new frozen bundle pointer and manifest atomically; never
        # leave an old manifest hashing newly overwritten input bytes on crash.
        frozen = local_path(path.parent, "prepared-" + item["batch"] + ".json", output=True)
        if frozen.exists() and read(frozen) != encoded(bundle):
            raise ValueError("prepared bundle conflict")
        save(frozen, bundle)
        item.update(bundle_file=frozen.name, quality_contract=contract, bundle_sha256=sha(encoded(bundle)), status="await_review", receipt=receipt)
        save(path, value)
    return {"manifest": str(path), "statuses": [i["status"] for i in value["items"]]}


def manifests(root):
    root = Path(root).expanduser().absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("manifest root must be a real directory")
    return sorted(set(root.rglob("*.manifest.json")) | set(root.rglob("draft-manifest.json")))


def verify_target(bundle, manuscript):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.services.publication_editorial import editorial_target_hash
    contract = bundle["quality_contract"]
    if editorial_target_hash(manuscript, contract, bundle.get("source_receipts", [])) != contract["target_hash"]:
        raise ValueError("full manuscript/contract/source receipt target mismatch")


def review_input(root, remote):
    for path in manifests(root):
        path, value = load_manifest(path)
        for item in value["items"]:
            if item["status"] != "await_review":
                continue
            contract = item["quality_contract"]
            attempt(remote, contract, {"await_review"})
            if local_path(path.parent, item["review_file"], output=True).exists():
                continue
            bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
            manuscript = read(local_path(path.parent, item["body_file"])).decode()
            verify_target(bundle, manuscript)
            request = {"manuscript": manuscript, "quality_contract": contract, "source_receipts": bundle.get("source_receipts", []), "purpose": "publication_editorial_review", "owner": "local_owner", "profile": "default",
                       **{k: contract[k] for k in ("issue_id", "revision", "attempt_id", "writer_sessions")},
                       "editorial_target_hash": contract["target_hash"]}
            files: dict = {key: str(local_path(path.parent, item[key], output=key == "review_file")) for key in ("bundle_file", "body_file", "review_file")}
            files.update({group: [{**entry, "path": str(local_path(path.parent, entry["path"]))} for entry in item[group]] for group in GROUPS})
            return encoded({"manifest": str(path), "read_only_inputs": files, "instruction": "Read inputs only; write only review_file. End with pure JSON {publication_review_result:{issue_id,revision,attempt_id,editorial_target_hash,review_file_hash,reviewer_session,decision}}; no tools after final. Do not stage or sign."}).decode() + "\nPUBLICATION_REVIEW_REQUEST\n" + encoded(request).decode() + "\nEND_PUBLICATION_REVIEW_REQUEST"
    return json.dumps({"status": "no_await_review"})


def native_attest(db, review, key):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.services.publication_review_provenance import attest_native_review
    secure = transport._secure_file(str(key), "editorial signing key", private=True)
    try:
        return attest_native_review(Path(db).expanduser(), review, Path(secure).read_bytes())
    except sqlite3.Error as exc:
        raise ValueError("native review database unavailable or invalid") from exc


def native_running(db, review):
    sid = review.get("reviewer_session", "")
    if not isinstance(sid, str) or not sid.startswith("hermes:"):
        return False
    try:
        with sqlite3.connect(Path(db).expanduser().resolve().as_uri() + "?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT ended_at FROM sessions WHERE id=?", (sid[7:],)).fetchone()
        return row is not None and row[0] is None
    except sqlite3.Error as exc:
        raise ValueError("native review database unavailable or invalid") from exc


def finalize(root, remote, *, db=Path("~/.hermes/state.db"), key=Path("~/.hermes/config/publication-editorial-private.pem"), attest=native_attest):
    results = []
    for path in manifests(root):
        path, value = load_manifest(path)
        for item in value["items"]:
            if item["status"] == "blocked":
                raise ValueError("blocked editorial item requires operator repair")
            if item["status"] != "await_review":
                continue
            review_path = local_path(path.parent, item["review_file"], output=True)
            if not review_path.exists():
                results.append({"status": "pending", "manifest": str(path)})
                continue
            try:
                raw = read(review_path)
                review = json.loads(raw)
                try:
                    proof = attest(db, review_path, key)
                except ValueError as exc:
                    if str(exc) == "native review is not completed" and native_running(db, review):
                        results.append({"status": "pending", "manifest": str(path)})
                        continue
                    raise
                if read(review_path) != raw:
                    raise ValueError("review changed during attestation")
                c = item["quality_contract"]
                expected = {"issue_id": c["issue_id"], "revision": c["revision"], "attempt_id": c["attempt_id"],
                            "editorial_target_hash": c["target_hash"], "writer_sessions": c["writer_sessions"],
                            "review_file_hash": sha(raw), "decision": review.get("decision")}
                if any(proof.get(k) != v for k, v in expected.items()) or proof.get("decision") not in {"approved", "rejected"}:
                    raise ValueError("signed proof does not bind manifest")
                # Revalidate every frozen input after native DB work and before upload.
                load_manifest(path)
                proof_path = local_path(path.parent, item["proof_file"], output=True)
                if proof_path.exists() and read(proof_path) != encoded(proof):
                    raise ValueError("proof output conflict")
                save(proof_path, proof)
                bundle = json.loads(read(local_path(path.parent, item["bundle_file"])))
                current = attempt(remote, c, {"await_review", "approved", "rejected"})
                if current["state"] == "await_review":
                    remote.operator("record-editorial-review", *arguments(remote, path.parent, item, bundle, raw, proof))
                receipt = attempt(remote, c, {review["decision"]})
                if receipt.get("review_hash") != sha(raw):
                    raise ValueError("recorded review hash mismatch")
                if review["decision"] == "approved":
                    bundle["review"] = {"content_hash": review["content_hash"], "decision": "approved", "reviewed_by": review["reviewer_session"], "reviewed_at": review["reviewed_at"], "receipt": None}
                    staged = remote.operator("stage", *arguments(remote, path.parent, item, bundle, raw, proof))
                    status = remote.operator("status")
                    matches = [r for r in status.get("items", []) if r.get("edition_id") == staged.get("edition_id")]
                    if len(matches) != 1 or not staged.get("edition_id"):
                        raise ValueError("stage readback missing")
                    row = matches[0]
                    if (row.get("state") not in {"staged", "scheduled", "published"} or row.get("content_hash") != item["body_sha256"]
                            or row.get("bundle", {}).get("quality_contract") != c or row.get("issue_id") != c["issue_id"]):
                        raise ValueError("stage ID/hash/state readback mismatch")
                    receipt = {"attempt": receipt, "edition": row}
                item.update(status="staged" if review["decision"] == "approved" else "rejected", receipt=receipt)
                item.pop("error", None)
                save(path, value)
                results.append({"status": item["status"], "manifest": str(path), "attempt_id": c["attempt_id"]})
            except Exception as exc:
                # Keep await_review for deterministic readback/retry after uncertain SSH writes.
                item["error"] = str(exc)
                save(path, value)
                raise
    return {"items": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-file")
    parser.add_argument("--known-hosts-file")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare").add_argument("--manifest", required=True, type=Path)
    for name in ("review-input", "finalize"):
        sub.add_parser(name).add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        remote = Remote(*transport._trust(args))
        # Existing Cron jobs are serial; flock also rejects accidental overlap.
        directory = args.manifest.expanduser().absolute().parent if args.action == "prepare" else args.root.expanduser().absolute()
        lock = directory / ".publication-editorial.lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = prepare(args.manifest, remote) if args.action == "prepare" else review_input(args.root, remote) if args.action == "review-input" else finalize(args.root, remote)
        print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False), end="" if isinstance(result, str) else "\n")
        return 0
    except Exception as exc:
        print(f"publication editorial failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
