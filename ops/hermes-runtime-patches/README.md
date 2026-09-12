# Local research deposition: native lifecycle compatibility

This is a **local integration patch**, not an upstream Hermes feature or a second runtime.

Base inspected: Hermes `63279301bcbdc185c1b07b98a9312eb0c862f26d`.

`0001-transform-output-task-scope.patch` forwards Hermes' existing canonical task and turn IDs to `transform_llm_output`. It does not generate IDs, change hook ordering, or add a scheduler. The AI Lab plugin requires those exact IDs to bind a deposit receipt to the response being delivered. Tools recover the same turn from Hermes' native observability context.

Apply only after the plugin/pipeline regression gates pass, to the intended local default-profile installation:

```sh
git apply --check /absolute/path/to/0001-transform-output-task-scope.patch
git apply /absolute/path/to/0001-transform-output-task-scope.patch
```

An already-applied patch is detected with `git apply --reverse --check`; never apply it twice. Revalidate this seam after an upstream Hermes update instead of blindly overwriting newer code.

Rollback: first disable the local plugin's `research_deposit.enabled` setting, then reverse this exact patch. Do not reset the runtime checkout or restore an entire config file over unrelated changes.

Existing processes cache imported Python modules. Files on disk are not proof of activation: verify a newly started native Hermes process and the target serving process separately. Hook exceptions remain Hermes' existing fail-open behavior; a failed observer is not a successfully completed deposit.

## Browser resolver budget

`0003-browser-deadline.patch` targets the same exact base. It passes one monotonic budget through the existing resolver, profile snapshot, startup and CLI; no new runtime. Consent and profile pins remain required. Expiry stops fallback; only newly owned resources are cleaned. Synchronous filesystem/configuration and process-creation boundaries remain cooperative, not an absolute hard whole-call guarantee.

Independent Python 3.11 macOS gate after the supervisor fix: 305 passed, 0 failed, 2 OS-specific skips across eight browser/dependency files; real-browser integration tests excluded. Apply/reverse and live consumer acceptance are separate release gates; retain backups and verify hashes.

`0003` does not depend on the unpublished `0002` DDGS experiment. Search recovery uses the existing Keenable provider configuration. Bing is unavailable in installed DDGS 9.16.0; Exa free search was observed rate-limited. Neither failure path is claimed repaired.
