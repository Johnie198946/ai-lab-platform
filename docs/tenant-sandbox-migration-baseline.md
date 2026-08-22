# Tenant Hermes Sandbox Migration Baseline

> task_id: 20260822-tenant-hermes-sandbox-v1
> status: baseline-frozen
> repository: ai-lab-platform
> branch: main
> baseline_commit: 749ca2f
> execution_scope: Phase 0 + Phase 1 only

## Current request path

```text
iOS ChatView
  -> APIClient.chatStream
  -> POST /api/chat/stream
  -> backend.api.chat
  -> HERMES_BRIDGE_STREAM_URL
  -> scripts/hermes_bridge.py /v1/chat/stream
  -> Hermes native runner / hermes serve
  -> SSE events back to iOS
```

## Existing compatibility contract

The migration must preserve these endpoint families and event semantics:

- `POST /api/chat/stream`
- chat status / resume path
- clarify submission and exact clarify id handling
- explicit stream cancel
- SSE events: `thought`, `delta`, `tool_start`, `tool_end`, `clarify`, `done`, `error`
- server-derived tenant context from authenticated request
- client-selected `agent_id` resolved by server capability policy

## Current runtime boundary

The current implementation still uses a host-level Hermes Bridge with global/default paths such as:

- `HERMES_BIN`
- `HERMES_CWD`
- `HERMES_STATE_DB`
- global Bridge run maps and watermarks
- global/default Hermes skill policy

Tenant agents are currently represented as effective capability/configuration snapshots. This baseline does not claim that each tenant already has an independent `HERMES_HOME`, SessionDB, memory directory, or workspace.

## Phase 1 artifact

`backend/services/hermes_template_registry.py` adds a read-only validation layer. It does not provision, copy, activate, or route traffic to a tenant Sandbox. That separation is intentional: the next phase will add `TenantSandboxManager` and only then bind Bridge execution to a validated Sandbox.

## Safety rules captured by the registry

- Template identity must match its path and manifest.
- Required manifest fields are mandatory.
- Template and manifest paths cannot escape the registry root.
- Symlinks are rejected.
- `.env`, OAuth/auth files, SessionDB, sessions, memory, and declared excluded paths are rejected.
- Declared SHA-256 file hashes are verified when present.
- Registry loading is read-only and returns a deterministic fingerprint.

## Verification commands

```bash
cd /Users/dengzhaoyu/Desktop/AI\ Lab/ai-lab-platform
PYTHONPATH=. .venv/bin/pytest -q tests/test_hermes_template_registry.py
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_hermes_template_registry.py \
  tests/test_chat_stream_api.py \
  tests/test_chat_status.py \
  tests/test_hermes_bridge.py \
  tests/test_bridge_locking.py
```

The broader bridge suite was also attempted. `tests/test_bridge_skill_binding.py` currently cannot collect its `agent.skill_commands` patch target in the local project `.venv` because the Hermes-installed `agent` package is not present. The other 120 tests in that batch passed; this dependency gap is recorded as a pre-existing environment limitation and is not changed by Phase 1.

## Non-claims

- This document does not claim tenant Sandbox isolation is complete.
- It does not claim iOS has been changed.
- It does not claim the server has been deployed.
- It does not claim OpenAgents or Multica has been integrated.
