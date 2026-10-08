from pathlib import Path


ROOT = Path(__file__).parents[1]
HELPER = ROOT / "scripts" / "publication_container_exec.sh"
RELEASE = ROOT / "scripts" / "publication_release_remote.py"
EDITORIAL = ROOT / "scripts" / "publication_editorial_remote.py"


def test_publication_exec_is_serialized_and_avoids_compose_image_enumeration() -> None:
    script = HELPER.read_text(encoding="utf-8")
    assert "flock -w" in script
    assert "docker ps" in script
    assert "com.docker.compose.project=" in script
    assert "com.docker.compose.service=" in script
    assert "docker exec -i" in script
    assert "docker compose" not in script
    assert "images/json" not in script
    assert "${#containers[@]} != 1" in script


def test_all_publication_container_calls_use_the_bounded_helper() -> None:
    release = RELEASE.read_text(encoding="utf-8")
    editorial = EDITORIAL.read_text(encoding="utf-8")
    assert '"sudo", "-n", "/usr/local/sbin/ai-lab-publication-exec"' in release
    assert '"docker", "compose"' not in release
    assert "transport.CONTAINER_EXEC" in editorial
    assert "transport.OPERATOR[:" not in editorial
