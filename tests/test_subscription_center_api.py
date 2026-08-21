"""Tenant-derived subscription-center proxy contract tests."""

from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta

import httpx

os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def _headers(user_id: str = "member-1") -> dict[str, str]:
    from jose import jwt

    token = jwt.encode(
        {"sub": user_id, "exp": datetime.utcnow() + timedelta(hours=1)},
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestSubscriptionCenterProxy(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth
        import backend.api.subscriptions as subscriptions
        from backend.main import app

        self.auth = auth
        self.subscriptions = subscriptions
        self._old_resolver = auth.tenant_resolver
        self._old_request = subscriptions._authen_request
        self._old_base_status = subscriptions.base_knowledge_status
        self._old_private_status = subscriptions.tenant_private_knowledge_status
        self.calls: list[tuple[str, str, dict]] = []
        self.super_admin = False
        self.base_status = {
            "status": "building",
            "document_count": 0,
            "minimum_document_count": 5,
            "category_count": 0,
            "minimum_category_count": 2,
            "categories": [],
            "last_compiled_at": None,
        }

        async def resolver(_user_id):
            return {
                "tenant_key": "tenant-a",
                "org_id": "11111111-1111-1111-1111-111111111111",
                "is_super_admin": self.super_admin,
                "categories": set(),
            }

        async def authen_request(method, path, **kwargs):
            self.calls.append((method, path, kwargs))
            if path.endswith("/plans"):
                return {"plans": [
                    {"id": "plan-pro", "name": "Pro", "pack_allowance": 2},
                    {"id": "plan-basic", "name": "团队知识基础版", "pack_allowance": 0},
                ]}
            if path.endswith("/subscription-center"):
                return {
                    "organization_id": "11111111-1111-1111-1111-111111111111",
                    "application_id": "ai-lab-platform",
                    "subscription": None,
                    "requests": [],
                    "knowledge_packs": [{"id": "pack-1", "status": "draft"}],
                    "active_pack_grants": [],
                    "pack_allowance": 0,
                }
            if path.endswith("/subscription-requests") and method == "POST":
                return {"id": "request-1", **(kwargs.get("json") or {})}
            return {"application_id": "ai-lab-platform", "requests": []}

        auth.tenant_resolver = resolver
        subscriptions._authen_request = authen_request
        subscriptions.base_knowledge_status = lambda _vault: self.base_status
        subscriptions.tenant_private_knowledge_status = lambda _tenant, _vault: {
            "document_count": 0,
            "category_count": 0,
            "categories": [],
        }
        self.transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        self.auth.tenant_resolver = self._old_resolver
        self.subscriptions._authen_request = self._old_request
        self.subscriptions.base_knowledge_status = self._old_base_status
        self.subscriptions.tenant_private_knowledge_status = self._old_private_status

    async def _request(self, method, path, **kwargs):
        async with httpx.AsyncClient(
            transport=self.transport,
            base_url="http://testserver",
            headers=_headers(),
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method, path, **kwargs):
        return asyncio.run(self._request(method, path, **kwargs))

    def test_center_uses_server_derived_organization(self):
        response = self.request("GET", "/api/v1/subscription-center")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["plans"][0]["name"], "Pro")
        center_call = next(call for call in self.calls if call[1].endswith("subscription-center"))
        self.assertIn("11111111-1111-1111-1111-111111111111", center_call[1])

    def test_requester_and_organization_cannot_be_spoofed(self):
        response = self.request(
            "POST",
            "/api/v1/subscription-requests",
            json={
                "request_id": "ios-request-0001",
                "plan_id": "plan-pro",
                "requested_entitlements": ["audit-pro"],
                "requested_pack_ids": ["pack-1", "pack-2"],
                "reason": "需要审计知识",
                "organization_id": "attacker-org",
                "requested_by": "attacker",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        post_call = next(call for call in self.calls if call[0] == "POST")
        self.assertIn("11111111-1111-1111-1111-111111111111", post_call[1])
        self.assertEqual(post_call[2]["json"]["requested_by"], "member-1")
        self.assertEqual(post_call[2]["json"]["requested_pack_ids"], ["pack-1", "pack-2"])
        self.assertNotIn("organization_id", post_call[2]["json"])

    def test_center_forwards_knowledge_pack_governance_state(self):
        response = self.request("GET", "/api/v1/subscription-center")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["knowledge_packs"][0]["status"], "draft")
        self.assertEqual(body["pack_allowance"], 0)
        self.assertEqual(body["base_knowledge"]["status"], "building")
        basic = next(item for item in body["plans"] if item["id"] == "plan-basic")
        self.assertFalse(basic["is_available"])
        self.assertEqual(basic["availability"], "content_building")

    def test_base_plan_application_is_blocked_until_public_corpus_is_ready(self):
        response = self.request(
            "POST",
            "/api/v1/subscription-requests",
            json={
                "request_id": "ios-basic-request-0001",
                "plan_id": "plan-basic",
                "requested_entitlements": [],
                "requested_pack_ids": [],
                "reason": "申请基础公共知识",
            },
        )
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "base_knowledge_building")
        self.assertEqual(detail["action"], "retry_later")
        self.assertFalse(any(call[0] == "POST" for call in self.calls))

    def test_base_plan_application_is_forwarded_when_public_corpus_is_ready(self):
        self.base_status = {
            **self.base_status,
            "status": "ready",
            "document_count": 5,
            "category_count": 2,
            "categories": ["knowledge/product/public", "knowledge/methodology/public"],
        }
        response = self.request(
            "POST",
            "/api/v1/subscription-requests",
            json={
                "request_id": "ios-basic-request-0002",
                "plan_id": "plan-basic",
                "requested_entitlements": [],
                "requested_pack_ids": [],
                "reason": "申请基础公共知识",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(any(call[0] == "POST" for call in self.calls))

    def test_member_cannot_read_admin_approval_queue(self):
        response = self.request("GET", "/api/v1/admin/subscription-requests")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "admin_required")


if __name__ == "__main__":
    unittest.main()
