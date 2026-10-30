"""`bridge-kit.yaml`: bridge-kit's single configuration, and `bridge-kit.local.yaml`, one person's overrides beside it.
Both are checked against their schemas in the kit's `schema/` folder, then against the rules a schema can't say: a
writer only on a read-write repo, a git repo's remote and branch, the model repo and its consumers declared, micromamba
with an environment's name, a token's or a connection string's source complete. A file with any problem stops every
command that reads it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bridge_kit.internal_model import ModelLayout
from bridge_kit.paths import kit_dir, repo_root
from bridge_kit.schema import problems

CONFIG_FILE = "bridge-kit.yaml"
LOCAL_FILE = "bridge-kit.local.yaml"


class ConfigError(Exception):
    """bridge-kit.yaml is missing or wrong, or doesn't declare what a command needs."""


@dataclass
class Repo:
    name: str
    path: Path
    access: str
    git: bool
    build: str | None = None
    mode: str = "local"
    remote: str | None = None
    branch: str | None = None
    writers: list[str] = field(default_factory=list)
    declared_path: str = ""  # as bridge-kit.yaml or bridge-kit.local.yaml writes it
    overridden: bool = False  # bridge-kit.local.yaml changed its mode or path


@dataclass
class Consumer:
    component: str
    uses: str  # java | python
    repo: str | None = None


@dataclass
class Environment:
    manager: str = "none"  # micromamba | none
    name: str | None = None
    tools: dict[str, str] = field(default_factory=dict)  # tool -> version range
    files: list[str] = field(default_factory=list)


@dataclass
class GitLabProject:
    name: str
    id: int
    path: str
    access: str
    key: str | None = None
    wiki: bool = False


@dataclass
class GitLabGroup:
    name: str
    id: int
    path: str
    wiki: bool = False
    epics: bool = False


@dataclass
class GitLabConfig:
    url: str
    token: dict  # where the token is: {"from": "env", "env": ...}, never the token
    projects: dict[str, GitLabProject] = field(default_factory=dict)
    groups: dict[str, GitLabGroup] = field(default_factory=dict)
    default_project: str | None = None
    ca_file: str | None = None


@dataclass
class MongoRaw:
    collection: str  # the environment variable naming it, never the name
    id_field: str = "requestId"
    upstream_field: str = "upstream"
    operation_field: str = "operation"


@dataclass
class MongoService:
    name: str
    database: str  # the environment variables naming them, never the names
    collection: str
    schema: str  # the model contract its payloads follow
    id_field: str = "requestId"
    payload_field: str | None = None
    raw: MongoRaw | None = None


@dataclass
class MongoConfig:
    uri: dict  # where the connection string is: {"from": "env", "env": ...}, never the string
    environment: str  # the environment variable naming it
    test_data_only: bool
    services: dict[str, MongoService] = field(default_factory=dict)


# What `validate model` checks a change against, unless bridge-kit.yaml's model.conventions says otherwise
CONVENTIONS = {
    "json_schema": "draft-07", "file_names": "kebab-case", "field_names": "camelCase", "booleans": "no-prefix",
    "enum_values": "UPPER_SNAKE_CASE", "lists": "required", "nulls": "forbidden", "objects": "closed",
    "descriptions": "required", "money": "Amount", "dates": "on", "currencies": "on", "countries": "on",
}


@dataclass
class Config:
    repos: dict[str, Repo]
    model_repo: str | None
    consumers: list[Consumer] = field(default_factory=list)
    environment: Environment = field(default_factory=Environment)
    nexus_url: str | None = None
    rules: dict = field(default_factory=dict)  # the rules section, as written
    work_items: dict = field(default_factory=dict)
    file: Path | None = None
    local_file: Path | None = None  # bridge-kit.local.yaml, when there is one
    gitlab: GitLabConfig | None = None
    model_layout: ModelLayout = field(default_factory=ModelLayout)
    conventions: dict[str, str] = field(default_factory=lambda: dict(CONVENTIONS))
    mongodb: MongoConfig | None = None

    def repo(self, name: str) -> Repo:
        if name not in self.repos:
            raise ConfigError(f"bridge-kit.yaml declares no repo named {name}")
        return self.repos[name]

    @property
    def model(self) -> Repo:
        if not self.model_repo:
            raise ConfigError("bridge-kit.yaml doesn't say which repo holds the internal model (model.repo)")
        return self.repo(self.model_repo)

    @property
    def work_branch_prefix(self) -> str:
        return str((self.rules.get("writes") or {}).get("work_branch_prefix") or "feature/")


