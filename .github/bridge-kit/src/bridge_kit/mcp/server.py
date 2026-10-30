"""The bridge-kit MCP server: JSON-RPC 2.0 over stdio, one message per line, as the Model Context Protocol's stdio
transport says. It answers `initialize`, `ping`, `tools/list` and `tools/call`, and ignores notifications.

Its tools are the GitLab calls `bridge-kit gitlab` makes and the payload reads `bridge-kit payload` makes, through the
same functions (`gitlab.py`, `payloads.py`), so both front ends reach only what `bridge-kit.yaml` declares and never
show a token or a connection string. The read tools are marked read-only. The four write
tools (create and update an issue, add a note, link two issues) write only to projects declared `read-write`, and
aren't marked read-only, so the IDE asks the BA to confirm each call; their descriptions say to call one only once
the BA has approved exactly that. The payload tools are read-only, and go through the payload guard first. A tool
that fails (not declared, the token refused, nothing there) answers with `isError` and the one line the command line
would print; a server whose `bridge-kit.yaml` has no GitLab or no MongoDB still starts, and each tool says what to add.

Each call appends a line to the audit log, `.work/logs/bridge-kit.jsonl` (`audit.py`), which the command line's
payload reads share. Nothing but protocol messages goes to stdout.
"""

from __future__ import annotations

import json
import sys
from typing import Callable

from bridge_kit import audit
from bridge_kit.paths import repo_root

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")  # newest first
SERVER = {"name": "bridge-kit", "title": "bridge-kit: GitLab and stored payloads for the BA's agents",
          "version": "0.1.0"}
INSTRUCTIONS = ("GitLab tools for the projects and wikis the BA repo's bridge-kit.yaml declares: reading stories with "
                "their comments and links, epics, and wiki pages; and, in read-write projects only, creating and "
                "updating a story, commenting and linking two. Write only once the BA has approved exactly what you'll "
                "write, in the chat. Name a story as REQ-101, <project>#101 or its link. Start with bridge_kit_status "
                "when anything fails. To keep a story or a page as a work item's input, run `bridge-kit inputs add` on "
                "the command line. The payload tools read stored payloads from MongoDB by request id, from dev or SIT "
                "only: start with payload_status.")

STORY = {"type": "string", "description": "REQ-101 (a project's key and number), <project>#101, or its GitLab link"}
PROJECT = {"type": "string", "description": "The declared project a bare story number is in"}
WIKI = {"type": "string", "description": "The declared project or group whose wiki; needed when more than one has one"}


