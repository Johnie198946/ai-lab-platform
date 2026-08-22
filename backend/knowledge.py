from __future__ import annotations

from dataclasses import dataclass


class KnowledgeDenied(PermissionError):
    pass


@dataclass(frozen=True)
class KnowledgePolicy:
    tenant_id: str
    allowed_scopes: frozenset[str]

    def authorize(self, color: str, owner_tenant: str | None = None) -> None:
        normalized = color.lower()
        if normalized == "green" and "public" in self.allowed_scopes:
            return
        if normalized == "yellow" and ("yellow" in self.allowed_scopes or "public" in self.allowed_scopes):
            return
        if normalized == "red" and owner_tenant == self.tenant_id and self.tenant_id in self.allowed_scopes:
            return
        raise KnowledgeDenied(f"knowledge policy denied {normalized} material")


def policy_for(tenant_id: str) -> KnowledgePolicy:
    return KnowledgePolicy(tenant_id=tenant_id, allowed_scopes=frozenset({"public", tenant_id}))
