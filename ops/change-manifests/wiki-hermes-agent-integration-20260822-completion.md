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

- status: `TESTED`
- commit_sha: not created; user did not request a commit
- GitHub remote/ref/SHA: not configured / not pushed / not authorized
- server_before: not inspected; deployment not authorized in this task
- server_after: not applicable
- health_check: not applicable; not deployed
- functional_check: local targeted Wiki/chat/tenant-sync tests passed
- rollback_point: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`

## Remaining risks

- The current chat loop performs one request-scoped Wiki retrieval before Hermes reasoning. Full iterative `wiki_search/wiki_read/wiki_neighbors` requires a request-context-aware MCP tool server in the next phase.
- Production validation requires the mounted Vault and real `knowledge_catalog.json`/`knowledge_matrix.json`; repository data intentionally does not include them.
- The iOS local note store exists on the separate `codex/knowledge-notion-ui` task branch. Its client-side uploader must be integrated after these branches are reconciled; this task provides the server sync contract only.
- No deployment, remote push, or production health check was performed.
