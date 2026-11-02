"""Component knowledge, on a made-up AI layer in the collecting service's checkout: the scan finds it and proposes
pointers by kind, `--write` adds them only where the catalog has none and the build keeps them, `knowledge show` reads
a kind and flags a pointer whose file is gone, and `knowledge term` reads the team's glossary."""

import json
from pathlib import Path

import yaml

from bridge_kit.cli import main
from bridge_kit.component_knowledge import scan, team_glossaries
from bridge_kit.components import build
from bridge_kit.config import load_config
from bridge_kit.knowledge import find_term

LAYER = {
    "skills/domain-glossary/SKILL.md": ("domain-glossary", "What the domain's codes and acronyms mean",
                                        "| CP | contact preference: how the customer wants to be contacted |"),
    "skills/collector-anatomy/SKILL.md": ("collector-anatomy", "The API, controller, service, connector and mapper "
                                                               "chain, and where each kind of change goes", ""),
    "skills/audit-redaction/SKILL.md": ("audit-redaction", "How raw upstream responses are redacted and kept", ""),
    "agents/mr-review.agent.md": ("mr-review", "Reviewing a diff before a merge request", "tools: [read, search]"),
    "agents/mapper-builder.agent.md": ("mapper-builder", "Writing or fixing a mapper into the shared model",
                                       "tools: [read, edit, execute]"),
    "prompts/update-mapping.prompt.md": ("", "Add, change or repair a field mapping", ""),
    "prompts/write-spec.prompt.md": ("", "Write a spec from a ticket, spec-driven", ""),
}


def with_layer(ba_repo: Path) -> Path:
    github = ba_repo.parent / "service-a-java" / ".github"
    for path, (name, description, extra) in LAYER.items():
        front = ([f"name: {name}"] if name else []) + [f"description: {description}"]
        front += [extra] if extra.startswith("tools") else []
        body = "" if extra.startswith("tools") else extra
        (github / path).parent.mkdir(parents=True, exist_ok=True)
        (github / path).write_text("---\n" + "\n".join(front) + f"\n---\n\n# {name or path}\n\n{body}\n",
                                   encoding="utf-8")
    return github


def test_the_scan_finds_the_layer_and_proposes_pointers_by_kind(model_layout):
    with_layer(model_layout)

    [found] = scan(model_layout, load_config(model_layout), "service-a-java")

    kinds = {item.name: (item.kind, item.edits) for item in found.items}
    assert kinds == {"domain-glossary": ("glossary", None), "collector-anatomy": ("anatomy", None),
                     "audit-redaction": ("privacy", None), "mr-review": ("other", False),
                     "mapper-builder": ("playbooks", True), "update-mapping": ("playbooks", None),
                     "write-spec": ("intake", None)}
    assert found.proposed["playbooks"] == [".github/agents/mapper-builder.agent.md",
                                           ".github/prompts/update-mapping.prompt.md"]
    assert found.broken == []


def test_write_adds_pointers_only_where_the_catalog_has_none_and_the_build_keeps_them(model_layout, monkeypatch,
                                                                                      capsys):
    with_layer(model_layout)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(model_layout))

    assert main(["components", "scan", "--write"]) == 0

    out = capsys.readouterr().out
    assert "Added knowledge to service-a-java" in out and "shared-model: " in out
    catalog = yaml.safe_load((model_layout / "architecture/components.yaml").read_text(encoding="utf-8"))
    knowledge = catalog["components"]["service-a-java"]["knowledge"]
    assert knowledge["glossary"] == ".github/skills/domain-glossary/SKILL.md"
    assert "knowledge" not in catalog["components"]["shared-model"]  # its checkout has no AI layer
    built = build(model_layout)
    assert built.ok and "knowledge" in yaml.safe_load(built.text)["components"]["service-a-java"]


def test_show_reads_a_kind_and_a_broken_pointer_is_said(model_layout, monkeypatch, capsys):
    github = with_layer(model_layout)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(model_layout))
    main(["components", "scan", "--write"])
    capsys.readouterr()

    assert main(["knowledge", "show", "service-a-java", "privacy"]) == 0
    assert "## service-a-java: .github/skills/audit-redaction/SKILL.md" in capsys.readouterr().out

    (github / "skills/audit-redaction/SKILL.md").unlink()
    assert main(["knowledge", "show", "service-a-java", "privacy"]) == 1
    assert main(["components", "scan", "service-a-java", "--json"]) == 1
    capsys.readouterr()
    main(["components", "scan", "service-a-java", "--json"])
    assert json.loads(capsys.readouterr().out)["components"][0]["broken"] == [
        ".github/skills/audit-redaction/SKILL.md"]


def test_knowledge_term_reads_the_team_s_glossary(model_layout, monkeypatch):
    with_layer(model_layout)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(model_layout))
    main(["components", "scan", "--write"])

    teams = team_glossaries(model_layout, load_config(model_layout))
    found = find_term("contact preference", model_layout, teams=teams)

    assert found.teams == [("service-a-java", "SKILL.md", "CP | contact preference: how the customer wants to be "
                                                          "contacted")]
