from __future__ import annotations

import importlib.util
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
