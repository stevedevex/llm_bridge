"""One audit log for the command line and the MCP server, `.work/logs/bridge-kit.jsonl`: a line per call to GitLab
through the MCP server, and per payload read from either front end. Each line says when, who (the OS user), from where
(`cli` or `mcp`), the call, its arguments, and whether it worked. What was written to GitLab is in GitLab, so a
description or a comment shows by its length only; no line carries a token, a connection string or a payload.
"""

from __future__ import annotations

import getpass
import json
from datetime import datetime, timezone

from bridge_kit.paths import work_dir

LOG = "bridge-kit.jsonl"
BY_LENGTH = ("description", "body")


def record(via: str, call: str, arguments: dict, ok: bool, error: str | None = None) -> None:
    try:
        who = getpass.getuser()
    except (OSError, KeyError):
        who = "unknown"
    shown = {k: f"<{len(v)} characters>" if k in BY_LENGTH and isinstance(v, str) else v
             for k, v in arguments.items() if v is not None}
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "who": who, "via": via, "tool": call,
            "arguments": shown, "ok": ok, **({"error": error} if error else {})}
    try:
        log = work_dir() / "logs" / LOG
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass  # an audit line that can't be written never stops a read
