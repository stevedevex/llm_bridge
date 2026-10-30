"""bridge-kit.yaml and bridge-kit.local.yaml: the landscape's file and the example pass their schema and rules, broken
copies fail with what's wrong, and overrides change only what the design lets them."""

import re
from pathlib import Path

import pytest
import yaml
from conftest import KIT, LANDSCAPE

from bridge_kit.cli import main
from bridge_kit.config import ConfigError, check_config, check_local, load_config
from bridge_kit.spec_resolver import _configured_nexus

LANDSCAPE_CONFIG = yaml.safe_load((LANDSCAPE / "bridge-kit.yaml").read_text(encoding="utf-8"))
EXAMPLE_TEXT = (KIT / "bridge-kit.example.yaml").read_text(encoding="utf-8")
MONGODB = {"uri": {"from": "env", "env": "BRIDGE_KIT_MONGO_URI"},
           "environment": {"from": "env", "env": "BRIDGE_KIT_MONGO_ENV"},
           "test_data_only": True,
           "services": {"service-a-java": {"database": {"from": "env", "env": "DC_DB"},
                                                    "collection": {"from": "env", "env": "DC_COLLECTION"},
                                                    "schema": "model-input",
                                                    "raw": {"collection": {"from": "env", "env": "DC_RAW"}}},
                        "service-b-python": {"database": {"from": "env", "env": "CS_DB"},
                                                   "collection": {"from": "env", "env": "CS_COLLECTION"},
                                                   "schema": "model-output", "payload_field": "payload"}}}


def filled(text: str) -> str:
    """The example with its placeholders filled the way a BA repo would fill them."""
    values = {"<environment>": "lending-tools",
              "<https URL of the Nexus repository the spec jars are in>": "https://nexus.example/repository/specs",
              "<https URL of the GitLab>": "https://gitlab.example"}
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    return re.sub(r"<[^>]+>", "something", text)


def config(**changes) -> dict:
    """A copy of the landscape's file with one or more paths set: changes as {"a.b.c": value}, None to delete."""
    data = yaml.safe_load(yaml.safe_dump(LANDSCAPE_CONFIG))
    for path, value in changes.items():
        *parents, last = path.split(".")
        node = data
        for key in parents:
            node = node[key]
        if value is None:
            del node[last]
        else:
            node[last] = value
    return data


def ba_repo(tmp_path: Path, data: dict, local: dict | None = None) -> Path:
    kit = tmp_path / "ba-repo" / ".github" / "bridge-kit"
    kit.mkdir(parents=True)
    (kit / "bridge-kit.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    if local is not None:
        (kit / "bridge-kit.local.yaml").write_text(yaml.safe_dump(local), encoding="utf-8")
    return tmp_path / "ba-repo"


def test_the_landscape_s_file_passes():
    assert check_config(LANDSCAPE_CONFIG) == []


def test_the_example_passes_once_its_placeholders_are_filled():
    assert check_config(yaml.safe_load(filled(EXAMPLE_TEXT))) == []


def test_the_example_doesn_t_pass_with_its_placeholders():
    assert check_config(yaml.safe_load(EXAMPLE_TEXT))


@pytest.mark.parametrize("changes, problem", [
    ({"workspace.repos.shared-model.colour": "blue"}, "workspace.repos.shared-model: colour isn't "
                                                             "allowed"),
    ({"workspace.repos.shared-model.mode": "copy"}, "workspace.repos.shared-model.mode must be one of "
                                                           "local, clone"),
    ({"rules.workspace.on_remote_mismatch": "ask"}, "rules.workspace.on_remote_mismatch must be stop"),
    ({"rules.workspace.never_delete_checkouts": False}, "rules.workspace.never_delete_checkouts must be True"),
    ({"workspace.repos.service-a-java.writers": ["model-designer"]},
     "workspace.repos.service-a-java: writers need access: read-write"),
    ({"workspace.repos.service-a-java.git": True},
     "workspace.repos.service-a-java: a git repo needs its remote and branch, which the preflight checks"),
    ({"environment.manager": "micromamba"}, "environment: micromamba needs the environment's name"),
    ({"environment.name": "my tools"}, "environment.name doesn't match ^[A-Za-z0-9][A-Za-z0-9._-]*$"),
    ({"environment.tools.java": "21 or later"}, "environment.tools.java doesn't match"),
    ({"model.repo": "credit-model"}, "model.repo: credit-model isn't a repo under workspace.repos"),
    ({"bridge-kit": None}, "bridge-kit is missing"),
    ({"integrations": {"confluence": {"url": "https://wiki.example"}}}, "integrations: confluence isn't allowed"),
    ({"integrations": {"mongodb": {**MONGODB, "uri": {"from": "file"}}}}, "integrations.mongodb.uri: from file needs "
                                                                          "its file"),
    ({"integrations": {"mongodb": {**MONGODB, "services": {"service-a-java": {
        **MONGODB["services"]["service-a-java"], "database": "lending"}}}}},
     "integrations.mongodb.services.service-a-java.database must be object"),
    ({"integrations": {"mongodb": {**MONGODB, "environment": "dev"}}},
     "integrations.mongodb.environment must be object"),
])
def test_a_broken_file_says_what_s_wrong(changes, problem):
    found = check_config(config(**changes))

    assert any(p.startswith(problem) for p in found), found


def test_a_broken_file_stops_the_commands_that_read_it(tmp_path, monkeypatch, capsys):
    repo = ba_repo(tmp_path, config(**{"rules.workspace.on_remote_mismatch": "ask"}))
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))

    with pytest.raises(ConfigError, match="1 problem"):
        load_config(repo)
    assert main(["model", "diff", "REQ-1"]) == 1
    assert "rules.workspace.on_remote_mismatch must be stop" in capsys.readouterr().err


