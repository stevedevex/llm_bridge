"""The shared model's layout and conventions from bridge-kit.yaml: by default the kit's; set otherwise, as a model may
need: booleans that start with is, snake_case names, schemas in subfolders, the version in package.json, no examples
folder. Made-up models only."""

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from bridge_kit.config import CONVENTIONS, ConfigError, load_config
from bridge_kit.internal_model import InternalModel, ModelError, ModelLayout, read_version
from bridge_kit.model_change import diff_models, start_change
from bridge_kit.validators.model import check_change


def configure(ba_repo: Path, model: dict) -> None:
    file = ba_repo / ".github" / "bridge-kit" / "bridge-kit.yaml"
    data = yaml.safe_load(file.read_text(encoding="utf-8"))
    data["model"].update(model)
    file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_by_default_the_layout_and_conventions_are_the_kit_s(model_layout):
    config = load_config(model_layout)

    assert config.model_layout == ModelLayout("schemas", False, "examples", ["pom.xml", "python/pyproject.toml"])
    assert config.conventions == CONVENTIONS


def test_bridge_kit_yaml_sets_them_and_yaml_s_bare_off_is_off(model_layout):
    (model_layout / ".github" / "bridge-kit" / "bridge-kit.yaml").write_text(
        (model_layout / ".github" / "bridge-kit" / "bridge-kit.yaml").read_text(encoding="utf-8").replace(
            "  repo: shared-model\n",
            "  repo: shared-model\n  layout:\n    schemas: src/schemas\n    nested: true\n    examples: none\n"
            "    version_files: [package.json]\n  conventions:\n    booleans: is-prefix\n    money: off\n"
            "    countries: off\n", 1), encoding="utf-8")

    config = load_config(model_layout)

    assert config.model_layout == ModelLayout("src/schemas", True, None, ["package.json"])
    assert (config.conventions["booleans"], config.conventions["money"], config.conventions["countries"],
            config.conventions["dates"]) == ("is-prefix", "off", "off", "on")


@pytest.mark.parametrize("model, problem", [
    ({"conventions": {"booleans": "maybe"}}, "model.conventions.booleans"),
    ({"conventions": {"fieldNames": "camelCase"}}, "model.conventions: fieldNames isn't allowed"),
    ({"layout": {"version_files": "pom.xml"}}, "model.layout.version_files"),
])
def test_a_setting_the_kit_doesn_t_know_is_refused(model_layout, model, problem):
    configure(model_layout, model)

    with pytest.raises(ConfigError, match=re.escape(problem)):
        load_config(model_layout)


@pytest.mark.parametrize("name, content, version", [
    ("pom.xml", '<project xmlns="http://maven.apache.org/POM/4.0.0"><version>2.1.0</version></project>', "2.1.0"),
    ("pyproject.toml", '[project]\nname = "model"\nversion = "2.1.0"\n', "2.1.0"),
    ("pyproject.toml", '[tool.poetry]\nname = "model"\nversion = "2.1.0"\n', "2.1.0"),
    ("package.json", '{"name": "model", "version": "2.1.0"}', "2.1.0"),
    ("package.json", '{"name": "model"}', None),
    ("package.json", "not json", None),
])
def test_a_version_from_each_kind_of_build_file(tmp_path, name, content, version):
    (tmp_path / name).write_text(content, encoding="utf-8")

    assert read_version(tmp_path / name) == version
    assert read_version(tmp_path / "missing.xml") is None


def schema(title: str, properties: dict, required: list | None = None) -> dict:
    return {"$schema": "http://json-schema.org/draft-07/schema#", "title": title, "description": f"The {title}.",
            "type": "object", "additionalProperties": False, "properties": properties, "required": required or []}