def config_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".github" / "bridge-kit"


def check_config(data: dict) -> list[str]:
    """What's wrong with bridge-kit.yaml's content: its schema, then the rules across its sections."""
    found = problems(data, _schema("bridge-kit.schema.json"))
    if found or not isinstance(data, dict):
        return found
    repos = data["workspace"]["repos"]
    for name, repo in repos.items():
        where = f"workspace.repos.{name}"
        if repo.get("writers") and repo["access"] != "read-write":
            found.append(f"{where}: writers need access: read-write")
        if repo.get("git", True) and not (repo.get("remote") and repo.get("branch")):
            found.append(f"{where}: a git repo needs its remote and branch, which the preflight checks")
        if repo.get("shallow") is not None and repo["mode"] != "clone":
            found.append(f"{where}: shallow is for clone mode only")
    environment = data["environment"]
    if environment["manager"] == "micromamba" and not environment.get("name"):
        found.append("environment: micromamba needs the environment's name")
    model = data.get("model") or {}
    if model.get("repo") and model["repo"] not in repos:
        found.append(f"model.repo: {model['repo']} isn't a repo under workspace.repos")
    for i, consumer in enumerate(model.get("consumers") or []):
        if consumer.get("repo") and consumer["repo"] not in repos:
            found.append(f"model.consumers[{i}]: {consumer['repo']} isn't a repo under workspace.repos")
    gitlab = (data.get("integrations") or {}).get("gitlab")
    if gitlab:
        found += _check_gitlab(gitlab)
    mongodb = (data.get("integrations") or {}).get("mongodb")
    if mongodb:
        found += _check_token(mongodb["uri"], "integrations.mongodb.uri")
    return found


def _check_gitlab(gitlab: dict) -> list[str]:
    found = []
    projects = gitlab.get("projects") or {}
    keys = [p["key"] for p in projects.values() if p.get("key")]
    for key in sorted({k for k in keys if keys.count(k) > 1}):
        found.append(f"integrations.gitlab.projects: the key {key} names more than one project")
    if gitlab.get("default_project") and gitlab["default_project"] not in projects:
        found.append(f"integrations.gitlab.default_project: {gitlab['default_project']} isn't a declared project")
    found += _check_token(gitlab["auth"]["token"], "integrations.gitlab.auth.token")
    return found


def _check_token(token: dict, where: str) -> list[str]:
    source = token.get("from")
    return [f"{where}: from {source} needs its {source}"] if source and not token.get(source) else []


def check_local(data: dict, config: dict) -> list[str]:
    """What's wrong with bridge-kit.local.yaml's content, against the bridge-kit.yaml it overrides."""
    found = problems(data, _schema("bridge-kit.local.schema.json"), unknown="can't be overridden")
    if found or not isinstance(data, dict):
        return found
    if (config.get("rules") or {}).get("workspace", {}).get("allow_local_overrides") is False:
        return ["bridge-kit.yaml turns overrides off (rules.workspace.allow_local_overrides: false)"]
    declared = config["workspace"]["repos"]
    for name in ((data.get("workspace") or {}).get("repos") or {}):
        if name not in declared:
            found.append(f"workspace.repos.{name}: bridge-kit.yaml declares no such repo")
    token = (((data.get("integrations") or {}).get("gitlab") or {}).get("auth") or {}).get("token")
    if token is not None:
        if not (config.get("integrations") or {}).get("gitlab"):
            found.append("integrations.gitlab: bridge-kit.yaml declares no GitLab")
        found += _check_token(token, "integrations.gitlab.auth.token")
    uri = ((data.get("integrations") or {}).get("mongodb") or {}).get("uri")
    if uri is not None:
        if not (config.get("integrations") or {}).get("mongodb"):
            found.append("integrations.mongodb: bridge-kit.yaml declares no MongoDB")
        found += _check_token(uri, "integrations.mongodb.uri")
    return found


