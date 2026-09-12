"""Read-only projection of sole-Writer evidence, never a second writer/store."""
from pathlib import Path
import fcntl
import hashlib
import importlib.util
import json
import os
import sys
import threading

_LOAD_LOCK = threading.RLock()


def _writer(pipeline_path):
    path = Path(pipeline_path).resolve(strict=True).with_name("wiki_contract_apply.py")
    name = "_research_status_writer_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    with _LOAD_LOCK:
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ValueError("writer_module_unavailable")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(name, None)
                raise
        return sys.modules[name]


def read_compilation(vault, pipeline_path, receipt, revision, task_id):
    """Only called after parent authorization and exact deposit receipt validation.

    Scan contract metadata, not the raw corpus; read under the Writer's shared
    lock, fail closed on recovery, malformed evidence, scan limits or contention.
    No durable state is mutated, including the stored writer-trigger intent.
    """
    result = {"verified": False, "state": "not_verified", "targets": []}
    try:
        root = Path(vault).resolve(strict=True)
        writer = _writer(pipeline_path)
        def read(path):
            relative = Path(path).relative_to(root)
            return writer.read_stable_bytes(root, relative)
        lock = root / "raw/.contract-apply.lock"
        if lock.is_symlink():
            raise ValueError("unsafe_lock")
        with open(lock, "rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            journal = root / writer.TRANSACTION_DIR / "journal.json"
            if journal.exists() and json.loads(read(journal)).get("state") != "committed":
                raise ValueError("writer_recovery_required")
            raw = Path(receipt["raw_path"])
            if raw.is_absolute():
                raw = raw.relative_to(root)
            raw_text = read(root / raw)
            if hashlib.sha256(raw_text).hexdigest() != receipt["sha256"]:
                raise ValueError("source_hash_changed")
            fm, error = writer.parse_frontmatter(raw_text.decode())
            if error or fm.get("source_revision") != revision or fm.get("task_id") != task_id:
                raise ValueError("source_revision_binding_mismatch")
            if fm.get("owner_tenant") != "local_owner" or fm.get("tenant") != "local_owner":
                raise ValueError("source_tenant_mismatch")
            compiled = root / "raw/compiled"
            seen = 0
            candidates = []
            for directory, dirs, files in os.walk(compiled, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
                for filename in files:
                    if not filename.endswith(".contract.md"):
                        continue
                    seen += 1
                    if seen > 5000:
                        raise ValueError("contract_scan_budget_exceeded")
                    path = Path(directory) / filename
                    data = read(path)
                    if len(data) > 1000000:
                        raise ValueError("contract_size_budget_exceeded")
                    meta, body = writer.parse_contract(data.decode())
                    refs = meta.get("source_files") or []
                    if not isinstance(refs, list) or raw.as_posix() not in refs:
                        continue
                    hashes = meta.get("source_sha256") or {}
                    if isinstance(hashes, str):
                        hashes = json.loads(hashes)
                    if hashes.get(raw.as_posix()) != receipt["sha256"]:
                        raise ValueError("contract_source_hash_mismatch")
                    if meta.get("task_id") != task_id:
                        raise ValueError("contract_task_mismatch")
                    digest = writer.contract_sha256(meta, body)
                    # An archive's parent ledger is the consuming transaction's
                    # ledger, including legacy nested _consumed directories.
                    ledger_dir = path.parent.parent if path.parent.name == "_consumed" else path.parent
                    ledger = json.loads(read(ledger_dir / "consumed.json"))
                    applied = False
                    for row in ledger["records"]:
                        matches = row.get("target") == meta.get("target") and row.get("sha256") == digest
                        if matches:
                            applied = row.get("status") in {"applied", "skipped_duplicate"}
                        if row.get("status") == "rolled_back" and (matches or not row.get("target")):
                            applied = False
                    if not applied:
                        candidates.append(False)
                        continue
                    from tools.contract_validator import dir_for_type
                    subdir = dir_for_type(meta.get("type"))
                    target = meta.get("target")
                    if not subdir or not isinstance(target, str) or Path(target).name != target or target in {".", ".."}:
                        raise ValueError("unsafe_target")
                    target_path = root / ("knowledge" if meta.get("type") == "industry-knowledge" else "wiki") / subdir / (target + ".md")
                    content = read(target_path)
                    target_fm, error = writer.parse_frontmatter(content.decode())
                    if error or writer.resolve_tenant(target_fm) != "local_owner":
                        raise ValueError("target_tenant_mismatch")
                    if fm.get("noexport") is True and target_fm.get("noexport") is not True:
                        raise ValueError("target_restriction_mismatch")
                    present = writer.block_already_present(content.decode(), body)
                    candidates.append(present)
                    if present:
                        result["targets"].append({"path": target_path.relative_to(root).as_posix(),
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "contract_sha256": digest, "ledger": (ledger_dir / "consumed.json").relative_to(root).as_posix()})
            result["verified"] = bool(candidates) and all(candidates)
            result["state"] = "compiled" if result["verified"] else "partial" if any(candidates) else "not_verified"
            result["source_revision"] = revision
    except Exception as exc:
        result = {"verified": False, "state": "unavailable", "reason": type(exc).__name__, "targets": []}
    return result
