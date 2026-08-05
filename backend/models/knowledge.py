"""
AI Lab 知识库数据模型

对应 Obsidian vault 的三层架构:
raw/ → 研究系统/来源卡片/ → 研究系统/专题档案/
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Table, Enum, Boolean
from sqlalchemy.orm import relationship

# ---------- 原始文章 ----------
class Article:
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    source_url = Column(String(2000))
    source_kind = Column(String(50))  # manual / horizon / cron-agent
    credibility = Column(String(20))  # high / medium / low
    ingested_at = Column(DateTime, default=datetime.utcnow)
    tags = Column(String(500))  # comma-separated
    
    # 外键到来源卡片(1:1)
    source_card = relationship("SourceCard", back_populates="article", uselist=False)

# ---------- 来源卡片 ----------
class SourceCard:
    __tablename__ = "source_cards"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), unique=True)
    title = Column(String(500))
    summary = Column(Text)  # 用 AI Lab 统一语言重述
    wikilinks = Column(String(2000))  # JSON array of linked card IDs
    tags = Column(String(500))
    diff_status = Column(String(50))  # strengthened / weakened / uncontested / new
    created_at = Column(DateTime, default=datetime.utcnow)
    
    article = relationship("Article", back_populates="source_card")
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)

# ---------- 专题档案 ----------
class Topic:
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    content = Column(Text)  # Synth 综合撰写
    source_count = Column(Integer, default=0)  # 聚合的卡片数
    status = Column(String(30), default="draft")  # draft / published / archived
    last_synthesized_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    cards = relationship("SourceCard", backref="topic")

# ---------- 蒸馏简报 ----------
class DistillBrief:
    __tablename__ = "distill_briefs"
    
    id = Column(Integer, primary_key=True)
    week = Column(String(20))  # 2026-W32
    competition_talking_points = Column(Text)  # 竞争话术 JSON
    industry_trends = Column(Text)             # 行业趋势 JSON
    customer_pain_points = Column(Text)        # 客户痛点 JSON(7行业)
    solution_highlights = Column(Text)         # 方案亮点 JSON
    created_at = Column(DateTime, default=datetime.utcnow)

# ---------- Agent 运行日志 ----------
class AgentLog:
    __tablename__ = "agent_logs"
    
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(100), nullable=False)
    run_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20))  # running / success / error
    output_summary = Column(Text)
    files_processed = Column(Integer, default=0)
    token_used = Column(Integer)
    error_message = Column(Text)

# ---------- Manifest (数据通道) ----------
class Manifest:
    __tablename__ = "manifests"
    
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(100))
    files = Column(Text)  # JSON array of file paths
    summary = Column(String(500))
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
