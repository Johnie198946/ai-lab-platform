"""Run with Hermes Python 3.11; uses real PluginContext/State and Vault module.

HERMES_SOURCE and RESEARCH_PIPELINE_MODULE may select read-only checkouts.
No live profile/Vault writes; every test owns a temporary HERMES_HOME + Vault.
"""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERMES = Path(os.environ.get("HERMES_SOURCE", str(Path.home() / ".hermes/hermes-agent")))
if not (HERMES / "hermes_cli/plugins.py").is_file():
    raise unittest.SkipTest("Native SDK integration requires HERMES_SOURCE")
sys.path.insert(0, str(HERMES))
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest

PLUGIN = Path(__file__).resolve().parents[1] / "agency/hermes-plugins/ai-lab-capabilities"
PIPELINE = Path(os.environ.get("RESEARCH_PIPELINE_MODULE", str(Path.home() / "Projects/ai-lab-vault-deposition-20260912/tools/article_research_pipeline.py")))
if not PIPELINE.is_file():
    raise unittest.SkipTest("Native SDK integration requires RESEARCH_PIPELINE_MODULE")
spec = importlib.util.spec_from_file_location("research_plugin_test", PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)])
assert spec is not None and spec.loader is not None
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)

# These are test study findings, not production evidence or manufactured execution output.
BODY = "## 事件\nA public research study https://arxiv.org/abs/2005.11401 compares two retrieval designs.\n## 要点\nThe reported benchmark result is a hypothesis, not a verified universal fact.\n## 含义\nEvaluate corpus coverage and reproduce comparisons before adoption.\n" * 4


# Privacy-safe fixtures reproduce observed CLI failure shapes.
# Real research bodies, private cron prompts and receipts remain outside this repo.
def rejected_handoff_fixture(index):
    url = f"https://example.org/research-{index}"
    analysis_label = "机制分析" if index == 0 else "分析"
    body = (
        f"Synthetic regression input, not a research finding. 测试参数：两个独立来源，不是实测结果。 Source: {url}\n事实："
        + "官方测试文档描述了一个假设性系统，版本与结果只作为测试输入，不表示真实产品能力。" * 9
        + f"\n{analysis_label}："
        + "本段用于检验交接的章节结构和逐项隔离；来源宣称与可验证事实分开，未知信息不填补。" * 9
        + "\n启示："
        + "生产结论仍应依据独立证据；此固定文本仅在临时测试目录执行，不作为入库事实或效果证明。" * 9
    )
    return {"title": f"Synthetic handoff {index}", "body": body,
            "source_urls": [url], "confidence": 0.76, "source_kind": "research_analysis"}


REJECTED_HANDOFF_FIXTURES = [rejected_handoff_fixture(i) for i in range(2)]
CRON_INTENT_FIXTURES = [
    [f"fixture-{i}", f"运行公开资料研究任务 {i}。\n\n正式 Wiki 由 Wiki Writer 处理。"]
    for i in range(8)
] + [["fixture-writer", "你是 AI Lab 唯一 Wiki Writer。\n\n核验既有研究候选。"]]


class ResearchDepositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="research-deposition-")
        self.home = Path(self.tmp.name) / "hermes"
        self.home.mkdir()
        self.vault = Path(self.tmp.name) / "vault"
        self.vault.mkdir()
        self.env = patch.dict(os.environ, {"HERMES_HOME": str(self.home), "AI_LAB_AGENT_OS_MODE": "local_single_tenant"})
        self.env.start()
        self.cfg = {"enabled": True, "vault_root": str(self.vault), "pipeline_module": str(PIPELINE), "deployment_mode": "local_single_tenant"}
        self.config_file()
        self.manager = PluginManager()
        self.ctx = PluginContext(PluginManifest(name="ai-lab-capabilities"), self.manager)
        # Real config/state/locks, real plugin import + register. Prevent unrelated
        # skill inventory monkeypatching; router gets its own scoring regression.
        self.tools = {}
        self.hooks = {}
        with patch.object(plugin, "install_capability_router"), patch.object(self.ctx, "register_web_search_provider"), \
             patch.object(self.ctx, "register_tool", side_effect=lambda **kw: self.tools.update({kw["name"]: kw["handler"]})), \
             patch.object(self.ctx, "register_hook", side_effect=lambda name, fn: self.hooks.setdefault(name, []).append(fn)):
            plugin.register(self.ctx)
        self.deposit = plugin.research_deposition
        self.scope = dict(session_id="session-a", turn_id="turn-a", task_id="task-a", platform="desktop")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def config_file(self):
        import yaml
        (self.home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"entries": {"ai-lab-capabilities": {"settings": {"research_deposit": self.cfg}}}}}))

    def inputs(self, confidence: float | None=.8):
        return dict(title="Retrieval study", body=BODY, source_urls=["https://arxiv.org/abs/2005.11401"], confidence=confidence, source_kind="research_analysis")

    def begin(self, text="研究检索设计", scope=None):
        return self.deposit.pre(text, **(scope or self.scope))

    def execute(self, inputs=None, scope=None):
        return json.loads(self.tools["ai_lab_execute"]({"capability": "research_deposit", "inputs": inputs or self.inputs()}, **(scope or self.scope)))

    def item_record(self, task=None):
        task = task or self.ctx.state.get(self.deposit.key(self.deposit.scope(self.scope)))
        return next(iter(task["items"].values()))

    def test_actual_context_config_and_registration(self):
        self.assertEqual(self.ctx.profile_name, "default")
        self.assertEqual(self.ctx.get_config("research_deposit")["vault_root"], str(self.vault))
        self.assertIn("post_llm_call", self.hooks)
        self.assertIn("ai_lab_execute", self.begin()["context"])
        out = self.execute()
        self.assertTrue(out["success"], out)
        self.assertTrue(out["complete"], out)
        self.assertEqual(out["stage"], "queued")
        self.assertFalse(out["wiki_compiled"])
        self.assertEqual(out["storage_scope"], "user_vault_existing_sync")

    def test_real_registry_dispatch_preserves_host_callback_scope(self):
        from tools.registry import registry
        with patch.object(plugin, "install_capability_router"), patch.object(self.ctx, "register_web_search_provider"):
            plugin.register(self.ctx)
        try:
            self.begin()
            out = json.loads(registry.dispatch("ai_lab_execute", {"capability": "research_deposit", "inputs": self.inputs()},
                                              scope=self.manager.scope_key, **self.scope))
            self.assertTrue(out["success"], out)
            self.assertEqual(out["receipt"]["binding"]["scope"], self.deposit.scope(self.scope))
            from model_tools import handle_function_call
            # Actual SDK drops turn_id from handler kwargs but sets approval context.
            native = json.loads(handle_function_call("ai_lab_execute", {"capability": "research_deposit", "inputs": self.inputs()},
                task_id=self.scope["task_id"], session_id=self.scope["session_id"], turn_id=self.scope["turn_id"],
                skip_pre_tool_call_hook=True, skip_tool_request_middleware=True, skip_tool_execution_middleware=True))
            self.assertTrue(native.get("success"), native)
        finally:
            self.manager.unload()

    def test_native_hook_composition_with_host_transform_scope(self):
        import ast
        host = ast.parse((HERMES / "agent/turn_finalizer.py").read_text())
        transforms = [node for node in ast.walk(host) if isinstance(node, ast.Call)
                      and node.args and isinstance(node.args[0], ast.Constant)
                      and node.args[0].value == "transform_llm_output"]
        self.assertTrue(any({"task_id", "turn_id", "session_id"} <= {kw.arg for kw in call.keywords}
                            for call in transforms), "Install the parent-owned generic finalizer scope patch")
        router = sys.modules["research_plugin_test.capability_router"]
        router._INSTALLED = False
        with patch.object(router, "_extend_tool_search"), patch.object(router, "_compact_skill_manifest"), \
             patch.object(router, "_skill_capabilities", return_value=[]), patch.object(router, "_agency_capabilities", return_value=[]), \
             patch.object(self.ctx, "register_web_search_provider"):
            plugin.register(self.ctx)
            try:
                pre = self.manager.invoke_hook("pre_llm_call", user_message="研究检索设计", **self.scope)
                self.assertTrue(any("Local research contract" in x.get("context", "") for x in pre if isinstance(x, dict)))
                self.assertEqual(len(self.manager._hooks["transform_llm_output"]), 1)
                # Exact kwargs added by the parent-owned generic finalizer patch.
                result = self.manager.invoke_hook("transform_llm_output", response_text=BODY, **self.scope)
                self.assertEqual(len(result), 1)
                self.assertIn(BODY, result[0])
                self.assertIn("研究沉淀", result[0])
                observed = self.manager.invoke_hook("post_llm_call", assistant_response=result[0], **self.scope)
                self.assertTrue(any(x.get("success") for x in observed if isinstance(x, dict)), observed)
            finally:
                self.manager.unload()
                router._INSTALLED = False

    def test_scope_context_mismatch_denied(self):
        from tools.approval import set_current_observability_context, reset_current_observability_context
        self.begin()
        tokens = set_current_observability_context(session_id="different", turn_id="wrong")
        try:
            self.assertEqual(self.execute()["error"], "host_observability_session_mismatch")
        finally:
            reset_current_observability_context(tokens)

    def test_classification_and_ambiguous_continuation(self):
        for idx, text in enumerate(["翻译 https://example.org/paper", "仅摘要 https://example.org/paper", "只回答问题 https://example.org/paper"]):
            scope = dict(self.scope, task_id=f"nonresearch-{idx}")
            self.assertIsNone(self.begin(text, scope))
            self.assertFalse(self.execute(scope=scope)["success"])
        self.begin()
        continuation = dict(self.scope, task_id="new-task", turn_id="new-turn")
        self.assertIn("blocked", self.begin("继续", continuation)["context"])
        self.assertFalse(self.execute(scope=continuation)["success"])
        same_task = dict(self.scope, turn_id="continued-turn")
        self.assertIn("Local research contract", self.begin("继续", same_task)["context"])

    def test_disabled_default_and_existing_feishu_owner(self):
        self.cfg.pop("enabled")
        self.config_file()
        self.assertFalse(self.deposit.enabled())
        self.cfg["enabled"] = True
        self.config_file()
        scope = dict(self.scope, platform="feishu", sender_id="existing-owner-surface")
        self.assertIsNotNone(self.begin(scope=scope))
        self.assertTrue(self.execute(scope=scope)["success"])

    def test_security_research_benign_query_and_actual_secret(self):
        self.begin("研究 AI secret management")
        payload = self.inputs()
        payload["title"] = "AI secret and password handling research"
        payload["source_urls"] = ["https://arxiv.org/search/?query=retrieval&searchtype=all"]
        payload["body"] += "\nhttps://arxiv.org/search/?query=retrieval&searchtype=all\n"
        self.assertTrue(self.execute(payload)["success"])
        scope = dict(self.scope, task_id="credential")
        self.begin(scope=scope)
        token = "sk-" + "abcdef1234567890" * 3
        self.assertFalse(self.execute(dict(self.inputs(), body=BODY + token), scope)["success"])
        self.assertNotIn(token, self.ctx.state.path.read_text())

    def test_completed_projection_does_not_keep_body(self):
        self.begin()
        self.assertTrue(self.execute()["success"])
        record = self.item_record()
        self.assertNotIn("body", record["payload"])
        self.assertEqual(self.deposit.materialize(record)["body"], BODY)
        self.assertNotIn(BODY, self.ctx.state.path.read_text())

    def test_post_insufficient_input_is_not_saved(self):
        self.begin()
        out = self.deposit.post(assistant_response="Still checking evidence.", **self.scope)
        self.assertFalse(out["success"])
        self.assertEqual(out["stage"], "pending")
        self.assertFalse((self.vault / "raw/pending").exists())

    def test_session_end_observes_interruption(self):
        self.begin()
        result = self.deposit.session_end(interrupted=True, completed=False, **self.scope)
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "pending")
        self.assertEqual(result["reason"], "interrupted_or_failed")

    def test_no_save_opaque_veto_and_retry(self):
        text = "研究 https://example.org/DO-NOT-COPY 只看看 不保存 TITLE-SECRET"
        self.begin(text)
        state = self.ctx.state.path.read_text()
        self.assertNotIn("DO-NOT-COPY", state)
        self.assertNotIn("TITLE-SECRET", state)
        self.begin("继续研究", dict(self.scope, turn_id="retry"))
        self.assertEqual(self.execute()["error"], "no_save")
        self.assertFalse((self.vault / "raw").exists())

    def test_no_save_variants_before_payload_copy(self):
        for idx, text in enumerate(["先不存", "不存", "不记录"]):
            scope = dict(self.scope, task_id=f"veto-{idx}")
            self.begin("研究私有素材 " + text, scope)
            self.assertEqual(self.execute(scope=scope)["error"], "no_save")
        self.assertNotIn("私有素材", self.ctx.state.path.read_text())

    def test_writer_discovers_bounded_projection_and_recovers(self):
        scopes = [dict(self.scope, task_id=f"recover-{i}") for i in range(4)]
        with patch.object(self.deposit.pipeline(), "deposit_research", side_effect=OSError("injected storage outage")):
            for scope in scopes:
                self.begin(scope=scope)
                self.assertFalse(self.execute(scope=scope)["success"])
        writer_scope = dict(self.scope, task_id="writer", turn_id="writer-turn", platform="cron")
        self.begin("Wiki Writer 编译研究素材，只消费 manifest", writer_scope)
        writer_record = self.ctx.state.get(self.deposit.key(self.deposit.scope(writer_scope)))
        self.assertNotIn("obligation", writer_record)
        # Native tool callback lacks platform; authenticated pre projection binds it.
        host_scope = self.deposit.scope(writer_scope)
        listing = self.deposit.execute({"action": "status"}, **host_scope)
        self.assertEqual(listing["total"], 4)
        self.assertEqual(listing["returned"], 3)
        self.assertTrue(listing["has_more"])
        self.assertNotIn("body", json.dumps(listing))
        results = self.deposit.execute({"action": "recover"}, **host_scope)
        self.assertEqual(results["returned"], 3)
        self.assertTrue(all(x["result"]["success"] for x in results["pending"]), results)
        self.assertEqual(self.deposit.execute({"action": "status"}, **host_scope)["total"], 1)

    def test_research_cron_governance_text_is_not_control_or_veto(self):
        scope = dict(self.scope, platform="cron")
        contract = self.begin("研究每日技术变化，按既有治理契约执行；完成后调用 ai_lab_execute research_deposit 并核验沉淀。", scope)
        self.assertIn("Local research contract", contract["context"])
        self.assertTrue(self.execute(scope=scope)["success"])
        other = dict(scope, task_id="existence")
        self.assertIn("Local research contract", self.begin("研究不存在的服务如何检测", other)["context"])

    def test_owner_status_task_needs_no_research_obligation(self):
        self.begin("查看沉淀状态")
        record = self.ctx.state.get(self.deposit.key(self.deposit.scope(self.scope)))
        self.assertTrue(record["control"])
        self.assertNotIn("obligation", record)
        out = self.deposit.execute({"action": "status"}, **self.deposit.scope(self.scope))
        self.assertEqual(out["total"], 0)
        self.deposit.post(assistant_response=BODY, **self.scope)
        self.assertFalse((self.vault / "raw").exists())

    def test_raw_written_before_manifest_failure_is_recoverable(self):
        self.begin()
        with patch.object(self.deposit.pipeline(), "append_manifest_receipt", side_effect=OSError("manifest unavailable")):
            out = self.execute()
        self.assertFalse(out["success"], out)
        key = self.deposit.key(self.deposit.scope(self.scope))
        record = self.item_record(self.ctx.state.get(key))
        self.assertTrue((self.vault / record["receipt"]["raw_path"]).is_file())
        self.assertIn("body", record["payload"])
        recovered = self.execute({"action": "recover"})
        self.assertTrue(recovered["success"], recovered)
        self.assertNotIn("body", self.item_record(self.ctx.state.get(key))["payload"])

    def test_low_and_unknown_confidence(self):
        for idx, confidence in enumerate([.59, None]):
            scope = dict(self.scope, task_id=f"low-{idx}")
            self.begin(scope=scope)
            out = self.execute(self.inputs(confidence), scope)
            self.assertTrue(out["success"], out)
            self.assertEqual(out["stage"], "saved")
            self.assertEqual(out["admission_state"], "pending")
            self.assertFalse(out["receipt"]["compile_eligible"])
        self.assertFalse((self.vault / "raw/_manifest.json").exists())

    def test_cloud_denial_and_no_model_principal(self):
        self.cfg["deployment_mode"] = "cloud_multi_tenant"
        self.config_file()
        self.assertIsNone(self.begin())
        self.assertFalse(self.execute(dict(self.inputs(), principal="local_owner"))["success"])
        self.assertFalse((self.vault / "raw").exists())

    def test_child_unknown_sender_and_sensitive_denied(self):
        for scope in [dict(self.scope, parent_session_id="parent"), dict(self.scope, platform="telegram", sender_id="stranger"), dict(self.scope, sensitivity="unknown")]:
            self.assertIsNone(self.begin(scope=scope))
            self.assertFalse(self.execute(scope=scope)["success"])
        self.assertIsNone(self.begin("研究客户私有机密", dict(self.scope, sensitivity="sensitive")))
        self.assertFalse(self.execute()["success"])

    def test_duplicate_and_concurrent_tasks(self):
        self.begin()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.execute(), range(4)))
        self.assertTrue(all(r["success"] for r in results), results)
        self.assertEqual(len({r["receipt"]["raw_path"] for r in results}), 1)
        scopes = [dict(self.scope, task_id=f"parallel-{i}", turn_id=f"turn-{i}") for i in range(4)]
        def run(scope):
            self.begin(scope=scope)
            return self.execute(scope=scope)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, scopes))
        self.assertTrue(all(r["success"] for r in results), results)
        self.assertEqual(len({r["receipt"]["raw_path"] for r in results}), 4)
        self.assertEqual(len(json.loads((self.vault / "raw/_manifest.json").read_text())), 5)

    def test_stale_receipt_scope_and_source_hash(self):
        self.begin()
        out = self.execute()
        self.assertTrue(out["success"], out)
        key = self.deposit.key(self.deposit.scope(self.scope))
        task = self.ctx.state.get(key)
        record = self.item_record(task)
        record["receipt"]["binding"]["scope"]["turn_id"] = "stale"
        self.ctx.state.set(key, task)
        self.assertFalse(self.execute({"action": "status"})["success"])
        self.assertFalse(self.deposit.verify_receipt(record))
        record["payload"]["title"] += "changed"
        self.assertFalse(self.deposit.verify_receipt(record))

    def test_tampered_raw_not_success(self):
        self.begin()
        out = self.execute()
        self.assertTrue(out["success"], out)
        raw = Path(out["receipt"]["raw_path"])
        raw = raw if raw.is_absolute() else self.vault / raw
        raw.write_text(raw.read_text() + "tampered")
        self.assertFalse(self.execute({"action": "status"})["success"])
        self.assertFalse(self.execute({"action": "recover"})["success"])

    def test_restart_repair_missing_manifest(self):
        self.begin()
        out = self.execute()
        self.assertTrue(out["success"], out)
        (self.vault / "raw/_manifest.json").unlink()
        self.deposit = plugin.ResearchDeposit(self.ctx)
        self.assertFalse(self.deposit.execute({"action": "status"}, **self.scope)["success"])
        import subprocess
        child_code = f'''import sys, importlib.util, json
sys.path.insert(0, {str(HERMES)!r})
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
spec = importlib.util.spec_from_file_location("restart_plugin", {str(PLUGIN / '__init__.py')!r}, submodule_search_locations=[{str(PLUGIN)!r}])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
ctx = PluginContext(PluginManifest(name="ai-lab-capabilities"), PluginManager())
print(json.dumps(module.ResearchDeposit(ctx).execute({{"action": "recover"}}, **{self.scope!r})))
'''
        completed = subprocess.run([sys.executable, "-c", child_code], capture_output=True, text=True, check=True)
        repaired = json.loads(completed.stdout)
        self.assertTrue(repaired["success"], repaired)
        self.assertEqual(repaired["receipt"]["raw_path"], out["receipt"]["raw_path"])

    def test_post_fallback_pending_without_invented_confidence(self):
        self.begin()
        out = self.hooks["post_llm_call"][0](assistant_response=BODY, **self.scope)
        self.assertTrue(out["success"], out)
        self.assertFalse(out["complete"])
        self.assertEqual(out["stage"], "saved")
        self.assertIn(BODY, out["response_text"])
        self.assertIn("pending", out["response_text"])
        record = self.item_record()
        self.assertIsNone(record["payload"]["confidence"])
        self.assertFalse((self.vault / "raw/_manifest.json").exists())

    def test_failure_persisted_and_bounded_recovery(self):
        self.begin()
        with patch.object(self.deposit.pipeline(), "deposit_research", side_effect=OSError("injected disk failure")):
            out = self.execute()
            self.assertEqual(out["stage"], "pending")
            self.assertFalse(out["success"])
            for _ in range(3):
                self.assertFalse(self.execute({"action": "recover"})["success"])
            self.assertEqual(self.execute({"action": "recover"})["error"], "recovery_exhausted_or_missing_payload")
        self.assertFalse((self.vault / "raw").exists())

    def test_task_scope_missing_or_wrong_and_casual(self):
        self.assertIsNone(self.begin("你好"))
        self.assertFalse(self.execute()["success"])
        self.begin()
        self.assertFalse(self.execute(scope={"session_id": "session-a"})["success"])
        self.assertFalse(self.execute(scope=dict(self.scope, task_id="other"))["success"])
        self.assertIsNone(self.deposit.transform(BODY, session_id="session-a"))

    def test_parent_revision_conflict_and_interrupt(self):
        self.begin()
        self.assertTrue(self.execute()["success"])
        self.assertEqual(self.execute(dict(self.inputs(), body=BODY + "change"))["error"], "source_revision_conflict")
        scope = dict(self.scope, task_id="interrupt")
        self.begin(scope=scope)
        out = self.deposit.verify_completion(BODY, interrupted=True, **scope)
        self.assertFalse(out["complete"])
        self.assertNotEqual(out["stage"], "saved")

    def test_cli_shaped_two_rejected_items_are_independent_and_actionable(self):
        self.begin("研究 DDR 和 Yuxi 两项")
        results = [self.execute(payload) for payload in REJECTED_HANDOFF_FIXTURES]
        self.assertEqual(len({r["item_id"] for r in results}), 2)
        for result in results:
            self.assertFalse(result["success"], result)
            self.assertEqual(result["reason"], "quality_rejected")
            self.assertIn("missing_substantive_markdown_sections", result["quality_reason"])
            self.assertNotIn("通过确定性评分门禁", result["quality_reason"])
            self.assertEqual(result["minchars"], 800)
            self.assertTrue(result["required_structure"]["actual_newlines"])
        status = self.execute({"action": "status"})
        self.assertEqual(status["total"], 2)
        self.assertFalse(status["complete"])
        self.assertFalse((self.vault / "raw").exists())
        task = self.ctx.state.get(self.deposit.key(self.deposit.scope(self.scope)))
        for original in REJECTED_HANDOFF_FIXTURES:
            stored = task["items"][self.deposit.item_id(original)]
            self.assertEqual(stored["payload"], original)  # no automatic decode/fill
        # Explicit correction changes formatting ONLY, preserving every original word.
        for idx, original in enumerate(REJECTED_HANDOFF_FIXTURES):
            corrected = dict(original)
            for label in ("事实", "机制分析" if idx == 0 else "分析", "启示"):
                corrected["body"] = corrected["body"].replace("\n" + label + "：", "\n## " + label + "\n")
            result = self.execute(corrected)
            self.assertTrue(result["success"], result)
            self.assertEqual(result["item_id"], self.deposit.item_id(original))
            self.assertEqual(result["complete"], idx == 1)
        self.assertTrue(self.execute({"action": "status"})["complete"])
        self.assertEqual(len(json.loads((self.vault / "raw/_manifest.json").read_text())), 2)

    def test_literal_backslash_n_is_not_automatically_decoded(self):
        self.begin()
        malformed = dict(self.inputs(), body=BODY.replace("\n", "\\n"))
        rejected = self.execute(malformed)
        self.assertEqual(rejected["reason"], "quality_rejected")
        self.assertIn("actual_newlines", rejected["quality_reason"])
        self.assertEqual(self.item_record()["payload"]["body"], malformed["body"])
        self.assertTrue(self.execute()["complete"])

    def test_mixed_items_summary_cannot_complete_or_overwrite_body(self):
        self.begin()
        self.assertTrue(self.execute()["complete"])
        bad = dict(REJECTED_HANDOFF_FIXTURES[0])
        rejected = self.execute(bad)
        self.assertFalse(rejected["complete"])
        before = self.ctx.state.get(self.deposit.key(self.deposit.scope(self.scope)))
        result = self.deposit.verify_completion("Brief user summary, not the research body", **self.scope)
        self.assertFalse(result["complete"])
        self.assertEqual(result["stage"], "pending")
        self.assertFalse(self.execute()["complete"])  # repeating successful item cannot hide failed peer
        after = self.ctx.state.get(self.deposit.key(self.deposit.scope(self.scope)))
        self.assertEqual(after["items"][rejected["item_id"]]["payload"], before["items"][rejected["item_id"]]["payload"])

    def test_source_identity_survives_revision_and_turn_changes(self):
        self.begin()
        saved = self.execute()
        self.assertTrue(saved["success"])
        changed = dict(self.inputs(), body=BODY + "Changed conclusion", title="Changed title")
        conflict = self.execute(changed)
        self.assertEqual(conflict["item_id"], saved["item_id"])
        self.assertEqual(conflict["error"], "source_revision_conflict")
        self.assertFalse(self.deposit.verify_completion("New conclusion", **self.scope)["complete"])
        continuation = dict(self.scope, turn_id="next-turn")
        self.begin("继续研究", continuation)
        self.assertEqual(self.execute(changed, continuation)["error"], "source_revision_conflict")
        self.assertFalse(self.execute({"action": "status"}, continuation)["complete"])
        self.assertEqual(len(list((self.vault / "raw/reports").glob("*.md"))), 1)

    def test_multi_item_recovery_bounded_and_veto_task_wide(self):
        self.begin()
        with patch.object(self.deposit.pipeline(), "deposit_research", side_effect=OSError("outage")):
            for index in range(4):
                url = f"https://arxiv.org/abs/test-{index}"
                self.execute(dict(self.inputs(), source_urls=[url], body=BODY + "\n" + url))
        recovered = self.execute({"action": "recover"})
        self.assertFalse(recovered["complete"])
        self.assertEqual(sum(item["success"] for item in recovered["items"]), 3)
        self.assertTrue(self.execute({"action": "recover"})["complete"])
        self.begin("不保存 NEVER-COPY-BODY", dict(self.scope, turn_id="veto-turn"))
        self.assertEqual(self.execute()["error"], "no_save")
        state = self.ctx.state.get(self.deposit.key(self.deposit.scope(self.scope)))
        self.assertEqual(state, {"veto": True, "stage": "blocked", "reason": "no_save"})
        self.assertNotIn("NEVER-COPY-BODY", self.ctx.state.path.read_text())

    def test_multi_item_status_discovery_and_recovery_references(self):
        self.begin()
        with patch.object(self.deposit.pipeline(), "deposit_research", side_effect=OSError("outage")):
            for index in range(4):
                url = f"https://arxiv.org/abs/test-{index}"
                self.execute(dict(self.inputs(), source_urls=[url], body=BODY + "\n" + url))
        writer = dict(self.scope, task_id="writer", platform="cron")
        self.begin("Wiki Writer 编译 manifest", writer)
        result = self.execute({"action": "status", "limit": 2}, writer)
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["returned"], 2)
        self.assertTrue(result["has_more"])
        self.assertEqual(len({p["item_id"] for p in result["pending"]}), 2)
        recovered = self.execute({"action": "recover", "limit": 20}, writer)
        self.assertEqual(recovered["returned"], 3)
        self.assertTrue(all(p["result"]["success"] for p in recovered["pending"]))
        self.assertEqual(self.execute({"action": "status"}, writer)["total"], 1)

    def test_legacy_rejected_migration_is_lossless_and_does_not_mint_owner(self):
        self.begin()
        bad = REJECTED_HANDOFF_FIXTURES[0]
        self.execute(bad)
        legacy = self.item_record()
        legacy.update(obligation=True, custom_legacy_field={"keep": "this"})
        key = self.deposit.key(self.deposit.scope(self.scope))
        self.ctx.state.set(key, legacy)
        self.execute({"action": "status"})
        task = self.ctx.state.get(key)
        self.assertEqual(task["migrated_from"], "single_record_v1")
        migrated = self.item_record(task)
        for field, value in legacy.items():
            self.assertEqual(migrated[field], value)
        legacy.pop("owner")
        self.ctx.state.set(key, legacy)
        self.begin()
        self.assertFalse(self.execute()["success"])
        self.assertNotIn("owner", self.ctx.state.get(key))

    def test_legacy_zero_for_null_raw_receipt_repairs_exact_bytes(self):
        self.begin()
        pipeline = self.deposit.pipeline()
        normalize = pipeline.normalize_confidence
        with patch.object(pipeline, "normalize_confidence", side_effect=lambda value: 0.0 if value is None else normalize(value)):
            out = self.execute(self.inputs(None))
        self.assertTrue(out["success"], out)
        path = self.vault / out["receipt"]["raw_path"]
        before = path.read_bytes()
        legacy = self.item_record()
        legacy["obligation"] = True
        # Missing verification bit needs old-byte recovery (no new null-hash raw).
        legacy["receipt"]["storage_verified"] = False
        self.ctx.state.set(self.deposit.key(self.deposit.scope(self.scope)), legacy)
        recovered = self.execute({"action": "recover"})
        self.assertTrue(recovered["success"], recovered)
        self.assertEqual(recovered["receipt"]["raw_path"], out["receipt"]["raw_path"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list((self.vault / "raw/pending").glob("*.md"))), 1)

    def test_immutable_manifest_failure_cannot_accept_corrected_revision(self):
        self.begin()
        with patch.object(self.deposit.pipeline(), "append_manifest_receipt", side_effect=OSError("manifest outage")):
            self.execute()
        self.assertEqual(self.execute(dict(self.inputs(), body=BODY + "changed"))["error"], "source_revision_conflict")
        self.assertFalse(self.execute({"action": "recover"})["complete"])
        self.assertFalse(self.deposit.verify_completion("Changed answer", **self.scope)["complete"])
        self.assertTrue(self.execute()["complete"])  # explicit identical old content is honest

    def test_concurrent_independent_items_and_low_vs_missing(self):
        self.begin()
        def run(index):
            url = f"https://arxiv.org/abs/item-{index}"
            return self.execute(dict(self.inputs(None if index == 0 else .59), source_urls=[url], body=BODY + "\n" + url))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, range(4)))
        self.assertTrue(all(result["success"] for result in results), results)
        self.assertEqual(len({result["item_id"] for result in results}), 4)
        import yaml
        metadata = [yaml.safe_load((self.vault / result["receipt"]["raw_path"]).read_text().split("---", 2)[1]) for result in results]
        self.assertIsNone(metadata[0]["confidence"])
        self.assertEqual(metadata[1]["confidence"], .59)
        self.assertTrue(self.execute({"action": "status"})["complete"])
        self.assertFalse((self.vault / "raw/_manifest.json").exists())

    def test_nine_cron_intent_fixtures_classify_primary_purpose_only(self):
        research, controls = [], []
        for identity, prompt in CRON_INTENT_FIXTURES:
            scope = dict(self.scope, task_id=identity, platform="cron")
            out = self.begin(prompt, scope)
            record = self.ctx.state.get(self.deposit.key(self.deposit.scope(scope)))
            if record.get("control"):
                controls.append(identity)
                self.assertIn("Research maintenance", out["context"])
            else:
                research.append(identity)
                self.assertTrue(record.get("obligation"), (identity, record, out))
                self.assertIn("Local research contract", out["context"])
        self.assertEqual(len(research), 8)
        self.assertEqual(controls, ["fixture-writer"])

    def test_nonresearch_exclusion_is_primary_action_not_output_format(self):
        for index, text in enumerate(("调研翻译模型，最后只回答三句", "研究摘要生成模型，正式Wiki由Wiki Writer处理")):
            scope = dict(self.scope, task_id=f"positive-{index}", platform="cron")
            self.assertIn("Local research contract", self.begin(text, scope)["context"])
        for index, text in enumerate(("请翻译 https://example.org/research", "仅摘要这份研究 https://example.org/research")):
            scope = dict(self.scope, task_id=f"negative-{index}", platform="cron")
            self.assertIsNone(self.begin(text, scope))
            self.assertFalse(self.execute(scope=scope)["success"])
        scope = dict(self.scope, task_id="purpose", task_purpose="wiki_compile", platform="cron")
        self.assertIn("Research maintenance", self.begin("研究补证", scope)["context"])

    def test_score_ingestion_not_excluded_without_store_word(self):
        router = sys.modules["research_plugin_test.capability_router"]
        card = {"id": "skill:research", "kind": "skill", "name": "research", "description": "research analysis", "skill_path": "knowledge/ingestion", "negative_phrases": []}
        _, factors = router._score_capability(card, "research retrieval designs", {})
        self.assertNotIn("excluded", factors)
        self.assertEqual(router._score_capability(card, "research but do not save", {})[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
