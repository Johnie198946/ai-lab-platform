from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.chat import ChatRuntime, build_router
from .api.runs import build_router as build_runs_router
from .auth import auth_dependency
from .config import Settings
from .governance import RunGovernance
from .hermes_linux import HermesLinuxRunner
from .persistence import RunRepository
from .sandbox import SandboxManager
from .template import TemplateRegistry

settings = Settings.from_env()
repository = RunRepository(settings.state_db)
sandbox_manager = SandboxManager(settings.sandbox_root)
runner = HermesLinuxRunner(settings, repository, sandbox_manager)
templates = TemplateRegistry(settings.hermes_template)
governance = RunGovernance(repository)
runtime = ChatRuntime(settings, repository, sandbox_manager, runner, templates)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository.init()
    governance.init()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Hermes Linux tenant-sandbox backend",
    lifespan=lifespan,
)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(build_router(runtime, auth_dependency(settings)))
app.include_router(build_runs_router(governance, repository, runner, auth_dependency(settings)))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": settings.version, "runtime": "hermes-linux"}


@app.get("/ready")
async def ready() -> dict:
    if not settings.hermes_template.is_dir():
        return {"status": "not_ready", "reason": "Hermes template unavailable"}
    return {"status": "ready", "version": settings.version, "runtime": "hermes-linux"}
