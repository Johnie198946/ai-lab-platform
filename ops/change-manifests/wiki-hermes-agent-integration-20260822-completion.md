# Completion Manifest

- task_id: `wiki-hermes-agent-integration-20260822`
- objective: Correct the Wiki-versus-note domain model, restore tenant-scoped Wiki evidence in chat, enable Hermes delegation for insight tasks, and add only the user-Markdown transport into AI Lab's existing compiler pipeline.
- branch: `codex/wiki-agent-integration`
- worktree: `/private/tmp/ai-lab-wiki-agent-integration`
- base_head: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`

## Changed files

- `backend/api/knowledge.py`
- `backend/api/chat.py`
- `backend/api/knowledge_sync.py`
- `backend/main.py`
- `scripts/hermes_bridge.py`
- `tests/test_knowledge_api.py`
- `tests/test_chat_api.py`
- `tests/test_knowledge_sync_api.py`
- `tests/test_wiki_chat_bridge.py`
- `docs/wiki-hermes-chat-architecture.md`
- `research/wiki-hermes-agent/outline.yaml`
- `research/wiki-hermes-agent/fields.yaml`

## Pre-flight Git inventory

- status: clean new worktree at task start (`## codex/wiki-agent-integration`)
- branch: `codex/wiki-agent-integration`
- HEAD: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- remote: none configured
- worktrees observed:
  - `/Users/dengzhaoyu/Documents/AI Lab` on `feature/gsap-motion-system`
  - `/private/tmp/ai-lab-knowledge-notion-ui` on `codex/knowledge-notion-ui` with unrelated uncommitted iOS changes
  - `/private/tmp/ai-lab-platform-token-main` on `main`
  - `/private/tmp/ai-lab-wiki-agent-integration` on this task branch
  - `/Users/dengzhaoyu/Documents/AI Lab/ai-lab-platform-showroom` on `codex/showroom-visitor-session-v17`

## Verification

- `PYTHONPATH=. pytest -q tests/test_knowledge_api.py tests/test_chat_api.py tests/test_chat_stream_api.py tests/test_wiki_chat_bridge.py tests/test_knowledge_policy_v2.py tests/test_hermes_bridge.py tests/test_chat_agent_routing.py tests/test_knowledge_sync_api.py`
  - result: `79 passed`
- `ruff check backend/api/knowledge_sync.py tests/test_knowledge_sync_api.py tests/test_wiki_chat_bridge.py`
  - result: passed
- `python3 -m py_compile backend/api/chat.py backend/api/knowledge.py backend/api/knowledge_sync.py backend/main.py scripts/hermes_bridge.py`
  - result: passed
- `git diff --check`
  - result: passed
- Full-suite diagnostic:
  - initial collection is blocked by an existing Starlette/httpx `TestClient` incompatibility in `tests/test_agents_api.py`.
  - excluding that file produced `423 passed, 23 failed, 3 errors`; failures are legacy/stale isolation and orchestration contracts plus `tools/test_retrieval.py` fixture collection, outside this change. Relevant targeted suites pass.

## Delivery state

- status: `VERIFIED`
- commit_sha: `6540ffbd3dba3ced82ed6be1146b35912e2e6b41`
- GitHub remote/ref/SHA: `https://github.com/Johnie198946/ai-lab-platform.git`; refs `main` and `codex/wiki-agent-integration`; verified with `git ls-remote` at `6540ffbd3dba3ced82ed6be1146b35912e2e6b41`
- server_before: `/opt/ai-lab-platform/.deployed-sha` was `a3e12a5ccfecd595fe86bcb0b41afcff1c7262db`; health `{"status":"ok","version":"0.8.0"}`
- server_after: `/opt/ai-lab-platform/.deployed-sha` is `f064dbf3e81682a7228430952d04feafa6039a69`; Docker Compose services rebuilt; `hermes-bridge` systemd service active
- health_check: `bash scripts/update.sh f064dbf3e81682a7228430952d04feafa6039a69` passed runtime contract audit; `curl http://127.0.0.1:8000/health` returned `{"status":"ok","version":"0.8.0"}`
- functional_check: server-side authenticated smoke query `超聚变是做什么的？` returned HTTP 200 with Wiki sources including `wiki/产品/超聚变官网洞察.md` and `wiki/竞品情报/华为vs超聚变一页纸.md`; local targeted suite after remote-main merge: `90 passed`
- rollback_point: `/opt/ai-lab-platform-backups/wiki-hermes-agent-integration-20260822-115508.tgz`

## Remaining risks

- The current chat loop performs one request-scoped Wiki retrieval before Hermes reasoning. Full iterative `wiki_search/wiki_read/wiki_neighbors` requires a request-context-aware MCP tool server in the next phase.
- Production validation requires the mounted Vault and real `knowledge_catalog.json`/`knowledge_matrix.json`; repository data intentionally does not include them.
- The iOS local note store exists on the separate `codex/knowledge-notion-ui` task branch. Its client-side uploader must be integrated after these branches are reconciled; this task provides the server sync contract only.
- Final manifest and server marker refer to the same verified SHA.
