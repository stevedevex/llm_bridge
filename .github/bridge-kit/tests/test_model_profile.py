"""bridge-kit model profile, on the fixture's shared model and copies of it with other habits: its own conventions and
layout come back, a habit every field shares is proposed, a mixed one is off with its counts, and a folder with no
schemas says so."""

import json
import re
import shutil

import pytest
from conftest import SHARED_MODEL

from bridge_kit.cli import main
from bridge_kit.config import CONVENTIONS
from bridge_kit.model_profile import ProfileError, profile


@pytest.fixture
def model(tmp_path):
    """A copy of the shared model's checkout: its schemas, examples and version files."""
    checkout = tmp_path / "shared-model"
    shutil.copytree(SHARED_MODEL, checkout)
    return checkout


def rewrite(checkout, change):
    """Rewrites every schema file with `change(schema)`."""
    for file in (checkout / "schemas").glob("*.json"):
        schema = json.loads(file.read_text(encoding="utf-8"))
        change(schema)
        file.write_text(json.dumps(schema, indent=2), encoding="utf-8")


def rename_properties(schema, rename):
    props = schema.get("properties", {})
    schema["properties"] = {rename(name, prop): prop for name, prop in props.items()}
    if "required" in schema:
        schema["required"] = [rename(name, props[name]) for name in schema["required"]]


def test_the_model_gives_back_its_own_conventions_and_layout(model):
    result = profile(model)

    assert result.conventions == {name: ("Amount" if name == "money" else value) for name, value in
                                  CONVENTIONS.items()}
    assert result.layout == {"schemas": "schemas", "nested": False, "examples": "examples",
                             "version_files": ["pom.xml", "python/pyproject.toml"]}
    lists = next(r for r in result.rules if r.name == "lists")
    assert (lists.follow, lists.examples) == ({"required": 2}, [])


def test_a_habit_every_field_shares_is_proposed(model):
    def is_prefix(name, prop):
        return f"is{name[0].upper()}{name[1:]}" if prop.get("type") == "boolean" else name

    rewrite(model, lambda schema: rename_properties(schema, is_prefix))
    rewrite(model, lambda schema: schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema"}))

    result = profile(model)

    assert (result.conventions["booleans"], result.conventions["json_schema"]) == ("is-prefix", "2020-12")


def test_a_mixed_habit_is_off_with_its_counts(model):
    def snake(name, prop):
        return re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()

    for name in ("customer-record", "contact-preference-slot"):
        file = model / "schemas" / f"{name}.json"
        schema = json.loads(file.read_text(encoding="utf-8"))
        rename_properties(schema, snake)
        file.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    rule = next(r for r in profile(model).rules if r.name == "field_names")

    assert rule.proposed == "off"
    assert rule.comment.startswith("off: camelCase ")
    assert all(n < 0.9 * rule.applies_to for n in rule.follow.values())


def test_a_folder_with_no_schemas_isn_t_a_model(tmp_path):
    with pytest.raises(ProfileError, match="No JSON Schemas in"):
        profile(tmp_path)


def test_the_command_profiles_the_model_bridge_kit_yaml_names(model_layout, monkeypatch, capsys):
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(model_layout))

    assert main(["model", "profile"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("The model in ") and "    booleans: no-prefix" in out
    assert main(["model", "profile", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["model"]["conventions"]["dates"] == "on"
