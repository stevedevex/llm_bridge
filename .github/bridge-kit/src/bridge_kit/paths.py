"""Where the kit and its repo are. The kit finds them from its own location, so it works wherever it's checked out."""

from __future__ import annotations

import os
from pathlib import Path


def kit_dir() -> Path:
    """`.github/bridge-kit` of the repo the kit belongs to."""
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    override = os.environ.get("BRIDGE_KIT_REPO_ROOT")
    return Path(override).resolve() if override else kit_dir().parents[1]


def work_dir() -> Path:
    """The git-ignored folder for caches, scratch files and run output."""
    return repo_root() / ".work"
