"""The docs against what's there: the README's Commands table names every command the command line has, and no other,
each with options the command takes; every agent and standalone prompt has its page and its rows; and every link in a
doc that ships is to a file that ships too, so none points into the design, which stays in BRIDGE's own repo."""

import argparse
import re

import pytest
from conftest import KIT

from bridge_kit.cli import build_parser
from bridge_kit.export import shipped
from bridge_kit.markdown import read_markdown

BA_REPO = KIT.parents[1]
README = KIT / "README.md"
GUIDES = KIT / "guides"
SHIPPED_DOCS = [README, KIT / "GUIDE.md", *sorted(GUIDES.glob("*.md"))]
LINK = re.compile(r"\]\(([^)#\s]+)[^)]*\)")


def commands(parser: argparse.ArgumentParser, words: tuple[str, ...] = ()) -> dict[tuple[str, ...], set[str]]:
    """Every command the command line has, by its words, with its options."""
    subparsers = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subparsers:
        return {words: {option for action in parser._actions for option in action.option_strings}}
    found = {}
    for action in subparsers:
        for name, sub in action.choices.items():
            found |= commands(sub, words + (name,))
    return found


def table(text: str, heading: str) -> list[str]:
    """The first cell of each row of the table under a heading."""
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return [line.split(" | ")[0] for line in section.splitlines() if line.startswith("| `")]


def test_the_commands_table_names_every_command_and_no_other():
    have = commands(build_parser())
    named = set()
    for cell in table(README.read_text(encoding="utf-8"), "Commands"):
        usage = cell.split("`")[1].split()
        assert usage[0] == "bridge-kit", cell
        words = []
        for word in usage[1:]:
            if not re.fullmatch(r"[a-z][a-z-]*", word):
                break
            words.append(word)
        command = tuple(words)
        assert command in have, f"{' '.join(command)}: not a command"
        assert set(re.findall(r"--[a-z][a-z-]*", cell)) <= have[command], cell
        named.add(command)

    assert named == set(have), sorted(set(have) - named)
    # the README says every command but spec digest takes --json
    assert {command for command, options in have.items() if "--json" not in options} == {("spec", "digest")}


def test_every_agent_and_standalone_prompt_has_its_page_and_its_rows():
    readme = README.read_text(encoding="utf-8")
    index = (GUIDES / "README.md").read_text(encoding="utf-8")
    prompts = (GUIDES / "prompts.md").read_text(encoding="utf-8")
    for agent in sorted((KIT.parent / "agents").glob("*.agent.md")):
        name = agent.name.removesuffix(".agent.md")
        assert (GUIDES / f"{name}.md").is_file(), name
        assert f"]({name}.md)" in index and f"| `{name}` |" in readme, name
    for prompt in sorted((KIT.parent / "prompts").glob("*.prompt.md")):
        if "agent" not in read_markdown(prompt.read_text(encoding="utf-8")).front_matter:
            name = prompt.name.removesuffix(".prompt.md")
            assert f"| `/{name}` |" in prompts, name
            assert f"| `/{name} " in readme or f"| `/{name}` |" in readme, name


@pytest.mark.parametrize("doc", SHIPPED_DOCS, ids=lambda doc: doc.relative_to(KIT).as_posix())
def test_every_link_in_a_doc_that_ships_is_to_a_file_that_ships(doc):
    ships = set(shipped(BA_REPO))
    for target in LINK.findall(doc.read_text(encoding="utf-8")):
        if not target.startswith(("http://", "https://", "mailto:")):
            path = (doc.parent / target).resolve()
            assert path.is_relative_to(BA_REPO) and path.relative_to(BA_REPO).as_posix() in ships, target


def test_every_link_in_the_repo_s_readme_resolves():
    for target in LINK.findall((BA_REPO / "README.md").read_text(encoding="utf-8")):
        if not target.startswith(("http://", "https://", "mailto:")):
            assert (BA_REPO / target).exists(), target
