"""Logical knowledge-pack catalog, wallet and retrieval isolation tests."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"

FAKE_SUPER = False


def _headers() -> dict[str, str]:
    from jose import jwt as jose_jwt

    token = jose_jwt.encode(
        {"sub": "1", "exp": datetime.utcnow() + timedelta(hours=1)},
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestLogicalKnowledgePacks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="logical-catalog-test-"))
        wiki = self.tmp / "wiki/方法论"
        raw = self.tmp / "raw"
        wiki.mkdir(parents=True)
        raw.mkdir()
        for name, body in [
            ("公共方法", "DeepSeek 公共方法"),
            ("审计", "公共审计知识"),
            ("专业方法", "高级套餐证据"),
            ("私有方法", "租户内部口径"),
            ("待复核", "不得进入检索"),
        ]:
            (wiki / f"{name}.md").write_text(f"# {name}\n{body}\n", encoding="utf-8")
        (raw / "原文.md").write_text("# 原文\n不得直接检索 DeepSeek。\n", encoding="utf-8")

        packs = [
            self._pack("knowledge/methodology/public", "公共方法论", "green", 1),
            self._pack("knowledge/行业知识/审计", "审计", "green", 1),
            self._pack(
                "knowledge/methodology/entitlement/premium-methodology",
                "专业方法论", "yellow", 1, entitlement="premium-methodology",
            ),
            self._pack(
                "knowledge/methodology/private/u-test",
                "私有方法论", "red", 1, owner="u-test",
            ),
        ]
        documents = [
            self._document("wiki/方法论/公共方法.md", packs[0]["category"], "green"),
            self._document("wiki/方法论/审计.md", packs[1]["category"], "green"),
            self._document("wiki/方法论/专业方法.md", packs[2]["category"], "yellow"),
            self._document("wiki/方法论/私有方法.md", packs[3]["category"], "red"),
        ]
        (self.tmp / "knowledge_catalog.json").write_text(
            json.dumps({
                "version": "2.0",
                "generated_at": "2026-08-19T00:00:00Z",
                "packs": packs,
                "documents": documents,
                "excluded_count": 1,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        matrix = {
            "version": "2.0",
            "stats": {"total_documents": 5},
            "entity_index": {
                "DeepSeek": ["wiki/方法论/公共方法.md", "raw/原文.md"],
                "私有口径": ["wiki/方法论/私有方法.md"],
            },
            "categories": {
                "wiki": {
                    "公共方法": {"path": "wiki/方法论/公共方法.md"},
                    "专业方法": {"path": "wiki/方法论/专业方法.md"},
                    "私有方法": {"path": "wiki/方法论/私有方法.md"},
                    "待复核": {"path": "wiki/方法论/待复核.md"},
                },
                "raw": {"原文": {"path": "raw/原文.md"}},
            },
        }
        (self.tmp / "knowledge_matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
        )

        import backend.api.auth as auth
        import backend.api.knowledge as knowledge
        from backend.services.knowledge_catalog import clear_manifest_cache

        self.auth = auth
        self.knowledge = knowledge
        self._old_resolver = auth.tenant_resolver
        self._old_vault = knowledge._vault
        self._old_matrix_path = knowledge.MATRIX_PATH
        knowledge._vault = lambda: self.tmp
        knowledge.MATRIX_PATH = self.tmp / "knowledge_matrix.json"
        knowledge._matrix.cache_clear()
        clear_manifest_cache()

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "org_id": "org-test",
                "is_super_admin": FAKE_SUPER,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver
        from backend.main import app

        self.transport = httpx.ASGITransport(app=app)

    @staticmethod
    def _pack(category, title, security, count, owner="public", entitlement=""):
        return {
            "category": category,
            "path_prefix": "wiki/",
            "title": title,
            "doc_count": count,
            "open": True,
            "security_level": security,
            "owner_tenant": owner,
            "entitlement_key": entitlement,
            "knowledge_level": "K5",
            "classification_status": "approved",
            "freshness": "current",
            "source_count": count * 2,
        }

    @staticmethod
    def _document(path, pack, security):
        return {
            "knowledge_id": "kn-" + Path(path).stem,
            "path": path,
            "title": Path(path).stem,
            "pack_id": pack,
            "knowledge_level": "K5",
            "classification_status": "approved",
            "security_level": security,
            "freshness": "current",
            "source_count": 2,
        }

    def tearDown(self):
        global FAKE_SUPER
        FAKE_SUPER = False
        self.auth.tenant_resolver = self._old_resolver
        self.knowledge._vault = self._old_vault
        self.knowledge.MATRIX_PATH = self._old_matrix_path
        self.knowledge._matrix.cache_clear()
        from backend.services.knowledge_catalog import clear_manifest_cache

        clear_manifest_cache()
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def _request(self, method, path, **kwargs):
        async with httpx.AsyncClient(
            transport=self.transport,
            base_url="http://testserver",
            headers=_headers(),
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method, path, **kwargs):
        return asyncio.run(self._request(method, path, **kwargs))

    def test_catalog_contains_logical_packs_not_physical_folders(self):
        response = self.request("GET", "/api/v1/catalog")
        self.assertEqual(response.status_code, 200)
        catalog = {item["category"]: item for item in response.json()["catalog"]}
        self.assertIn("knowledge/methodology/public", catalog)
        self.assertIn("knowledge/methodology/private/u-test", catalog)
        self.assertEqual(
            catalog["knowledge/methodology/entitlement/premium-methodology"]["access_state"],
            "upgrade_required",
        )
        self.assertNotIn("raw", catalog)
        self.assertNotIn("wiki", catalog)

    def test_search_excludes_raw_pending_and_unentitled_yellow(self):
        public = self.request("GET", "/api/knowledge/search", params={"q": "DeepSeek"})
        paths = [item["path"] for item in public.json()["docs"]]
        self.assertEqual(paths, ["wiki/方法论/公共方法.md"])
        self.assertFalse(any(path.startswith("raw/") for path in paths))
        premium = self.request("GET", "/api/knowledge/search", params={"q": "高级套餐"})
        self.assertEqual(premium.json()["docs"], [])
        pending = self.request("GET", "/api/knowledge/search", params={"q": "不得进入检索"})
        self.assertEqual(pending.json()["docs"], [])

    def test_red_owner_is_visible_and_matrix_cannot_leak_raw(self):
        private = self.request("GET", "/api/knowledge/search", params={"q": "租户内部"})
        self.assertEqual(private.json()["docs"][0]["security_level"], "red")
        matrix = self.request("GET", "/api/knowledge/matrix").json()
        all_paths = json.dumps(matrix, ensure_ascii=False)
        self.assertNotIn("raw/原文.md", all_paths)
        self.assertNotIn("待复核.md", all_paths)

    def test_wallet_accepts_effective_pack_and_rejects_physical_folder(self):
        ok = self.request(
            "POST", "/api/v1/me/subscriptions",
            json={"category": "knowledge/methodology/public"},
        )
        self.assertEqual(ok.status_code, 200)
        denied = self.request(
            "POST", "/api/v1/me/subscriptions", json={"category": "raw"}
        )
        self.assertEqual(denied.status_code, 404)

    def test_wallet_body_endpoint_preserves_chinese_multisegment_category(self):
        category = "knowledge/行业知识/审计"
        added = self.request(
            "PUT", "/api/v1/me/knowledge-wallet", json={"category": category}
        )
        self.assertEqual(added.status_code, 200, added.text)
        self.assertIn(category, added.json()["categories"])

        removed = self.request(
            "DELETE", "/api/v1/me/knowledge-wallet", json={"category": category}
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertNotIn(category, removed.json()["categories"])

    def test_wallet_errors_are_actionable(self):
        response = self.request(
            "PUT", "/api/v1/me/knowledge-wallet", json={"category": "missing/类目"}
        )
        self.assertEqual(response.status_code, 404)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "catalog_item_not_found")
        self.assertEqual(detail["action"], "refresh_catalog")

    def test_super_admin_still_cannot_see_pending_or_raw(self):
        global FAKE_SUPER
        FAKE_SUPER = True
        stats = self.request("GET", "/api/knowledge/stats").json()
        self.assertEqual(stats["total_md_files"], 4)
        catalog = self.request("GET", "/api/v1/catalog").json()
        self.assertEqual(catalog["pending_review_count"], 1)
        self.assertNotIn("raw", {item["category"] for item in catalog["catalog"]})

    def test_visibility_is_pack_membership_not_path_prefix(self):
        visible = frozenset({"knowledge/methodology/public"})
        self.assertTrue(self.knowledge._rel_visible("wiki/方法论/公共方法.md", visible))
        self.assertFalse(self.knowledge._rel_visible("wiki/方法论/专业方法.md", visible))
        self.assertFalse(self.knowledge._rel_visible("raw/原文.md", None))
        self.assertFalse(self.knowledge._rel_visible("wiki/方法论/待复核.md", None))


if __name__ == "__main__":
    unittest.main()
