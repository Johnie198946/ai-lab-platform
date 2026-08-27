# Change Manifest — QuantumWorkspace M0

```yaml
task_id: 20260827-1556-quantumworkspace-m0
repo: platform
owner: hermes-main-session
scope:
  - frontend/
  - backend/
  - tests/
  - migrations/
  - ops/change-manifests/20260827-1556-quantumworkspace-m0.md
  - ops/change-manifests/20260827-1556-quantumworkspace-m0-completion.md
base: e10ff99fb1e7b98a60f18a1ec6837da8dcae4f3b
change_type: CODE_RELEASE
status: active
rollback: "GitHub revert final delivery commit(s); server: bash /opt/ai-lab-platform/scripts/update.sh e10ff99fb1e7b98a60f18a1ec6837da8dcae4f3b"
```

## Scope lock

- 独立 clone：`/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- 唯一开发/交付分支：`main`
- 复用候选：`8556928796bc85f65beaef46044845ba14eb8a50` 的 Taskboard 透明投影；以补丁方式迁入，不把功能分支作为新基线。
- AI Lab 保持 Workflow/Execution/Event/Artifact/Usage 唯一事实源；Hermes 保持唯一 Runtime。
- 禁止提交 Vault、runtime data、`.env`、凭据、证书私钥或第三方 Sim 源码。

## Required release evidence

```yaml
commit_sha: pending
remote_sha: pending
server_before: pending
server_after: pending
deploy_time: pending
health_check: pending
functional_check: pending
rollback_point: e10ff99fb1e7b98a60f18a1ec6837da8dcae4f3b
independent_verifier: pending
```
