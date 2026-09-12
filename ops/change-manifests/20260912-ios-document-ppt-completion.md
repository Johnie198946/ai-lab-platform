# iOS document-to-PPT completion record

## Delivery state

```text
task_id: 20260912-ios-document-ppt
status: RELEASED_AND_E2E_VERIFIED
branch: main
task_feature_commit: fd5f4d0fee0007999502522146e46b7e96ae243e
production_hardening_commits:
  - 64db499b372481d1dae20b8e501ee63782a9efbb
  - 50ee79f20adc56b717b761e57937ba7fd0bf86a5
  - 52996b4806f256464fe69e00cf7e193aa8a38757
  - da6b9370cc5a000071970cb14961560332581a14
  - 9e13f6dce9bafb825c96e2cd531e77c23ff30616
  - 79ba8f330344567782ae6636540560c5bf3fbbfa
production_observed_sha: 67d6f15ed575fa4f3dd561eef81413ea6e1d6238
latest_github_main_at_receipt_draft: 0e79ca56b6af25e3725004ad642f86f55435a581
rollback_sha_observed_before_task_deploy: 019ed32eb802ba3bf46875a83d7e525dc6ab965a
release_date: 2026-09-12
```

`production_observed_sha` is a later GitHub-main descendant of `79ba8f3` and therefore contains the complete document-to-PPT implementation and its production hardening. Later unrelated commits continued to land on `main`; this record does not claim the server always equals the moving branch tip.

## Delivered behavior

- Real DOCX/PDF upload with tenant-bound private original, extracted text, metadata, preview/download routes, SHA-256 integrity checks, and a 50 MB client/server upload contract.
- Extracted private text has its own digest and fails closed if missing, modified, or non-UTF-8.
- Contribution is no longer opted out by default. The iOS client sends only an explicit per-file opt-out; the server independently applies authenticated tenant consent, governance admission, async contribution, withdrawal, and non-blocking failure semantics.
- Existing Workflow/Hermes stages implement outline, design, and final review gates without adding a second runtime or knowledge system.
- Approved outline and design are bound by artifact id, content hash, and version. Final generation validates the exact approved outline slide sequence and applies the approved theme.
- The structured renderer normalizes common model aliases (`key_points`, `process/steps`, section points/subtitles, two-column title/point/nested forms), retries malformed structured JSON once, and still rejects unknown/unused fields.
- Editable PPTX and PDF preview are produced from the same final deck bytes/version. iOS exposes authenticated preview, download, Files export, and share actions.
- iOS and Dashi surfaces are fixed to light appearance; dark-mode switching and system-theme synchronization are removed.
- The production image includes LibreOffice and Noto CJK fonts, avoiding Chinese tofu glyphs in rendered previews.

## Production E2E evidence

### Upload and private-source verification

- Source document: `doc_976baabd3ba54d62b5efbd97ca47123a`
- Real DOCX upload returned HTTP 201.
- Extracted text returned HTTP 200 and contained the expected Chinese title.
- Original download returned HTTP 200, 37,086 bytes, and matched the server content hash.
- Authorized default contribution path returned `contribution_status=queued` with a queue receipt.
- A separate explicit-opt-out upload returned `contribution_status=opted_out` and no receipt.

### Multi-stage Workflow/Hermes verification

