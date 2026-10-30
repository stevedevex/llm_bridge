"""`bridge-kit validate model`, on changes to copies of the fixture's shared model: a right change has no findings;
the conventions on what changed, the version, the example, and the description against the diff are each checked.
The model's build isn't run here: the fixture model has none."""

import json
from pathlib import Path

from conftest import SHARED_MODEL, edit
from model_solutions import set_version, solve, write_description

from bridge_kit.cli import main
from bridge_kit.config import load_config
from bridge_kit.model_change import start_change
from bridge_kit.validators.model import check_change, validate_model


def check(ba_repo: Path, work_item: str) -> list[tuple[str, str, str]]:
    findings = check_change(SHARED_MODEL, work_item, load_config(ba_repo), ba_repo, build=False)
    return [(f.severity, f.check, f.message) for f in findings]


def errors(ba_repo: Path, work_item: str) -> list[str]:
    return [message for severity, _, message in check(ba_repo, work_item) if severity == "error"]


def model_of(ba_repo: Path) -> Path:
    return load_config(ba_repo).model.path


def change_schema(ba_repo: Path, name: str, change) -> None:
    path = model_of(ba_repo) / "schemas" / name
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_a_right_change_has_no_findings(model_layout):
    solve("contact-channel", model_layout, SHARED_MODEL)

    assert check(model_layout, "REQ-101") == []


def test_the_command_needs_the_base_from_model_start(model_layout, monkeypatch, capsys):
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(model_layout))

    assert main(["validate", "model", "REQ-111", "--no-build"]) == 1
    assert "run `bridge-kit model start REQ-111`" in capsys.readouterr().out


def test_the_command_checks_against_the_recorded_base(model_layout, monkeypatch):
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(model_layout))
    config = load_config(model_layout)
    start_change(config, model_layout / ".work", "REQ-111")
    solve("overdraft-limit", model_layout, SHARED_MODEL)

    findings = validate_model("REQ-111", config, model_layout / ".work", model_layout, build=False)

    assert findings == []
    assert main(["validate", "model", "REQ-111", "--no-build"]) == 0


def test_conventions_are_checked_on_what_changed(model_layout):
    def change(data):
        data["properties"].update({
            "isOverdrawn": {"type": "boolean", "description": "x"},
            "rateType": {"type": "string", "enum": ["Fixed", "VARIABLE"], "description": "x"},
            "fees": {"type": "array", "items": {"type": "string"}},
            "review_date": {"type": "string", "description": "x"},
            "limit": {"title": "Limit", "type": "object", "description": "x",
                      "properties": {"value": {"type": "number", "description": "x"},
                                     "currency": {"type": "string", "description": "x"}}}})
    change_schema(model_layout, "account.json", change)
    set_version(model_of(model_layout), "3.1.0")
    write_description(model_layout, SHARED_MODEL, "REQ-111", "x", "x")

    found = check(model_layout, "REQ-111")
    messages = " | ".join(message for _, _, message in found)

    for expected in ("booleans are plain adjectives", "enum values are UPPER_SNAKE_CASE: Fixed",
                     "every property has a description", "lists are always present and required",
                     "field names are camelCase", "every object has additionalProperties: false",
                     "money is the Amount schema", "a currency is ISO 4217"):
        assert expected in messages, expected
    assert "openingDate" not in messages  # existing fields aren't checked


def test_the_version_must_be_the_one_the_change_needs(model_layout):
    solve("overdraft-limit", model_layout, SHARED_MODEL)
    edit(model_of(model_layout) / "python" / "pyproject.toml", 'version = "3.1.0"', 'version = "3.0.0"')

    assert errors(model_layout, "REQ-111") == [
        "pom.xml says 3.1.0 and python/pyproject.toml says 3.0.0: they must be equal"]

    edit(model_of(model_layout) / "pom.xml", "<version>3.1.0</version>", "<version>3.0.0</version>")
    write_description(model_layout, SHARED_MODEL, "REQ-111", "x", "x")

    assert "The version should be 3.1.0: the change is additive (minor), from 3.0.0" in errors(model_layout, "REQ-111")


def test_the_example_uses_every_object(model_layout):
    solve("consents", model_layout, SHARED_MODEL)
    example = model_of(model_layout) / "examples" / "customer-record.example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    data["consents"]["consents"] = []
    example.write_text(json.dumps(data, indent=2), encoding="utf-8")

    assert "The example doesn't use Consent: it uses every object" in errors(model_layout, "REQ-112")


def test_the_description_must_say_what_the_diff_says(model_layout):
    solve("contact-time-codes", model_layout, SHARED_MODEL)
    description = model_layout / "work" / "REQ-113" / "model-change.md"
    edit(description, "change: breaking", "change: additive")
    text = description.read_text(encoding="utf-8")
    description.write_text(text.replace("service-c-java", "the business service"), encoding="utf-8")

    found = errors(model_layout, "REQ-113")

    assert "change says additive, but the diff is breaking" in found
    assert "A breaking change hits service-c-java: Consumers affected must name it" in found


def test_every_change_needs_a_row(model_layout):
    solve("overdraft-limit", model_layout, SHARED_MODEL)
    change_schema(model_layout, "account.json", lambda d: d["properties"].update(
        nickname={"type": "string", "description": "The name the customer gave the account."}))

    assert any(m.startswith("Changes has no row for CustomerRecord.accounts[].nickname")
               for m in errors(model_layout, "REQ-111"))


def test_reused_paths_must_exist(model_layout):
    solve("display-name-exists", model_layout, SHARED_MODEL)
    edit(model_layout / "work" / "REQ-114" / "model-change.md", "`CustomerRecord.displayName`",
         "`CustomerRecord.tradingName`")

    assert errors(model_layout, "REQ-114") == [
        "Reused names `CustomerRecord.tradingName`, which isn't a path of the model"]


def test_a_missing_description_is_an_error(model_layout):
    assert errors(model_layout, "REQ-114") == ["Write the merge request description to work/REQ-114/model-change.md"]
