"""Checks the repo's agents, manifests, skills and prompts against Copilot's formats and against each other."""

import json
import re

import pytest
import yaml

from bridge_kit.markdown import read_markdown
from bridge_kit.paths import kit_dir
from bridge_kit.schema import problems

GITHUB = kit_dir().parent
MANIFESTS = sorted((GITHUB / "bridge-kit" / "agents").glob("*/manifest.yaml"))
AGENT_FILES = sorted((GITHUB / "agents").glob("*.agent.md"))
SKILL_FILES = sorted((GITHUB / "skills").glob("*/SKILL.md"))
PROMPT_FILES = sorted((GITHUB / "prompts").glob("*.prompt.md"))

# Front matter Copilot reads in agent files; anything else belongs in the manifest.
COPILOT_AGENT_FIELDS = {"name", "description", "target", "tools", "model", "disable-model-invocation",
                        "user-invocable", "mcp-servers", "metadata", "argument-hint", "handoffs"}
TOOL_ALIASES = {"execute", "shell", "read", "edit", "search", "agent", "custom-agent", "web", "todo"}
SKILL_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def front_matter(path):
    return read_markdown(path.read_text(encoding="utf-8")).front_matter


def manifest(name):
    return yaml.safe_load((GITHUB / "bridge-kit" / "agents" / name / "manifest.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.name)
def test_agent_files_use_only_copilot_fields(path):
    fields = front_matter(path)
    body = path.read_text(encoding="utf-8").split("\n---", 1)[1]

    assert set(fields) <= COPILOT_AGENT_FIELDS, set(fields) - COPILOT_AGENT_FIELDS
    assert fields.get("description")
    assert fields["name"] == path.name.removesuffix(".agent.md")
    assert set(fields.get("tools", [])) <= TOOL_ALIASES
    assert len(body) <= 30_000


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.name)
def test_every_agent_has_a_matching_manifest(path):
    name = path.name.removesuffix(".agent.md")
    data = manifest(name)

    assert data["name"] == name
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(data["version"]))
    assert data["layer"] in ("workflow", "specialist", "checker")
    assert data["status"] in ("experimental", "stable", "deprecated")
    for skill in data.get("skills", {}):
        assert (GITHUB / "skills" / skill / "SKILL.md").exists(), f"{name} needs the skill {skill}"
    if data["layer"] == "checker":  # it fixes nothing: at most its report, so the report outlives the chat
        assert set(data.get("writes") or []) <= {"work/*/validation-*.md"}


MANIFEST_SCHEMA = json.loads((GITHUB / "bridge-kit" / "schema" / "manifest.schema.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.parent.name)
def test_every_manifest_fits_the_manifest_schema(path):
    assert problems(yaml.safe_load(path.read_text(encoding="utf-8")), MANIFEST_SCHEMA) == []


def test_the_manifest_schema_catches_what_drifts():
    found = problems({"name": "x", "version": "1.0", "status": "beta", "layer": "specialist", "colour": "blue",
                      "skills": {"a": "latest"}}, MANIFEST_SCHEMA)

    assert "version doesn't match ^\\d+\\.\\d+\\.\\d+$" in found
    assert "status must be one of experimental, stable, deprecated" in found
    assert "colour isn't allowed" in found and "owner is missing" in found
    assert any(f.startswith("skills.a doesn't match") for f in found)


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.parent.name)
def test_every_manifest_has_its_agent_file(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert (GITHUB / "agents" / f"{data['name']}.agent.md").exists()


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skills_follow_the_agent_skills_format(path):
    fields = front_matter(path)

    assert set(fields) <= SKILL_FIELDS, set(fields) - SKILL_FIELDS
    assert fields["name"] == path.parent.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"]) and len(fields["name"]) <= 64
    assert 0 < len(fields["description"]) <= 1024
    assert all(isinstance(v, str) for v in (fields.get("metadata") or {}).values())


@pytest.mark.parametrize("path", PROMPT_FILES, ids=lambda p: p.name)
def test_prompts_name_existing_agents(path):
    agent = front_matter(path).get("agent")

    assert agent is None or (path.parents[1] / "agents" / f"{agent}.agent.md").exists()


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.name)
def test_every_ba_agent_starts_with_the_preflight_and_names_its_checkouts(path):
    text = path.read_text(encoding="utf-8")
    steps = text.split("## Before you start\n\n", 1)[1].split("\n## ", 1)[0]

    assert steps.startswith("1. Run `.github/bridge-kit/bin/bridge-kit preflight` on its own. If it ends in STOP, stop")
    assert "checkouts the preflight confirmed" in text.split("## When you finish", 1)[1]


INSTRUCTIONS = [GITHUB.parent / "mappings" / "FORMAT.md", *SKILL_FILES, *AGENT_FILES]


@pytest.mark.parametrize("path", INSTRUCTIONS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_no_instruction_shows_a_default_in_two_pairs_of_backticks(path):
    """Agents read the raw text: a default shown as `` `GBP` `` there is copied with its inner backticks, which the
    row verifier then reads as part of the value."""
    assert "`` `" not in path.read_text(encoding="utf-8")


def _command_exists(words: list[str]) -> bool:
    """Whether `bridge-kit <words>` names a command the kit has: each word a subcommand until one takes arguments."""
    import argparse

    from bridge_kit.cli import build_parser

    parser = build_parser()
    for word in words:
        sub = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
        if sub is None:
            return True  # the rest are its arguments
        if word not in sub.choices:
            return False
        parser = sub.choices[word]
    return True


INSTRUCTION_FILES = [*AGENT_FILES, *SKILL_FILES, *PROMPT_FILES]


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_bridge_kit_command_an_instruction_names_exists(path):
    text = path.read_text(encoding="utf-8")
    code = re.findall(r"```.*?```", text, re.DOTALL) + re.findall(r"`([^`\n]+)`", text)  # commands, not prose
    named = {tuple(m.group(1).split()) for span in code
             for m in re.finditer(r"\bbridge-kit((?: [a-z][a-z-]*){1,3})", span)}

    assert [" ".join(words) for words in sorted(named) if not _command_exists(list(words))] == []
