"""The glossary: a business term looked up in the glossary, the model's fields and the profiles; the glossary checked,
the landscape's and broken ones, against the shared model as REQ-101 leaves it. Made-up content only."""

import json
import shutil
from pathlib import Path

import pytest
from conftest import LANDSCAPE, SHARED_MODEL
from model_solutions import contact_channel

from bridge_kit.cli import main
from bridge_kit.internal_model import InternalModel
from bridge_kit.knowledge import check_glossary, find_term, format_found

GLOSSARY = "architecture/glossary"
PROFILE = """---
component: ui-react
---

# ui-react

## Business areas and data

| Business term | What it is here | Where |
|---|---|---|
| preferred contact channel | `contactPreference.channel`, shown on the Customer panel | `src/app/customer/Panel.tsx` |

## Contracts
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "ba-repo"
    (repo / ".github").mkdir(parents=True)
    shutil.copytree(LANDSCAPE / GLOSSARY, repo / GLOSSARY)
    (repo / "architecture" / "components").mkdir()
    (repo / "architecture" / "components" / "ui-react.md").write_text(PROFILE, encoding="utf-8")
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    return repo


@pytest.fixture
def model(tmp_path) -> InternalModel:
    """The shared model with REQ-101's change in: the contact channel, which the landscape's glossary names."""
    checkout = tmp_path / "shared-model"
    shutil.copytree(SHARED_MODEL, checkout)
    contact_channel(checkout)
    return InternalModel(checkout / "schemas")


def write(repo: Path, area: str, text: str) -> None:
    (repo / GLOSSARY / f"{area}.yaml").write_text(text, encoding="utf-8")


@pytest.mark.parametrize("words, name", [("customer number", "customer id"),
                                         ("Preferred Channel", "preferred contact channel"),
                                         ("full", "customer name"), ("bal", "account balance")])
def test_a_term_by_a_synonym_or_its_words(repo, words, name):
    assert find_term(words, repo).terms[0].name == name


def test_a_term_nothing_knows(repo):
    found = find_term("monkey business", repo)

    assert format_found("monkey business", found).startswith(
        "Nothing matches \"monkey business\": not in the glossary, the model's fields or the profiles. Ask the BA")


def test_a_term_with_no_data_element_is_a_warning(repo):
    write(repo, "more", "terms:\n  credit committee:\n    definition: Who approves the credit.\n")

    assert [(f.severity, f.message) for f in check_glossary(repo)] == [
        ("warning", "credit committee names no data element: say where it is in the model, or that it isn't data")]


def test_the_commands(repo, capsys):
    assert main(["knowledge", "term", "name on file", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["terms"][0]["name"] == "customer name"

    write(repo, "more", "terms:\n  overdraft:\n    data:\n      - x\n")
    assert main(["knowledge", "check"]) == 1
    out = capsys.readouterr()
    assert "overdraft has no definition" in out.out
    assert "data elements aren't checked" in out.err  # this BA repo has no bridge-kit.yaml, so no model to read


def test_a_term_says_where_its_definition_comes_from(repo):
    write(repo, "more", "terms:\n  credit committee:\n    definition: Who approves the credit.\n"
                        "    source: wiki, governance/committees\n    note: Not data.\n")

    found = find_term("credit committee", repo)

    assert found.terms[0].source == "wiki, governance/committees"
    assert "Who approves the credit. (source: wiki, governance/committees)" in format_found("credit committee", found)
    assert [f.message for f in check_glossary(repo) if f.severity == "error"] == []


def test_a_term_from_the_glossary_the_model_and_the_profiles(repo, model):
    found = find_term("preferred contact channel", repo, model)

    assert [t.name for t in found.terms] == ["preferred contact channel"]
    assert found.terms[0].data == ["CustomerRecord.contactPreference.channel"]
    assert found.fields[0][0] == "CustomerRecord.contactPreference.channel"
    assert found.profiles == [("ui-react", "preferred contact channel", "`contactPreference.channel`, shown on the "
                                                                       "Customer panel `src/app/customer/Panel.tsx`")]
    text = format_found("preferred contact channel", found)
    assert text.startswith("Glossary:\n  preferred contact channel (customer-record): How the customer asked to be "
                           "contacted.\n    → ")
    assert "Model fields:\n" in text and "Profiles:\n  ui-react: preferred contact channel: " in text


def test_the_landscape_s_glossary_fits_the_model(repo, model):
    assert check_glossary(repo, model) == []


@pytest.mark.parametrize("text, message", [
    ("terms:\n  account status:\n    definition: Another.\n    data:\n      - CustomerRecord.customerId\n",
     "account status is defined twice: under account status (customer-record) and account status (more)"),
    ("terms:\n  customer number:\n    definition: Another.\n    data:\n      - CustomerRecord.customerId\n",
     "customer number is defined twice: under customer id (customer-record) and customer number (more)"),
    ("terms:\n  overdraft:\n    data:\n      - CustomerRecord.customerId\n", "overdraft has no definition"),
    ("terms:\n  overdraft:\n    definition: x\n    data:\n      - CustomerRecord.overdraft\n",
     "overdraft: CustomerRecord.overdraft isn't a path of the model"),
    ("terms: [overdraft\n", "isn't YAML"),
    ("words:\n  overdraft: x\n", "has no terms"),
])
def test_what_the_check_finds(repo, model, text, message):
    write(repo, "more", text)

    errors = [f.message for f in check_glossary(repo, model) if f.severity == "error"]

    assert len(errors) == 1 and errors[0].startswith(message)
