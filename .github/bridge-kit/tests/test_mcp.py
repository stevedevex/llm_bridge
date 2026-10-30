"""bridge-kit-mcp: the MCP SDK's own client talks to the server over stdio, as an IDE's Copilot would, and reads the
stand-in GitLab through it; and the protocol's details, message by message: version negotiation, notifications,
unknown methods and tools, parse errors."""

import io
import json
import os
import sys
from pathlib import Path

import anyio
import pytest
import yaml
from fixtures.fake_gitlab import FakeGitLab
from test_gitlab import TOKEN, config, routes

from bridge_kit.mcp.server import PROTOCOL_VERSIONS, TOOLS, Server, serve

pytest.importorskip("mcp")


@pytest.fixture
def repo(tmp_path):
    """A BA repo declaring the stand-in GitLab, and the stand-in itself."""
    with FakeGitLab({}) as fake:
        fake.routes.update(routes(fake.url))
        repo = tmp_path / "ba-repo"
        (repo / ".github" / "bridge-kit").mkdir(parents=True)
        (repo / ".github" / "bridge-kit" / "bridge-kit.yaml").write_text(yaml.safe_dump(config(fake.url)),
                                                                         encoding="utf-8")
        yield {"repo": repo, "fake": fake}


def session(repo: Path, calls):
    """Starts the server as a subprocess and runs `calls(session)` with the SDK's client; returns what it returns."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "bridge_kit.mcp"],
                                   env={**os.environ, "BRIDGE_KIT_REPO_ROOT": str(repo),
                                        "BRIDGE_KIT_TEST_GITLAB_TOKEN": TOKEN})

    async def go():
        async with stdio_client(params, errlog=open(os.devnull, "w")) as (read, write):
            async with ClientSession(read, write) as client:
                return await calls(client)

    return anyio.run(go)


def text(result) -> str:
    return "".join(part.text for part in result.content)


def test_the_sdk_s_client_lists_the_tools_and_reads_a_story(repo):
    async def calls(client):
        init = await client.initialize()
        tools = await client.list_tools()
        story = await client.call_tool("gitlab_get_issue", {"story": "REQ-142", "notes": True})
        status = await client.call_tool("bridge_kit_status", {})
        return init, tools, story, status

    init, tools, story, status = session(repo["repo"], calls)

    assert init.server_info.name == "bridge-kit" and init.protocol_version in PROTOCOL_VERSIONS
    assert [t.name for t in tools.tools] == [t["name"] for t in TOOLS]
    assert all(t.annotations.read_only_hint is (t.name not in WRITES) for t in tools.tools)
    assert not story.is_error
    assert text(story).startswith("# REQ-142: Show each legal entity's EU VAT registration")
    assert "Which countries count as EU?" in text(story)
    assert text(status).endswith("GitLab: OK\n")
    assert {token for _, _, token in repo["fake"].requests} == {TOKEN}


def test_a_refused_read_is_a_tool_error_with_the_command_line_s_line(repo):
    async def calls(client):
        await client.initialize()
        return (await client.call_tool("gitlab_get_issue", {"story": "other-project#5"}),
                await client.call_tool("gitlab_get_wiki_page", {"slug": "home"}))

    undeclared, which_wiki = session(repo["repo"], calls)

    assert undeclared.is_error and text(undeclared).startswith("other-project isn't a declared project")
    assert which_wiki.is_error and text(which_wiki).startswith("Which wiki? Name it with --wiki")
    assert repo["fake"].requests == []


def test_every_call_is_audited_without_the_token(repo):
    async def calls(client):
        await client.initialize()
        await client.call_tool("gitlab_search_wiki", {"text": "time zone", "wiki": "ba-requirements"})
        await client.call_tool("gitlab_get_epic", {"group": "nowhere", "iid": 1})

    session(repo["repo"], calls)

    log = (repo["repo"] / ".work" / "logs" / "bridge-kit.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(line) for line in log.splitlines()]
    assert [(l["tool"], l["ok"]) for l in lines] == [("gitlab_search_wiki", True), ("gitlab_get_epic", False)]
    assert lines[1]["error"].startswith("nowhere isn't a declared group") and TOKEN not in log


def test_without_a_gitlab_the_server_starts_and_each_tool_says_what_to_add(tmp_path, monkeypatch):
    from conftest import LANDSCAPE

    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    (repo / ".github" / "bridge-kit" / "bridge-kit.yaml").write_text((LANDSCAPE / "bridge-kit.yaml").read_text(),
                                                                     encoding="utf-8")
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))

    result = Server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "bridge_kit_status", "arguments": {}}})["result"]

    assert result["isError"] and result["content"][0]["text"].startswith("bridge-kit.yaml declares no GitLab")


@pytest.mark.parametrize("asked, answered", [("2024-11-05", "2024-11-05"), ("2025-06-18", "2025-06-18"),
                                             ("2031-01-01", PROTOCOL_VERSIONS[0])])
def test_the_protocol_version_is_the_client_s_when_the_server_speaks_it(asked, answered):
    response = Server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": asked, "capabilities": {}}})

    assert response["result"]["protocolVersion"] == answered
    assert response["result"]["capabilities"] == {"tools": {"listChanged": False}}


@pytest.mark.parametrize("message, expected", [
    ({"jsonrpc": "2.0", "method": "notifications/initialized"}, None),
    ({"jsonrpc": "2.0", "id": 7, "method": "ping"}, {"jsonrpc": "2.0", "id": 7, "result": {}}),
    ({"jsonrpc": "2.0", "id": 8, "method": "resources/list"},
     {"jsonrpc": "2.0", "id": 8, "error": {"code": -32601, "message": "Method not found: resources/list"}}),
    ({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "gitlab_delete_issue"}},
     {"jsonrpc": "2.0", "id": 9, "error": {"code": -32602, "message": "Unknown tool: gitlab_delete_issue"}}),
])
def test_notifications_pings_and_unknowns(message, expected):
    assert Server().handle(message) == expected


def test_one_message_per_line_and_a_line_that_isn_t_json_is_a_parse_error():
    out = io.StringIO()
    serve(io.StringIO('\n{not json}\n[1, 2]\n{"jsonrpc": "2.0", "id": 1, "method": "ping"}\n'), out)

    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [l.get("error", {}).get("code") for l in lines] == [-32700, -32600, None]
    assert lines[2] == {"jsonrpc": "2.0", "id": 1, "result": {}}


WRITES = {"gitlab_create_issue", "gitlab_update_issue", "gitlab_add_note", "gitlab_link_issues"}


def test_the_reads_are_read_only_and_the_four_writes_ask_first():
    for tool in TOOLS:
        assert tool["inputSchema"]["type"] == "object" and tool["description"]
        assert tool["annotations"]["readOnlyHint"] is (tool["name"] not in WRITES)
    assert {t["name"] for t in TOOLS if not t["annotations"]["readOnlyHint"]} == WRITES
    assert all("only once the BA has approved exactly this" in t["description"] for t in TOOLS if t["name"] in WRITES)
    assert not any("delete" in t["name"] for t in TOOLS)


def test_a_write_goes_only_to_a_read_write_project_and_its_text_isn_t_logged(repo):
    fake = repo["fake"]
    fake.routes["POST /api/v4/projects/101/issues"] = lambda body: {"iid": 151, "web_url": f"{fake.url}/x/151", **body}

    async def calls(client):
        await client.initialize()
        return (await client.call_tool("gitlab_create_issue", {"project": "ba-requirements", "title": "Show VAT",
                                                               "description": "As a credit analyst, ...",
                                                               "labels": ["vat"]}),
                await client.call_tool("gitlab_add_note", {"story": "service-a#5", "body": "Hello"}))

    created, refused = session(repo["repo"], calls)

    assert not created.is_error and text(created).startswith("Created REQ-151 in ba-requirements: Show VAT")
    assert fake.writes == [("POST", "/api/v4/projects/101/issues",
                            {"title": "Show VAT", "description": "As a credit analyst, ...", "labels": "vat"}, TOKEN)]
    assert refused.is_error and text(refused).startswith("service-a is read-only in bridge-kit.yaml")
    log = (repo["repo"] / ".work" / "logs" / "bridge-kit.jsonl").read_text(encoding="utf-8")
    assert "<24 characters>" in log and "As a credit analyst" not in log
