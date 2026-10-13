from __future__ import annotations

import importlib.util
import types
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "quansyn.py"
)


def load_quansyn_module():
    spec = importlib.util.spec_from_file_location("quansyn_richtext_test", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class State:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class Context:
    def __init__(self, data_dir: Path):
        self.state = State(data_dir)

    def get_config(self, *_args):
        return ""


def _saved(text: str):
    return {"imported": True, "completed": False, "text": text, "blocks": [], "files": []}


def assert_richtext_instruction(result):
    instruction = result["goal"]["instruction"]
    assert "完整 result 文本作为兼容回退" in instruction
    assert "markdown、code、table、chart" in instruction


def test_batch_and_single_execution_request_structured_blocks_without_losing_result(tmp_path):
    module = load_quansyn_module()
    quansyn = module.QuanSyn(Context(tmp_path))
    sender = "owner"
    batch_id = "qs_" + "a" * 32
    single_id = "qs_" + "b" * 32

    quansyn.ctx.state.set(quansyn.key(sender, batch_id), _saved("batch"))
    quansyn.pending_rows = lambda _sender: []
    quansyn.queue = lambda _sender: [batch_id]
    quansyn.queue_add = lambda *_args: None
    quansyn.queue_remove = lambda *_args: None

    batch = quansyn._command(
        {"sender": sender, "action": "批量执行", "id": None, "selection": None, "turn_id": "t1", "reply": None}
    )
    assert_richtext_instruction(batch)

    quansyn.ctx.state.set(quansyn.key(sender, single_id), _saved("single"))
    single = quansyn._command(
        {"sender": sender, "action": "执行", "id": single_id, "selection": None, "turn_id": "t2", "reply": None}
    )
    assert_richtext_instruction(single)


def test_public_slashes_skip_without_model_or_binding(tmp_path):
    module = load_quansyn_module()
    quansyn = module.QuanSyn(Context(tmp_path), owner_check=lambda platform, sender: True)
    source = types.SimpleNamespace(platform="feishu", user_id="owner", chat_id="chat-1", chat_type="dm")
    calls = []
    quansyn.schedule_relay = lambda *args: calls.append(args)
    for command in ("/push", "/pull"):
        event = types.SimpleNamespace(source=source, text=command, raw_message=None)
        assert quansyn.gateway(event=event, gateway=types.SimpleNamespace(adapters={})) == {
            "action": "skip", "reason": "quansyn_relay_only"}
        assert module.canonical_command(command) is None
        assert quansyn.before_turn(command, platform="feishu", session_id="session-1", sender_id="owner") is None
    assert len(calls) == 2
    for legacy in ("/quansyn", "查看 QuanSyn", "执行 QuanSyn qs_" + "a" * 32,
                   "推送 QuanSyn qs_" + "a" * 32):
        assert module.canonical_command(legacy) is None


def test_feishu_uses_current_store_session_and_sends_drafts(tmp_path):
    import asyncio
    import json
    module = load_quansyn_module()

    async def scenario():
        q = module.QuanSyn(Context(tmp_path), owner_check=lambda *args: True)
        source = types.SimpleNamespace(platform="feishu", user_id="owner", chat_id="chat", chat_type="dm")
        sent, acked, selected = [], [], []
        class Adapter:
            _loop = asyncio.get_running_loop()
            async def _feishu_send_with_retry(self, **kw):
                sent.append(json.loads(kw["payload"]))
                return True
            def _finalize_send_result(self, result, _error):
                return types.SimpleNamespace(success=result)
        class Store:
            def get_or_create_session(self, actual):
                assert actual is source
                return types.SimpleNamespace(session_id="current-session")
            def _db_for_session_id(self, session):
                assert session == "current-session"
                return "same-db"
        q.pending_rows = lambda sender: [{"id": "one"}, {"id": "two"}]
        q.pull = lambda sender, ident, acknowledge: {"id": ident, "text": ident, "files": []}
        q.ack_relay_pull = lambda sender, item: acked.append(item["id"])
        def push(owner, session, directory, http, db):
            selected.append((session, db))
            return {"noop": True, "success": True}
        module.push_recent = push
        adapter = Adapter()
        gateway = types.SimpleNamespace(adapters={"feishu": adapter}, session_store=Store())
        for command in ("/pull", "/push"):
            event = types.SimpleNamespace(source=source, text=command, raw_message=None)
            assert q.gateway(event=event, gateway=gateway)["action"] == "skip"
            tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            await asyncio.gather(*tasks)
        assert acked == ["one", "two"]
        assert [card["header"]["title"]["content"] for card in sent[:2]] == ["待发送草稿"] * 2
        assert selected == [("current-session", "same-db")]
    asyncio.run(scenario())


def test_feishu_failed_presentation_does_not_ack(tmp_path):
    import asyncio
    module = load_quansyn_module()
    async def scenario():
        q = module.QuanSyn(Context(tmp_path))
        source = types.SimpleNamespace(chat_id='synthetic-chat')
        acked = []
        class Adapter:
            _loop = asyncio.get_running_loop()
            async def _feishu_send_with_retry(self, **kw):
                return False
            def _finalize_send_result(self, result, error):
                return types.SimpleNamespace(success=False)
        q.pending_rows = lambda sender: [{'id': 'synthetic'}]
        q.pull = lambda *args: {'id': 'synthetic', 'text': 'draft', 'files': []}
        q.ack_relay_pull = lambda *args: acked.append(args)
        q.schedule_relay(Adapter(), source, 'owner', '/pull', None)
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        # Both draft and failure receipt delivery fail. Neither permits an ack.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert results == [None]
        assert not acked
    asyncio.run(scenario())
