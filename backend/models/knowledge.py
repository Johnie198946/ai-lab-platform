"""
AI Lab 知识库数据模型 (Karpathy LLM Wiki v4.0)

架构: raw/ → wiki/ (两步，砍掉来源卡片中间层)
wiki 条目是唯一真理源，wikilinks 织成知识网
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    JSON,
)
from sqlalchemy.orm import relationship


# ---------- Wiki 条目 (核心模型) ----------
class WikiEntry:
    """LLM Wiki 条目——单一真理源。同一事实只在这个条目里出现一次。"""

    __tablename__ = "wiki_entries"

    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False, unique=True)
    entity_type = Column(String(50))  # 竞品 / 产品 / 战略信号 / 方法论 / 客户
    content = Column(Text)  # Markdown body
    aliases = Column(String(500))  # comma-separated
    tags = Column(String(500))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # wikilinks: 指向其它 wiki 条目的连接
    linked_entries = relationship(
        "WikiEntry",
        secondary="wiki_wikilinks",
        primaryjoin="WikiEntry.id == WikiLink.source_id",
        secondaryjoin="WikiEntry.id == WikiLink.target_id",
    )


class WikiLink:
    """Wiki 条目之间的 wikilink 连接"""

    __tablename__ = "wiki_wikilinks"

    source_id = Column(Integer, ForeignKey("wiki_entries.id"), primary_key=True)
    target_id = Column(Integer, ForeignKey("wiki_entries.id"), primary_key=True)


# ---------- 原始素材 (raw) ----------
class Article:
    """raw/ — 只追加不删除的原始素材"""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    source_url = Column(String(2000))
    source_kind = Column(String(50))  # manual / horizon / dialogue / report
    credibility = Column(String(20))  # high / medium / low
    ingested_at = Column(DateTime, default=datetime.utcnow)
    tags = Column(String(500))

    # 指向 wiki 条目 (raw 直接关联 wiki，没有来源卡片中间层)
    wiki_entry_id = Column(Integer, ForeignKey("wiki_entries.id"), nullable=True)


# ---------- Diff 快照 ----------
class DiffSnapshot:
    """每次编译的变更记录"""

    __tablename__ = "diff_snapshots"

    id = Column(Integer, primary_key=True)
    wiki_entry_id = Column(Integer, ForeignKey("wiki_entries.id"))
    status = Column(String(20))  # strengthened / weakened / uncontested / new
    change_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 蒸馏产物 ----------
class DistillOutput:
    """wiki → 营销资产 (七角色话术 / MOR材料 / Battle Card)"""

    __tablename__ = "distill_outputs"

    id = Column(Integer, primary_key=True)
    week = Column(String(20))  # 2026-W32
    output_type = Column(String(30))  # talking_points / mor_brief / battle_card
    content = Column(JSON)
    source_wiki_ids = Column(JSON)  # 溯源: 蒸馏自哪些 wiki 条目
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- Agent 运行日志 ----------
class AgentLog:
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True)
    agent_name = Column(String(100), nullable=False)
    run_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20))
    output_summary = Column(Text)
    files_processed = Column(Integer, default=0)
    token_used = Column(Integer)
    error_message = Column(Text)


# ---------- Manifest (数据通道) ----------
class Manifest:
    __tablename__ = "manifests"

    id = Column(Integer, primary_key=True)
    agent_name = Column(String(100))
    files = Column(JSON)
    summary = Column(String(500))
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 对话资产 ----------
class DialogueChunk:
    """raw/dialogues/ 对话片段"""

    __tablename__ = "dialogue_chunks"

    id = Column(Integer, primary_key=True)
    session_date = Column(String(20))
    topic = Column(String(300))
    entities = Column(JSON)  # 提取的实体列表
    decisions = Column(JSON)  # 决策记录
    wiki_entry_id = Column(Integer, ForeignKey("wiki_entries.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- Agent 任务流转 ----------
class Task:
    """Agent 间任务流转——投递、inbox、状态追踪"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    priority = Column(Integer, default=0)
    from_agent = Column(String(100))
    to_agent = Column(String(100))
    task_type = Column(String(50))
    payload = Column(JSON)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
