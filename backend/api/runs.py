from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import AuthContext
from ..governance import RunGovernance


def build_router(governance: RunGovernance, repository, runner, auth_dependency) -> APIRouter:
    router = APIRouter(prefix="/api/runs", tags=["runs"])

    @router.get("/{run_id}/events")
    async def events(run_id: str, after: int = 0, auth: AuthContext = Depends(auth_dependency)):
        if not repository.get(run_id, auth.tenant_id):
            raise HTTPException(status_code=404, detail="run not found")
        return {"run_id": run_id, "events": [event.__dict__ for event in repository.events(run_id, after)]}

    @router.post("/{run_id}/approval")
    async def approval(run_id: str, payload: dict, auth: AuthContext = Depends(auth_dependency)):
        try:
            result = governance.approve(run_id, auth.tenant_id, auth.subject, bool(payload.get("approved")))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        return result.__dict__

    @router.post("/{run_id}/cancel")
    async def cancel(run_id: str, auth: AuthContext = Depends(auth_dependency)):
        if not repository.get(run_id, auth.tenant_id):
            raise HTTPException(status_code=404, detail="run not found")
        cancelled = await runner.cancel(run_id, auth.tenant_id)
        return {"run_id": run_id, "cancelled": cancelled}

    return router