def write_model(root: Path, version: str = "1.0.0") -> None:
    """A small model with its schemas in subfolders, a ref written relative to its file, its version in package.json,
    and no examples."""
    for folder in ("src/schemas/common", "src/schemas/file"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "src/schemas/common/amount.json").write_text(json.dumps(schema("Amount", {
        "value": {"type": "number", "description": "How much"},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$", "description": "Its currency"}},
        ["value", "currency"])), encoding="utf-8")
    (root / "src/schemas/file/portfolio.json").write_text(json.dumps(schema("Portfolio", {
        "isClosed": {"type": "boolean", "description": "Whether it's closed"},
        "limit": {"$ref": "../common/amount.json", "description": "The limit"}})), encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"name": "model", "version": version}), encoding="utf-8")


def test_schemas_in_subfolders_with_refs_relative_to_their_file(tmp_path):
    write_model(tmp_path)

    model = InternalModel(tmp_path / "src/schemas", nested=True)

    assert sorted(model.files) == ["common/amount.json", "file/portfolio.json"]
    assert model.payload_roots == ["Portfolio"]
    assert list(model.fields(model.roots["Portfolio"])["limit"].schema["properties"]) == ["value", "currency"]
    (tmp_path / "src/schemas/file/amount.json").write_text(json.dumps(schema("Other", {})), encoding="utf-8")
    with pytest.raises(ModelError, match=r"Can't resolve \$ref \.\./common/amount\.json"):
        InternalModel(tmp_path / "src/schemas", nested=True).fields(model.roots["Portfolio"])


@pytest.fixture
def own_model(model_layout):
    """The layout's model replaced by one laid out its own way, with bridge-kit.yaml saying so."""
    root = model_layout.parent / "shared-model"
    shutil.rmtree(root)
    write_model(root)
    configure(model_layout, {"layout": {"schemas": "src/schemas", "nested": True, "examples": "none",
                                        "version_files": ["package.json"]},
                             "conventions": {"booleans": "is-prefix", "field_names": "off"}})
    config = load_config(model_layout)
    start_change(config, model_layout / ".work", "REQ-900")
    return {"ba_repo": model_layout, "root": root, "config": config}


def change(own_model, properties: dict, version: str) -> list[tuple[str, str]]:
    file = own_model["root"] / "src/schemas/file/portfolio.json"
    data = json.loads(file.read_text(encoding="utf-8"))
    data["properties"].update(properties)
    file.write_text(json.dumps(data), encoding="utf-8")
    (own_model["root"] / "package.json").write_text(json.dumps({"name": "model", "version": version}),
                                                       encoding="utf-8")
    base = own_model["ba_repo"] / ".work" / "model-base" / "REQ-900"
    findings = check_change(base, "REQ-900", own_model["config"], own_model["ba_repo"], build=False)
    return [(f.check, f.message) for f in findings if f.check != "merge-request"]


def test_a_change_is_checked_by_the_model_s_own_layout_and_conventions(own_model):
    base = own_model["ba_repo"] / ".work" / "model-base" / "REQ-900"
    assert sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()) == [
        "package.json", "src/schemas/common/amount.json", "src/schemas/file/portfolio.json", "started.json"]

    found = change(own_model, {"isOverdrawn": {"type": "boolean", "description": "Whether it's overdrawn"},
                                  "review_date": {"type": "string", "format": "date", "description": "When reviewed"}},
                   "1.1.0")

    assert found == []  # is-prefix booleans, snake_case allowed, no subfolder error, no example wanted
    diff = diff_models(base, own_model["root"], own_model["config"])
    assert (diff.version, diff.versions, diff.expected_version) == ("1.1.0", {"package.json": "1.1.0"}, "1.1.0")


def test_the_model_s_own_rules_still_catch_what_breaks_them(own_model):
    found = change(own_model, {"overdrawn": {"type": "boolean", "description": "Whether it's overdrawn"}}, "1.0.1")

    assert found == [
        ("names", "Portfolio.overdrawn: booleans start with is or has, e.g. isActive"),
        ("version", "The version should be 1.1.0: the change is additive (minor), from 1.0.0")]
