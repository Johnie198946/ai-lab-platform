from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "AI Lab Platform"
    version: str = "1.0.0-rewrite"
    hermes_bin: str = "hermes"
    hermes_template: Path = Path("/opt/ai-lab/hermes-template")
    sandbox_root: Path = Path("/var/lib/ai-lab/sandboxes")
    state_db: Path = Path("/var/lib/ai-lab/state/runs.sqlite3")
    authen_jwks_url: str = ""
    allow_dev_auth: bool = False
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(x.strip() for x in os.getenv("AI_LAB_CORS_ORIGINS", "").split(",") if x.strip())
        return cls(
            hermes_bin=os.getenv("HERMES_BIN", "hermes"),
            hermes_template=Path(os.getenv("AI_LAB_HERMES_TEMPLATE", "/opt/ai-lab/hermes-template")),
            sandbox_root=Path(os.getenv("AI_LAB_SANDBOX_ROOT", "/var/lib/ai-lab/sandboxes")),
            state_db=Path(os.getenv("AI_LAB_STATE_DB", "/var/lib/ai-lab/state/runs.sqlite3")),
            authen_jwks_url=os.getenv("AUTHEN_JWKS_URL", ""),
            allow_dev_auth=os.getenv("AI_LAB_ALLOW_DEV_AUTH", "0") == "1",
            cors_origins=origins,
        )
