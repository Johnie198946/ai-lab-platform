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
