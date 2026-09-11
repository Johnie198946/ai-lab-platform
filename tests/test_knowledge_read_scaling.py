"""Synthetic vault regressions: scan complexity, live barriers and loop liveness.

These are local fixtures, not production/business latency measurements.
"""
import asyncio
import json
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from backend.api import knowledge as k
from backend.api import knowledge_policy as gateway
from backend.api.tenant import current_visibility
from backend.services import knowledge_catalog as catalog


def test_empty_candidate_reads_do_not_consume_scan_capacity(monkeypatch):
    async def forbidden_worker(*args, **kwargs):
        pytest.fail("empty candidates must not submit disk work")

    monkeypatch.setattr(catalog, "run_knowledge_read", forbidden_worker)

    async def concurrent_empty_reads():
        return await asyncio.gather(*(
            catalog.filter_database_live_documents([]) for _ in range(20)
        ))

    assert asyncio.run(concurrent_empty_reads()) == [[] for _ in range(20)]


@pytest.fixture
def vault(tmp_path, monkeypatch):
    def create(count=12):
        (tmp_path / "wiki").mkdir(exist_ok=True)
        documents = []
        for i in range(count):
            relative = f"wiki/topic-{i}.md"
            (tmp_path / relative).write_text(
                f"---\ntitle: topic-{i}\nstatus: active\n---\n"
                f"# topic-{i}\nEvidence [[topic-{(i + 1) % count}]] [[unknown|PRIVATE]].\n")
            documents.append({"path": relative, "pack_id": "public", "security_level": "green",
                              "classification_status": "approved", "knowledge_level": "K5"})
        (tmp_path / "knowledge_catalog.json").write_text(json.dumps({
            "version": "2.0", "documents": documents, "packs": []}))
        matrix = {"entity_index": {f"topic-{i}": [d["path"]] for i, d in enumerate(documents)},
                  "categories": {"public": {d["path"]: {**d, "title": "topic"} for d in documents}}}
        monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
        monkeypatch.setattr(k, "_matrix", lambda: matrix)
        catalog.clear_knowledge_caches()
        return documents, matrix
    return create


@pytest.mark.parametrize("count", [8, 32])
@pytest.mark.parametrize("operation", ["search", "iter", "entities", "links", "model", "detail", "list", "matrix", "stats"])
def test_one_candidate_scan_and_linear_live_reads(vault, monkeypatch, tmp_path, count, operation):
    _, matrix = vault(count)
    scans, reads = [], []
    original_index, original_live = k.document_index, catalog._live_frontmatter
    def index(root):
        scans.append(root)
        return original_index(root)
    def live(*args, **kwargs):
        reads.append(args[1])
        return original_live(*args, **kwargs)
    monkeypatch.setattr(k, "document_index", index)
    monkeypatch.setattr(catalog, "_live_frontmatter", live)
    links = " ".join(f"[[topic-{i}]]" for i in range(count))
    operations = {
        "search": lambda: k._search_docs(tmp_path, "topic", count),
        "iter": lambda: list(k._iter_md_files(tmp_path)),
        "entities": lambda: k._filtered_entity_index(matrix),
        "links": lambda: k._visible_wikilinks(links, tmp_path),
        "model": lambda: k._model_text(links, "wiki/topic-0.md", tmp_path),
        "detail": lambda: k.get_wiki("topic-0"),
        "list": k.list_wiki, "matrix": k.get_matrix, "stats": k.get_stats,
    }
    assert operations[operation]()
    assert len(scans) == 1
    assert count <= len(reads) <= 16 * count
    assert k._CANDIDATE_INDEX.get() is None


def test_request_candidates_never_cache_live_authorization(vault, tmp_path):
    vault()
    documents = catalog.document_index(tmp_path)
    with k._candidate_scope(tmp_path, documents):
        assert k._rel_visible("wiki/topic-0.md", {"public"})
        assert not k._rel_visible("wiki/topic-0.md", {"another-tenant"})
        assert not k._rel_visible("wiki/unknown.md", None)
        target = tmp_path / "wiki/topic-0.md"
        target.write_text(target.read_text().replace("status: active", "status: withdrawn"))
        assert not k._rel_visible("wiki/topic-0.md", {"public"})
        assert k._visible_wikilinks("[[topic-0|PRIVATE]]", tmp_path) == []
        assert k._model_text("[[topic-0|PRIVATE]]", "wiki/topic-1.md", tmp_path) == ""
    assert k._CANDIDATE_INDEX.get() is None