- Workflow: `wf_046043a4d2254e86bb323e98d78130c9`
- Execution: `wfr_1e464188f92b4a6ca7fe74d794c07525`
- Runtime: Hermes; provider/model receipt reported `openai-codex` / `gpt-5.6-sol`.
- Outline review approved: artifact `wfa_9d4cdf0141e443f2877ea9fc7e685da0`, SHA-256 `523a9563c31c6d72e6a1740819570e3bec1ca3335f4b3a451508003b58d75a88`, version 1.
- Design review approved: artifact `wfa_01029fb6ddb041fd9c8d8efc5e837922`, SHA-256 `eb26ebd8c0a5f85fea6e979d0d74e172840655104f422e32b2edc39ce5bcf7fe`, version 1.
- Final editable PPTX: artifact `wfa_921d6338b2bc4422ad78d1c2720f1a87`, 49,728 bytes, SHA-256 `bdb043f2ea133a2648f3e47e3015a8962d4fdbb571f9d2b7dc3c8215373e8803`.
- Same-version PDF preview: artifact `wfa_6ef17dff4ffb49c79e162e584d3a4983`, 45,028 bytes, SHA-256 `f43d62721155661dcfab93481389581544283f845e30d1ef085e7c3124aa38d3`.
- PPTX and PDF were downloaded through authenticated production routes and independently re-hashed to the values above.
- Final PPTX metadata contained the exact approved design and outline bindings listed above; preview metadata referenced the final PPTX artifact id/hash/version.
- Output approval returned HTTP 200; final execution state was `completed`, progress 100.

### Deployment and health

- Exact-SHA deployments used immutable source archives, SHA-256 verification, preloaded linux/amd64 images, image attestations, health gates, and rollback tags.
- Production was read back at GitHub SHA `67d6f15ed575fa4f3dd561eef81413ea6e1d6238`.
- API container image label matched that SHA and `/ready` returned `{"status":"ready","version":"0.8.0"}`.
- Rollback lineage remained available from the previous immutable release; deployment did not delete data volumes.

## Automated and visual verification

- Final focused backend gate on the latest integrated tree: `118 passed`.
- Final frontend gate: `149 passed`, production Vite build succeeded.
- Latest integrated iOS Debug Simulator build: `** BUILD SUCCEEDED **`.
- The built app was installed and launched on simulator `A5005DE7-3D7E-4FA0-A9D9-92967B4A699A` with a real production JWT supplied only through the Debug E2E environment hook.
- Screenshot `/tmp/ios-document-ppt-final-latest.png` showed authenticated Quantumn UI, fixed light appearance, no visible error banner/clipping, and a real document-to-presentation production run card.
- An independent read-only review returned `PASS`: approved-outline binding and extracted-text integrity were both closed; its own gates were 41 backend contract tests, 75 workflow projection/API tests, iOS build, frontend light-theme tests, compileall, and `git diff --check`.
- Production-container LibreOffice rendering and Quick Look visual inspection confirmed Chinese glyphs rendered after adding Noto CJK fonts.

## TestFlight

- App Store Connect build `1.0.3 (34)` was archived from convergence commit `45c502e28dea35515883820e0feea64c14178eea`; Git ancestry verification confirms task commit `79ba8f330344567782ae6636540560c5bf3fbbfa` is included in that archive source.
- Archive: `/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-13/Quantumn-1.0.3-34.xcarchive`; binary SHA-256 `d56014f51f7b67d7f1c4ab005bad0a80a2393a58d881946d5548492715eafcdd`.
- Xcode/App Store Connect returned `Upload succeeded`, `Uploaded package is processing`, and `EXPORT SUCCEEDED`.
- App Store Connect processing and test-group visibility could not be independently read back because the automation browser remained in an authentication-failed state after the manual login attempt. Upload is verified; tester visibility remains pending Apple/session readback.

## Evidence boundaries and remaining non-blockers

- No duplicate TestFlight build was uploaded; build 34 already contains the document-to-PPT task. Processing/test-group visibility remains pending readback.
- Current text extraction intentionally excludes legacy `.doc` and image-only/scanned PDF OCR. Complex equations and pixel-perfect recreation of arbitrary source graphics remain outside this acceptance scope.
- The selected local full-suite environment exposed unrelated pre-existing research-deposition integration failures; task-scoped backend, workflow, frontend, container, iOS, and production E2E gates passed. This record does not relabel those unrelated failures as task success.
- Concurrent unrelated commits and deployments continued during the task. Every task deployment re-read the active SHA and used compare-before-switch checks; the final production SHA is reported separately from the moving GitHub tip.
