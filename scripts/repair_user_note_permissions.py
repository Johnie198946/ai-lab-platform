#!/usr/bin/env python3
"""Normalize shared private-note transport permissions without changing ownership.

Hermes and the API remain responsible for tenant/user authorization. This script
only makes the server-owned bind mount traversable/readable across their distinct
runtime namespaces. Symlinks are never followed or modified.
"""
from __future__ import annotations

import argparse
import errno
import os
import stat
from pathlib import Path

DIRECTORY_MODE = 0o755
FILE_MODE = 0o644
ALLOWED_SUFFIXES = {".md", ".json"}


def repair_tree(root: Path) -> dict[str, int]:
    counts = {"directories": 0, "files": 0, "skipped_symlinks": 0}
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return counts
    except OSError as error:
        if error.errno not in {errno.ENOTDIR, errno.ELOOP}:
            raise
        raise ValueError("note permission root must be a real directory")

    def repair_directory(directory_fd: int) -> None:
        os.fchmod(directory_fd, DIRECTORY_MODE)
        counts["directories"] += 1
        for name in os.listdir(directory_fd):
            try:
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(entry.st_mode):
                counts["skipped_symlinks"] += 1
                continue
            if stat.S_ISDIR(entry.st_mode):
                try:
                    child_fd = os.open(
                        name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory_fd,
                    )
                except OSError as error:
                    if error.errno not in {errno.ENOENT, errno.ENOTDIR, errno.ELOOP}:
                        raise
                    counts["skipped_symlinks"] += error.errno == errno.ELOOP
                    continue
                try:
                    repair_directory(child_fd)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(entry.st_mode) or Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            try:
                child_fd = os.open(
                    name,
                    os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except OSError as error:
                if error.errno not in {errno.ENOENT, errno.ELOOP}:
                    raise
                continue
            try:
                if stat.S_ISREG(os.fstat(child_fd).st_mode):
                    os.fchmod(child_fd, FILE_MODE)
                    counts["files"] += 1
            finally:
                os.close(child_fd)

    try:
        repair_directory(root_fd)
    finally:
        os.close(root_fd)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    counts = repair_tree(args.root)
    print(
        "user_note_permissions "
        f"directories={counts['directories']} files={counts['files']} "
        f"skipped_symlinks={counts['skipped_symlinks']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
