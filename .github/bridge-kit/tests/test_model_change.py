"""`bridge-kit model start` and `diff`, on copies of the fixture's shared model: each kind of change classified as
patch, minor or major by the model's conventions, the version that follows, and the code a breaking change hits in
the consumers that are checked out."""

import json
from pathlib import Path

import pytest
from conftest import SHARED_MODEL

from bridge_kit.cli import main
from bridge_kit.config import load_config
from bridge_kit.model_change import ChangeError, bump_version, diff_models, start_change


def schema(layout: Path, name: str) -> tuple[Path, dict]:
    path = layout.parent / "shared-model" / "schemas" / name
    return path, json.loads(path.read_text(encoding="utf-8"))


def change(layout: Path, name: str, edit) -> None:
    path, data = schema(layout, name)
    edit(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def diff(layout: Path):
    return diff_models(SHARED_MODEL, layout.parent / "shared-model", load_config(layout))


def test_the_unchanged_model_has_no_changes(model_layout):
    result = diff(model_layout)

    assert result.changes == []
    assert (result.bump, result.change_kind, result.expected_version) == ("none", "none", "3.0.0")


def test_a_new_optional_field_is_minor(model_layout):
    change(model_layout, "account.json", lambda d: d["properties"].update(
        nickname={"type": "string", "description": "The name the customer gave the account."}))

    result = diff(model_layout)

    assert [(c.path, c.change, c.bump) for c in result.changes] == [
        ("CustomerRecord.accounts[].nickname", "added", "minor")]
    assert (result.change_kind, result.expected_version) == ("additive", "3.1.0")
    assert result.consumers == {}


def test_a_reused_object_adds_no_fields_of_its_own(model_layout):
    change(model_layout, "account.json", lambda d: d["properties"].update(
        overdraftLimit={"$ref": "amount.json", "description": "The agreed overdraft limit."}))

    result = diff(model_layout)

    assert [c.path for c in result.changes] == ["CustomerRecord.accounts[].overdraftLimit"]
    assert result.changes[0].detail == "New optional field: overdraftLimit, object Amount"


def test_a_new_object_lists_its_fields_with_it(model_layout):
    def edit(d):
        d["properties"]["riskRating"] = {
            "title": "RiskRating", "type": "object", "additionalProperties": False, "description": "x",
            "properties": {"rating": {"type": "string", "description": "x"},
                           "ratedDate": {"type": "string", "format": "date", "description": "x"}}}

    change(model_layout, "customer-record.json", edit)

    result = diff(model_layout)

    assert [(c.path, c.within_new) for c in result.changes] == [
        ("CustomerRecord.riskRating", False), ("CustomerRecord.riskRating.rating", True),
        ("CustomerRecord.riskRating.ratedDate", True)]
    assert [c.path for c in result.top_changes] == ["CustomerRecord.riskRating"]


def test_a_new_list_is_minor_with_a_risk(model_layout):
    def edit(d):
        d["properties"]["holders"] = {"type": "array", "items": {"type": "string"}, "description": "x"}
        d["required"].append("holders")

    change(model_layout, "account.json", edit)

    [added] = diff(model_layout).changes

    assert (added.path, added.bump) == ("CustomerRecord.accounts[].holders[]", "minor")
    assert "older version" in added.risk


def test_a_new_slot_is_major(model_layout):
    def edit(d):
        d["properties"]["marketing"] = {"title": "MarketingSlot", "type": "object", "additionalProperties": False,
                                        "description": "x", "properties": {}}
        d["required"].append("marketing")

    change(model_layout, "customer-record.json", edit)

    [added] = diff(model_layout).changes

    assert (added.path, added.bump) == ("CustomerRecord.marketing", "major")
    assert added.detail == "New slot: marketing, object MarketingSlot"
    assert "must collect and fill it" in added.risk


def test_a_new_required_field_is_major(model_layout):
    def edit(d):
        d["properties"]["sector"] = {"type": "string", "description": "x"}
        d["required"].append("sector")

    change(model_layout, "customer-record.json", edit)

    assert diff(model_layout).bump == "major"


def test_a_new_enum_value_is_minor_with_a_risk(model_layout):
    change(model_layout, "account.json", lambda d: d["properties"]["status"]["enum"].append("DORMANT"))

    [added] = diff(model_layout).changes

    assert (added.change, added.bump, added.detail) == ("enum-added", "minor", "Values added: DORMANT")
    assert added.risk


@pytest.mark.parametrize("edit, kind", [
    (lambda d: d["properties"].pop("openingDate"), "removed"),
    (lambda d: d["properties"]["accountId"].update(pattern="^AC-[0-9]+$"), "format"),
    (lambda d: d["required"].remove("joint"), "optional"),
    (lambda d: d["properties"]["status"]["enum"].remove("FROZEN"), "enum-removed"),
    (lambda d: d["properties"]["joint"].update(type="string"), "type"),
])
def test_breaking_changes_are_major(model_layout, edit, kind):
    change(model_layout, "account.json", edit)

    result = diff(model_layout)

    assert [c.change for c in result.changes] == [kind]
    assert (result.bump, result.change_kind, result.expected_version) == ("major", "breaking", "4.0.0")


def test_a_description_change_is_a_patch(model_layout):
    change(model_layout, "account.json", lambda d: d["properties"]["openingDate"].update(
        description="The day the account was opened."))

    result = diff(model_layout)

    assert [(c.change, c.bump) for c in result.changes] == [("description", "patch")]
    assert result.expected_version == "3.0.1"


def test_a_breaking_change_finds_the_code_that_uses_the_field(model_layout):
    change(model_layout, "contact-preference-slot.json", lambda d: d["properties"]["contactTime"].update(
        enum=["MORNING", "AFTERNOON", "EVENING"]))

    result = diff(model_layout)

    [breaking] = result.changes
    assert (breaking.change, breaking.detail) == ("type", "A free string becomes a coded value: MORNING, AFTERNOON, "
                                                          "EVENING")
    affected = result.affected_consumers()
    assert list(affected) == ["service-a-java", "service-c-java", "service-d-java", "service-b-python"]
    assert [Path(f).name for f in affected["service-a-java"]] == ["ContactPreferenceMapper.java:17",
                                                                  "ContactPreferenceMapperTest.java:14"]
    assert affected["service-c-java"] == []


def test_code_is_searched_only_where_it_names_the_class(model_layout):
    change(model_layout, "account.json", lambda d: d["properties"]["status"].update(enum=["OPEN", "CLOSED"]))

    result = diff(model_layout)

    files = [Path(f).name.split(":")[0] for f in result.affected_consumers()["service-a-java"]]
    assert files == ["AccountMapper.java", "AccountMapperTest.java"]  # not CallLog.java's getStatus()


def test_bumping_versions():
    assert [bump_version("1.4.0", b) for b in ("none", "patch", "minor", "major")] == [
        "1.4.0", "1.4.1", "1.5.0", "2.0.0"]


def test_start_records_the_base_once(model_layout):
    config = load_config(model_layout)
    work = model_layout / ".work"

    base, version, recorded = start_change(config, work, "REQ-111")
    (config.model.path / "schemas" / "account.json").write_text("{}", encoding="utf-8")
    again = start_change(config, work, "REQ-111")

    assert (version, recorded) == ("3.0.0", True)
    assert again == (base, "3.0.0", False)
    assert json.loads((base / "schemas" / "account.json").read_text(encoding="utf-8"))["title"] == "Account"
    assert (base / "python" / "pyproject.toml").exists()


def test_start_on_a_git_checkout_isnt_built_yet(model_layout):
    config = load_config(model_layout)
    config.model.git = True

    with pytest.raises(ChangeError, match="isn't built yet"):
        start_change(config, model_layout / ".work", "REQ-111")


def test_the_commands(model_layout, monkeypatch, capsys):
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(model_layout))

    assert main(["model", "diff", "REQ-111"]) == 1
    assert "bridge-kit model start REQ-111" in capsys.readouterr().err
    assert main(["model", "start", "REQ-111"]) == 0
    change(model_layout, "account.json", lambda d: d["properties"]["status"]["enum"].append("DORMANT"))
    assert main(["model", "diff", "REQ-111", "--json"]) == 0

    out = json.loads(capsys.readouterr().out.split("\n", 1)[1])
    assert (out["change"], out["expected_version"]) == ("additive", "3.1.0")
