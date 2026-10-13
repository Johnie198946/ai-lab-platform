"""Local Hermes Desktop bridge for the manual QuanSyn relay workflow."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit

try:
    from ..quansyn_relay import push_recent, draft_text
except ImportError:  # standalone dashboard loading
    import importlib.util
    _helper_path = Path(__file__).resolve().parent.parent / "quansyn_relay.py"
    _spec = importlib.util.spec_from_file_location("quansyn_relay", _helper_path)
    _relay = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_relay)
    push_recent, draft_text = _relay.push_recent, _relay.draft_text

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from hermes_constants import get_hermes_home
except ImportError:  # pragma: no cover - standalone fallback
    def get_hermes_home() -> Path:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")

router = APIRouter()
ID_PATTERN = r"^qs_[a-f0-9]{32}$"
MAX_BYTES = 25 * 1024 * 1024
MAX_PENDING = 100


class PullBody(BaseModel):
    pass


class PublishCopyBody(BaseModel):
    text: str = Field(min_length=1, max_length=250_000)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _owner_sender() -> str:
    values = {
        item.strip()
        for name in ("AI_LAB_LOCAL_OWNER_IDS", "FEISHU_CODE_WRITE_OWNER_IDS")
        for item in os.environ.get(name, "").split(",")
        if item.strip()
    }
    if len(values) != 1:
        raise ValueError("QuanSyn Desktop requires exactly one configured local owner")
    return next(iter(values))


def _api_base() -> str:
    value = str(os.environ.get("QUANSYN_API_BASE_URL") or "").strip().rstrip("/")
    if not value:
        try:
            from hermes_cli.config import load_config
            cfg = load_config() or {}
            value = str(
                (((cfg.get("plugins") or {}).get("entries") or {}).get("ai-lab-capabilities") or {})
                .get("settings", {}).get("quansyn", {}).get("api_base", "")
            ).strip().rstrip("/")
        except Exception:
            value = ""
    parts = urlsplit(value)
    local = parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"}
    if (parts.scheme != "https" and not local) or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("QuanSyn HTTPS API is not configured")
    return value


def _token(sender: str) -> str:
    account = _digest(_api_base() + "\0" + sender)
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-a", account, "-s", "com.quantum.quansyn", "-w"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode:
        raise ValueError("QuanSyn is not bound on this Mac")
    return result.stdout.strip()


def _request(sender: str, method: str, path: str, *, payload=None, sink=None, data=None, filename=None):
    headers = {"Authorization": "Bearer " + _token(sender), "X-QuanSyn-Sender": sender}
    if filename:
        headers["X-File-Name"] = quote(filename, safe="")
        headers["Content-Type"] = "application/octet-stream"
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        if sink is not None:
            with client.stream(method, _api_base() + "/api/v1/quansyn" + path, headers=headers) as response:
                if response.status_code >= 300:
                    raise ValueError(f"QuanSyn request failed (HTTP {response.status_code})")
                total = 0
                digest = hashlib.sha256()
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("QuanSyn attachment exceeds 25 MB")
                    digest.update(chunk)
                    sink.write(chunk)
                return digest.hexdigest()
        response = client.request(method, _api_base() + "/api/v1/quansyn" + path, headers=headers, json=payload, content=data)
    if response.status_code >= 300:
        raise ValueError(f"QuanSyn request failed (HTTP {response.status_code})")
    return response.json()


def _root(sender: str, transfer_id: str) -> Path:
    root = get_hermes_home() / "plugin-data" / "ai-lab-capabilities" / "quansyn-desktop" / _digest(sender + "\0" + transfer_id)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root.resolve()


def _state_path(sender: str, transfer_id: str) -> Path:
    return _root(sender, transfer_id) / "receipt.json"


def _read_state(sender: str, transfer_id: str) -> dict:
    try:
        value = json.loads(_state_path(sender, transfer_id).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(sender: str, transfer_id: str, value: dict) -> None:
    path = _state_path(sender, transfer_id)
    temp = path.with_suffix(".tmp-" + secrets.token_hex(6))
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _pending(sender: str) -> list[dict]:
    rows: list[dict] = []
    before = None
    seen = set()
    while True:
        suffix = "?target=mac&pending=true&limit=100"
        if before:
            suffix += "&before=" + quote(str(before), safe="")
        page = _request(sender, "GET", "/transfers" + suffix)
        batch = page.get("items", []) if isinstance(page, dict) else []
        rows.extend(batch)
        if len(rows) > MAX_PENDING:
            raise ValueError("QuanSyn pending queue exceeds 100 items")
        before = page.get("next") if isinstance(page, dict) else None
        if not before:
            return rows
        if before in seen:
            raise ValueError("QuanSyn pagination cursor repeated")
        seen.add(before)
        if len(rows) >= MAX_PENDING or len(seen) > MAX_PENDING:
            raise ValueError("QuanSyn pending queue exceeds 100 items")


def _pull_one(sender: str, transfer_id: str) -> dict:
    saved = _read_state(sender, transfer_id)
    row = _request(sender, "GET", "/transfers/" + transfer_id)
    if row.get("direction") != "request" or row.get("target") != "mac":
        raise ValueError("The selected transfer is not a Mac request")
    if saved.get("imported"):
        return saved

    claim = str(saved.get("claim") or secrets.token_urlsafe(32))
    _write_state(sender, transfer_id, {**saved, "claim": claim})
    leased = _request(sender, "POST", f"/transfers/{transfer_id}/claim", payload={"revision": row["revision"], "claim": claim})
    files = []
    root = _root(sender, transfer_id)
    for index, file in enumerate(row.get("files", [])):
        name = Path(file.get("metadata", {}).get("original_name") or file["filename"]).name
        destination = root / f"{index + 1}-{name}"
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                content_hash = _request(sender, "GET", "/files/" + file["artifact_id"], sink=stream)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        if content_hash != file["content_hash"]:
            destination.unlink(missing_ok=True)
            raise ValueError("QuanSyn attachment hash mismatch")
        files.append({"path": str(destination), "name": name, "hash": content_hash})

    saved = {
        "id": transfer_id,
        "claim": claim,
        "text": str(row.get("text") or ""),
        "blocks": row.get("blocks") or [],
        "files": files,
        "imported": False,
    }
    _write_state(sender, transfer_id, saved)
    saved["revision"] = leased["revision"]
    _write_state(sender, transfer_id, saved)
    return saved


class RecentBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)


class AckBody(BaseModel):
    transfer_ids: list[str] = Field(max_length=MAX_PENDING)


def _error(exc: Exception) -> HTTPException:
    message = str(exc) if isinstance(exc, ValueError) else "QuanSyn Desktop operation failed"
    return HTTPException(status_code=409 if isinstance(exc, ValueError) else 500, detail=message)


@router.post("/desktop/pull")
def pull_to_composer(body: PullBody):
    try:
        sender = _owner_sender()
        rows = _pending(sender)
        items = [_pull_one(sender, str(row["id"])) for row in rows]
        return {"success": True, "empty": not items, "items": items,
                "text": "\n\n".join(draft_text(row) for row in items)}
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/desktop/pull-presented")
def pull_presented(body: AckBody):
    try:
        sender = _owner_sender()
        for transfer in body.transfer_ids:
            import re
            if not re.fullmatch(ID_PATTERN, transfer):
                raise ValueError("Invalid transfer ID")
            saved = _read_state(sender, transfer)
            if saved.get("imported"):
                continue
            if "revision" not in saved:
                raise ValueError("Draft not fetched")
            for file in saved["files"]:
                with Path(file["path"]).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != file["hash"]:
                        raise ValueError("Attachment changed before presentation")
            _request(sender, "POST", f"/transfers/{transfer}/imported",
                     payload={"revision": saved["revision"], "claim": saved["claim"]})
            saved["imported"] = True
            _write_state(sender, transfer, saved)
        return {"success": True}
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/desktop/push-recent")
def push_recent_session(body: RecentBody):
    try:
        return push_recent(_owner_sender(), body.session_id,
                           get_hermes_home() / "plugin-data" / "ai-lab-capabilities", _request)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/desktop/push-copy")
def push_copy(body: PublishCopyBody):
    try:
        sender = _owner_sender()
        payload = {"request_id": "copy-" + _digest(sender + "\0" + body.text),
                   "direction": "result", "target": "mac", "text": body.text, "files": []}
        receipt = _request(sender, "POST", "/transfers", payload=payload)
        if not receipt.get("id"):
            raise ValueError("Remote transfer was not confirmed")
        return {"success": True, "result_id": receipt["id"]}
    except Exception as exc:
        raise _error(exc) from exc
