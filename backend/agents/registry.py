"""
Agent 注册表 + 运行时引擎

Agent 广场的"发现层"——不依赖前端
每个 Agent 的元数据、依赖关系、触发条件都在这里
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class AgentMeta:
    """Agent 元数据"""

    name: str
    description: str
    layer: str  # 采集 / 处理 / 编译 / 看板 / 治理
    schedule: str  # cron 表达式 或 "manual"
    tools: List[str]  # 需要的工具集
    inputs: List[str]  # 输入目录 / 上游 manifest
    outputs: List[str]  # 输出目录
    depends_on: List[str] = None  # 上游 Agent
    token_budget: int = 50000
    model: str = "deepseek-chat"
    knowledge_scope: List[str] = None
    allow_network: bool = False
    requires_review: bool = False

    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []
        if self.knowledge_scope is None:
            self.knowledge_scope = []


class AgentRegistry:
    """Agent 注册表——从配置文件读取，不依赖前端"""

    def __init__(self):
        self._agents: Dict[str, AgentMeta] = {}
        self._load_builtins()

    def _load_builtins(self):
        """加载内置 Agent"""
        builtins = [
            AgentMeta(
                name="Horizon",
                description="AI 情报雷达·每日扫描互联网",
                layer="采集",
                schedule="0 18 * * *",
                tools=["web_search", "browser_navigate", "write_file"],
                inputs=["互联网"],
                outputs=["raw/articles/", "raw/_manifest.json"],
                token_budget=30000,
                allow_network=True,
            ),
            AgentMeta(
                name="竞品情报",
                description="19家竞品每日对标·攻防话术",
                layer="采集",
                schedule="0 17 * * *",
                tools=["web_search", "browser_navigate", "write_file"],
                inputs=["互联网"],
                outputs=["竞品情报/", "raw/_manifest.json"],
                token_budget=40000,
                allow_network=True,
            ),
            AgentMeta(
                name="Wiki Ingester",
                description="raw → wiki: 读 manifest·直接写 wiki 条目·不建来源卡片",
                layer="处理",
                schedule="30 */2 * * *",
                tools=["read_file", "write_file", "search_files"],
                inputs=["raw/_manifest.json"],
                outputs=["wiki/"],
                depends_on=["Horizon", "竞品情报", "GPU追踪", "客户画像"],
                token_budget=50000,
                knowledge_scope=["raw", "wiki"],
                requires_review=True,
            ),
            AgentMeta(
                name="Dialogue Ingester",
                description="对话 → wiki: 提取实体+决策·更新 wiki 条目",
                layer="处理",
                schedule="30 */2 * * *",
                tools=["read_file", "write_file", "search_files"],
                inputs=["00_Inbox/", "raw/dialogues/"],
                outputs=["wiki/"],
                token_budget=30000,
                knowledge_scope=["00_Inbox", "raw/dialogues", "wiki"],
                requires_review=True,
            ),
            AgentMeta(
                name="Wiki Writer",
                description="每2h·Ingest+Diff: raw→wiki·标记 strengthened/weakened",
                layer="编译",
                schedule="0 */2 * * *",
                tools=["read_file", "write_file", "search_files"],
                inputs=["wiki/"],
                outputs=["wiki条目更新·Diff标记"],
                depends_on=["Wiki Ingester", "Dialogue Ingester"],
                token_budget=20000,
                knowledge_scope=["wiki"],
                requires_review=True,
            ),
            AgentMeta(
                name="Deep Compiler",
                description="夜间02:00·Synth+Distill: 跨条目交叉验证+蒸馏",
                layer="编译",
                schedule="0 2 * * *",
                tools=["read_file", "write_file", "search_files"],
                inputs=["wiki/"],
                outputs=["wiki条目交叉验证·Diff快照·蒸馏产物"],
                depends_on=["Wiki Writer"],
                token_budget=80000,
                model="deepseek-v4",
                knowledge_scope=["wiki", "研究系统", "蒸馏"],
                requires_review=True,
            ),
            AgentMeta(
                name="Knowledge Evolution",
                description="读diff快照·刷新dashboard",
                layer="看板",
                schedule="30 18 * * *",
                tools=["read_file", "write_file", "search_files"],
                inputs=["raw/_diff_snapshot.md"],
                outputs=["dashboard更新"],
                depends_on=["Deep Compiler"],
                token_budget=15000,
                knowledge_scope=["raw", "wiki"],
            ),
            AgentMeta(
                name="空间清理",
                description="周日删构建垃圾",
                layer="治理",
                schedule="0 8 * * 0",
                tools=["terminal"],
                inputs=["产品设计/"],
                outputs=[],
                token_budget=5000,
            ),
            # --- 独立 Agent（按需触发·不依赖 Cron）---
            AgentMeta(
                name="SuperVision",
                description="独立审计Agent·零侵入代码审查·知识库巡检",
                layer="治理",
                schedule="manual",
                tools=["terminal", "read_file", "search_files", "write_file"],
                inputs=["ai-lab-platform/", "研究系统/来源卡片/"],
                outputs=["研究系统/来源卡片/", "raw/reports/"],
                token_budget=80000,
                model="deepseek-v4",
                knowledge_scope=["ai-lab-platform", "研究系统", "raw/reports"],
                requires_review=True,
            ),
            AgentMeta(
                name="Code Agent",
                description="代码沙箱·隔离执行·HTML/SwiftUI/Python",
                layer="独立服务",
                schedule="manual",
                tools=["sandbox:write_file", "sandbox:read_file", "sandbox:run"],
                inputs=["用户需求"],
                outputs=["sandbox://"],
                token_budget=50000,
                model="deepseek-v4",
                requires_review=True,
            ),
            AgentMeta(
                name="Image Agent",
                description="图片理解·多模态·OCR·图表分析",
                layer="独立服务",
                schedule="manual",
                tools=["image_analyze"],
                inputs=["用户上传图片"],
                outputs=["分析结果"],
                token_budget=20000,
                model="gpt-4o-mini",
            ),
            AgentMeta(
                name="Doc Maker",
                description="文档渲染·Markdown→DOCX/PDF·图表生成",
                layer="独立服务",
                schedule="manual",
                tools=["terminal", "write_file", "read_file"],
                inputs=["产品设计/"],
                outputs=["docx_build/", "产品设计/*.png"],
                token_budget=30000,
            ),
        ]
        for a in builtins:
            self._agents[a.name] = a

    # ---------- 查询接口 ----------
    def list_all(self) -> List[AgentMeta]:
        """列出所有 Agent"""
        return list(self._agents.values())

    def list_by_layer(self, layer: str) -> List[AgentMeta]:
        """按层列出"""
        return [a for a in self._agents.values() if a.layer == layer]

    def get_dependencies(self, name: str) -> List[str]:
        """获取上游依赖"""
        agent = self._agents.get(name)
        return agent.depends_on if agent else []

    def get_downstream(self, name: str) -> List[str]:
        """获取下游消费者"""
        return [a.name for a in self._agents.values() if name in a.depends_on]

    def search(self, keyword: str) -> List[AgentMeta]:
        """按关键词搜索 Agent"""
        kw = keyword.lower()
        return [
            a
            for a in self._agents.values()
            if kw in a.name.lower() or kw in a.description.lower()
        ]

    def export_for_tenant(self) -> Dict:
        """导出给租户看——不含内部配置"""
        return {
            name: {
                "description": a.description,
                "layer": a.layer,
                "schedule": a.schedule,
                "depends_on": a.depends_on,
            }
            for name, a in self._agents.items()
        }
