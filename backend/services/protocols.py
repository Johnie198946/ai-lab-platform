"""
协议派发服务 — 将创建好的协议写入 Obsidian Vault 的 00_Inbox/

现有机制: main/supervision/coder 三方通过读取 00_Inbox/ 进行协作
新协议创建后自动写入 inbox，agent 可直接读取并签署
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime

from backend.models.protocol import AgentProtocol


def _default_vault_path() -> Path:
    """获取 Obsidian Vault 路径（从环境变量或默认）"""
    vault = os.environ.get("INBOX_PATH", "")
    if vault:
        return Path(vault)
    # 默认路径: 用户文档目录下的 Obsidian Vault
    home = Path.home()
    candidates = [
        home / "Documents" / "Obsidian Vault" / "00_Inbox",
        home / "Obsidian" / "00_Inbox",
        home / "Desktop" / "Obsidian" / "00_Inbox",
    ]
    for c in candidates:
        if c.exists():
            return c
    # 兜底: 项目根目录下的 data/inbox（开发环境）
    return Path(__file__).parent.parent.parent / "data" / "inbox"


def dispatch_to_inbox(protocol: AgentProtocol) -> Path:
    """
    将协议写入 inbox 目录，生成 Frontmatter 格式的 markdown 文件

    Frontmatter 契约:
    ---
    id: <protocol.id>
    title: <protocol.title>
    status: <protocol.status>
    tenant_key: <protocol.tenant_key>
    created_by: <protocol.created_by>
    created_at: <ISO 格式时间>
    agents:
      - name: <agent_name>
        status: <signature.status>
        signed_at: <ISO 格式时间或 null>
    ---

    返回写入的文件路径
    """
    inbox_dir = _default_vault_path()
    inbox_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名: 时间戳 + 标题（安全化）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in protocol.title)
    safe_title = safe_title[:50]  # 限制长度
    filename = f"{timestamp}-{safe_title}.md"
    filepath = inbox_dir / filename

    # 构建 Frontmatter
    agents_yaml = []
    for sig in protocol.signatures:
        agent_entry = {
            "name": sig.agent_name,
            "status": sig.status,
            "signed_at": sig.signed_at.isoformat() if sig.signed_at else None,
        }
        agents_yaml.append(agent_entry)

    # 手动构建 YAML（避免引入 pyyaml 依赖）
    frontmatter_lines = [
        "---",
        f"id: {protocol.id}",
        f"title: {protocol.title}",
        f"status: {protocol.status}",
        f"tenant_key: {protocol.tenant_key}",
        f"created_by: {protocol.created_by}",
        f"created_at: {protocol.created_at.isoformat()}",
        "agents:",
    ]
    for agent in agents_yaml:
        frontmatter_lines.append(f"  - name: {agent['name']}")
        frontmatter_lines.append(f"    status: {agent['status']}")
        signed_at_str = agent['signed_at'] if agent['signed_at'] else "null"
        frontmatter_lines.append(f"    signed_at: {signed_at_str}")
    frontmatter_lines.append("---")

    frontmatter = "\n".join(frontmatter_lines)
    content = f"{frontmatter}\n\n{protocol.content}\n"

    # 写入文件
    filepath.write_text(content, encoding="utf-8")
    return filepath
