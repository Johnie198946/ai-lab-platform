# Hermes Linux Backend Rewrite

This branch is the clean server-side rewrite. The previous `backend/` and
`scripts/hermes_bridge.py` were removed in commit `7993f83`; this package is a
new implementation rather than a compatibility copy.

## Runtime boundary

```text
Authen verified JWT
  -> FastAPI tenant context
  -> RunManifest
  -> Tenant Sandbox / HERMES_HOME
  -> Hermes Linux subprocess
  -> SQLite Run + RunEvent ledger
  -> SSE / status / cancel API
```

## Required runtime configuration

```text
HERMES_BIN=hermes
AI_LAB_HERMES_TEMPLATE=/opt/ai-lab/hermes-template
AI_LAB_SANDBOX_ROOT=/var/lib/ai-lab/sandboxes
AI_LAB_STATE_DB=/var/lib/ai-lab/state/runs.sqlite3
AUTHEN_JWKS_URL=<configured at deployment>
AI_LAB_ALLOW_DEV_AUTH=0
```

The backend never trusts a client tenant header. The tenant is derived from
the verified authentication claims. Each run receives a server-generated
manifest and an isolated `HERMES_HOME`; credentials are not copied from the
template.

## API compatibility surface

```text
GET  /health
GET  /ready
POST /api/chat
POST /api/chat/stream
GET  /api/chat/status/{session_id}
POST /api/chat/stream/cancel
```

## Current state

The new backend is an initial runnable core, not a production deployment. The
remaining rewrite slices are knowledge governance, catalog/subscription APIs,
workflow APIs, durable cancellation/reconnect semantics, JWKS verification,
and the server rollout migration. No server has been modified by this commit.
