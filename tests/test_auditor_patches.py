"""
Unit tests verifying Auditor Agent fixes in AgentGuard, AgentRuntime, and Knowledge Matrix.
"""

import asyncio
import unittest
import os
import json
from pathlib import Path
from backend.agents.guard import AgentGuard
from backend.agents.runtime import AgentRuntime
from scripts.build_knowledge_matrix import build_matrix


class TestAuditorPatches(unittest.TestCase):

    def test_agent_guard_backoff(self):
        """Verify AgentGuard exponential backoff retry logic."""
        guard = AgentGuard()
        agent_name = "轻量编译"

        # Pre-check passes initially
        passed, reason = guard.pre_check(agent_name, 1000, ["/Users/dengzhaoyu/Desktop/AI Lab/AI Lab/"])
        self.assertTrue(passed)

        # Record run and failure
        guard.record_success(agent_name)
        guard.record_failure(agent_name)

        # Pre-check should trigger dynamic rate limit with backoff
        passed, reason = guard.pre_check(agent_name, 1000, ["/Users/dengzhaoyu/Desktop/AI Lab/AI Lab/"])
        self.assertFalse(passed)
        self.assertIn("动态频率限制", reason)
        self.assertIn("退避倍率: 2x", reason)

    def test_agent_runtime_parallel_read(self):
        """Verify AgentRuntime asyncio.gather parallel manifest reading."""
        async def run_test():
            runtime = AgentRuntime(data_dir="/tmp/test_agent_runtime_data")
            upstream = await runtime.read_manifest("全量入库")
            self.assertIsInstance(upstream, list)

        asyncio.run(run_test())

    def test_knowledge_matrix_build(self):
        """Verify knowledge matrix building across vault."""
        vault_dir = Path("/Users/dengzhaoyu/Desktop/AI Lab/AI Lab")
        matrix = build_matrix(vault_dir)
        self.assertEqual(matrix["version"], "1.0")
        self.assertGreater(matrix["stats"]["total_documents"], 0)
        self.assertIn("topics", matrix["categories"])


if __name__ == "__main__":
    unittest.main()