def load_config(root: Path | None = None) -> Config:
    """Reads the BA repo's bridge-kit.yaml and its bridge-kit.local.yaml, if any; repo paths are relative to the BA
    repo."""
    root = root or repo_root()
    path = config_dir(root) / CONFIG_FILE
    if not path.exists():
        raise ConfigError(f"No bridge-kit.yaml at {path}")
    data = _read(path)
    found = check_config(data)
    if found:
        raise ConfigError(f"{path} has {len(found)} problem(s):\n" + "\n".join(f"  {p}" for p in found))
    local_path = config_dir(root) / LOCAL_FILE
    local = _read(local_path) if local_path.exists() else {}
    if local_path.exists():
        found = check_local(local, data)
        if found:
            raise ConfigError(f"{local_path} has {len(found)} problem(s):\n" + "\n".join(f"  {p}" for p in found))

    overrides = (local.get("workspace") or {}).get("repos") or {}
    repos = {}
    for name, entry in data["workspace"]["repos"].items():
        mine = overrides.get(name) or {}
        declared = str(mine.get("path", entry["path"]))
        repos[name] = Repo(name, (root / declared).resolve(), entry["access"], bool(entry.get("git", True)),
                           entry.get("build"), str(mine.get("mode", entry["mode"])), entry.get("remote"),
                           entry.get("branch"), list(entry.get("writers") or []), declared, bool(mine))
    environment = data["environment"]
    model = data.get("model") or {}
    consumers = [Consumer(str(c["component"]), str(c.get("uses", "java")), c.get("repo"))
                 for c in model.get("consumers") or []]
    return Config(
        repos, model.get("repo"), consumers,
        Environment(environment["manager"], (local.get("environment") or {}).get("name", environment.get("name")),
                    dict(environment.get("tools") or {}), list(environment.get("files") or [])),
        ((data.get("integrations") or {}).get("nexus") or {}).get("url"),
        dict(data.get("rules") or {}), dict(data.get("work_items") or {}),
        path, local_path if local_path.exists() else None,
        _gitlab(data, local), _layout(model), _conventions(model), _mongodb(data, local))


def _layout(model: dict) -> ModelLayout:
    layout, default = model.get("layout") or {}, ModelLayout()
    examples = str(layout.get("examples", default.examples))
    return ModelLayout(str(layout.get("schemas", default.schemas)), bool(layout.get("nested", default.nested)),
                       None if examples == "none" else examples,
                       [str(f) for f in layout.get("version_files", default.version_files)])


def _conventions(model: dict) -> dict[str, str]:
    """The defaults, with what bridge-kit.yaml sets; YAML reads a bare on and off as true and false."""
    given = {k: ("on" if v is True else "off" if v is False else str(v)) for k, v in
             (model.get("conventions") or {}).items()}
    return {**CONVENTIONS, **given}


def _gitlab(data: dict, local: dict) -> GitLabConfig | None:
    gitlab = (data.get("integrations") or {}).get("gitlab")
    if not gitlab:
        return None
    mine = ((local.get("integrations") or {}).get("gitlab") or {}).get("auth") or {}
    projects = {name: GitLabProject(name, int(p["id"]), str(p["path"]).strip("/"), p["access"], p.get("key"),
                                    bool(p.get("wiki")))
                for name, p in (gitlab.get("projects") or {}).items()}
    groups = {name: GitLabGroup(name, int(g["id"]), str(g["path"]).strip("/"), bool(g.get("wiki")),
                                bool(g.get("epics")))
              for name, g in (gitlab.get("groups") or {}).items()}
    return GitLabConfig(str(gitlab["url"]).rstrip("/"), dict(mine.get("token") or gitlab["auth"]["token"]),
                        projects, groups, gitlab.get("default_project"), (gitlab.get("tls") or {}).get("ca_file"))


def _mongodb(data: dict, local: dict) -> MongoConfig | None:
    mongodb = (data.get("integrations") or {}).get("mongodb")
    if not mongodb:
        return None
    mine = ((local.get("integrations") or {}).get("mongodb") or {}).get("uri")
    services = {}
    for name, s in (mongodb.get("services") or {}).items():
        raw = s.get("raw")
        services[name] = MongoService(
            name, str(s["database"]["env"]), str(s["collection"]["env"]), str(s["schema"]),
            str(s.get("id_field", "requestId")), s.get("payload_field"),
            MongoRaw(str(raw["collection"]["env"]), str(raw.get("id_field", "requestId")),
                     str(raw.get("upstream_field", "upstream")), str(raw.get("operation_field", "operation")))
            if raw else None)
    return MongoConfig(dict(mine or mongodb["uri"]), str(mongodb["environment"]["env"]),
                       mongodb.get("test_data_only") is True, services)


def _read(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} isn't valid YAML: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a mapping of sections")
    return data


def _schema(name: str) -> dict:
    return json.loads((kit_dir() / "schema" / name).read_text(encoding="utf-8"))