@pytest.mark.parametrize("change", ["symlink", "malformed", "unreadable"])
def test_live_target_failure_is_not_legacy_approval(vault, tmp_path, monkeypatch, change):
    vault()
    documents = catalog.document_index(tmp_path)
    target = tmp_path / "wiki/topic-0.md"
    if change == "symlink":
        outside = tmp_path.parent / (tmp_path.name + "-secret.md")
        outside.write_text("PRIVATE")
        target.unlink()
        target.symlink_to(outside)
    elif change == "malformed":
        target.write_text("---\nstatus: [broken\n---\nPRIVATE")
    else:
        original = type(target).open
        def fail(path, *args, **kwargs):
            if path == target:
                raise PermissionError("synthetic unreadable file")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(type(target), "open", fail)
    with k._candidate_scope(tmp_path, documents):
        assert not k._rel_visible("wiki/topic-0.md", None)


def test_hidden_link_is_not_restored_by_empty_snippet_fallback(vault, tmp_path):
    vault(1)
    (tmp_path / "wiki/topic-0.md").write_text("# topic-0\n[[unknown|PRIVATE]]")
    docs = k._search_docs(tmp_path, "topic", 1)
    assert len(docs) == 1
    assert "PRIVATE" not in json.dumps(docs)


def test_partial_iterator_does_not_leave_candidate_context(vault, tmp_path):
    vault()
    iterator = k._iter_md_files(tmp_path)
    assert next(iterator)
    assert k._CANDIDATE_INDEX.get() is None
    iterator.close()
    assert k._CANDIDATE_INDEX.get() is None


@pytest.mark.parametrize("oversized", [False, True])
def test_live_frontmatter_reads_only_bounded_header(vault, tmp_path, monkeypatch, oversized):
    vault(1)
    target = tmp_path / "wiki/topic-0.md"
    header = "---\nstatus: active\n" + ("padding: " + "x" * 70_000 + "\n" if oversized else "") + "---\n"
    target.write_text(header + "PRIVATE BODY" * 100_000)
    original = type(target).open
    bytes_read = []
    class Tracked:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.handle.close()
        def readline(self, size):
            value = self.handle.readline(size)
            bytes_read.append(len(value))
            return value
    def open_file(path, *args, **kwargs):
        handle = original(path, *args, **kwargs)
        return Tracked(handle) if path == target else handle
    monkeypatch.setattr(type(target), "open", open_file)
    metadata = catalog._live_frontmatter(tmp_path, "wiki/topic-0.md")
    if oversized:
        assert metadata is catalog._UNREADABLE_FRONTMATTER
        assert sum(bytes_read) <= 65_537
    else:
        assert metadata == {"status": "active"}
        assert sum(bytes_read) == len(header.encode())


async def wait_entered(event):
    async def poll():
        while not event.is_set():
            await asyncio.sleep(0.001)
    await asyncio.wait_for(poll(), 2)


@pytest.mark.asyncio
async def test_worker_capacity_cancellation_and_context_reset(monkeypatch):
    monkeypatch.setattr(catalog, "_READ_WORKERS", threading.BoundedSemaphore(1))
    entered, release = threading.Event(), threading.Event()
    def blocking():
        assert current_visibility.get() == frozenset({"tenant-a"})
        current_visibility.set(frozenset({"worker-only"}))
        assert catalog.AUTHORIZED_DOCUMENT_PATHS.get() == frozenset({"tenant-a.md"})
        entered.set()
        assert release.wait(3)
        assert current_visibility.get() == frozenset({"worker-only"})
        assert catalog.AUTHORIZED_DOCUMENT_PATHS.get() == frozenset({"tenant-a.md"})
    token = current_visibility.set(frozenset({"tenant-a"}))
    paths_token = catalog.AUTHORIZED_DOCUMENT_PATHS.set(frozenset({"tenant-a.md"}))
    task = asyncio.create_task(catalog.run_knowledge_read(blocking))
    try:
        await wait_entered(entered)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(HTTPException) as error:
            await catalog.run_knowledge_read(lambda: None)
        assert error.value.status_code == 503
        assert current_visibility.get() == frozenset({"tenant-a"})
    finally:
        release.set()
        current_visibility.reset(token)
        catalog.AUTHORIZED_DOCUMENT_PATHS.reset(paths_token)
        await asyncio.gather(*list(catalog._READ_TASKS))
        await asyncio.sleep(0)
    token = current_visibility.set(frozenset({"tenant-b"}))
    try:
        assert await catalog.run_knowledge_read(current_visibility.get) == frozenset({"tenant-b"})
        assert await catalog.run_knowledge_read(catalog.AUTHORIZED_DOCUMENT_PATHS.get) is None
    finally:
        current_visibility.reset(token)


