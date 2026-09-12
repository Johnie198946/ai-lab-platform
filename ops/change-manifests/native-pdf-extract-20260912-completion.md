# native-pdf-extract-20260912 completion

- task_id: native-pdf-extract-20260912
- status: TESTED (publication/deployment evidence is recorded after execution)
- branch: main
- worktree: authorized platform worktree; clean at entry
- baseline: aaaef7f2b120f86cc41991ba16b18da9a8656c7d; fetch confirmed origin/main equal
- repository visibility: Public, independently checked through the native web extraction tool
- authorization: scoped source publication and default Mac plugin deployment; no cloud/profile changes

## Change and boundaries

The existing native extract provider remains the sole entry. URL scheme, public-address,
website policy and each-redirect checks are unchanged. PDF is identified by exact MIME
plus `%PDF-` signature, or signature with absent/octet-stream MIME. Conflicting MIME,
bad PDFs, encrypted PDFs and missing text layers fail explicitly. No CAPTCHA bypass,
new user-agent workaround, new Agent/runtime, shell PDF executable or network bypass.

Uses pypdf 6.14.2 (BSD-3-Clause, Python >=3.9), preferring the active runtime library,
with a plugin-local dependency directory when absent. A fixed offline Python worker
makes parsing killable without any URL or shell invocation. PDF wire/decompressed-body
cap: 32,000,000 bytes; extraction cap: 1,000 pages and 1,000,000 text characters;
parse wall and CPU budgets: 20 seconds. PDF body download checks a 60-second budget
between transport chunks; an in-flight read retains the existing 20-second timeout.
Darwin rejects RLIMIT_DATA/AS changes on the tested host; no hard memory isolation is
claimed there. Other POSIX hosts additionally request a 512 MiB data-segment limit.
The HTML 2 MB / existing WeChat 5 MB caps and request profiles remain unchanged.

Original/final URL metadata, inline source URL, 1-based page markers, empty-text-page
warnings and explicit page/text truncation metadata are retained. This is text-layer
extraction, not OCR, signature verification or a guarantee of financial-table layout.

## Executed checks

`python3 -m pytest tests/test_native_extract_pdf.py tests/test_agency_integration.py -q`
passed: **73 tests** (30 PDF and 43 existing integration), zero failures/skips.
`git diff --check` and Python compile checks passed. Six existing dependency deprecation
warnings remain. Fixtures are generated real PDFs, not successful text mocks; transport
is synthetic/in-memory. Coverage includes a real PDF exceeding the original HTML cap,
PDF over-budget rejection, split signatures, strict MIME conflicts, bad/encrypted/empty
PDFs, mixed text layers, actual worker timeout, page/text truncation, original URL,
redirect policy/private-address/scheme barriers, redirect count, fetch budget and 403.
The first resource-limit experiment failed on Darwin and was corrected before passing.

## Publication / deployment / rollback

- head/local_commit: pending commit containing this file
- remote_sha: pending verified push
- server_before/server_after: pending default Mac plugin deployment
- health_check / functional_check: pending new-process handler acceptance
- rollback_point: to be established before any deployment, outside Git
- remaining_risks: current long-lived desktop may retain cached provider; no restart authorized

Only source, pinned dependency specification, synthetic tests and this sanitized manifest
are published. Private research URLs, raw research, credentials and operational receipts
remain outside Git. The private acceptance JSON is authoritative for observed release
SHA, deployed hashes, actual handler outcomes, rollback and runtime-cache status.
