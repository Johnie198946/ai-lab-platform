---
title: Cloud user complaint feedback completion
task_id: cloud-user-complaint-feedback-20260829
status: TESTED
date: 2026-08-29
tags:
  - ops/change-manifest
  - feedback
---

# Cloud user complaint feedback completion

## Delivery receipt

- **branch:** `main`
- **worktree:** `/Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828`
- **base head:** `daf3e200069e0c8194ca8d341f88dab9d341d9c0`
- **local commit:** pending
- **remote SHA:** `daf3e200069e0c8194ca8d341f88dab9d341d9c0` before this change
- **server before:** `a33f1c65a0bf19ddf59f95131f3d47dd8607d597`
- **server after:** not deployed
- **rollback point:** `/opt/releases/ai-lab-platform-a33f1c65a0bf.YQvuls`
- **protocol:** `ops/protocols/cloud-user-complaint-feedback-v1.yaml`

## Scope

- Deterministic complaint classification on the current user message only.
- Sanitized excerpts and HMAC-scoped identifiers in `feedback_events`.
- Per-user/content HMAC deduplication within the 90-day retention window, PostgreSQL-atomic daily rate limiting, and concurrent reconnect folding.
- Shared capture path for `/api/chat` and `/api/chat/stream`.
- SSE `feedback_receipt` only after durable persistence.
- Deterministic daily digest with PostgreSQL advisory lock, durable delivery ledger, and retry.
- Inferred complaints retain only category metadata; explicit excerpts are redacted and expire after 90 days.
- A user can type `撤销刚才的反馈` to revoke the latest scoped record.
- iOS receipt decoding and visible toast.
- No Hermes Core, Memory, Wiki, Skill, training-set, assistant-output, tool-output, or quoted-context ingestion.

## Verification

- Backend full suite: `809 passed, 2 skipped, 10 warnings`.
- Feedback/chat/deployment-contract targeted suite: `66 passed, 6 warnings`.
- iOS changed-contract tests: `2 passed` (SSE and ordinary response DTO).
- Live PostgreSQL transaction-lock primitive: contended connection returned `false`; after holder commit returned `true` (read-only SQL, no business tables changed).
- Server HMAC source: dedicated feedback key absent, stable auth secret present (48 characters; value never read or logged).
- iOS `WorkflowLifecycleDTOTests`: `28 passed` within full run.
- iOS full run: `32 passed, 1 unrelated existing failure` in `KnowledgeNoteStoreTests.testReloadAndIndexedSearchScaleToOneThousandNotes`; isolated rerun reproduced `notes.count == 0`, and this task does not modify the note store.
- `git diff --check`: passed.

## Three-party review

- Required rounds: 3; completed rounds: 5.
- `main_agent`: **APPROVE**.
- `supervision`: **APPROVE** after reproducible DLP and retention-contract findings were fixed.
- `coder`: **APPROVE** after PostgreSQL locking, concurrent dedupe, retry stability, and both client contracts were verified.
- Signed protocol: `ops/protocols/cloud-user-complaint-feedback-v1.yaml`.

## Production blockers

> [!danger] Deployment is blocked
> The live server runs `a33f1c65a0bf19ddf59f95131f3d47dd8607d597`, which is not an ancestor or descendant of GitHub `main` at `daf3e200069e0c8194ca8d341f88dab9d341d9c0`. Deploying current `main` would regress independently deployed Quantum Workspace changes. Repository policy forbids automatic merge/rebase on divergence.

> [!warning] Feishu delivery is not configured
> The live API container reports `FEISHU_WEBHOOK_CONFIGURED=no`. Real daily-message receipt cannot pass until a webhook is configured securely on the server.

## Remaining risks

- Rule-based detection deliberately prioritizes precision; euphemistic complaints may be missed.
- Ninety-day cleanup runs with the digest; if the scheduler is unavailable, deletion is delayed until its next successful transaction.
- Feishu webhook delivery is at-least-once by protocol; a stable Digest ID exposes the narrow crash-window duplicate instead of making a false exactly-once claim.
- Production deployment and real Feishu delivery remain unverified.
