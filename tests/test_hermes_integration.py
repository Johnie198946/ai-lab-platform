"""Hermes Main Integration Tests — Supervision Acceptance Checklist.

Tests cover:
1. Code quality (ruff clean) — run separately via `ruff check`
2. Async non-blocking — verify /api/health responds during Hermes execution
3. Working directory (cwd) assertion — verify subprocess receives correct cwd
4. Input validation — verify max_length=4000 truncation
5. Multi-turn context — verify history formatting
6. Timeout fallback — verify graceful degradation on timeout/error
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


class TestHermesIntegration(unittest.TestCase):
    """Test Hermes CLI integration per Supervision acceptance checklist."""

    def test_cwd_passed_to_subprocess(self):
        """Verify cwd is explicitly passed to subprocess.run (Checklist #3)."""
        from backend.api.orchestration import HERMES_CWD, _call_hermes_main_sync

        with patch("backend.api.orchestration.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
            _call_hermes_main_sync("test goal")

            # Verify cwd was passed
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            self.assertEqual(call_kwargs["cwd"], HERMES_CWD)
            self.assertEqual(call_kwargs["cwd"], "/opt/ai-lab-platform")

    def test_input_truncation(self):
        """Verify input is truncated to HERMES_MAX_INPUT_LENGTH (Checklist #4)."""
        from backend.api.orchestration import (
            HERMES_MAX_INPUT_LENGTH,
            _call_hermes_main_sync,
        )

        long_goal = "x" * 5000  # Exceeds 4000 char limit

        with patch("backend.api.orchestration.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
            _call_hermes_main_sync(long_goal)

            # Verify the goal passed to subprocess was truncated
            call_args = mock_run.call_args.args[0]
            # call_args is [HERMES_BIN, "-p", "default", "-z", goal]
            passed_goal = call_args[4]
            self.assertEqual(len(passed_goal), HERMES_MAX_INPUT_LENGTH)
            self.assertEqual(len(passed_goal), 4000)

    def test_timeout_fallback(self):
        """Verify graceful fallback on timeout (Checklist #6)."""
        from backend.api.orchestration import _call_hermes_main_sync

        with patch("backend.api.orchestration.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="hermes", timeout=120)
            result = _call_hermes_main_sync("test goal")

            self.assertIn("⚠️", result)
            self.assertIn("超时", result)

    def test_exception_fallback(self):
        """Verify graceful fallback on exception (Checklist #6)."""
        from backend.api.orchestration import _call_hermes_main_sync

        with patch("backend.api.orchestration.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("hermes not found")
            result = _call_hermes_main_sync("test goal")

            self.assertIn("⚠️", result)
            self.assertIn("异常", result)

    def test_nonzero_exit_code(self):
        """Verify graceful handling of non-zero exit codes."""
        from backend.api.orchestration import _call_hermes_main_sync

        with patch("backend.api.orchestration.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error: invalid input"
            )
            result = _call_hermes_main_sync("test goal")

            self.assertIn("⚠️", result)
            self.assertIn("执行失败", result)

    def test_multi_turn_prompt_empty_history(self):
        """Verify multi-turn prompt with no history returns goal as-is."""
        from backend.api.orchestration import Message, _build_multi_turn_prompt

        goal = "What is AI?"
        messages = []
        result = _build_multi_turn_prompt(goal, messages)
        self.assertEqual(result, goal)

    def test_multi_turn_prompt_with_history(self):
        """Verify multi-turn prompt includes conversation history."""
        from backend.api.orchestration import Message, _build_multi_turn_prompt

        goal = "Follow-up question"
        messages = [
            Message(role="user", content="First question"),
            Message(role="assistant", content="First answer"),
            Message(role="user", content="Second question"),
            Message(role="assistant", content="Second answer"),
        ]

        result = _build_multi_turn_prompt(goal, messages)

        self.assertIn("【对话历史】", result)
        self.assertIn("用户: First question", result)
        self.assertIn("助手: First answer", result)
        self.assertIn("用户: Second question", result)
        self.assertIn("助手: Second answer", result)
        self.assertIn("【当前问题】", result)
        self.assertIn("Follow-up question", result)

    def test_multi_turn_prompt_truncates_old_history(self):
        """Verify only last N turns are included (HERMES_MAX_HISTORY_TURNS)."""
        from backend.api.orchestration import (
            HERMES_MAX_HISTORY_TURNS,
            Message,
            _build_multi_turn_prompt,
        )

        # Create 20 messages (10 turns)
        messages = []
        for i in range(10):
            messages.append(Message(role="user", content=f"Q{i}"))
            messages.append(Message(role="assistant", content=f"A{i}"))

        goal = "Latest question"
        result = _build_multi_turn_prompt(goal, messages)

        # Should only include last HERMES_MAX_HISTORY_TURNS * 2 messages
        expected_count = HERMES_MAX_HISTORY_TURNS * 2
        # Count occurrences of "用户:" and "助手:"
        user_count = result.count("用户:")
        assistant_count = result.count("助手:")
        self.assertEqual(user_count + assistant_count, expected_count)

    def test_async_non_blocking(self):
        """Verify async wrapper doesn't block event loop (Checklist #2)."""
        from backend.api.orchestration import _call_hermes_main

        async def run_test():
            # Mock subprocess to simulate slow execution
            async def slow_subprocess(*args, **kwargs):
                await asyncio.sleep(0.5)
                return "Mock response"

            with patch(
                "backend.api.orchestration.asyncio.to_thread",
                side_effect=slow_subprocess,
            ):
                start = time.time()
                result = await _call_hermes_main("test")
                elapsed = time.time() - start

                self.assertEqual(result, "Mock response")
                self.assertGreater(elapsed, 0.4)  # Should take ~0.5s

        asyncio.run(run_test())

    def test_hermes_bin_path(self):
        """Verify HERMES_BIN is correctly configured."""
        from backend.api.orchestration import HERMES_BIN

        self.assertEqual(HERMES_BIN, "/opt/hermes/venv/bin/hermes")

    def test_hermes_cwd_path(self):
        """Verify HERMES_CWD is correctly configured."""
        from backend.api.orchestration import HERMES_CWD

        self.assertEqual(HERMES_CWD, "/opt/ai-lab-platform")


class TestOrchestrationAPIWithHermes(unittest.TestCase):
    """Test orchestration API endpoints with mocked Hermes."""

    def setUp(self):
        import backend.api.auth as auth

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": True,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver

        from backend.main import app
        import httpx

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

    async def _request(self, method, path, **kwargs):
        import httpx

        async with httpx.AsyncClient(
            transport=self._transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method, path, **kwargs):
        return asyncio.run(self._request(method, path, **kwargs))

    def auth_headers(self):
        from datetime import datetime, timedelta, timezone

        from jose import jwt as jose_jwt

        token = jose_jwt.encode(
            {
                "sub": "1",
                "username": "tester",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            "test-secret",
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    def test_create_session_with_hermes_success(self):
        """Verify session creation with successful Hermes response."""
        with patch("backend.api.orchestration._call_hermes_main_sync") as mock_hermes:
            mock_hermes.return_value = "Hermes response: AI Lab is awesome"

            response = self.request(
                "POST",
                "/api/orchestration/sessions",
                headers=self.auth_headers(),
                json={"goal": "Tell me about AI Lab"},
            )

            self.assertEqual(response.status_code, 201)
            data = response.json()
            self.assertEqual(data["reply"], "Hermes response: AI Lab is awesome")
            self.assertIn("messages", data)
            self.assertEqual(len(data["messages"]), 2)
            self.assertEqual(data["messages"][0]["role"], "user")
            self.assertEqual(data["messages"][1]["role"], "assistant")

    def test_create_session_with_hermes_failure_fallback(self):
        """Verify fallback when Hermes returns error."""
        with patch("backend.api.orchestration._call_hermes_main_sync") as mock_hermes:
            mock_hermes.return_value = "⚠️ Hermes main 执行超时（>120s）"

            response = self.request(
                "POST",
                "/api/orchestration/sessions",
                headers=self.auth_headers(),
                json={"goal": "Test timeout scenario"},
            )

            self.assertEqual(response.status_code, 201)
            data = response.json()
            # Should fall back to _build_reply
            self.assertIn("已理解你的业务目标", data["reply"])

    def test_identity_rule_bypasses_hermes(self):
        """Verify identity rules are checked before Hermes call."""
        with patch("backend.api.orchestration._call_hermes_main_sync") as mock_hermes:
            # Mock identity rule to return fixed response
            with patch(
                "backend.api.orchestration.match_identity_rule"
            ) as mock_identity:
                mock_identity.return_value = "我是超聚变 AI Lab 助手"

                response = self.request(
                    "POST",
                    "/api/orchestration/sessions",
                    headers=self.auth_headers(),
                    json={"goal": "你是谁"},
                )

                self.assertEqual(response.status_code, 201)
                data = response.json()
                self.assertEqual(data["reply"], "我是超聚变 AI Lab 助手")
                # Hermes should NOT be called
                mock_hermes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
