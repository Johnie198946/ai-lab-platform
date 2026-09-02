"""Governed base public knowledge readiness and last-known-good tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.services.knowledge_catalog import (
    base_knowledge_status,
    clear_manifest_cache,
    load_manifest,
)


class TestBaseKnowledgeStatus(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="base-knowledge-")
        self.vault = Path(self.temp.name)

    def tearDown(self):
        clear_manifest_cache()
        self.temp.cleanup()

    @staticmethod
    def _document(index: int, pack: str, security: str = "green") -> dict:
        return {
            "knowledge_id": f"kn-{index}",
            "path": f"wiki/方法论/{index}.md",
            "pack_id": pack,
            "knowledge_level": "K5",
            "classification_status": "approved",
            "security_level": security,
        }

    def _write(self, documents: list[dict], generated_at: str = "2026-08-20T00:00:00Z") -> None:
        (self.vault / "knowledge_catalog.json").write_text(
            json.dumps({
                "version": "2.0",
                "generated_at": generated_at,
                "packs": [],
                "documents": documents,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        clear_manifest_cache()

    def test_four_documents_are_building(self):
        self._write([
            self._document(index, "knowledge/methodology/public")
            for index in range(4)
        ])
        status = base_knowledge_status(self.vault)
        self.assertEqual(status["status"], "building")
        self.assertEqual(status["document_count"], 4)

    def test_five_documents_across_two_categories_are_ready(self):
        documents = [
            self._document(index, "knowledge/methodology/public")
            for index in range(4)
        ]
        documents.append(self._document(5, "knowledge/product/public"))
        documents.append(self._document(6, "knowledge/methodology/entitlement/pro", "yellow"))
        self._write(documents)
        status = base_knowledge_status(self.vault)
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["document_count"], 5)
        self.assertEqual(status["category_count"], 2)
        self.assertNotIn("knowledge/methodology/entitlement/pro", status["categories"])

    def test_approved_green_documents_are_visible_regardless_of_knowledge_level(self):
        document = self._document(1, "knowledge/methodology/public")
        document["knowledge_level"] = "K3"
        self._write([document])
        status = base_knowledge_status(self.vault)
        self.assertEqual(status["document_count"], 1)
        self.assertEqual(status["categories"], ["knowledge/methodology/public"])

    def test_invalid_rebuild_keeps_last_valid_projection(self):
        self._write([
            self._document(index, "knowledge/methodology/public")
            for index in range(5)
        ])
        first = load_manifest(self.vault)
        self.assertEqual(len(first["documents"]), 5)
        (self.vault / "knowledge_catalog.json").write_text("{partial", encoding="utf-8")
        clear_manifest_cache()
        recovered = load_manifest(self.vault)
        self.assertEqual(len(recovered["documents"]), 5)


if __name__ == "__main__":
    unittest.main()
