# Selected-book longform retrieval completion

- task_id: selected-book-longform
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
- head/local_commit: 32c0e37ad2e7dedae17ad6c6eb273f9ee739475e (no commit created)
- remote_sha: origin/main 32c0e37ad2e7dedae17ad6c6eb273f9ee739475e at preflight fetch; HEAD...origin/main 0/0
- server_before: not inspected; no deployment authorized
- server_after: unchanged by this task
- health_check: not applicable; local only
- rollback_point: initial HEAD; revert only task-specific hunks if required, never other writers' files

## Governance and boundaries

Executed status/branch/HEAD/remotes/worktrees/fetch preflight. Existing publication/editorial/iOS changes belonged to coordinated parallel writers. This task did not modify knowledge_publication_store.py, publication_editorial.py or any iOS file. No git staging, commit, push or deployment.

## Task files

- backend/api/chat.py
- backend/api/knowledge_policy.py
- backend/services/knowledge_policy.py
- scripts/hermes_bridge.py
- agency/hermes-plugins/ai-lab-capabilities/__init__.py
- tests/test_selected_book_longform.py (new)
- this completion manifest

## Implemented contract

ChatContextScope preserves selected_book_id and adds optional selected_book_version and selected_book_section_id. Version mismatch fails 409; nonexistent section fails 422. The current live policy, not caller-provided visible categories, governs the initial reader lookup. Chat now injects the complete stable-ID/level TOC and retrieval instructions, not four ranked sections clipped to 12,000 characters.

Server-signed capability book_scope contains the authorized book_id and content_version, bound to existing tenant/reader identity. Existing knowledge_search accepts query plus book_id, content_version, operation=toc|read, section (stable ID or exact title), and page. A request selector cannot mint or enlarge its grant. Each page re-enters _available_book_body and checks live edition; policy is checked before read and before response audit. metadata_only is not full text. Book errors do not recommend public-web substitution. The original query-only Wiki path remains intact.

TOC pages contain at most 100 entries. Read pages contain at most 12,000 characters, with explicit truncated/next/total_pages. page means a character page, not a printed/PDF page number. Full-book traversal omits section; chapter reads include all descendants until the next peer/ancestor heading. No chapter markdown body is silently discarded. Chapter title matching supports Chinese numerals via exact titles from TOC.

The backend-to-Bridge 12,000-character goal clipping was also removed for signed book scope only: its bounded envelope is 262,144 characters; oversize book context fails explicitly, not by dropping the TOC. Ordinary chat retains its original 12,000-character budget. Legacy non-sandbox execution remains denied for signed requests.

## Actual functional checks

Python: project .venv Python 3.11.15; PYTHONPATH=.

```sh
PYTHONPATH=. .venv/bin/python -m pytest tests/test_selected_book_longform.py tests/test_wiki_chat_bridge.py tests/test_bridge_locking.py tests/test_owner_private_bookshelf.py tests/test_isolation.py tests/test_ordinary_knowledge_tool_availability.py tests/test_knowledge_disclosure_incremental.py tests/test_chat_api.py tests/test_chat_stream_api.py tests/test_chat_agent_routing.py tests/test_chat_triage.py -q --tb=short --junitxml=/tmp/selected-book-longform-results.xml
```

Result: **201 passed**, 37 warnings, 14.45s. JUnit parsed: 201 tests / 0 failures / 0 errors / 0 skipped. New selected-book suite contributes 26 tests.

The long fixture uses actual snapshot export/import and private reader authorization, chat capability minting, FastAPI Gateway and the real Hermes knowledge_search handler over in-process HTTP transport. It reconstructs a 121-section book across every returned page and verifies first/middle/last evidence; also tests huge single chapter, H2/H3/H4 inclusion, Chinese titles, TOC pagination, iOS fields, long TOC transport, missing/tampered scope, cross-book/user/tenant, stale edition, revocation and metadata-only denial. Synthetic book bytes are test fixtures, not fabricated model answers.

```sh
PYTHONPATH=. .venv/bin/python -m pytest tests/test_publication_editorial.py tests/test_daily_publication.py --import-mode=importlib -q --tb=short --junitxml=/tmp/selected-book-publication-regression.xml
```

Result: **61 passed**, 4 warnings, 2.45s. These parallel-writer regression files were not modified by this task. Initial default-import collection encountered tests.test_publication_editorial not found; explicit importlib collection with the editorial module first succeeded.

`git diff --check` passed. Deprecation/test-secret-length warnings remain; no test failures in final runs.

## Remaining risks / acceptance

- Real Hermes/model Q&A is delegated to the parent and was not run or mocked here. Passing retrieval tests does not establish answer quality or full-book synthesis under a particular model context/iteration budget.
- A capability expiry or live edition/policy change intentionally interrupts subsequent page reads; caller must refresh chat context rather than silently switch editions.
- The 262,144-character signed-book context envelope is finite. Printed-page mapping is not provided; tool page is explicitly character-based.
- Shared working tree continues to contain other writers' changes. No claim about full-repository tests, remote deployment or iOS validation.
