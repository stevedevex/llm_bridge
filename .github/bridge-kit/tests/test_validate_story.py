"""bridge-kit validate story: a reference story set has no errors, and each of the template's rules is caught."""

import shutil
from pathlib import Path

import pytest
from conftest import KIT, LANDSCAPE, edit
from story_solutions import reference_stories

from bridge_kit.cli import main
from bridge_kit.validators.story import validate_stories

BA_REPO = KIT.parents[1]
CASES = Path(__file__).parent / "fixtures" / "story-cases"


@pytest.fixture
def repo(tmp_path) -> Path:
    """A BA repo with the catalog and the template, and nothing else."""
    copy = tmp_path / "ba-repo"
    shutil.copytree(LANDSCAPE / "architecture", copy / "architecture")
    shutil.copytree(BA_REPO / "templates", copy / "templates")
    return copy


def stories(repo: Path, case: str = "vat-registration") -> list[Path]:
    return reference_stories(CASES / case, repo, repo)


def story(files: list[Path], component: str) -> Path:
    return next(f for f in files if f.name.startswith(f"{component}-"))


def errors(findings, check=None):
    return [f for f in findings if f.severity == "error" and (check is None or f.check == check)]


def test_a_reference_set_has_no_errors(repo):
    for case in sorted(p.name for p in CASES.iterdir() if (p / "expected.yaml").exists()):
        files = stories(repo, case)
        assert errors(validate_stories(files, repo)) == [], case


def test_a_missing_section(repo):
    files = stories(repo)
    edit(story(files, "ui-react"), "## Scope\n", "## Range\n")

    assert "The Scope section is missing" in [f.message for f in errors(validate_stories(files, repo), "sections")]


def test_sections_out_of_order(repo):
    files = stories(repo)
    file = story(files, "ui-react")
    edit(file, "## Dependencies\n", "## Placeholder\n")
    edit(file, "## Open questions\n", "## Dependencies\n")
    edit(file, "## Placeholder\n", "## Open questions\n")

    assert errors(validate_stories(files, repo), "sections")


def test_the_component_section_names_the_component(repo):
    files = stories(repo)
    edit(story(files, "ui-react"), "## Component details: ui-react",
         "## Component details: service-d-java")

    assert errors(validate_stories(files, repo), "sections")


def test_a_criterion_needs_given_when_and_then(repo):
    files = stories(repo)
    edit(story(files, "ui-react"), "\nThen ", "\nAnd ")

    [error] = errors(validate_stories(files, repo), "criteria")
    assert "AC-1 lacks Then" in error.message


def test_criteria_are_numbered_from_one(repo):
    files = stories(repo)
    edit(story(files, "ui-react"), "### AC-1:", "### AC-2:")

    assert errors(validate_stories(files, repo), "criteria")


def test_a_component_outside_the_catalog(repo):
    files = stories(repo)
    edit(story(files, "ui-react"), "component: ui-react", "component: mobile-app")

    assert errors(validate_stories(files, repo), "catalog")


def test_the_order_is_the_catalogs(repo):
    files = stories(repo)
    edit(story(files, "ui-react"), "order: 6", "order: 7")

    assert errors(validate_stories(files, repo), "order")


def test_a_contract_belongs_to_the_story_of_the_component_that_owns_it(repo):
    files = stories(repo)
    edit(story(files, "service-c-java"), "contract: service-c-api", "contract: service-d-api")

    [error] = errors(validate_stories(files, repo), "contracts")
    assert "service-d-java's story" in error.message


def test_no_schema_change_where_defines_schemas_is_false(repo):
    files = stories(repo)
    edit(story(files, "service-b-python"), "contracts: []",
         "contracts:\n- contract: model-output\n  change: additive")

    assert errors(validate_stories(files, repo), "schemas")


def test_a_header_that_breaks_the_schema(repo):
    files = stories(repo)
    edit(story(files, "ui-react"), "status: draft", "status: done")

    [error] = errors(validate_stories(files, repo), "header")
    assert "status must be one of draft, approved, created" in error.message


def test_blocked_by_a_story_outside_the_set(repo):
    files = stories(repo)
    story(files, "shared-model").unlink()
    files = [f for f in files if f.exists()]

    assert any("S1, which isn't in the set" in e.message for e in errors(validate_stories(files, repo),
                                                                         "dependencies"))


def test_blocked_by_a_later_story(repo):
    files = stories(repo)
    edit(story(files, "service-a-java"), "blocked_by:\n- S1", "blocked_by:\n- S5")

    assert any("comes after it" in e.message for e in errors(validate_stories(files, repo), "dependencies"))


def test_a_missing_dependency_is_a_warning(repo):
    files = stories(repo)
    edit(story(files, "service-c-java"), "blocked_by:\n- S1", "blocked_by: []")

    findings = validate_stories(files, repo)
    assert not errors(findings)
    assert any(f.check == "dependencies" and f.severity == "warning" for f in findings)


def test_open_questions_block_approval(repo):
    files = stories(repo, "rename-for-clients")
    edit(story(files, "service-d-java"), "status: draft", "status: approved")

    assert errors(validate_stories(files, repo), "status")


def test_the_command_takes_a_folder_of_stories(repo, monkeypatch, capsys):
    files = stories(repo)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))

    assert main(["validate", "story", str(files[0].parent)]) == 0
    assert "6 file(s): 0 error(s)" in capsys.readouterr().out
