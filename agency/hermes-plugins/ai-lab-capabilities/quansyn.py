"""Relay-only public mailbox commands; explicit execution is legacy compatibility."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .quansyn_relay import push_recent, draft_text
except ImportError:  # standalone plugin loading
    import importlib.util
    _helper_path = Path(__file__).resolve().parent / "quansyn_relay.py"
    _spec = importlib.util.spec_from_file_location("quansyn_relay", _helper_path)
    _relay = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_relay)
    push_recent, draft_text = _relay.push_recent, _relay.draft_text

import httpx

COMMAND = re.compile(r"(绑定)\s*QuanSyn(?:\s+(\S+))?(?:\s+附件\s+([0-9,，]+))?", re.I)
ID = re.compile(r"qs_[a-f0-9]{32}")
RUN_TTL_SECONDS = 2 * 60 * 60
MAX_BATCH_ITEMS = 100
CARD_ACTION_TTL_SECONDS = 15 * 60


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def canonical_command(text):
    """Map the public slash entry point to the existing trusted command grammar."""
    value = str(text or "").strip().replace("qs\\_", "qs_")
    if value.lower() in {"/push", "/pull"}:
        return None
    return value if COMMAND.fullmatch(value) else None


class MacKeychain:
    """Credentials stay in the macOS login Keychain, never plugin JSON/model input."""
    service = "com.quantum.quansyn"

    def get(self, account):
        result = subprocess.run(["/usr/bin/security", "find-generic-password", "-a", account,
                                 "-s", self.service, "-w"], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise ValueError("请先在 Web 连接 Mac，并发送绑定 QuanSyn 配对码")
        return result.stdout.strip()

    def set(self, account, token):
        result = subprocess.run(["/usr/bin/security", "add-generic-password", "-U", "-a", account,
                                 "-s", self.service, "-w", token], capture_output=True, timeout=10)
        if result.returncode:
            raise ValueError("无法写入 Mac Keychain，绑定未在本机完成；请在 Web 撤销后重试")


class QuanSyn:
    def __init__(self, ctx, owner_check=None):
        self.ctx = ctx
        self.owner_check = owner_check or (lambda platform, sender: False)
        self.credentials = MacKeychain()
        self.turns = {}
        self.delivery = {}
        self.card_callbacks = {}
        self.card_actions = {}
        if callable(getattr(ctx, "register_hook", None)):
            ctx.register_hook("pre_gateway_dispatch", self.gateway)

    def gateway(self, event=None, gateway=None, **kw):
        source = getattr(event, "source", None)
        platform = getattr(source, "platform", "")
        if str(getattr(platform, "value", platform)).lower() not in {"feishu", "lark"}:
            return None
        text = str(getattr(event, "text", "") or "").strip()
        native = getattr(getattr(event, "raw_message", None), "event", None)
        value = getattr(getattr(native, "action", None), "value", None)
        card = isinstance(value, dict) and "quansyn_command" in value
        command = str(value.get("quansyn_command", "")) if isinstance(value, dict) and card else canonical_command(text)
        relay_command = text.lower() if text.lower() in {"/pull", "/push"} and not card else None
        if not command and not relay_command:
            return None
        sender = str(getattr(source, "user_id", "") or "")
        chat_id = str(getattr(source, "chat_id", "") or "")
        if getattr(source, "chat_type", "") != "dm":
            route = self.delivery.get(sender)
            if not card or not route or route[1] != chat_id:
                return {"action": "skip", "reason": "quansyn_private_chat_only"}
        if not sender or not self.owner_check(str(getattr(platform, "value", platform)), sender):
            return {"action": "skip", "reason": "quansyn_local_owner_required"}
        if relay_command:
            adapter = getattr(gateway, "adapters", {}).get(platform)
            store = kw.get("session_store") or getattr(gateway, "session_store", None)
            self.schedule_relay(adapter, source, sender, relay_command, store)
            return {"action": "skip", "reason": "quansyn_relay_only"}
        if card:
            return {"action": "skip", "reason": "quansyn_legacy_card_disabled"}
        adapter = getattr(gateway, "adapters", {}).get(platform)
        if adapter is not None:
            if len(self.delivery) >= 128 and sender not in self.delivery:
                self.delivery.clear()
            self.delivery[sender] = (adapter, str(source.chat_id))
            if card:
                context = getattr(native, "context", None)
                message_id = str(getattr(context, "open_message_id", "") or "")
                match = COMMAND.fullmatch(command)
                if match is None:
                    return {"action": "skip", "reason": "quansyn_invalid_card_command"}
                action, transfer, selection = match.groups()
                if action in {"查看", "拉取", "推送"}:
                    self.run_card_action(adapter, message_id, sender, action, transfer, selection)
                    return {"action": "skip", "reason": "quansyn_card_handled"}
                if message_id:
                    self.card_callbacks[sender] = (message_id, command)
                self.update_progress_card(adapter, message_id, sender, command)
        return {"action": "rewrite", "text": command}

    def schedule_relay(self, adapter, source, sender, command, store):
        # The gateway hook is synchronous; schedule on the existing adapter loop.
        loop = getattr(adapter, "_loop", None)
        if loop is None or not loop.is_running():
            return False

        async def send(text, title="QuanSyn 回执"):
            # Keep full text, split to stay within Feishu card payload bounds.
            for offset in range(0, len(text), 4000):
                payload = {"config": {"wide_screen_mode": True},
                           "header": {"title": {"tag": "plain_text", "content": title}},
                           "elements": [{"tag": "markdown", "content": text[offset:offset + 4000]}]}
                response = await adapter._feishu_send_with_retry(
                    chat_id=str(source.chat_id), msg_type="interactive",
                    payload=json.dumps(payload, ensure_ascii=False), reply_to=None, metadata=None)
                if not adapter._finalize_send_result(response, "QuanSyn relay delivery failed").success:
                    raise ValueError("待发送草稿未成功发送，未确认导入")

        async def run():
            try:
                if command == "/push":
                    if store is None:
                        raise ValueError("Hermes SessionStore unavailable")
                    entry = await asyncio.to_thread(store.get_or_create_session, source)
                    # Borrow the same scoped SessionDB that Hermes uses for this session.
                    db = store._db_for_session_id(entry.session_id)
                    if db is None:
                        raise ValueError("Hermes SessionDB unavailable")
                    receipt = await asyncio.to_thread(push_recent, sender, entry.session_id,
                                                      self.ctx.state.data_dir, self.http, db)
                    await send(receipt.get("receipt") or "无新的可推送消息。")
                else:
                    rows = await asyncio.to_thread(self.pending_rows, sender)
                    items = [await asyncio.to_thread(self.pull, sender, row["id"], False) for row in rows]
                    for item in items:
                        await send(draft_text(item), "待发送草稿")
                        await asyncio.to_thread(self.ack_relay_pull, sender, item)
                    if not items:
                        await send("暂无新的 QuanSyn 消息。")
            except Exception as exc:
                try:
                    await send(str(exc) if isinstance(exc, (ValueError, OSError)) else "QuanSyn 操作失败，未确认成功。")
                except Exception:
                    logging.getLogger(__name__).warning("QuanSyn relay receipt delivery failed; operation not presented")

        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            loop.create_task(run())
        else:
            asyncio.run_coroutine_threadsafe(run(), loop)
        return True

    def ack_relay_pull(self, sender, saved):
        for file in saved["files"]:
            with Path(file["path"]).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != file["hash"]:
                    raise ValueError("附件哈希不符，未确认导入")
        self.http(sender, "POST", f"/transfers/{saved['id']}/imported",
                  payload={"revision": saved["revision"], "claim": saved["claim"]})
        saved["imported"] = True
        self.ctx.state.set(self.key(sender, saved["id"]), saved)

    def run_card_action(self, adapter, message_id, sender, action, transfer, selection):
        """Run deterministic card actions without creating an LLM turn."""
        now = time.time()
        self.card_actions = {key: stamp for key, stamp in self.card_actions.items()
                             if now - stamp < CARD_ACTION_TTL_SECONDS}
        key = (sender, message_id, action, transfer or "", selection or "")
        if key in self.card_actions:
            return False
        self.card_actions[key] = now
        command = f"{action} QuanSyn" + (f" {transfer}" if transfer else "")
        if selection:
            command += f" 附件 {selection}"
        self.update_progress_card(adapter, message_id, sender, command)
        turn = {"sender": sender, "action": action, "id": transfer, "selection": selection,
                "reply": None, "card_message_id": message_id}

        async def run():
            await asyncio.to_thread(self._command, turn)
            self.update_progress_card(adapter, message_id, sender, "", turn=turn)

        loop = getattr(adapter, "_loop", None)
        if loop is None or not loop.is_running():
            self.card_actions.pop(key, None)
            return False
        try:
            if asyncio.get_running_loop() is loop:
                loop.create_task(run())
            else:
                asyncio.run_coroutine_threadsafe(run(), loop)
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(run(), loop)
        return True

    def progress_card(self, sender, command):
        return self.card({"sender": sender, "action": "执行中", "progress": True,
                          "reply": f"⏳ **执行中**\n\n已接收：`{command}`\n正在拉取并执行，请勿重复点击。"})

    def update_progress_card(self, adapter, message_id, sender, command, turn=None):
        """Replace the clicked card in place, or send it when no message ID is available."""
        loop = getattr(adapter, "_loop", None)
        if loop is None or not loop.is_running():
            return False
        payload = json.dumps(self.card(turn) if turn else self.progress_card(sender, command), ensure_ascii=False)

        async def update():
            try:
                if message_id and getattr(adapter, "_client", None) is not None:
                    body = adapter._build_update_message_body(msg_type="interactive", content=payload)
                    request = adapter._build_update_message_request(message_id=message_id, request_body=body)
                    response = await adapter._run_blocking(adapter._client.im.v1.message.update, request)
                    return adapter._finalize_send_result(response, "QuanSyn progress update failed").success
                response = await adapter._feishu_send_with_retry(
                    chat_id=self.delivery[sender][1], msg_type="interactive", payload=payload,
                    reply_to=None, metadata=None)
                return adapter._finalize_send_result(response, "QuanSyn progress card failed").success
            except Exception:
                return False

        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            loop.create_task(update())
        else:
            asyncio.run_coroutine_threadsafe(update(), loop)
        return True

    def card(self, turn):
        sender = turn["sender"]
        def button(label, command, primary=False):
            return {"tag": "button", "text": {"tag": "plain_text", "content": label},
                    "type": "primary" if primary else "default",
                    "value": {"quansyn_command": command, "sender_id": sender}}
        elements = []
        if turn.get("progress"):
            elements.append({"tag": "markdown", "content": turn["reply"]})
        elif "rows" in turn:
            rows = turn["rows"]
            for row in rows[:10]:
                elements.append({"tag": "markdown", "content":
                    f'**待处理需求**\n{row["text"][:300]}\n附件：{len(row["files"])} 个 · `{row["id"]}`'})
                elements.append({"tag": "action", "actions": [
                    button("拉取并执行", "拉取并执行 QuanSyn " + row["id"], True),
                    button("仅拉取", "拉取 QuanSyn " + row["id"]) ]})
            if not rows:
                elements.append({"tag": "markdown", "content": "暂无发给 Mac 的待处理需求。"})
            elif len(rows) > 10:
                elements.append({"tag": "markdown", "content": "先显示前10条，处理后刷新查看其余需求。"})
            if rows:
                elements.append({"tag": "action", "actions": [
                    button("全部拉取并执行", "批量执行 QuanSyn", True)]})
        else:
            elements.append({"tag": "markdown", "content": str(turn.get("reply") or "执行已完成，可回传完整结果。")[:600]})
            transfer = turn.get("id")
            if transfer and ID.fullmatch(transfer) and not turn.get("failed"):
                saved = self.ctx.state.get(self.key(sender, transfer), {})
                if saved.get("completed"):
                    names = "、".join(Path(f["path"]).name for f in saved.get("outputs", []))
                    elements.append({"tag": "markdown", "content": "生成附件：" + (names[:500] or "无")})
                    if not turn.get("published"):
                        elements.append({"tag": "action", "actions": [button("推送完整结果到 QuanSyn", "推送 QuanSyn " + transfer, True)]})
                elif saved.get("imported") and turn.get("action") == "拉取":
                    elements.append({"tag": "action", "actions": [button("开始执行", "执行 QuanSyn " + transfer, True)]})
        if not turn.get("progress"):
            elements.append({"tag": "action", "actions": [button("刷新待处理", "查看 QuanSyn"),
                {"tag": "button", "text": {"tag": "plain_text", "content": "打开 QuanSyn"},
                 "type": "default", "url": self.base() + "/quansyn/"}]})
        template = "orange" if turn.get("progress") or turn.get("partial") else "red" if turn.get("failed") else "green" if turn.get("completed_count") else "blue"
        return {"config": {"wide_screen_mode": True},
                "header": {"template": template,
                           "title": {"tag": "plain_text", "content": "Quantum · QuanSyn" + (" · 执行中" if turn.get("progress") else "")}},
                "elements": elements}

    def deliver_card(self, turn):
        route = self.delivery.get(turn["sender"])
        if route is None:
            return False
        adapter, chat_id = route
        loop = getattr(adapter, "_loop", None)
        if loop is None or not loop.is_running():
            return False
        async def send():
            response = await adapter._feishu_send_with_retry(chat_id=chat_id,
                msg_type="interactive", payload=json.dumps(self.card(turn), ensure_ascii=False),
                reply_to=None, metadata=None)
            return adapter._finalize_send_result(response, "QuanSyn card failed").success
        try:
            if asyncio.get_running_loop() is loop:
                loop.create_task(send())
                return True
        except RuntimeError:
            pass
        future = asyncio.run_coroutine_threadsafe(send(), loop)
        try:
            return bool(future.result(timeout=15))
        except Exception:
            future.cancel()
            return False

    def base(self):
        value = str(self.ctx.get_config("quansyn.api_base", "") or os.environ.get("QUANSYN_API_BASE_URL", "")).rstrip("/")
        parts = urlsplit(value)
        if (parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"})) or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("需配置 quansyn.api_base 为 QuanSyn HTTPS 地址（本地验收可使用 localhost）")
        return value

    def account(self, sender):
        return digest(self.base() + "\0" + sender)

    def key(self, sender, transfer):
        return "quansyn:" + digest(sender + "\0" + transfer)

    def queue_key(self, sender):
        return "quansyn-queue:" + digest(sender)

    def queue(self, sender):
        value = self.ctx.state.get(self.queue_key(sender), {"ids": []})
        return [item for item in value.get("ids", []) if ID.fullmatch(str(item))]

    def queue_add(self, sender, transfer):
        ids = self.queue(sender)
        if transfer not in ids:
            ids.append(transfer)
            self.ctx.state.set(self.queue_key(sender), {"ids": ids})

    def queue_remove(self, sender, transfer):
        ids = [item for item in self.queue(sender) if item != transfer]
        self.ctx.state.set(self.queue_key(sender), {"ids": ids})

    def pending_rows(self, sender):
        """Collect every server-pending row without silently truncating pagination."""
        rows = []
        before = None
        seen = set()
        while True:
            suffix = "?target=mac&pending=true&limit=100"
            if before:
                from urllib.parse import quote
                suffix += "&before=" + quote(str(before), safe="")
            page = self.http(sender, "GET", "/transfers" + suffix)
            if not isinstance(page, dict):
                raise ValueError("QuanSyn 待处理队列返回格式无效")
            batch = page.get("items", [])
            rows.extend(batch)
            if len(rows) > MAX_BATCH_ITEMS:
                raise ValueError("QuanSyn pending queue exceeds 100 items")
            before = page.get("next")
            if not before:
                break
            if before in seen:
                raise ValueError("QuanSyn pagination cursor repeated")
            seen.add(before)
            if len(rows) >= MAX_BATCH_ITEMS or len(seen) > MAX_BATCH_ITEMS:
                raise ValueError(f"待处理需求超过 {MAX_BATCH_ITEMS} 条，请先减少队列后重试")
        return rows

    def root(self, sender, transfer):
        root = self.ctx.state.data_dir / "quansyn" / digest(sender + "\0" + transfer)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return root.resolve()

    def http(self, sender, method, path, *, payload=None, data=None, filename=None, public=False, sink=None):
        headers = {} if public else {"Authorization": "Bearer " + self.credentials.get(self.account(sender)), "X-QuanSyn-Sender": sender}
        if filename:
            from urllib.parse import quote
            headers["X-File-Name"] = quote(filename, safe="")
            headers["Content-Type"] = "application/octet-stream"
        if hasattr(data, "read"):
            source = data
            data = iter(lambda: source.read(1024 * 1024), b"")
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            if path.startswith("/files/") and method == "GET":
                with client.stream(method, self.base() + "/api/v1/quansyn" + path, headers=headers) as response:
                    if response.status_code >= 300:
                        raise ValueError(f"QuanSyn 请求失败（HTTP {response.status_code}），未确认成功")
                    raw = bytearray()
                    content_hash = hashlib.sha256()
                    total = 0
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        total += len(chunk)
                        if total > 25 * 1024 * 1024:
                            raise ValueError("QuanSyn attachment exceeds 25 MB")
                        content_hash.update(chunk)
                        if sink is not None:
                            sink.write(chunk)
                        else:
                            raw.extend(chunk)
                    return content_hash.hexdigest() if sink is not None else bytes(raw)
            response = client.request(method, self.base() + "/api/v1/quansyn" + path,
                                      headers=headers, json=payload, content=data)
        if response.status_code >= 300:
            # Never include request headers or credentials in errors/model context.
            raise ValueError(f"QuanSyn 请求失败（HTTP {response.status_code}），未确认成功")
        return response.json()

    def pull(self, sender, transfer, acknowledge=True):
        key = self.key(sender, transfer)
        saved = self.ctx.state.get(key, {})
        row = self.http(sender, "GET", "/transfers/" + transfer)
        if row["direction"] != "request" or row["target"] != "mac":
            raise ValueError("请选择发给 Mac 的需求")
        if saved.get("imported"):
            if not saved.get("completed"):
                self.queue_add(sender, transfer)
            return saved
        if acknowledge and row["status"] in {"claimed", "imported", "returned"} and saved.get("claim") and "files" in saved and "text" in saved:
            for file in saved["files"]:
                with Path(file["path"]).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != file["hash"]:
                        raise ValueError("本地附件哈希不符，未确认导入")
            self.http(sender, "POST", f"/transfers/{transfer}/imported", payload={"revision": row["revision"], "claim": saved["claim"]})
            saved["imported"] = True
            self.ctx.state.set(key, saved)
            if not saved.get("completed"):
                self.queue_add(sender, transfer)
            return saved
        claim = saved.get("claim") or secrets.token_urlsafe(32)
        saved.update(claim=claim, id=transfer, sender=sender)
        self.ctx.state.set(key, saved)
        leased = self.http(sender, "POST", f"/transfers/{transfer}/claim", payload={"revision": row["revision"], "claim": claim})
        local_files = []
        for index, file in enumerate(row["files"]):
            name = Path(file.get("metadata", {}).get("original_name") or file["filename"]).name
            destination = self.root(sender, transfer) / f"{index + 1}-{name}"
            if not destination.resolve().is_relative_to(self.root(sender, transfer)):
                raise ValueError("附件路径越界")
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                content_hash = self.http(sender, "GET", "/files/" + file["artifact_id"], sink=stream)
                stream.flush()
                os.fsync(stream.fileno())
            if content_hash != file["content_hash"]:
                raise ValueError("附件哈希不符，未确认导入")
            local_files.append({"path": str(destination), "name": name, "hash": file["content_hash"]})
        saved.update(text=row["text"], blocks=row["blocks"], files=local_files, imported=False)
        self.ctx.state.set(key, saved)
        saved["revision"] = leased["revision"]
        self.ctx.state.set(key, saved)
        if not acknowledge:
            return saved
        self.http(sender, "POST", f"/transfers/{transfer}/imported", payload={"revision": leased["revision"], "claim": claim})
        saved["imported"] = True
        self.ctx.state.set(key, saved)
        self.queue_add(sender, transfer)
        return saved

    def before_turn(self, user_message="", **kw):
        platform = str(getattr(kw.get("platform"), "value", kw.get("platform")) or "").lower()
        session = str(kw.get("session_id") or "")
        sender = str(kw.get("sender_id") or "")
        if platform not in {"feishu", "lark"} or not session or not sender or not self.owner_check(platform, sender):
            return None
        # Human command must be the entire trusted gateway message, not quoted instructions in content.
        command = canonical_command(user_message)
        match = COMMAND.fullmatch(command or "")
        if not match:
            self.turns.pop(session, None)
            return None
        if len(self.turns) >= 128:
            self.turns.clear()
        action, transfer, selection = match.groups()
        turn = {"sender": sender, "action": action, "id": transfer, "turn_id": kw.get("turn_id"), "reply": None}
        callback = self.card_callbacks.pop(sender, None)
        if callback and callback[1] == command:
            turn["card_message_id"] = callback[0]
        self.turns[session] = turn
        turn["selection"] = selection
        return {"context": "用户已明确授权当前 QuanSyn 指令。必须调用 ai_lab_execute capability=quansyn inputs={action:command} 获取真实回执。成功领取并执行时，按照返回 goal 在现有 Hermes 中执行。不要自行构造配对、账号、文件或回传状态。"}

    def pre_tool(self, tool_name, args=None, **kw):
        if tool_name != "ai_lab_execute:quansyn":
            return None
        turn = self.turns.get(str(kw.get("session_id") or ""), {})
        action = (args or {}).get("inputs", {}).get("action")
        if not turn or not turn.get("turn_id") or kw.get("turn_id") != turn["turn_id"] or action not in {"command", "outputs"}:
            return {"action": "block", "message": "QuanSyn 缺少当前回合的可信用户指令"}
        if action == "outputs" and not turn.get("executing"):
            return {"action": "block", "message": "QuanSyn 尚未开始执行，不能登记输出"}
        # Native Hermes omits turn_id at handler dispatch; its trusted pre-tool hook supplies admission.
        turn.setdefault("admitted", set()).add(action)
        return None

    def authorized(self, turn, action, kw):
        if not turn or not turn.get("turn_id"):
            return False
        if kw.get("turn_id"):
            return kw["turn_id"] == turn["turn_id"]
        admitted = turn.get("admitted", set())
        if action not in admitted:
            return False
        admitted.remove(action)
        return True

    def command(self, **kw):
        session = str(kw.get("session_id") or "")
        turn = self.turns.get(session, {})
        if not self.authorized(turn, "command", kw):
            raise ValueError("缺少本回合可信 QuanSyn 指令")
        if turn.get("command_result") is not None:
            return turn["command_result"]
        result = self._command(turn)
        turn["command_result"] = result
        return result

    def _command(self, turn):
        sender, action, transfer, selection = turn["sender"], turn["action"], turn["id"], turn["selection"]
        try:
            if action == "绑定":
                paired = self.http(sender, "POST", "/devices/exchange", public=True, payload={"code": transfer, "sender_id": sender})
                self.credentials.set(self.account(sender), paired["token"])
                turn["reply"] = "QuanSyn 已绑定。发送“查看 QuanSyn”即可读取发给 Mac 的需求；可在 Web 撤销权限。"
            elif action == "查看":
                rows = self.pending_rows(sender)
                turn["rows"] = rows
                turn["reply"] = "\n".join(f'{r["id"]} · {r["text"][:100]} · {len(r["files"])} 个附件' for r in rows) or "暂无发给 Mac 的待处理需求。"
            elif action == "批量执行":
                rows = self.pending_rows(sender)
                ids = self.queue(sender)
                for row in reversed(rows):
                    if row["id"] not in ids:
                        ids.append(row["id"])
                if len(ids) > MAX_BATCH_ITEMS:
                    raise ValueError(f"本地与服务端待处理需求合计超过 {MAX_BATCH_ITEMS} 条，请先减少队列后重试")
                items = []
                running = []
                now = time.time()
                for item_id in ids:
                    saved = self.ctx.state.get(self.key(sender, item_id), {})
                    if not saved.get("imported"):
                        saved = self.pull(sender, item_id)
                    if saved.get("completed"):
                        self.queue_remove(sender, item_id)
                        continue
                    if float(saved.get("running_until") or 0) > now:
                        running.append(item_id)
                        continue
                    saved.update(completed=False, outputs=[], running_until=now + RUN_TTL_SECONDS,
                                 running_turn=str(turn.get("turn_id") or ""))
                    self.ctx.state.set(self.key(sender, item_id), saved)
                    items.append({"id": item_id, "request": saved["text"], "blocks": saved["blocks"],
                                  "files": saved["files"], "output_directory": str(self.root(sender, item_id))})
                if not items:
                    turn["reply"] = (f"{len(running)} 条需求已在执行中，请勿重复提交。" if running
                                     else "暂无未处理的 QuanSyn 需求。")
                else:
                    turn.update(executing=True, batch=True, batch_ids=[item["id"] for item in items])
                    return {"success": True, "goal": {
                        "batch": True, "items": items,
                        "instruction": (
                            "逐条独立完成 items 中的全部需求；一条失败不得阻断其他条目。每条输出文件只能保存在其 output_directory。"
                            "结果在保留完整 result 文本作为兼容回退的同时，尽可能按 markdown、code、table、chart 结构化写入 blocks，供 Web 富文本展示。"
                            "完成后必须调用一次 ai_lab_execute capability=quansyn action=outputs，inputs.items 中逐条提交 "
                            "id、success、result、paths、blocks；失败项提交 success=false 与 error。不要自动回传到 Web。"
                        ),
                    }}
            elif not transfer or not ID.fullmatch(transfer):
                raise ValueError("请提供完整需求编号 qs_…")
            elif action == "推送":
                saved = self.ctx.state.get(self.key(sender, transfer), {})
                if not saved.get("result") or not saved.get("completed"):
                    raise ValueError("该需求还没有已完成的运行结果")
                staged = saved.get("outputs", [])
                chosen = sorted(set(int(x) - 1 for x in selection.replace("，", ",").split(","))) if selection else list(range(len(staged)))
                files = []
                for index in chosen:
                    if index < 0 or index >= len(staged):
                        raise ValueError("附件编号不存在")
                    file = staged[index]
                    path = Path(file["path"])
                    root = self.root(sender, transfer)
                    if not path.resolve().is_relative_to(root) or path.is_symlink():
                        raise ValueError("输出文件路径越界")
                    with open(path, "rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != file["hash"]:
                            raise ValueError("输出文件已改变，请重新执行并确认")
                        stream.seek(0)
                        receipt = self.http(sender, "POST", "/files", data=stream, filename=path.name)
                    files.append({"artifact_id": receipt["artifact_id"]})
                receipt = self.http(sender, "POST", "/transfers", payload={
                    "request_id": "mac-" + digest(transfer + saved["result"] + json.dumps(files, sort_keys=True)),
                    "direction": "result", "target": "mac", "reply_to": transfer,
                    "text": saved["result"], "blocks": saved.get("result_blocks", []), "files": files,
                })
                turn["published"] = True
                turn["reply"] = f'已回传 QuanSyn：{receipt["id"]}，包含 {len(files)} 个附件。'
            else:
                saved = self.pull(sender, transfer) if action in {"拉取", "拉取并执行"} else self.ctx.state.get(self.key(sender, transfer), {})
                if not saved.get("imported"):
                    raise ValueError("请先拉取该需求")
                if action == "拉取":
                    turn["reply"] = f'已拉取 {transfer}：\n{saved["text"]}\n附件：\n' + "\n".join(f['path'] for f in saved["files"]) + f"\n发送“执行 QuanSyn {transfer}”开始运行。"
                elif saved.get("completed"):
                    turn["reply"] = "该需求已执行完成，可直接回传已有完整结果，无需重新执行。"
                    self.queue_remove(sender, transfer)
                elif float(saved.get("running_until") or 0) > time.time():
                    turn["reply"] = "该需求已在执行中，请勿重复提交。"
                else:
                    turn["executing"] = True
                    saved["completed"] = False
                    saved["outputs"] = []
                    saved["running_until"] = time.time() + RUN_TTL_SECONDS
                    saved["running_turn"] = str(turn.get("turn_id") or "")
                    self.ctx.state.set(self.key(sender, transfer), saved)
                    return {"success": True, "goal": {
                        "request": saved["text"], "blocks": saved["blocks"], "files": saved["files"],
                        "output_directory": str(self.root(sender, transfer)),
                        "instruction": "沿用当前工具完成需求；输出文件保存在 output_directory。结果在保留完整 result 文本作为兼容回退的同时，尽可能按 markdown、code、table、chart 结构化写入 blocks，供 Web 富文本展示。使用 ai_lab_execute capability=quansyn action=outputs 登记生成的文件。不要自动回传。",
                    }}
        except Exception as exc:
            turn["failed"] = True
            turn["reply"] = str(exc) if isinstance(exc, ValueError) else "QuanSyn 操作失败，未确认成功，请检查连接或重试。"
        return {"success": not turn.get("failed", False), "receipt": turn["reply"]}

    def validate_outputs(self, sender, transfer, paths, blocks):
        if not isinstance(paths, list) or len(paths) > 10:
            raise ValueError("最多登记 10 个文件")
        # Installed packages include an exact copy of the canonical server contract.
        try:
            from ._quansyn_contract import Block
        except ImportError:
            from backend.contracts.quansyn import Block
        if not isinstance(blocks, list) or len(blocks) > 100 or len(json.dumps(blocks).encode()) > 512_000:
            raise ValueError("输出块超过 100 项或 512 KB")
        validated = [Block.model_validate(b).model_dump() for b in blocks]
        root = self.root(sender, transfer)
        outputs = []
        for value in paths:
            path = Path(value)
            if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("只允许登记当前任务目录内的文件")
            if path.stat().st_size == 0:
                raise ValueError("输出文件为空")
            with path.open("rb") as stream:
                content_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            outputs.append({"path": str(path), "hash": content_hash})
        return outputs, validated

    def outputs(self, inputs, **kw):
        session = str(kw.get("session_id") or "")
        turn = self.turns.get(session, {})
        if not turn.get("executing") or not self.authorized(turn, "outputs", kw):
            raise ValueError("只有当前可信执行回合可以登记输出")
        sender = turn["sender"]
        if turn.get("batch"):
            items = inputs.get("items")
            if not isinstance(items, list):
                raise ValueError("批量执行必须逐条登记 items")
            expected = list(turn.get("batch_ids") or [])
            supplied = [str(item.get("id") or "") for item in items if isinstance(item, dict)]
            if len(items) != len(supplied) or len(supplied) != len(set(supplied)) or set(supplied) != set(expected):
                raise ValueError("批量输出必须且只能覆盖本回合全部需求")
            prepared = []
            for item in items:
                transfer = str(item["id"])
                success = item.get("success") is True
                if success:
                    result = str(item.get("result") or "").strip()
                    if not result:
                        raise ValueError(f"{transfer} 缺少完整执行结果")
                    outputs, blocks = self.validate_outputs(
                        sender, transfer, item.get("paths", []), item.get("blocks", []))
                    prepared.append((transfer, True, result, outputs, blocks, ""))
                else:
                    error = str(item.get("error") or "").strip()
                    if not error:
                        raise ValueError(f"{transfer} 失败项缺少错误说明")
                    prepared.append((transfer, False, "", [], [], error[:1000]))
            completed = failed = 0
            for transfer, success, result, outputs, blocks, error in prepared:
                saved = self.ctx.state.get(self.key(sender, transfer), {})
                saved.pop("running_until", None)
                saved.pop("running_turn", None)
                if success:
                    saved.update(outputs=outputs, result_blocks=blocks, result=result, completed=True)
                    self.queue_remove(sender, transfer)
                    completed += 1
                else:
                    saved.update(completed=False, last_error=error)
                    self.queue_add(sender, transfer)
                    failed += 1
                self.ctx.state.set(self.key(sender, transfer), saved)
            turn.update(batch_registered=True, completed_count=completed, failed_count=failed,
                        partial=bool(completed and failed), failed=bool(failed and not completed),
                        reply=f"批量执行完成：成功 {completed} 条，失败 {failed} 条。失败项已保留在队列，可再次发送 /quansyn 重试。")
            return {"success": failed == 0, "completed": completed, "failed": failed,
                    "message": turn["reply"]}

        paths = inputs.get("paths", [])
        blocks = inputs.get("blocks", [])
        transfer = turn["id"]
        outputs, validated = self.validate_outputs(sender, transfer, paths, blocks)
        saved = self.ctx.state.get(self.key(sender, transfer), {})
        saved.update(outputs=outputs, result_blocks=validated)
        self.ctx.state.set(self.key(sender, transfer), saved)
        return {"success": True, "files": [{"number": i + 1, "name": Path(f["path"]).name} for i, f in enumerate(outputs)], "message": "输出已登记，等待用户明确选择回传附件"}

    def finalize(self, response_text="", **kw):
        turn = self.turns.get(str(kw.get("session_id") or ""), {})
        if not turn or kw.get("turn_id") != turn.get("turn_id"):
            return None
        if turn.get("batch_registered"):
            for transfer in turn.get("batch_ids", []):
                saved = self.ctx.state.get(self.key(turn["sender"], transfer), {})
                completed = saved.get("completed") is True
                self.deliver_card({"sender": turn["sender"], "action": "批量执行", "id": transfer,
                    "reply": saved.get("result") if completed else saved.get("last_error", "执行失败"),
                    "failed": not completed, "completed_count": 1 if completed else 0})
            return turn["reply"]
        if turn.get("reply") is not None:
            message_id = turn.get("card_message_id")
            route = self.delivery.get(turn["sender"])
            if message_id and route:
                self.update_progress_card(route[0], message_id, turn["sender"], "", turn=turn)
            else:
                self.deliver_card(turn)
            return turn["reply"]
        if not turn.get("command_result"):
            return "QuanSyn 指令未取得实际执行回执，请重试。"
        if turn.get("batch"):
            for transfer in turn.get("batch_ids", []):
                saved = self.ctx.state.get(self.key(turn["sender"], transfer), {})
                saved.pop("running_until", None)
                saved.pop("running_turn", None)
                saved["completed"] = False
                self.ctx.state.set(self.key(turn["sender"], transfer), saved)
                self.queue_add(turn["sender"], transfer)
            turn.update(failed=True, reply="批量执行未登记逐项结果，全部需求已保留在队列；发送 /quansyn 可重试。")
            self.deliver_card(turn)
            return turn["reply"]
        if turn.get("executing") and response_text:
            key = self.key(turn["sender"], turn["id"])
            saved = self.ctx.state.get(key, {})
            saved.update(result=response_text, completed=True)
            saved.pop("running_until", None)
            saved.pop("running_turn", None)
            self.ctx.state.set(key, saved)
            self.queue_remove(turn["sender"], turn["id"])
            self.deliver_card(turn)
            outputs = saved.get("outputs", [])
            files = "\n".join(f'{i + 1}. {Path(f["path"]).name}' for i, f in enumerate(outputs))
            return response_text + f'\n\nQuanSyn 回传：发送“推送 QuanSyn {turn["id"]}”。' + ("\n可选附件：\n" + files + "\n回传附件时在指令后加“附件 1,2”。" if files else "")
        return None