def test_overrides_change_a_repo_s_path_and_mode_and_the_environment_s_name(tmp_path):
    data = config(**{"environment.manager": "micromamba", "environment.name": "team-tools"})
    repo = ba_repo(tmp_path, data, {"environment": {"name": "laptop-tools"},
                                    "workspace": {"repos": {"service-a-java": {"path": "/projects/dcs"}}}})

    loaded = load_config(repo)

    assert loaded.environment.name == "laptop-tools"
    assert loaded.repos["service-a-java"].path == Path("/projects/dcs")
    assert loaded.repos["service-a-java"].overridden
    assert not loaded.repos["shared-model"].overridden
    assert loaded.local_file == repo / ".github" / "bridge-kit" / "bridge-kit.local.yaml"


@pytest.mark.parametrize("local, problem", [
    ({"workspace": {"repos": {"service-a-java": {"branch": "main"}}}},
     "workspace.repos.service-a-java: branch can't be overridden"),
    ({"environment": {"manager": "none"}}, "environment: manager can't be overridden"),
    ({"rules": {"workspace": {"dirty_read_only": "warn"}}}, "rules can't be overridden"),
    ({"workspace": {"repos": {"ui-react": {"path": "../ui"}}}},
     "workspace.repos.ui-react: bridge-kit.yaml declares no such repo"),
])
def test_an_override_beyond_what_s_allowed_is_refused(local, problem):
    assert problem in check_local(local, LANDSCAPE_CONFIG)


def test_overrides_can_be_turned_off(tmp_path):
    repo = ba_repo(tmp_path, config(**{"rules.workspace.allow_local_overrides": False}),
                   {"environment": {"name": "laptop-tools"}})

    with pytest.raises(ConfigError, match="turns overrides off"):
        load_config(repo)


def test_the_nexus_url_comes_from_bridge_kit_yaml(tmp_path, monkeypatch):
    repo = ba_repo(tmp_path, config(integrations={"nexus": {"url": "https://nexus.example/repository/specs"}}))
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))

    assert _configured_nexus() == "https://nexus.example/repository/specs"

    (repo / ".github" / "bridge-kit" / "bridge-kit.yaml").write_text("bridge-kit: [broken", encoding="utf-8")
    assert _configured_nexus() is None


def test_mongodb_loads_the_names_of_its_variables_never_their_values(tmp_path):
    loaded = load_config(ba_repo(tmp_path, config(integrations={"mongodb": MONGODB}))).mongodb

    assert (loaded.uri, loaded.environment, loaded.test_data_only) == (
        {"from": "env", "env": "BRIDGE_KIT_MONGO_URI"}, "BRIDGE_KIT_MONGO_ENV", True)
    collection = loaded.services["service-a-java"]
    assert (collection.database, collection.collection, collection.schema, collection.id_field,
            collection.payload_field) == ("DC_DB", "DC_COLLECTION", "model-input", "requestId", None)
    assert (collection.raw.collection, collection.raw.id_field, collection.raw.upstream_field,
            collection.raw.operation_field) == ("DC_RAW", "requestId", "upstream", "operation")
    summary = loaded.services["service-b-python"]
    assert (summary.payload_field, summary.raw) == ("payload", None)


def test_mongodb_s_test_data_only_is_false_unless_it_says_true(tmp_path):
    mongodb = {k: v for k, v in MONGODB.items() if k != "test_data_only"}

    assert load_config(ba_repo(tmp_path, config(integrations={"mongodb": mongodb}))).mongodb.test_data_only is False


def test_a_person_s_file_may_say_where_their_connection_string_is(tmp_path):
    mine = {"from": "file", "file": "~/.config/mongo-uri"}
    repo = ba_repo(tmp_path, config(integrations={"mongodb": MONGODB}), {"integrations": {"mongodb": {"uri": mine}}})

    assert load_config(repo).mongodb.uri == mine
    assert "integrations.mongodb: bridge-kit.yaml declares no MongoDB" in check_local(
        {"integrations": {"mongodb": {"uri": mine}}}, LANDSCAPE_CONFIG)
