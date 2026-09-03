from pathlib import Path

import pytest

from scripts.repair_user_note_permissions import repair_tree


def test_repair_tree_normalizes_notes_metadata_and_directories(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    owner = root / "tenant" / "user"
    archive = owner / ".archive"
    archive.mkdir(parents=True)
    note = owner / "note.md"
    metadata = owner / "note.sync.json"
    archived = archive / "old.md"
    unrelated = owner / "keep.bin"
    for path in (note, metadata, archived, unrelated):
        path.write_text("data", encoding="utf-8")
        path.chmod(0o600)
    owner.chmod(0o700)
    archive.chmod(0o700)

    result = repair_tree(root)

    assert result["files"] == 3
    assert note.stat().st_mode & 0o777 == 0o644
    assert metadata.stat().st_mode & 0o777 == 0o644
    assert archived.stat().st_mode & 0o777 == 0o644
    assert unrelated.stat().st_mode & 0o777 == 0o600
    assert owner.stat().st_mode & 0o777 == 0o755
    assert archive.stat().st_mode & 0o777 == 0o755


def test_repair_tree_does_not_follow_or_modify_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    outside.chmod(0o600)
    (root / "linked.md").symlink_to(outside)
    outside_dir = tmp_path / "outside-directory"
    outside_dir.mkdir()
    hidden = outside_dir / "hidden.md"
    hidden.write_text("private", encoding="utf-8")
    hidden.chmod(0o600)
    (root / "linked-directory").symlink_to(outside_dir, target_is_directory=True)

    result = repair_tree(root)

    assert result["skipped_symlinks"] == 2
    assert outside.stat().st_mode & 0o777 == 0o600
    assert hidden.stat().st_mode & 0o777 == 0o600


def test_repair_tree_rejects_symlink_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="real directory"):
        repair_tree(linked)