def fake_gateway_policy(monkeypatch):
    claims = {"tenant_key": "synthetic-reader", "user_id": "fixture-user", "policy_version": "fixture-v1",
              "scopes": ["public"], "sources": ["tenant_knowledge", "user_notes"]}
    monkeypatch.setattr(gateway, "verify_capability", lambda _: claims)
    async def policy(*args, **kwargs):
        return SimpleNamespace(policy_version="fixture-v1"), None
    monkeypatch.setattr(gateway, "resolve_policy", policy)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["gateway", "http"])
async def test_ready_responds_while_search_is_running(vault, tmp_path, monkeypatch, entry):
    vault()
    fake_gateway_policy(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()
    original = k._search_docs
    def slow(*args, **kwargs):
        assert threading.get_ident() != main_thread
        if entry == "gateway":
            assert current_visibility.get() == frozenset({"public"})
        assert k._CANDIDATE_INDEX.get() is not None
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(k, "_search_docs", slow)
    for module, name in [(gateway, "compute_catalog"), (k, "document_index"),
                         (catalog, "_file_live_documents")]:
        function = getattr(module, name)
        def checked(*args, _function=function, **kwargs):
            assert threading.get_ident() != main_thread
            return _function(*args, **kwargs)
        monkeypatch.setattr(module, name, checked)
    def notes(**kwargs):
        assert threading.get_ident() != main_thread
        assert kwargs["tenant_key"] == "synthetic-reader"
        assert kwargs["user_id"] == "fixture-user"
        return []
    monkeypatch.setattr(gateway, "search_user_notes", notes)
    app = FastAPI()
    app.include_router(gateway.router)
    app.include_router(k.router)
    @app.get("/ready")
    async def ready():
        return {"ready": True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://fixture") as client:
        request = (client.post("/api/internal/knowledge/search", json={"query": "topic", "include_content": True})
                   if entry == "gateway" else client.get("/api/knowledge/search?q=topic"))
        task = asyncio.create_task(request)
        try:
            await wait_entered(entered)
            response = await asyncio.wait_for(client.get("/ready"), 0.5)
            assert response.json() == {"ready": True}
            assert not task.done()
        finally:
            release.set()
        response = await task
    assert response.status_code == 200, response.text
    assert response.json()["docs"]
    assert k._CANDIDATE_INDEX.get() is None
    assert catalog.AUTHORIZED_DOCUMENT_PATHS.get() is None


@pytest.mark.asyncio
async def test_cancelled_http_request_retains_worker_admission(vault, monkeypatch):
    vault(1)
    fake_gateway_policy(monkeypatch)
    monkeypatch.setattr(catalog, "_READ_WORKERS", threading.BoundedSemaphore(1))
    entered, release = threading.Event(), threading.Event()
    original = k._search_docs
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        # Request teardown must not replace the old worker's admission proof.
        assert current_visibility.get() == frozenset({"public"})
        assert catalog.AUTHORIZED_DOCUMENT_PATHS.get() == frozenset({"wiki/topic-0.md"})
        return original(*args, **kwargs)
    monkeypatch.setattr(k, "_search_docs", blocked)
    app = FastAPI()
    app.include_router(gateway.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://fixture") as client:
        task = asyncio.create_task(client.post("/api/internal/knowledge/search", json={
            "query": "topic", "sources": ["tenant_knowledge"]}))
        try:
            await wait_entered(entered)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            for _ in range(3):
                response = await client.post("/api/internal/knowledge/search", json={"query": "topic"})
                assert response.status_code == 503
                assert response.headers["Retry-After"] == "1"
        finally:
            release.set()
            await asyncio.gather(*list(catalog._READ_TASKS))
            await asyncio.sleep(0)
    assert k._CANDIDATE_INDEX.get() is None
    assert catalog.AUTHORIZED_DOCUMENT_PATHS.get() is None
    assert await catalog.run_knowledge_read(lambda: "available") == "available"


@pytest.mark.asyncio
async def test_gateway_rechecks_policy_after_search(vault, monkeypatch):
    vault(1)
    fake_gateway_policy(monkeypatch)
    calls = []
    async def changing_policy(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(policy_version="fixture-v1" if len(calls) == 1 else "revoked-v2"), None
    monkeypatch.setattr(gateway, "resolve_policy", changing_policy)
    with pytest.raises(HTTPException) as error:
        await gateway.capability_search(gateway.GatewaySearchRequest(
            query="topic", sources=["tenant_knowledge"]), "fixture")
    assert error.value.status_code == 403
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_gateway_rechecks_withdrawal_after_content(vault, tmp_path, monkeypatch):
    vault(1)
    fake_gateway_policy(monkeypatch)
    original = gateway._read_model_content
    def withdraw(*args, **kwargs):
        text = original(*args, **kwargs)
        target = tmp_path / "wiki/topic-0.md"
        target.write_text(target.read_text().replace("status: active", "status: withdrawn"))
        return text
    monkeypatch.setattr(gateway, "_read_model_content", withdraw)
    with pytest.raises(HTTPException) as error:
        await gateway.capability_search(gateway.GatewaySearchRequest(
            query="topic", sources=["tenant_knowledge"], include_content=True), "fixture")
    assert error.value.status_code == 409
    assert k._CANDIDATE_INDEX.get() is None
    assert catalog.AUTHORIZED_DOCUMENT_PATHS.get() is None


@pytest.mark.asyncio
async def test_gateway_perf_observability_is_internal_optional_and_fail_open(vault, monkeypatch):
    vault(1)
    fake_gateway_policy(monkeypatch)
    writes = []
    class Sink:
        def put_nowait(self, payload):
            writes.append(payload)
    monkeypatch.setattr(gateway, "_PERF_LOG_QUEUE", Sink())

    request = gateway.GatewaySearchRequest(
        query="PRIVATE_QUERY_MUST_NOT_ENTER_LOGS",
        sources=["tenant_knowledge"],
        book_id=None,
        content_version=None,
        section=None,
    )
    monkeypatch.setattr(gateway, "_PERF_OBSERVE", False)
    baseline = await gateway.capability_search(request, "fixture")
    assert writes == []

    monkeypatch.setattr(gateway, "_PERF_OBSERVE", True)
    observed = await gateway.capability_search(request, "fixture")
    assert observed == baseline
    assert len(writes) == 1
    line = writes[0].decode("ascii")
    assert line.startswith("knowledge_gateway_perf_v1 route=tenant_wiki_success ")
    assert "PRIVATE_QUERY_MUST_NOT_ENTER_LOGS" not in line
    assert "synthetic-reader" not in line
    for phase in (
        "capability_ms", "catalog_ms", "initial_policy_ms",
        "candidate_authorization_ms", "lexical_search_ms",
        "content_assembly_ms", "final_authorization_ms",
        "final_policy_audit_ms", "total_ms",
    ):
        assert f"{phase}=" in line

    class FullSink:
        def put_nowait(self, _payload):
            raise gateway.queue.Full
    monkeypatch.setattr(gateway, "_PERF_LOG_QUEUE", FullSink())
    assert await gateway.capability_search(request, "fixture") == baseline

    monkeypatch.setattr(gateway, "_PERF_LOG_QUEUE", Sink())
    monkeypatch.setattr(gateway, "search_user_notes", lambda **_: [])
    await gateway.capability_search(
        gateway.GatewaySearchRequest(
            query="note", sources=["user_notes"],
            book_id=None, content_version=None, section=None,
        ),
        "fixture",
    )
    assert len(writes) == 1

    from backend.services.knowledge_publication_store import PUBLICATION_CATEGORY, PublicationStore
    monkeypatch.setattr(gateway, "verify_capability", lambda _: {
        "tenant_key": "synthetic-reader", "user_id": "fixture-user",
        "policy_version": "fixture-v1",
        "scopes": ["public", PUBLICATION_CATEGORY],
        "sources": ["tenant_knowledge"],
    })
    monkeypatch.setattr(PublicationStore, "search", lambda *_: [])
    await gateway.capability_search(
        gateway.GatewaySearchRequest(
            query="publication", category_scope=[PUBLICATION_CATEGORY],
            sources=["tenant_knowledge"], book_id=None,
            content_version=None, section=None,
        ),
        "fixture",
    )
    assert len(writes) == 1
