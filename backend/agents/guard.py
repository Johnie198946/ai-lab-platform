"""
Agent 守护层（AgentCare PEP）

千问工程经验: 三层防御 → 我们做两层
1. pre_check: 执行前 → Token预算·权限边界·频率限制
2. post_check: 执行后 → 输出合规·文件安全·有效Token率
"""

from datetime import datetime, timedelta
from typing import Dict, Optional


class AgentGuard:
    """Policy Enforcement Point — 策略执行点"""

    def __init__(self):
        self._last_run: Dict[str, datetime] = {}  # agent_name → last_run_time
        self._retry_counts: Dict[str, int] = {}  # agent_name → failed_retries
        self._rate_limits: Dict[str, int] = {  # agent_name → base_cooldown_minutes
            "轻量编译": 110,  # 每2h · 留10分钟余量
            "深度编译": 1380,  # 每23h
            "竞品情报": 1380,
            "Horizon": 1380,
            "空间清理": 10080,  # 每周
        }

    def record_failure(self, agent_name: str):
        """记录失败，增加重试退避计数"""
        self._retry_counts[agent_name] = self._retry_counts.get(agent_name, 0) + 1

    def record_success(self, agent_name: str):
        """记录成功，重置退避计数"""
        self._retry_counts[agent_name] = 0
        self._last_run[agent_name] = datetime.now()

    # ---------- 执行前检查 ----------
    def pre_check(
        self,
        agent_name: str,
        estimated_tokens: int,
        allowed_dirs: list,
        max_token_budget: int = 50000,
    ) -> tuple[bool, str]:
        """
        返回 (pass, reason)

        Args:
            agent_name: Agent 名称
            estimated_tokens: 预估消耗 Token 数
            allowed_dirs: 允许访问的目录列表
            max_token_budget: 单次调用最大 Token 预算
        """
        # 1. Token 预算预检
        if estimated_tokens > max_token_budget:
            return False, f"Token预算超限: {estimated_tokens} > {max_token_budget}"

        # 2. 动态频率限制 (结合指数退避 Exponential Backoff)
        base_cooldown = self._rate_limits.get(agent_name)
        if base_cooldown and agent_name in self._last_run:
            retries = self._retry_counts.get(agent_name, 0)
            # 退避因子: 失败越多，等待越久 (最大 4 倍)
            backoff_factor = min(2 ** retries, 4) if retries > 0 else 1
            effective_cooldown = base_cooldown * backoff_factor

            elapsed = (datetime.now() - self._last_run[agent_name]).total_seconds() / 60
            if elapsed < effective_cooldown:
                remaining = int(effective_cooldown - elapsed)
                msg = (
                    f"动态频率限制: {agent_name} 需等待 {remaining} 分钟 "
                    f"(退避倍率: {backoff_factor}x)"
                )
                return False, msg

        # 3. 权限边界
        forbidden = ["/etc", "/root", "/var", "~/.ssh", "~/.hermes/profiles"]
        for d in allowed_dirs:
            for f in forbidden:
                if d.startswith(f):
                    return False, f"权限拒绝: {d} (禁止访问系统目录)"

        return True, "pass"

    # ---------- 执行后验证 ----------
    def post_check(
        self,
        agent_name: str,
        result_files: list,
        output_size: int,
        effective_token_rate: float,
    ) -> tuple[bool, str]:
        """
        返回 (pass / warn / rollback, reason)

        Args:
            result_files: Agent 输出的文件路径列表
            output_size: 输出总大小(bytes)
            effective_token_rate: 有效 Token 率(0-1)
        """
        # 1. 空输出告警
        if not result_files or output_size < 100:
            return "warn", f"几乎空输出: {output_size} bytes"

        # 2. 有效 Token 率过低
        if effective_token_rate < 0.3:
            return "warn", f"有效Token率过低: {effective_token_rate:.1%}"

        # 3. 输出文件路径安全
        safe_prefixes = [
            "/Users/dengzhaoyu/Desktop/AI Lab/AI Lab/",
            "/tmp/",
        ]
        for f in result_files:
            if not any(f.startswith(p) for p in safe_prefixes):
                return "rollback", f"输出到非法路径: {f}"

        return "pass", "ok"

    # ---------- 记录 ----------
    def record_run(self, agent_name: str):
        """记录本次执行时间"""
        self._last_run[agent_name] = datetime.now()
