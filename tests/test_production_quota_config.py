"""The production quota must reach every backend process, not only .env."""
from pathlib import Path

import yaml


def test_production_monthly_quota_environment():
    compose = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
    )
    for name in ("api", "workflow-worker", "planning-worker", "agent-evaluation-worker"):
        assert compose["services"][name]["environment"]["QUANTUM_MONTHLY_TOKEN_LIMIT"] == (
            "${QUANTUM_MONTHLY_TOKEN_LIMIT:-10000000}"
        )