def _tool(name: str, title: str, description: str, properties: dict, required: tuple = ()) -> dict:
    return {"name": name, "title": title, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": list(required),
                            "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "openWorldHint": False}}


TOOLS = [
    _tool("bridge_kit_status", "GitLab status", "Who the GitLab token is, and whether each declared project, group and "
          "wiki answers at its declared path", {}),
    _tool("gitlab_get_issue", "Read a story", "One GitLab story: title, state, labels, milestone, assignees, dates, "
          "link and description; with its comments and its linked stories when asked",
          {"story": STORY, "project": PROJECT,
           "notes": {"type": "boolean", "description": "With its comments (GitLab's system notes left out)"},
           "links": {"type": "boolean", "description": "With the stories it blocks, is blocked by, relates to"}},
          ("story",)),
    _tool("gitlab_list_issues", "List stories", "Stories in a declared project, latest updated first, one line each",
          {"project": {"type": "string", "description": "The declared project; by default default_project"},
           "label": {"type": "string", "description": "Labels, comma-separated: every one must be on the story"},
           "milestone": {"type": "string"}, "state": {"type": "string", "enum": ["opened", "closed", "all"]},
           "search": {"type": "string", "description": "Text in the title or description"},
           "author": {"type": "string", "description": "The author's username"},
           "limit": {"type": "integer", "minimum": 1, "maximum": 500, "description": "At most this many (50)"}}),
    _tool("gitlab_issue_links", "A story's links", "The stories one blocks, is blocked by, or relates to",
          {"story": STORY, "project": PROJECT}, ("story",)),
    _tool("gitlab_get_epic", "Read an epic", "An epic and its stories, where the GitLab tier has epics",
          {"group": {"type": "string", "description": "The declared group"},
           "iid": {"type": "integer", "minimum": 1, "description": "The epic's number in the group"}},
          ("group", "iid")),
    _tool("gitlab_list_wiki_pages", "List wiki pages", "A declared wiki's pages, with their slugs", {"wiki": WIKI}),
    _tool("gitlab_get_wiki_page", "Read a wiki page", "One wiki page, as its Markdown",
          {"slug": {"type": "string", "description": "The page's slug, as the list shows it (onboarding/checklist)"},
           "wiki": WIKI}, ("slug",)),
    _tool("gitlab_search_wiki", "Search the wiki", "The wiki pages holding some text, with the lines that match",
          {"text": {"type": "string"}, "wiki": WIKI}, ("text",)),
]


LABELS = {"type": "array", "items": {"type": "string"}, "description": "Labels, each one"}
APPROVED = " Call it only once the BA has approved exactly this, in the chat."


def _write_tool(name: str, title: str, description: str, properties: dict, required: tuple,
                destructive: bool = False) -> dict:
    tool = _tool(name, title, description + APPROVED, properties, required)
    tool["annotations"] = {"readOnlyHint": False, "destructiveHint": destructive, "idempotentHint": False,
                           "openWorldHint": False}
    return tool


TOOLS += [
    _write_tool("gitlab_create_issue", "Create a story", "A new issue in a declared read-write project, with its "
                "title, its Markdown description and its labels",
                {"project": {"type": "string", "description": "The declared read-write project"},
                 "title": {"type": "string"}, "description": {"type": "string", "description": "Markdown"},
                 "labels": LABELS}, ("project", "title")),
    _write_tool("gitlab_update_issue", "Update a story", "Change a story's title, description, labels or state "
                "(close, reopen), in a declared read-write project",
                {"story": STORY, "project": PROJECT, "title": {"type": "string"},
                 "description": {"type": "string", "description": "Markdown: it replaces the whole description"},
                 "labels": {**LABELS, "description": "Its labels, all of them: they replace the ones it has"},
                 "state": {"type": "string", "enum": ["close", "reopen"]}}, ("story",), destructive=True),
    _write_tool("gitlab_add_note", "Comment on a story", "A comment on a story in a declared read-write project",
                {"story": STORY, "project": PROJECT, "body": {"type": "string", "description": "Markdown"}},
                ("story", "body")),
    _write_tool("gitlab_link_issues", "Link two stories", "A \"relates to\" link from a story in a declared "
                "read-write project to another declared story",
                {"story": STORY, "target": {**STORY, "description": "The story it relates to"}, "project": PROJECT},
                ("story", "target")),
]


SERVICE = {"type": "string", "description": "A declared service, e.g. service-a-java"}
REQUEST_ID = {"type": "string", "description": "The request's UUID"}
FROM_MONGODB = (" From dev or SIT only, by request id, as bridge-kit.yaml declares; each payload kept in "
                ".work/payloads/.")

TOOLS += [
    _tool("payload_status", "Payload status", "MongoDB's environment, and whether each declared service's collection "
          "answers", {}),
    _tool("payload_get", "Read a payload", "One service's stored payload for a request, as JSON." + FROM_MONGODB,
          {"service": SERVICE, "request_id": REQUEST_ID}, ("service", "request_id")),
    _tool("payload_trace", "Trace a request", "The same request in every declared service, side by side: the "
          "collecting service's payload beside the summary service's." + FROM_MONGODB,
          {"request_id": REQUEST_ID}, ("request_id",)),
    _tool("payload_check", "Check a payload", "One stored payload against the internal model, by model path: fields "
          "the model doesn't have, required ones missing, nulls, wrong types, codes, formats." + FROM_MONGODB,
          {"service": SERVICE, "request_id": REQUEST_ID}, ("service", "request_id")),
    _tool("payload_profile", "Profile payloads", "The shape across several payloads of one service: per model path, "
          "how often it's there and null, its types, list sizes, the codes it takes." + FROM_MONGODB,
          {"service": SERVICE, "request_ids": {"type": "array", "items": REQUEST_ID, "minItems": 1}},
          ("service", "request_ids")),
    _tool("payload_raw", "Raw upstream responses", "The raw upstream responses behind a request, per upstream and "
          "operation, where a service keeps them." + FROM_MONGODB,
          {"request_id": REQUEST_ID, "upstream": {"type": "string", "description": "Only this upstream's"}},
          ("request_id",)),
]


def _payload_reads() -> dict[str, Callable]:
    from bridge_kit import payloads as p

    return {
        "payload_status": lambda c, a: p.read_status(c),
        "payload_get": lambda c, a: p.read_payload(c, str(a["service"]), str(a["request_id"])),
        "payload_trace": lambda c, a: p.read_trace(c, str(a["request_id"])),
        "payload_check": lambda c, a: p.read_check(c, str(a["service"]), str(a["request_id"]))[:2],
        "payload_profile": lambda c, a: p.read_profile(c, str(a["service"]), [str(r) for r in a["request_ids"]]),
        "payload_raw": lambda c, a: p.read_raw(c, str(a["request_id"]),
                                               None if a.get("upstream") is None else str(a["upstream"])),
    }


def _reads() -> dict[str, Callable]:
    from bridge_kit import gitlab as g

    return {
        "bridge_kit_status": lambda c, a: g.read_status(c),
        "gitlab_get_issue": lambda c, a: g.read_issue(c, a["story"], a.get("project"), bool(a.get("notes")),
                                                      bool(a.get("links"))),
        "gitlab_list_issues": lambda c, a: g.read_issue_list(c, a.get("project"), a.get("label"), a.get("milestone"),
                                                             a.get("state"), a.get("search"), a.get("author"),
                                                             int(a.get("limit") or 50)),
        "gitlab_issue_links": lambda c, a: g.read_links(c, a["story"], a.get("project")),
        "gitlab_get_epic": lambda c, a: g.read_epic(c, a["group"], int(a["iid"])),
        "gitlab_list_wiki_pages": lambda c, a: g.read_wiki_list(c, a.get("wiki")),
        "gitlab_get_wiki_page": lambda c, a: g.read_wiki_page(c, a["slug"], a.get("wiki")),
        "gitlab_search_wiki": lambda c, a: g.read_wiki_search(c, a["text"], a.get("wiki")),
        "gitlab_create_issue": lambda c, a: g.write_create_issue(c, a["project"], a["title"], a.get("description") or "",
                                                                 a.get("labels")),
        "gitlab_update_issue": lambda c, a: g.write_update_issue(c, a["story"], a.get("project"), a.get("title"),
                                                                 a.get("description"), a.get("labels"), a.get("state")),
        "gitlab_add_note": lambda c, a: g.write_add_note(c, a["story"], a["body"], a.get("project")),
        "gitlab_link_issues": lambda c, a: g.write_link_issues(c, a["story"], a["target"], a.get("project")),
    }


class Server:
    def __init__(self):
        self._client = None
        self._payloads = None

    def client(self):
        """The GitLab client, made on the first call that needs it: bridge-kit.yaml read and the token fetched then."""
        if self._client is None:
            from bridge_kit.config import ConfigError, load_config
            from bridge_kit.gitlab import GitLab

            config = load_config()
            if config.gitlab is None:
                raise ConfigError("bridge-kit.yaml declares no GitLab: add integrations.gitlab (see "
                                  "bridge-kit.example.yaml)")
            self._client = GitLab(config.gitlab)
        return self._client

    def payloads(self):
        """The payload reader, made on the first payload call: bridge-kit.yaml read and the guard passed then."""
        if self._payloads is None:
            from bridge_kit.config import load_config
            from bridge_kit.payloads import Payloads

            self._payloads = Payloads(load_config())
        return self._payloads

    def handle(self, message: dict) -> dict | None:
        """The response to one message, or None for a notification."""
        method, ident = message.get("method"), message.get("id")
        if "id" not in message:  # a notification: initialized, cancelled, ...
            return None
        if method == "initialize":
            asked = (message.get("params") or {}).get("protocolVersion")
            return _result(ident, {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                                   "capabilities": {"tools": {"listChanged": False}},
                                   "serverInfo": SERVER, "instructions": INSTRUCTIONS})
        if method == "ping":
            return _result(ident, {})
        if method == "tools/list":
            return _result(ident, {"tools": TOOLS})
        if method == "tools/call":
            params = message.get("params") or {}
            name, arguments = params.get("name"), params.get("arguments") or {}
            reads, payload_reads = _reads(), _payload_reads()
            if name in payload_reads:
                return _result(ident, self._call(name, arguments, payload_reads[name], self.payloads))
            if name not in reads:
                return _error(ident, -32602, f"Unknown tool: {name}")
            return _result(ident, self._call(name, arguments, reads[name], self.client))
        return _error(ident, -32601, f"Method not found: {method}")

    def _call(self, name: str, arguments: dict, read: Callable, client: Callable) -> dict:
        from bridge_kit.auth import TokenError
        from bridge_kit.config import ConfigError
        from bridge_kit.gitlab import GitLabError
        from bridge_kit.guard import GuardError
        from bridge_kit.payloads import PayloadError

        try:
            text, _ = read(client(), arguments)
            audit.record("mcp", name, arguments, True)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except (ConfigError, GuardError, TokenError, GitLabError, PayloadError, KeyError, ValueError) as e:
            line = f"Missing argument: {e}" if isinstance(e, KeyError) else str(e)
            audit.record("mcp", name, arguments, False, line)
            return {"content": [{"type": "text", "text": line}], "isError": True}


def _result(ident, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def _error(ident, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


def serve(stdin=None, stdout=None) -> None:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    server = Server()
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            response = server.handle(message) if isinstance(message, dict) else _error(None, -32600, "Invalid Request")
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def main() -> None:
    print(f"bridge-kit MCP server for {repo_root()}", file=sys.stderr)
    serve()
