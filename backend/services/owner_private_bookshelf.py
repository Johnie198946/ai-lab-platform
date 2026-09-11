"""Owner-bound external reading artifacts, separate from public publication."""

from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import html
import ipaddress
import json
import os
import re
import shutil
import socket
import sqlite3
import tempfile
from io import BytesIO
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from markdown_it import MarkdownIt
from pypdf import PdfReader

from backend.services.knowledge_publication_store import reader_sections


SCHEMA = "follow-builders.owner-private.v2"
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_READABLE_BYTES = 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_AUTHORITIES = 1_000
MAX_SOURCES = 10_000
_HASH = re.compile(r"^[a-f0-9]{64}$")
_SAFE_VALUE = re.compile(r"^[^\x00-\x1f]{1,2000}$")
_MD = MarkdownIt("commonmark", {"html": True})


class OwnerPrivateBookshelfError(ValueError):
    pass


class OwnerPrivateContentUnavailable(OwnerPrivateBookshelfError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _literal(value: Any, fallback: str, maximum: int, field: str) -> str:
    text = fallback if value is None or value == "" else str(value)
    if len(text) > maximum or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        raise OwnerPrivateBookshelfError(f"invalid source {field}")
    return text


def _owner(tenant_key: str, user_id: str) -> dict[str, str]:
    tenant_key, user_id = str(tenant_key), str(user_id)
    if (not tenant_key or not user_id or len(tenant_key) > 64 or len(user_id) > 64
            or tenant_key != tenant_key.strip() or user_id != user_id.strip()
            or not _SAFE_VALUE.fullmatch(tenant_key) or not _SAFE_VALUE.fullmatch(user_id)):
        raise OwnerPrivateBookshelfError("explicit tenant and user identities are required")
    return {"tenant_key": tenant_key, "user_id": user_id}


def _safe_url(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or re.search(r"[\x00-\x20\x7f]", value):
        raise OwnerPrivateBookshelfError("source URL must be a literal HTTP(S) URL")
    try:
        parsed = urlparse(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise OwnerPrivateBookshelfError("source URL is malformed") from exc
    if (len(value) > 2_000 or parsed.scheme not in {"http", "https"} or not host or "%" in parsed.netloc
            or parsed.username or parsed.password or (port is not None and not 0 < port < 65536)):
        raise OwnerPrivateBookshelfError("source URL must be HTTP(S)")
    host = host.casefold().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home")):
        raise OwnerPrivateBookshelfError("source URL cannot target a private host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if all(re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", part) for part in host.split(".")):
            raise OwnerPrivateBookshelfError("source URL cannot use a noncanonical numeric host")
        try:
            address = ipaddress.ip_address(socket.inet_aton(host)) if re.fullmatch(r"[0-9.]+", host) else None
        except OSError:
            address = None
    else:
        pass
    if address is not None and not address.is_global:
        raise OwnerPrivateBookshelfError("source URL cannot target a private address")
    if address is None and "." not in host:
        raise OwnerPrivateBookshelfError("source URL cannot target a private host")
    return value


def _safe_relative(value: Any, *, prefixes: tuple[str, ...], suffixes: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise OwnerPrivateBookshelfError("artifact path must be relative")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not any(value.startswith(prefix) for prefix in prefixes):
        raise OwnerPrivateBookshelfError("artifact path is outside its allowlist")
    if path.suffix.lower() not in suffixes:
        raise OwnerPrivateBookshelfError("artifact suffix is not allowed")
    return value


def _no_symlink_file(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = root / relative
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise OwnerPrivateBookshelfError("symlinks are not allowed")
    resolved = candidate.resolve()
    if root not in resolved.parents or not resolved.is_file():
        raise OwnerPrivateBookshelfError("artifact file is missing or escaped its root")
    return resolved


def _safe_link(value: str, base_url: str) -> str:
    return _safe_url(urljoin(base_url, html.unescape(value)))


def _markdown_destination(value: str, base_url: str) -> str:
    match = re.fullmatch(r'(?:<([^>]*)>|(\S+))(?:\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\)))?', value.strip())
    if not match:
        raise OwnerPrivateBookshelfError("Markdown link destination is malformed")
    return _safe_link(match.group(1) or match.group(2), base_url)


class _HTMLToMarkdown(HTMLParser):
    """Small passive HTML reader: no fetching, scripts, styles, SVG, or raw HTML."""

    _SKIP = {"script", "style", "noscript", "svg", "canvas", "head", "template", "nav", "footer", "aside"}
    _BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "aside", "nav", "li", "ul", "ol", "table", "tr", "blockquote"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = _safe_url(base_url)
        self.parts: list[str] = []
        self.skip = 0
        self.links: list[str | None] = []
        self.pre = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self._SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        values = dict(attrs)
        if re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "pre":
            self.pre += 1
            self.parts.append("\n\n```\n")
        elif tag == "code" and not self.pre:
            self.parts.append("`")
        elif tag == "a":
            try:
                target = _safe_link(values.get("href") or "", self.base_url)
            except OwnerPrivateBookshelfError:
                target = None
            self.links.append(target)
            self.parts.append("[")
        elif tag == "img":
            alt = str(values.get("alt") or "").strip()
            if alt:
                self.parts.append(alt)
        elif tag in self._BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "pre" and self.pre:
            self.pre -= 1
            self.parts.append("\n```\n\n")
        elif tag == "code" and not self.pre:
            self.parts.append("`")
        elif tag == "a" and self.links:
            target = self.links.pop()
            self.parts.append(f"]({target})" if target else "]")
        elif re.fullmatch(r"h[1-6]", tag) or tag in self._BLOCK:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        self.parts.append(data if self.pre else re.sub(r"\s+", " ", data))

    def markdown(self) -> str:
        return _clean_markdown("".join(self.parts), self.base_url)


class _MarkdownHTMLStripper(HTMLParser):
    """Remove actual HTML without decoding escaped markup back into tags."""

    _SKIP = _HTMLToMarkdown._SKIP

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self._SKIP:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._SKIP:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.skip:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.skip:
            self.parts.append(f"&#{name};")


def _protect_code(text: str) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}

    def protect(value: str) -> str:
        index = len(protected)
        key = f"\ue000CODE{index}\ue001"
        while key in text:
            index += 1
            key = f"\ue000CODE{index}\ue001"
        protected[key] = value
        return key

    def keep(match: re.Match[str]) -> str:
        return protect(match.group(0))

    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    ranges = [
        (offsets[token.map[0]], offsets[token.map[1]])
        for token in _MD.parse(text)
        if token.type in {"fence", "code_block"} and token.map
    ]
    output: list[str] = []
    cursor = 0
    for start, end in ranges:
        output.append(re.sub(r"(?s)(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", keep, text[cursor:start]))
        output.append(protect(text[start:end]))
        cursor = end
    output.append(re.sub(r"(?s)(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", keep, text[cursor:]))
    return "".join(output), protected


def _rewrite_markdown_links(text: str, base_url: str) -> str:
    definitions: dict[str, str] = {}
    definition = re.compile(r"(?m)^( {0,3})\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))(.*)$")

    def reference(match: re.Match[str]) -> str:
        target = _safe_link(match.group(3) or match.group(4), base_url)
        definitions[match.group(2).casefold()] = target
        return f"{match.group(1)}[{match.group(2)}]: {target}{match.group(5)}"

    text = definition.sub(reference, text)
    reference_use = re.compile(r"(!?)\[([^\]\n]*)\]\[([^\]\n]+)\]")

    def use(match: re.Match[str]) -> str:
        if match.group(3).casefold() not in definitions:
            return match.group(0)
        return match.group(2) if match.group(1) else match.group(0)

    text = reference_use.sub(use, text)
    text = re.sub(
        r"!\[([^\]\n]*)\]\[\]",
        lambda match: match.group(1) if match.group(1).casefold() in definitions else match.group(0), text,
    )
    text = re.sub(
        r"!\[([^\]\n]*)\](?![\[(])",
        lambda match: match.group(1) if match.group(1).casefold() in definitions else match.group(0), text,
    )
    output: list[str] = []
    cursor = 0
    opener = re.compile(r"(!?)\[([^\]\n]*)\]\(")
    while match := opener.search(text, cursor):
        output.append(text[cursor:match.start()])
        depth, escaped, end = 1, False, match.end()
        while end < len(text) and depth:
            char = text[end]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            end += 1
        if depth:
            output.append(text[match.start():])
            cursor = len(text)
            break
        target = _markdown_destination(text[match.end():end - 1], base_url)
        output.append(match.group(2) if match.group(1) else f"[{match.group(2)}]({target})")
        cursor = end
    output.append(text[cursor:])
    return "".join(output)


def _clean_markdown(text: str, base_url: str = "https://invalid.example/") -> str:
    if not isinstance(text, str) or "\x00" in text:
        raise OwnerPrivateBookshelfError("readable Markdown contains invalid bytes")
    if len(text.encode("utf-8")) > MAX_READABLE_BYTES:
        raise OwnerPrivateContentUnavailable("readable body exceeds its limit")
    text, protected = _protect_code(text)
    stripper = _MarkdownHTMLStripper()
    stripper.feed(text)
    stripper.close()
    text = _rewrite_markdown_links("".join(stripper.parts), base_url)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    for key, value in protected.items():
        text = text.replace(key, value)
    if len(text.encode("utf-8")) > MAX_READABLE_BYTES:
        raise OwnerPrivateContentUnavailable("readable body exceeds its limit")
    for token in _MD.parse(text):
        if token.type in {"html_block", "html_inline"} or any(child.type == "html_inline" for child in token.children or []):
            raise OwnerPrivateBookshelfError("raw HTML survived normalization")
        for child in token.children or []:
            if child.type in {"link_open", "image"}:
                _safe_link(child.attrGet("href") or child.attrGet("src") or "", base_url)
            if child.type == "image":
                raise OwnerPrivateBookshelfError("active Markdown images are not allowed")
    return text


def _html_to_markdown(data: bytes, base_url: str = "https://invalid.example/") -> str:
    if len(data) > MAX_ARTIFACT_BYTES:
        raise OwnerPrivateContentUnavailable("expanded HTML exceeds its limit")
    parser = _HTMLToMarkdown(base_url)
    parser.feed(data.decode("utf-8", errors="replace"))
    parser.close()
    return parser.markdown()


def _bounded_gzip(data: bytes) -> bytes:
    with gzip.GzipFile(fileobj=BytesIO(data)) as stream:
        decoded = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(decoded) > MAX_ARTIFACT_BYTES:
        raise OwnerPrivateBookshelfError("compressed snapshot exceeds its expanded limit")
    return decoded


def _summary_markdown(body: str, title: str, url: str) -> str:
    if not any(marker in body for marker in ('"@context":"https://schema.org"', "#nprogress", "--font-feature")):
        return _clean_markdown(body, url)
    match = re.search(r'"description":"((?:\\.|[^"\\])*)"', body)
    description = ""
    if match:
        try:
            description = unquote(json.loads('"' + match.group(1) + '"'))
        except json.JSONDecodeError:
            description = ""
    text = f"# {title}\n\n{description.strip()}\n\n[查看原始来源]({url})"
    return _clean_markdown(text, url)


def _reader_summary(record: str, readable: str, status: str, url: str, unavailable_reason: str | None = None) -> str:
    if status in {"link_only", "unavailable"}:
        return unavailable_reason or "仅提供原始来源链接；没有可验证的正文。"
    if status == "snapshot" or any(marker in record for marker in ('"@context":"https://schema.org"', "#nprogress", "--font-feature")):
        candidate = readable
    else:
        try:
            candidate = _clean_markdown(record, url)
        except OwnerPrivateBookshelfError:
            candidate = _html_to_markdown(record.encode(), url)
    candidate = re.sub(r"^#{1,6}\s+.*$", "", candidate, flags=re.M)
    candidate = re.sub(r"```.*?```", "", candidate, flags=re.S)
    candidate = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    suffix = "（已验哈希快照，不声明全文完整）" if status == "snapshot" else "（来源记录摘要，不声明全文完整）"
    return (candidate[:180].rstrip() + " " + suffix).strip()


def _artifact(output: Path, data: bytes, suffix: str) -> dict[str, Any]:
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise OwnerPrivateBookshelfError("artifact exceeds the per-file limit")
    digest = _digest(data)
    relative = f"artifacts/{digest}.{suffix}"
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(data)
        os.chmod(target, 0o600)
    return {"path": relative, "sha256": digest, "byte_count": len(data)}


def _latest_snapshot(connection: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT id,canonical_url,captured_at,snapshot_path,content_type,content_sha256,status "
        "FROM source_versions WHERE canonical_url=? AND status='captured' ORDER BY captured_at DESC,id DESC LIMIT 1",
        (url,),
    ).fetchone()


def _read_bounded(path: Path, limit: int = MAX_ARTIFACT_BYTES) -> bytes:
    if path.stat().st_size > limit:
        raise OwnerPrivateContentUnavailable("artifact exceeds its size limit")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise OwnerPrivateContentUnavailable("artifact exceeds its size limit")
    return data


def _json_file(path: Path, maximum: int = 8 * 1024 * 1024) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise OwnerPrivateBookshelfError("metadata input must be a regular file")
    data = _read_bounded(path, maximum)
    try:
        value = json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OwnerPrivateBookshelfError("metadata input is invalid JSON") from exc
    if not isinstance(value, dict):
        raise OwnerPrivateBookshelfError("metadata input must be an object")
    return value, _digest(data)


def _audit_indexes(audit_path: Path | None, rows: list[sqlite3.Row], authorities: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, Any]]:
    if audit_path is None:
        return {}, {}, {"audit_sha256": None, "audit_schema_version": None}
    audit, digest = _json_file(audit_path, 16 * 1024 * 1024)
    if audit.get("schema_version") != "follow-builders.source-audit.v1":
        raise OwnerPrivateBookshelfError("unsupported source audit schema")
    source_audit = {item.get("id"): item for item in audit.get("records", []) if isinstance(item, dict)}
    roster_audit = {item.get("id"): item for item in audit.get("roster", []) if isinstance(item, dict)}
    if len(source_audit) != len(rows) or len(roster_audit) != len(authorities):
        raise OwnerPrivateBookshelfError("audit cardinality does not match source database")
    for row in rows:
        item = source_audit.get(row["id"])
        if not item or any(item.get(key) != row[key] for key in ("canonical_url", "title", "author", "published", "kind", "license", "captured_at", "content_sha256")):
            raise OwnerPrivateBookshelfError(f"audit is not bound to source {row['id']}")
    for authority in authorities:
        item = roster_audit.get(authority["roster_id"])
        if not item or any(item.get(key) != authority[key] for key in ("handle", "display_name", "organization_or_role", "priority", "official_entry", "verification_status")):
            raise OwnerPrivateBookshelfError(f"audit is not bound to roster {authority['roster_id']}")
    return source_audit, roster_audit, {"audit_sha256": digest, "audit_schema_version": audit["schema_version"]}


def _audit_covers_snapshot(item: dict[str, Any], snapshot: sqlite3.Row | None, *, roster: bool = False) -> bool:
    if snapshot is None:
        return False
    candidates = item.get("profile_snapshots", []) if roster else item.get("source_versions", item.get("snapshots", []))
    if not roster and isinstance(item.get("projection"), dict):
        candidates = item["projection"].get("source_versions", candidates)
    if not isinstance(candidates, list):
        return False
    expected = {key: snapshot[key] for key in (
        "captured_at", "snapshot_path", "content_type", "content_sha256", "status",
    )}
    return any(
        isinstance(candidate, dict)
        and isinstance(candidate.get("version", candidate), dict)
        and all(candidate.get("version", candidate).get(key) == value for key, value in expected.items())
        for candidate in candidates
    )


def _validate_scope(scope_path: Path | None, rows: list[sqlite3.Row], authorities: list[dict[str, Any]]) -> dict[str, Any]:
    if scope_path is None:
        return {"scope_sha256": None}
    scope, digest = _json_file(scope_path)
    expected_sources = scope.get("sources")
    expected_people = scope.get("people")
    actual_sources = [{key: row[key] for key in ("id", "canonical_url", "title", "author", "published", "kind")} for row in rows]
    actual_people = [{key: authority[key if key != "id" else "roster_id"] for key in ("id", "handle", "display_name", "organization_or_role")} for authority in authorities]
    if expected_sources != actual_sources or expected_people != actual_people:
        raise OwnerPrivateBookshelfError("database no longer matches the explicit acceptance scope")
    return {"scope_sha256": digest}


def _pdf_markdown(data: bytes, url: str) -> tuple[str, dict[str, Any]]:
    try:
        reader = PdfReader(BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise OwnerPrivateContentUnavailable("PDF text extraction unavailable") from exc
    if not pages or not pages[0].strip() or not pages[-1].strip():
        raise OwnerPrivateContentUnavailable("PDF first/last page coverage could not be verified")
    text = "\n\n".join(pages)
    readable = _clean_markdown(text, url)
    return readable, {
        "identity": "pypdf.extract_text", "version": "1", "source_sha256": _digest(data),
        "body_sha256": _digest(readable.encode()), "page_count": len(pages),
        "first_page_sha256": _digest(pages[0].encode()), "last_page_sha256": _digest(pages[-1].encode()),
        "page_coverage": "first_and_last_nonempty_all_pages_joined",
    }


def _source_version(source: dict[str, Any]) -> str:
    return _digest(_canonical({key: value for key, value in source.items() if key != "content_version"}))


def export_follow_builders(
    source_root: Path, output: Path, tenant_key: str, user_id: str, *,
    audit_path: Path | None = None, scope_path: Path | None = None,
    expected_sources: int | None = None, expected_authorities: int | None = None,
) -> dict[str, Any]:
    """Export the bounded people roster and external sources; never documents."""
    owner = _owner(tenant_key, user_id)
    if source_root.is_symlink():
        raise OwnerPrivateBookshelfError("source root cannot be a symlink")
    source_root = source_root.resolve()
    db_relative = _safe_relative("data/follow_builders.sqlite3", prefixes=("data/",), suffixes=(".sqlite3",))
    db_path = _no_symlink_file(source_root, db_relative)
    existing = None
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise OwnerPrivateBookshelfError("output must be a package directory")
        manifest_path = _no_symlink_file(output, "manifest.json")
        if manifest_path.stat().st_size > 2 * 1024 * 1024:
            raise OwnerPrivateBookshelfError("existing manifest exceeds its size limit")
        existing = _json_file(manifest_path, 2 * 1024 * 1024)[0]

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN")
            authorities = [dict(row) for row in connection.execute(
                "SELECT id AS roster_id,handle,display_name,organization_or_role,priority,official_entry,verification_status FROM people ORDER BY id"
            )]
            source_rows = connection.execute(
                "SELECT id,canonical_url,title,author,published,kind,license,captured_at,content_sha256,body FROM sources ORDER BY id"
            ).fetchall()
            if not 0 < len(authorities) <= MAX_AUTHORITIES or not 0 < len(source_rows) <= MAX_SOURCES:
                raise OwnerPrivateBookshelfError("source database cardinality is outside the bounded schema")
            if expected_authorities is not None and len(authorities) != expected_authorities:
                raise OwnerPrivateBookshelfError(f"expected {expected_authorities} authorities, got {len(authorities)}")
            if expected_sources is not None and len(source_rows) != expected_sources:
                raise OwnerPrivateBookshelfError(f"expected {expected_sources} sources, got {len(source_rows)}")
            source_audit, roster_audit, audit_binding = _audit_indexes(audit_path, source_rows, authorities)
            scope_binding = _validate_scope(scope_path, source_rows, authorities)
            for authority in authorities:
                audit_item = roster_audit.get(authority["roster_id"], {})
                roster_snapshot = _latest_snapshot(connection, authority["official_entry"])
                bound = _audit_covers_snapshot(audit_item, roster_snapshot, roster=True)
                if bound:
                    try:
                        relative = _safe_relative(roster_snapshot["snapshot_path"], prefixes=("data/raw/",), suffixes=(".html", ".htm", ".md", ".txt", ".pdf"))
                        bound = _digest(_read_bounded(_no_symlink_file(source_root, relative))) == roster_snapshot["content_sha256"]
                    except (OSError, OwnerPrivateBookshelfError):
                        bound = False
                assessment = audit_item.get("assessment") if bound and isinstance(audit_item.get("assessment"), dict) else {}
                authority.update({
                    "identity_status": _literal(audit_item.get("identity_status") if bound else None, "as stored, not independently reverified", 200, "identity_status"),
                    "identity_assessment": _literal(assessment.get("category"), "unverified", 120, "identity_assessment"),
                    "identity_notes": [_literal(note, "", 1_000, "identity_note") for note in assessment.get("notes", [])[:10]],
                    "relationship_status": _literal(audit_item.get("relationship_status") if bound else None, "unknown; no source relationship supplied", 500, "relationship_status"),
                })
            sources: list[dict[str, Any]] = []
            for row in source_rows:
                body_data = str(row["body"]).encode()
                if _digest(body_data) != row["content_sha256"]:
                    raise OwnerPrivateBookshelfError(f"source record hash mismatch: {row['id']}")
                record = _artifact(temporary, body_data, "source")
                url = _safe_url(row["canonical_url"])
                audit_item = source_audit.get(row["id"], {})
                snapshot_row = _latest_snapshot(connection, row["canonical_url"])
                snapshot_audit_bound = _audit_covers_snapshot(audit_item, snapshot_row)
                assessment = audit_item.get("assessment") if (snapshot_row is None or snapshot_audit_bound) and isinstance(audit_item.get("assessment"), dict) else {}
                snapshot = None
                readable = ""
                status = "summary"
                unavailable_reason = None
                body_origin = "source_record_summary"
                derivation: dict[str, Any] = {"identity": "source-record-safe-markdown", "version": "2", "source_sha256": record["sha256"]}
                if snapshot_row:
                    try:
                        relative = _safe_relative(snapshot_row["snapshot_path"], prefixes=("data/raw/",), suffixes=(".html", ".htm", ".md", ".txt", ".pdf"))
                        snapshot_data = _read_bounded(_no_symlink_file(source_root, relative))
                        if _digest(snapshot_data) != snapshot_row["content_sha256"]:
                            raise OwnerPrivateContentUnavailable("snapshot hash mismatch")
                        suffix = PurePosixPath(relative).suffix.lower().lstrip(".")
                        snapshot = {**_artifact(temporary, snapshot_data, suffix),
                                    "content_type": _literal(snapshot_row["content_type"], "application/octet-stream", 120, "snapshot content_type"),
                                    "captured_at": _literal(snapshot_row["captured_at"], "", 80, "snapshot captured_at")}
                        decoded = _bounded_gzip(snapshot_data) if snapshot_data.startswith(b"\x1f\x8b") else snapshot_data
                        if suffix in {"html", "htm"}:
                            readable = _html_to_markdown(decoded, url)
                            body_origin = "raw_snapshot_html"
                            derivation = {"identity": "html-parser", "version": "2", "source_sha256": snapshot["sha256"], "body_sha256": _digest(readable.encode())}
                        elif suffix == "pdf":
                            readable, derivation = _pdf_markdown(decoded, url)
                            derivation["source_sha256"] = snapshot["sha256"]
                            body_origin = "derived_pdf_text"
                        else:
                            readable = _clean_markdown(decoded.decode("utf-8"), url)
                            body_origin = "raw_snapshot_text"
                            derivation = {"identity": "safe-markdown", "version": "2", "source_sha256": snapshot["sha256"], "body_sha256": _digest(readable.encode())}
                        status = "snapshot"
                    except (OSError, UnicodeError, OwnerPrivateBookshelfError) as exc:
                        readable, status = "", "unavailable"
                        unavailable_reason = f"快照不可用：{exc}"
                        body_origin = "unavailable"
                        derivation = {"identity": "unavailable", "version": "1", "source_sha256": (snapshot or record)["sha256"]}
                else:
                    try:
                        readable = _summary_markdown(str(row["body"]), str(row["title"] or url), url)
                        derivation["body_sha256"] = _digest(readable.encode())
                    except OwnerPrivateBookshelfError as exc:
                        readable, status = "", "unavailable"
                        unavailable_reason = f"来源记录不可读：{exc}"
                        body_origin = "unavailable"
                # Tiny/binary/landing records remain discoverable but are not presented as readable originals.
                if status != "unavailable" and len(re.sub(r"\W", "", readable, flags=re.UNICODE)) < 80:
                    readable, status = "", "link_only"
                    unavailable_reason = "仅提供原始来源链接；没有可验证的正文。"
                    derivation.pop("body_sha256", None)
                if snapshot_row is not None and (not snapshot_audit_bound or status != "snapshot"):
                    assessment = {}
                readable_artifact = _artifact(temporary, readable.encode(), "md") if readable else None
                completeness = "apparent_full_article_or_report" if assessment.get("apparent_full_readable_article_or_report") is True else "unverified"
                source_classification = _literal(assessment.get("category"), "as_stored_unreviewed", 120, "source_classification")
                reader_summary = _reader_summary(str(row["body"]), readable, status, url, unavailable_reason)
                book_id = "follow-builders-source-" + hashlib.sha256(url.encode()).hexdigest()[:24]
                source = {
                    "source_id": row["id"], "book_id": book_id, "canonical_url": url, "title": _literal(row["title"], url, 500, "title"),
                    "author": _literal(row["author"], "Unknown source", 500, "author"), "published": _literal(row["published"], "", 120, "published"),
                    "kind": _literal(row["kind"], "external source", 120, "kind"), "license": _literal(row["license"], "unknown", 500, "license"),
                    "captured_at": _literal(row["captured_at"], "", 80, "captured_at"), "state": "active", "content_status": status,
                    "reader_summary": reader_summary, "unavailable_reason": unavailable_reason,
                    "body_origin": body_origin, "completeness": completeness, "source_classification": source_classification,
                    "derivation": derivation,
                    "source_record": record, "source_snapshot": snapshot, "readable_body": readable_artifact,
                    "source_snapshot_hash": snapshot and snapshot["sha256"],
                    "readable_body_hash": readable_artifact and readable_artifact["sha256"],
                }
                source["content_version"] = _source_version(source)
                sources.append(source)
        finally:
            connection.close()
        manifest = {
            "schema_version": SCHEMA, "collection_id": "follow-builders", "collection_title": "Follow Builders",
            "visibility": "owner_private", "owner": owner,
            "acceptance": {**audit_binding, **scope_binding, "expected_sources": expected_sources, "expected_authorities": expected_authorities},
            "authorities": authorities, "sources": sources,
        }
        _validate_manifest(manifest, tenant_key, user_id)
        payload_bytes = sum(path.stat().st_size for path in (temporary / "artifacts").iterdir())
        if payload_bytes > MAX_PACKAGE_BYTES:
            raise OwnerPrivateBookshelfError("package exceeds the total payload limit")
        (temporary / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
        os.chmod(temporary / "manifest.json", 0o600)
        changed = existing is None
        if existing is not None:
            if _canonical(existing) != _canonical(manifest):
                raise OwnerPrivateBookshelfError("output already exists with different content")
            validated = _validate_manifest(existing, tenant_key, user_id)
            OwnerPrivateBookshelfStore()._verify_release_artifacts(output, validated)
        else:
            os.replace(temporary, output)
            temporary = None
        return {"changed": changed, "manifest_hash": _digest(_canonical(manifest)), "people": len(authorities), "sources": len(sources),
                "statuses": {name: sum(item["content_status"] == name for item in sources) for name in ("snapshot", "summary", "link_only", "unavailable")},
                "payload_bytes": payload_bytes, "output": str(output)}
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def _validate_artifact(value: Any, *, optional: bool = False) -> dict[str, Any] | None:
    if value is None and optional:
        return None
    if not isinstance(value, dict) or set(value) - {"path", "sha256", "byte_count", "content_type", "captured_at"}:
        raise OwnerPrivateBookshelfError("invalid artifact descriptor")
    path = _safe_relative(value.get("path"), prefixes=("artifacts/",), suffixes=(".source", ".html", ".htm", ".md", ".txt", ".pdf"))
    digest, size = value.get("sha256"), value.get("byte_count")
    if not isinstance(digest, str) or not _HASH.fullmatch(digest) or type(size) is not int or not 0 < size <= MAX_ARTIFACT_BYTES:
        raise OwnerPrivateBookshelfError("invalid artifact hash or size")
    if not PurePosixPath(path).name.startswith(digest + "."):
        raise OwnerPrivateBookshelfError("artifact name is not content addressed")
    return value


def _validate_manifest(manifest: Any, tenant_key: str, user_id: str) -> dict[str, Any]:
    expected_manifest_fields = {"schema_version", "collection_id", "collection_title", "visibility", "owner", "acceptance", "authorities", "sources"}
    if (not isinstance(manifest, dict) or set(manifest) != expected_manifest_fields
            or manifest.get("schema_version") != SCHEMA or manifest.get("owner") != _owner(tenant_key, user_id)):
        raise OwnerPrivateBookshelfError("manifest schema or owner binding mismatch")
    if manifest.get("visibility") != "owner_private" or manifest.get("collection_id") != "follow-builders":
        raise OwnerPrivateBookshelfError("manifest collection boundary mismatch")
    acceptance = manifest.get("acceptance")
    if not isinstance(acceptance, dict) or set(acceptance) != {
        "audit_sha256", "audit_schema_version", "scope_sha256", "expected_sources", "expected_authorities"
    }:
        raise OwnerPrivateBookshelfError("invalid acceptance binding")
    for key in ("audit_sha256", "scope_sha256"):
        if acceptance[key] is not None and (not isinstance(acceptance[key], str) or not _HASH.fullmatch(acceptance[key])):
            raise OwnerPrivateBookshelfError("invalid acceptance hash")
    if acceptance["audit_sha256"] is None and acceptance["audit_schema_version"] is not None:
        raise OwnerPrivateBookshelfError("audit schema lacks an audit hash")
    if acceptance["audit_sha256"] is not None and acceptance["audit_schema_version"] != "follow-builders.source-audit.v1":
        raise OwnerPrivateBookshelfError("unsupported bound audit schema")
    authorities, sources = manifest.get("authorities"), manifest.get("sources")
    if (not isinstance(authorities, list) or not 0 < len(authorities) <= MAX_AUTHORITIES
            or not isinstance(sources, list) or not 0 < len(sources) <= MAX_SOURCES):
        raise OwnerPrivateBookshelfError("manifest cardinality is outside the bounded schema")
    for key, actual in (("expected_sources", len(sources)), ("expected_authorities", len(authorities))):
        expected = acceptance[key]
        if expected is not None and (type(expected) is not int or expected != actual):
            raise OwnerPrivateBookshelfError("manifest does not meet its explicit acceptance count")
    seen_roster: set[int] = set()
    for authority in authorities:
        if not isinstance(authority, dict) or set(authority) != {
            "roster_id", "handle", "display_name", "organization_or_role", "priority", "official_entry", "verification_status",
            "identity_status", "identity_assessment", "identity_notes", "relationship_status",
        }:
            raise OwnerPrivateBookshelfError("invalid authority roster record")
        if type(authority["roster_id"]) is not int or authority["roster_id"] <= 0 or authority["roster_id"] in seen_roster:
            raise OwnerPrivateBookshelfError("invalid or duplicate roster id")
        seen_roster.add(authority["roster_id"])
        if authority.get("official_entry"):
            _safe_url(authority["official_entry"])
        if any(not isinstance(authority.get(field), (str, type(None))) or len(authority.get(field) or "") > 2_000 for field in (
            "handle", "display_name", "organization_or_role", "priority", "official_entry", "verification_status",
            "identity_status", "identity_assessment", "relationship_status",
        )) or not isinstance(authority["identity_notes"], list) or any(not isinstance(note, str) or len(note) > 1_000 for note in authority["identity_notes"]):
            raise OwnerPrivateBookshelfError("invalid authority field")
    seen: set[str] = set()
    seen_source_ids: set[int] = set()
    seen_urls: set[str] = set()
    for source in sources:
        expected_source_fields = {
            "source_id", "book_id", "canonical_url", "title", "author", "published", "kind", "license", "captured_at",
            "state", "content_status", "reader_summary", "source_record", "source_snapshot", "readable_body",
            "source_snapshot_hash", "readable_body_hash", "content_version", "unavailable_reason", "body_origin",
            "completeness", "source_classification", "derivation",
        }
        if (not isinstance(source, dict) or set(source) != expected_source_fields
                or source.get("content_status") not in {"snapshot", "summary", "link_only", "unavailable"}
                or source.get("state") not in {"active", "withdrawn"}):
            raise OwnerPrivateBookshelfError("invalid source record")
        source_id = source.get("source_id")
        if type(source_id) is not int or source_id <= 0 or source_id in seen_source_ids:
            raise OwnerPrivateBookshelfError("invalid or duplicate literal source id")
        seen_source_ids.add(source_id)
        book_id = source.get("book_id")
        if not isinstance(book_id, str) or not re.fullmatch(r"follow-builders-source-[a-f0-9]{24}", book_id) or book_id in seen:
            raise OwnerPrivateBookshelfError("invalid or duplicate source id")
        seen.add(book_id)
        canonical_url = _safe_url(source.get("canonical_url"))
        if canonical_url in seen_urls or book_id != "follow-builders-source-" + hashlib.sha256(canonical_url.encode()).hexdigest()[:24]:
            raise OwnerPrivateBookshelfError("duplicate URL or unstable source id")
        seen_urls.add(canonical_url)
        for field, maximum in (("title", 500), ("author", 500), ("published", 120), ("kind", 120),
                               ("license", 500), ("captured_at", 80), ("reader_summary", 1_000),
                               ("body_origin", 120), ("completeness", 120), ("source_classification", 120)):
            if not isinstance(source.get(field), str) or len(source[field]) > maximum:
                raise OwnerPrivateBookshelfError(f"invalid source {field}")
        if source["unavailable_reason"] is not None and (not isinstance(source["unavailable_reason"], str) or len(source["unavailable_reason"]) > 1_000):
            raise OwnerPrivateBookshelfError("invalid unavailable reason")
        derivation = source["derivation"]
        if not isinstance(derivation, dict):
            raise OwnerPrivateBookshelfError("invalid body derivation")
        record = _validate_artifact(source.get("source_record"))
        snapshot = _validate_artifact(source.get("source_snapshot"), optional=True)
        readable = _validate_artifact(source.get("readable_body"), optional=True)
        if source["content_status"] == "snapshot" and not snapshot:
            raise OwnerPrivateBookshelfError("snapshot status lacks a snapshot artifact")
        if source["content_status"] in {"link_only", "unavailable"} and readable:
            raise OwnerPrivateBookshelfError("unreadable source cannot contain a readable body")
        if source["content_status"] not in {"link_only", "unavailable"} and not readable:
            raise OwnerPrivateBookshelfError("readable status lacks a readable body")
        if source["content_status"] == "unavailable" and not source["unavailable_reason"]:
            raise OwnerPrivateBookshelfError("unavailable source lacks a truthful reason")
        if source.get("source_snapshot_hash") != (snapshot and snapshot["sha256"]) or source.get("readable_body_hash") != (readable and readable["sha256"]):
            raise OwnerPrivateBookshelfError("raw/readable hash fields are confused")
        snapshot_suffix = PurePosixPath(snapshot["path"]).suffix if snapshot else None
        allowed_snapshot_suffixes = {
            "raw_snapshot_html": {".html", ".htm"},
            "raw_snapshot_text": {".md", ".txt"},
            "derived_pdf_text": {".pdf"},
        }
        if source["body_origin"] in allowed_snapshot_suffixes and snapshot_suffix not in allowed_snapshot_suffixes[source["body_origin"]]:
            raise OwnerPrivateBookshelfError("body origin does not match its source artifact")
        expected_derivations = {
            "source_record_summary": ("source-record-safe-markdown", "2", record),
            "raw_snapshot_html": ("html-parser", "2", snapshot),
            "raw_snapshot_text": ("safe-markdown", "2", snapshot),
            "derived_pdf_text": ("pypdf.extract_text", "1", snapshot),
            "unavailable": ("unavailable", "1", snapshot or record),
        }
        expected_derivation = expected_derivations.get(source["body_origin"])
        fields = {"identity", "version", "source_sha256"}
        if readable:
            fields.add("body_sha256")
        if source["body_origin"] == "derived_pdf_text":
            fields.update({"page_count", "first_page_sha256", "last_page_sha256", "page_coverage"})
        if (not expected_derivation or not expected_derivation[2] or set(derivation) != fields
                or derivation.get("identity") != expected_derivation[0] or derivation.get("version") != expected_derivation[1]
                or derivation.get("source_sha256") != expected_derivation[2]["sha256"]):
            raise OwnerPrivateBookshelfError("invalid or unbound body derivation")
        if readable and derivation.get("body_sha256") != readable["sha256"]:
            raise OwnerPrivateBookshelfError("derivation body hash does not bind the readable body")
        if source["body_origin"] == "derived_pdf_text" and (
                type(derivation.get("page_count")) is not int or derivation["page_count"] <= 0
                or not isinstance(derivation.get("first_page_sha256"), str) or not _HASH.fullmatch(derivation["first_page_sha256"])
                or not isinstance(derivation.get("last_page_sha256"), str) or not _HASH.fullmatch(derivation["last_page_sha256"])
                or derivation.get("page_coverage") != "first_and_last_nonempty_all_pages_joined"):
            raise OwnerPrivateBookshelfError("invalid PDF derivation")
        if source.get("content_version") != _source_version(source) or not record:
            raise OwnerPrivateBookshelfError("invalid source version")
    return manifest


class OwnerPrivateBookshelfStore:
    def __init__(self, root: Path | None = None):
        default = Path(__file__).resolve().parents[2] / "data/owner-private-bookshelves"
        self.root = (root or Path(os.environ.get("OWNER_PRIVATE_BOOKSHELF_DIR", default))).resolve()

    @staticmethod
    def _scope(owner: dict[str, str]) -> str:
        return _digest(f"{owner['tenant_key']}\0{owner['user_id']}".encode())

    def _pointer(self, owner: dict[str, str]) -> Path:
        return self.root / "owners" / self._scope(owner) / "current.json"

    def _release(self, release: str) -> Path:
        if not _HASH.fullmatch(release):
            raise OwnerPrivateBookshelfError("invalid release id")
        return self.root / "releases" / release

    @staticmethod
    def _write_atomic(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(_canonical(value) + b"\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    @staticmethod
    def _verified_bytes(root: Path, descriptor: dict[str, Any]) -> bytes:
        path = _no_symlink_file(root, descriptor["path"])
        data = _read_bounded(path, descriptor["byte_count"])
        if len(data) != descriptor["byte_count"] or _digest(data) != descriptor["sha256"]:
            raise OwnerPrivateBookshelfError("artifact integrity check failed")
        return data

    def _verify_release_artifacts(self, root: Path, manifest: dict[str, Any]) -> int:
        total = sum(
            source[key]["byte_count"] for source in manifest["sources"]
            for key in ("source_record", "source_snapshot", "readable_body") if source.get(key)
        )
        if total > MAX_PACKAGE_BYTES:
            raise OwnerPrivateBookshelfError("package exceeds the total payload limit")
        for source in manifest["sources"]:
            for key in ("source_record", "source_snapshot", "readable_body"):
                descriptor = source.get(key)
                if not descriptor:
                    continue
                data = self._verified_bytes(root, descriptor)
                if key == "readable_body":
                    try:
                        markdown = data.decode("utf-8")
                    except UnicodeError as exc:
                        raise OwnerPrivateBookshelfError("readable body is not UTF-8") from exc
                    if _clean_markdown(markdown, source["canonical_url"]) != markdown:
                        raise OwnerPrivateBookshelfError("readable body is not normalized safe Markdown")
        return total

    def import_package(
        self, package: Path, tenant_key: str, user_id: str, *, expected_current: str | None
    ) -> dict[str, Any]:
        owner = _owner(tenant_key, user_id)
        if package.is_symlink():
            raise OwnerPrivateBookshelfError("package root cannot be a symlink")
        package = package.resolve()
        manifest_path = _no_symlink_file(package, "manifest.json")
        if manifest_path.stat().st_size > 2 * 1024 * 1024:
            raise OwnerPrivateBookshelfError("manifest exceeds its size limit")
        try:
            manifest = _validate_manifest(_json_file(manifest_path, 2 * 1024 * 1024)[0], tenant_key, user_id)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise OwnerPrivateBookshelfError("invalid manifest JSON") from exc
        release = _digest(_canonical(manifest))
        self._verify_release_artifacts(package, manifest)

        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.root / ".import.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            target = self._release(release)
            if not target.exists():
                (self.root / "releases").mkdir(parents=True, exist_ok=True, mode=0o700)
                temporary = Path(tempfile.mkdtemp(prefix=f".{release}.", dir=self.root / "releases"))
                try:
                    (temporary / "artifacts").mkdir()
                    for source in manifest["sources"]:
                        for key in ("source_record", "source_snapshot", "readable_body"):
                            descriptor = source.get(key)
                            if descriptor:
                                destination = temporary / descriptor["path"]
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                destination.write_bytes(self._verified_bytes(package, descriptor))
                                os.chmod(destination, 0o600)
                    (temporary / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
                    os.chmod(temporary / "manifest.json", 0o600)
                    os.replace(temporary, target)
                    temporary = None
                finally:
                    if temporary is not None:
                        shutil.rmtree(temporary, ignore_errors=True)
            target_root, target_manifest = self._load_release(owner, release)
            self._verify_release_artifacts(target_root, target_manifest)
            pointer = self._pointer(owner)
            current_release = None
            if pointer.is_file() and not pointer.is_symlink():
                current = _json_file(pointer, 4_096)[0]
                current_release = current.get("release")
                if current_release == release:
                    return {"changed": False, "release": release, "previous_release": current.get("previous_release"), "sources": len(manifest["sources"])}
            if current_release != expected_current:
                raise OwnerPrivateBookshelfError("active release changed; import CAS rejected")
            self._write_atomic(pointer, {"release": release, "previous_release": current_release})
        return {"changed": True, "release": release, "previous_release": current_release, "sources": len(manifest["sources"])}

    def rollback(self, tenant_key: str, user_id: str, *, expected_current: str, target_release: str) -> dict[str, Any]:
        owner = _owner(tenant_key, user_id)
        pointer = self._pointer(owner)
        if not pointer.is_file() or pointer.is_symlink():
            raise OwnerPrivateBookshelfError("no active owner collection")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.root / ".import.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = _json_file(pointer, 4_096)[0]
            current_release = current.get("release")
            if current_release == target_release:
                return {"changed": False, "release": target_release, "previous_release": current.get("previous_release")}
            if current_release != expected_current:
                raise OwnerPrivateBookshelfError("active release changed; rollback CAS rejected")
            root, manifest = self._load_release(owner, target_release)
            self._verify_release_artifacts(root, manifest)
            self._write_atomic(pointer, {"release": target_release, "previous_release": current_release})
        return {"changed": True, "release": target_release, "previous_release": current_release}

    def _load_release(self, owner: dict[str, str], release: str) -> tuple[Path, dict[str, Any]]:
        root = self._release(release)
        manifest_path = _no_symlink_file(root, "manifest.json")
        if manifest_path.stat().st_size > 2 * 1024 * 1024:
            raise OwnerPrivateBookshelfError("manifest exceeds its size limit")
        manifest = _validate_manifest(_json_file(manifest_path, 2 * 1024 * 1024)[0], owner["tenant_key"], owner["user_id"])
        if _digest(_canonical(manifest)) != release:
            raise OwnerPrivateBookshelfError("release manifest integrity check failed")
        return root, manifest

    def _active(self, tenant_key: str, user_id: str) -> tuple[Path, dict[str, Any]] | None:
        owner = _owner(tenant_key, user_id)
        pointer = self._pointer(owner)
        if not pointer.is_file() or pointer.is_symlink():
            return None
        try:
            value = _json_file(pointer, 4_096)[0]
            return self._load_release(owner, value["release"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError, OwnerPrivateBookshelfError):
            return None

    @staticmethod
    def _book(source: dict[str, Any], *, available: bool = True, unavailable_reason: str | None = None) -> dict[str, Any]:
        author = str(source.get("author") or "Unknown source")
        return {
            "id": source["book_id"], "source_kind": "owner_private_external",
            "title": source["title"], "author": author, "author_source": "external_source_record",
            "institution": author, "group_label": author,
            "summary": source["reader_summary"],
            "cover_theme": "external", "cover_variant": int(source["book_id"][-4:], 16) % 6, "cover_version": 1,
            "security_level": "owner_private", "knowledge_level": "external_source",
            "freshness": source.get("captured_at") or "unknown", "source_count": 1,
            "content_status": source["content_status"], "canonical_url": source["canonical_url"],
            "published": source.get("published") or None, "source_kind_label": source.get("kind") or "external source",
            "content_version": source["content_version"], "source_id": source["source_id"],
            "body_origin": source["body_origin"], "completeness": source["completeness"],
            "source_classification": source["source_classification"], "readable": available,
            "unavailable_reason": unavailable_reason or source.get("unavailable_reason"),
        }

    def catalog(self, tenant_key: str, user_id: str) -> list[dict[str, Any]]:
        active = self._active(tenant_key, user_id)
        if not active:
            return []
        root, manifest = active
        shelves: dict[str, dict[str, Any]] = {}
        for source in manifest["sources"]:
            if source["state"] != "active":
                continue
            available = source["content_status"] not in {"link_only", "unavailable"}
            unavailable_reason = source.get("unavailable_reason")
            integrity_failed = False
            if available:
                try:
                    for key in ("source_record", "source_snapshot", "readable_body"):
                        if source.get(key):
                            self._verified_bytes(root, source[key])
                except OwnerPrivateBookshelfError:
                    available = False
                    integrity_failed = True
                    unavailable_reason = "本地内容完整性校验失败"
            book = self._book(source, available=available, unavailable_reason=unavailable_reason)
            if integrity_failed:
                book["content_status"] = "unavailable"
            label = book["group_label"]
            shelf_id = "owner-private/follow-builders/" + hashlib.sha256(label.casefold().encode()).hexdigest()[:16]
            shelf = shelves.setdefault(shelf_id, {"id": shelf_id, "title": label, "security_level": "owner_private", "books": []})
            shelf["books"].append(book)
        for shelf in shelves.values():
            shelf["books"].sort(key=lambda item: item["title"])
            shelf["book_count"] = len(shelf["books"])
        return sorted(shelves.values(), key=lambda item: item["title"].casefold())

    def collection(self, tenant_key: str, user_id: str) -> dict[str, Any] | None:
        active = self._active(tenant_key, user_id)
        if not active:
            return None
        _, manifest = active
        return {"id": manifest["collection_id"], "title": manifest["collection_title"],
                "visibility": "owner_private", "authority_count": len(manifest["authorities"]),
                "source_count": len(manifest["sources"]), "authorities": manifest["authorities"]}

    def read_book(self, tenant_key: str, user_id: str, book_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        active = self._active(tenant_key, user_id)
        if not active:
            raise OwnerPrivateContentUnavailable("owner collection is unavailable")
        root, manifest = active
        source = next((item for item in manifest["sources"] if item["book_id"] == book_id), None)
        if not source or source["state"] != "active":
            raise OwnerPrivateContentUnavailable("source is missing or withdrawn")
        readable = source.get("readable_body")
        if source["content_status"] in {"link_only", "unavailable"} or not readable:
            raise OwnerPrivateContentUnavailable("source is link-only")
        try:
            for key in ("source_record", "source_snapshot"):
                if source.get(key):
                    self._verified_bytes(root, source[key])
            markdown = self._verified_bytes(root, readable).decode("utf-8")
        except (OwnerPrivateBookshelfError, UnicodeError) as exc:
            raise OwnerPrivateContentUnavailable("source artifacts failed integrity verification") from exc
        sections = reader_sections(markdown, preserve_source_whitespace=True)
        if not sections:
            raise OwnerPrivateContentUnavailable("readable artifact is empty")
        book = self._book(source)
        # Internal model guard is derived from the hash-verified live artifact,
        # never public request flags; ordinary owner-private reading is unchanged.
        from backend.services.knowledge_catalog import markdown_model_control
        book["_model_disclosure_controlled"] = markdown_model_control(markdown)
        body = {"book_id": book_id, "title": book["title"], "author": book["author"],
                "content_version": source["content_version"], "edition": 1,
                "citation": source["canonical_url"], "sections": sections,
                "content_status": source["content_status"], "source_kind": "owner_private_external",
                "canonical_url": source["canonical_url"], "source_snapshot_hash": source.get("source_snapshot_hash"),
                "readable_body_hash": source.get("readable_body_hash"), "body_origin": source["body_origin"],
                "completeness": source["completeness"], "source_classification": source["source_classification"]}
        return book, body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export/import owner-private Follow Builders sources")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--source-root", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--audit", type=Path)
    export.add_argument("--scope-file", type=Path)
    export.add_argument("--expected-sources", type=int)
    export.add_argument("--expected-authorities", type=int)
    for command in (export,):
        command.add_argument("--tenant", required=True)
        command.add_argument("--user", required=True)
    for name in ("import", "rollback"):
        command = commands.add_parser(name)
        command.add_argument("--store", type=Path, required=True)
        command.add_argument("--tenant", required=True)
        command.add_argument("--user", required=True)
        if name == "import":
            command.add_argument("--package", type=Path, required=True)
            command.add_argument("--expected-current", required=True, help="release SHA or 'none'")
        else:
            command.add_argument("--expected-current", required=True)
            command.add_argument("--target-release", required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        result = export_follow_builders(
            args.source_root, args.output, args.tenant, args.user, audit_path=args.audit,
            scope_path=args.scope_file, expected_sources=args.expected_sources,
            expected_authorities=args.expected_authorities,
        )
    else:
        store = OwnerPrivateBookshelfStore(args.store)
        if args.command == "import":
            expected = None if args.expected_current == "none" else args.expected_current
            result = store.import_package(args.package, args.tenant, args.user, expected_current=expected)
        else:
            result = store.rollback(args.tenant, args.user, expected_current=args.expected_current, target_release=args.target_release)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
