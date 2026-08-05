"""
TokenBox — Token 计量 + 质量门

追踪每个 Agent 的 Token 消耗、成本、有效 Token 率
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List


class TokenBox:
    """Token 计量和质量追踪"""

    def __init__(self):
        self.records: List[Dict] = []
        self.by_agent: Dict[str, List[Dict]] = defaultdict(list)

        # 模型单价 · 单位: ¥/1M tokens
        self.pricing = {
            "deepseek-chat": {"input": 1.0, "output": 2.0},
            "deepseek-v4": {"input": 4.0, "output": 8.0},
            "gpt-4o": {"input": 35.0, "output": 140.0},
            "qwen3.6-35b": {"input": 0, "output": 0},  # 本地模型·免费
        }

    def track(
        self,
        agent_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        status: str = "success",
    ) -> Dict:
        """记录一次 Agent 调用"""
        price = self.pricing.get(model, {"input": 0, "output": 0})
        cost = (
            prompt_tokens * price["input"] / 1_000_000
            + completion_tokens * price["output"] / 1_000_000
        )

        record = {
            "agent": agent_name,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_rmb": round(cost, 4),
            "status": status,
            "time": datetime.now().isoformat(),
        }

        self.records.append(record)
        self.by_agent[agent_name].append(record)
        return record

    def agent_summary(self, agent_name: str, days: int = 7) -> Dict:
        """单个 Agent 的统计摘要"""
        records = self.by_agent.get(agent_name, [])
        if not records:
            return {"agent": agent_name, "calls": 0}

        total_tokens = sum(r["total_tokens"] for r in records)
        total_cost = sum(r["cost_rmb"] for r in records)
        error_count = sum(1 for r in records if r["status"] != "success")

        return {
            "agent": agent_name,
            "calls": len(records),
            "total_tokens": total_tokens,
            "total_cost_rmb": round(total_cost, 2),
            "error_rate": f"{error_count}/{len(records)}",
        }

    def all_summary(self) -> Dict:
        """全局统计"""
        return {
            "total_calls": len(self.records),
            "total_cost_rmb": round(sum(r["cost_rmb"] for r in self.records), 2),
            "by_agent": {name: self.agent_summary(name) for name in self.by_agent},
        }

    def quality_gate(
        self, output_text: str, expected_entities: list
    ) -> tuple[bool, float]:
        """
        简单的质量门检查

        Args:
            output_text: Agent 输出文本
            expected_entities: 期望出现的实体/关键词列表

        Returns:
            (passed, score) — score 0-100
        """
        if not output_text or not expected_entities:
            return True, 100.0

        hits = sum(1 for e in expected_entities if e in output_text)
        score = hits / len(expected_entities) * 100
        return score >= 60, score
