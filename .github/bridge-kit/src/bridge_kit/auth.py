"""Tokens, and MongoDB's connection string, from where `bridge-kit.yaml` says they are: an environment variable, a file
only its owner can read, or a command that prints it. A token is never printed, logged or returned to an agent: it goes
from here into a request header (or the database driver) and nowhere else, and no error message carries it."""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
from pathlib import Path


class TokenError(Exception):
    """The token isn't where bridge-kit.yaml says, or can't be read safely."""


def read_token(source: dict, what: str = "GitLab", noun: str = "token") -> str:
    kind = source.get("from")
    if kind == "env":
        value = os.environ.get(str(source["env"]), "")
        if not value.strip():
            raise TokenError(f"No {what} {noun}: the environment variable {source['env']} isn't set")
        return value.strip()
    if kind == "file":
        path = Path(str(source["file"])).expanduser()
        if not path.is_file():
            raise TokenError(f"No {what} {noun}: {path} doesn't exist")
        if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise TokenError(f"The {what} {noun} file {path} can be read by others: chmod 600 it")
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            raise TokenError(f"No {what} {noun}: {path} is empty")
        return value
    if kind == "command":
        try:
            result = subprocess.run(shlex.split(str(source["command"])), capture_output=True, text=True, timeout=60,
                                    check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise TokenError(f"The {what} {noun}'s command didn't run: {type(e).__name__}") from None
        if result.returncode != 0 or not result.stdout.strip():
            raise TokenError(f"The {what} {noun}'s command exited with {result.returncode} and printed no {noun}")
        return result.stdout.strip().splitlines()[0].strip()
    raise TokenError(f"Unknown {what} {noun} source: {kind}")
