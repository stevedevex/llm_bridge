"""Component profiles and `bridge-kit components build`: profiles written here, in the shape `/profile-component` writes
them, merged into a catalog; the order worked out from the contracts; what people set kept; a contract owned twice, a
cycle, a broken block; and the prompt, standalone. Made-up content."""

import json

import pytest
import yaml
from conftest import KIT, LANDSCAPE

from bridge_kit.cli import main
from bridge_kit.components import CATALOG, build
from bridge_kit.markdown import read_markdown

PROMPT = KIT.parent / "prompts" / "profile-component.prompt.md"
CATALOG_TEXT = """# Our components, for the requirement agents.

components:
  shared-model:
    order: 1
    repo: shared-model
    stack: json-schema
    owns: [model-input]
    stories: {project: shared-model, labels: [model]}
    note: Contract first
  service-c-java:
    order: 2
    stack: java
    stories: {project: service-c-java, labels: [business]}

contracts:
  model-input: {kind: json-schema, source: shared-model, root: CustomerRecord}
"""


def profile(name: str, entry: str, contracts: str = "") -> str:
    return (f"---\ncomponent: {name}\nfolder: /projects/{name}\ncommit: abc1234 2026-10-28\nprofiled: 2026-10-28\n"
            f"status: draft\n---\n\n# {name}\n\nWhat it does.\n\n## Proposed catalog entry\n\n```yaml\n{name}:\n"
            f"{entry}" + (f"contracts:\n{contracts}" if contracts else "") + "```\n\n## Open questions\n\n- Which team?\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    (repo / "architecture" / "components").mkdir(parents=True)
    (repo / CATALOG).write_text(CATALOG_TEXT, encoding="utf-8")
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    return repo


def write(repo, name: str, text: str):
    (repo / "architecture" / "components" / f"{name}.md").write_text(text, encoding="utf-8")


def catalog(text: str) -> dict:
    return yaml.safe_load(text)


def test_profiles_are_merged_and_what_people_set_is_kept(repo):
    write(repo, "service-c-java", profile(
        "service-c-java", "  summary: Puts a credit file together for the presentation service\n  stack: java\n  "
                            "owns: [service-c-api]\n  consumes: [service-b-api, model-input]\n  "
                            "external: false\n",
        "  service-c-api: { kind: openapi, file: api/service-c-api.yaml }\n"))
    write(repo, "service-b-python", profile(
        "service-b-python", "  summary: Writes the summary\n  stack: python\n"
                                  "  owns: [service-b-api]\n  consumes: [model-input]\n",
        "  service-b-api: { kind: openapi, file: openapi.yaml }\n"))

    built = build(repo)

    assert built.ok and built.findings == []
    found = catalog(built.text)
    assert list(found["components"]) == ["shared-model", "service-b-python", "service-c-java"]
    business = found["components"]["service-c-java"]
    assert business == {"order": 3, "summary": "Puts a credit file together for the presentation service",
                        "stack": "java", "owns": ["service-c-api"], "consumes": ["service-b-api", "model-input"],
                        "external": False, "stories": {"project": "service-c-java", "labels": ["business"]},
                        "profile": "architecture/components/service-c-java.md"}
    assert found["components"]["shared-model"]["note"] == "Contract first"
    assert found["contracts"]["service-b-api"] == {"kind": "openapi", "source": "service-b-python",
                                               "file": "openapi.yaml"}
    assert built.text.startswith("# Our components, for the requirement agents.\n\ncomponents:\n")
    assert "+    summary: Puts a credit file together" in built.diff


def test_the_build_writes_only_with_write_and_then_has_nothing_to_change(repo, capsys):
    write(repo, "service-c-java", profile("service-c-java", "  owns: [service-c-api]\n",
                                            "  service-c-api: { kind: openapi }\n"))

    assert main(["components", "build"]) == 0
    assert capsys.readouterr().out.endswith("Not written: --write writes it\n")
    assert (repo / CATALOG).read_text(encoding="utf-8") == CATALOG_TEXT

    assert main(["components", "build", "--write"]) == 0
    assert capsys.readouterr().out.endswith("Wrote architecture/components.yaml\n")
    assert main(["components", "build", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (result["ok"], result["changed"], result["diff"]) == (True, False, "")


def test_the_order_puts_each_contract_s_owner_before_its_consumers(repo):
    write(repo, "ui-react", profile("ui-react", "  consumes: [service-d-api]\n"))
    write(repo, "service-d-java", profile("service-d-java", "  owns: [service-d-api]\n"
                                                                        "  consumes: [service-c-api]\n"))
    write(repo, "service-c-java", profile("service-c-java", "  owns: [service-c-api]\n"
                                                                "  consumes: [model-input]\n"))

    order = {name: entry["order"] for name, entry in catalog(build(repo).text)["components"].items()}

    assert order == {"shared-model": 1, "service-c-java": 2, "service-d-java": 3, "ui-react": 4}


@pytest.mark.parametrize("profiles, findings", [
    ({"service-c-java": "  owns: [model-input]\n"},
     [("error", "model-input is owned by shared-model and service-c-java: a contract has one "
                "owner")]),
    ({"service-c-java": "  owns: [service-c-api]\n  consumes: [service-b-api]\n"},
     [("warning", "service-c-api, owned by service-c-java, has no kind"),
      ("warning", "service-c-java consumes service-b-api, which no component owns yet")]),
    ({"service-c-java": "  owns: [service-c-api]\n  consumes: [service-b-api]\n",
      "service-b-python": "  owns: [service-b-api]\n  consumes: [service-c-api]\n"},
     [("warning", "service-c-api, owned by service-c-java, has no kind"),
      ("warning", "service-b-api, owned by service-b-python, has no kind"),
      ("error", "the components consume each other's contracts in a cycle: their order can't be worked out")]),
])
def test_what_doesn_t_add_up_across_the_profiles(repo, profiles, findings):
    for name, entry in profiles.items():
        write(repo, name, profile(name, entry))

    built = build(repo)

    assert [(f.severity, f.message) for f in built.findings] == findings
    assert built.ok is not any(severity == "error" for severity, _ in findings)


@pytest.mark.parametrize("text, message", [
    ("---\ncomponent: service-c-java\n---\n\n# service-c-java\n\nNo entry.\n",
     "has no Proposed catalog entry with a yaml block: not merged"),
    (profile("service-c-java", "  owns: [service-c-api\n"), "its proposed entry isn't YAML"),
    (profile("service-c-java", "  summary: <one line, in business words>\n  external: maybe\n"),
     "its proposed entry is wrong: summary isn't one line of text; external isn't true or false: not merged"),
])
def test_a_profile_whose_entry_can_t_be_merged(repo, text, message):
    write(repo, "service-c-java", text)

    built = build(repo)

    errors = [f.message for f in built.findings if f.severity == "error"]
    assert len(errors) == 1 and errors[0].startswith(message)
    assert "profile" not in catalog(built.text)["components"]["service-c-java"]


def test_what_people_set_is_left_to_people_and_other_components_to_their_profiles(repo):
    write(repo, "service-c-java", profile(
        "service-c-java", "  stack: java\n  stories: {project: elsewhere}\n  team: payments\n"))
    write(repo, "service-d-java", "---\ncomponent: service-d-java\n---\n\n## Proposed catalog entry\n\n"
                                        "```yaml\nservice-d-java:\n  stack: java\nui-react:\n  stack: react\n"
                                        "```\n")

    built = build(repo)

    assert [(f.severity, f.file, f.message) for f in built.findings] == [
        ("warning", "architecture/components/service-c-java.md",
         "stories is for people to set in the catalog, not a profile: left as it is"),
        ("warning", "architecture/components/service-c-java.md",
         "team is for people to set in the catalog, not a profile: left as it is"),
        ("error", "architecture/components/service-d-java.md",
         "its proposed entry is for service-d-java only, and names ui-react too: not merged")]
    assert catalog(built.text)["components"]["service-c-java"]["stories"] == {"project": "service-c-java",
                                                                               "labels": ["business"]}


def test_an_entry_whose_profile_is_gone(repo):
    (repo / CATALOG).write_text(CATALOG_TEXT.replace("    stack: java\n",
                                                     "    stack: java\n    profile: architecture/components/b.md\n"),
                                encoding="utf-8")

    assert [f.message for f in build(repo).findings] == [
        "service-c-java's profile architecture/components/b.md isn't there: profile it again, or take `profile` out"]


def test_errors_keep_the_catalog_as_it_is(repo, capsys):
    write(repo, "service-c-java", profile("service-c-java", "  owns: [model-input]\n"))

    assert main(["components", "build", "--write"]) == 1
    assert capsys.readouterr().out.endswith("Not written: fix the errors first\n")
    assert (repo / CATALOG).read_text(encoding="utf-8") == CATALOG_TEXT


def test_the_landscape_s_catalog_is_in_the_build_s_shape(monkeypatch):
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(LANDSCAPE))
    built = build(LANDSCAPE)

    assert built.ok and built.text == built.current


def test_the_prompt_is_standalone_and_writes_what_the_build_reads():
    text = PROMPT.read_text(encoding="utf-8")
    template = text.split("````markdown\n", 1)[1].split("\n````", 1)[0]

    assert "bridge-kit" not in text and ".github/" not in text  # it runs in any workspace
    assert read_markdown(template).front_matter.keys() >= {"component", "folder", "commit", "profiled", "status"}
    assert "## Proposed catalog entry\n\n```yaml\n<name>:\n" in template
    for heading in ("What it does", "What it doesn't do", "Business areas and data", "Contracts", "Screens",
                    "Where changes go", "Build and test", "Signs a requirement touches it", "Open questions"):
        assert f"\n## {heading}\n" in template
