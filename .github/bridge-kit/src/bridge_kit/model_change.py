"""Changes to the internal model: recording where a change starts, comparing two versions of the model, classifying
each difference by the version rules in the model's CONVENTIONS.md, and finding the consumers a breaking change hits.

The model is compared as payload paths (`CustomerRecord.contactPreference.channel`), walked from
the payload roots, so an object moved into its own file, or written inline, compares as the same thing.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from bridge_kit.config import Config, ConfigError, Consumer
from bridge_kit.internal_model import InternalModel, ModelError, ModelLayout, open_model, read_version

BUMPS = ("none", "patch", "minor", "major")
CHANGE_KINDS = {"none": "none", "patch": "patch", "minor": "additive", "major": "breaking"}
NOT_SEARCHED = {"target", "build", "generated-sources", "generated-python", ".venv", "node_modules", ".git"}


class ChangeError(Exception):
    """The change can't be compared: no base recorded, or the model can't be read."""


@dataclass
class Prop:
    path: str
    name: str
    kind: str  # string, date, date-time, enum, number, integer, boolean, email, currency, country, object <Title>,
    #            or "list of" one of these
    required: bool
    raw: dict  # the property as written, $ref and all
    schema: dict  # with $refs resolved; for lists, the item schema
    owner: str  # the title of the object that holds it
    enum: list[str] | None = None
    format: str | None = None
    pattern: str | None = None
    description: str | None = None
    title: str | None = None  # for objects: the class name

    @property
    def is_list(self) -> bool:
        return self.kind.startswith("list of ")

    @property
    def is_object(self) -> bool:
        return self.kind.removeprefix("list of ").startswith("object ")


@dataclass
class Change:
    path: str
    change: str  # added, removed, type, required, optional, enum-added, enum-removed, format, description
    bump: str  # patch | minor | major
    detail: str
    risk: str = ""
    within_new: bool = False  # a field of an object the change adds: listed with it

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Usage:
    component: str
    uses: str
    checked_out: bool
    references: list[str] = field(default_factory=list)  # file:line, relative to the consumer's repo

    @property
    def affected(self) -> bool:
        """Listed in a merge request: its code uses the change, or it isn't checked out, so nobody can tell."""
        return not self.checked_out or bool(self.references)


@dataclass
class ModelDiff:
    base_version: str | None
    version: str | None  # the first version file's
    versions: dict[str, str | None]  # each version file's, by its path in the model's checkout
    changes: list[Change]
    consumers: dict[str, list[Usage]] = field(default_factory=dict)  # breaking change path -> usages

    @property
    def bump(self) -> str:
        return max((c.bump for c in self.changes), key=BUMPS.index, default="none")

    @property
    def change_kind(self) -> str:
        """additive, breaking, patch or none, as the merge request says it."""
        return CHANGE_KINDS[self.bump]

    @property
    def expected_version(self) -> str | None:
        return bump_version(self.base_version, self.bump) if self.base_version else None

    @property
    def top_changes(self) -> list[Change]:
        return [c for c in self.changes if not c.within_new]

    def affected_consumers(self) -> dict[str, list[str]]:
        """Each consumer a breaking change hits, with the files it uses the changed fields in."""
        found: dict[str, list[str]] = {}
        for usages in self.consumers.values():
            for usage in usages:
                if usage.affected:
                    files = found.setdefault(usage.component, [])
                    files += [r for r in usage.references if r not in files]
        return found

    def to_dict(self) -> dict:
        return {"base_version": self.base_version, "version": self.version, "versions": self.versions,
                "bump": self.bump, "change": self.change_kind, "expected_version": self.expected_version,
                "changes": [c.to_dict() for c in self.changes],
                "consumers": {p: [asdict(u) for u in us] for p, us in self.consumers.items()}}


def bump_version(version: str, bump: str) -> str:
    major, minor, patch = (int(p) for p in version.split(".")[:3])
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return version


def model_versions(model_dir: Path, layout: ModelLayout) -> dict[str, str | None]:
    return {file: read_version(model_dir / file) for file in layout.version_files}


def load_model(model_dir: Path, layout: ModelLayout | None = None) -> InternalModel:
    try:
        return open_model(model_dir, layout)
    except (ModelError, json.JSONDecodeError, OSError) as e:
        raise ChangeError(f"The model in {model_dir} can't be read: {e}") from e


# --- Starting a change ---------------------------------------------------------------------------------------------

def base_dir(work: Path, work_item: str) -> Path:
    return work / "model-base" / work_item


def start_change(config: Config, work: Path, work_item: str) -> tuple[Path, str | None, bool]:
    """Records the model as it is before the change, as the base later diffs compare with. For a checkout that's a
    git repo, the base is the feature branch's start, which isn't built yet. Returns the base folder, its version,
    and whether it was recorded now (False: it already was)."""
    repo, layout = config.model, config.model_layout
    if repo.git:
        raise ChangeError(f"{repo.name} is a git checkout: creating its feature branch isn't built yet")
    if not (repo.path / layout.schemas).is_dir():
        raise ChangeError(f"No {layout.schemas} folder in {repo.path}: is the {repo.name} checkout there?")
    base = base_dir(work, work_item)
    if (base / layout.schemas).is_dir():
        return base, load_model(base, layout).version, False
    base.mkdir(parents=True, exist_ok=True)
    for name in layout.files:
        source = repo.path / name
        if source.is_dir():
            shutil.copytree(source, base / name)
        elif source.is_file():
            (base / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, base / name)
    version = load_model(base, layout).version
    (base / "started.json").write_text(json.dumps({
        "work_item": work_item, "repo": repo.name, "version": version,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2), encoding="utf-8")
    return base, version, True


# --- Reading the model as payload paths ----------------------------------------------------------------------------

def flatten(model: InternalModel) -> dict[str, Prop]:
    """Every property of the payload by its path from the payload roots, objects included."""
    props: dict[str, Prop] = {}

    def walk(obj: dict, path: str, depth: int) -> None:
        if depth > 12:
            return
        required = set(obj.get("required", []))
        for name, raw in obj.get("properties", {}).items():
            prop = _prop(model, path, name, raw, name in required, obj.get("title", path))
            props[prop.path] = prop
            if prop.is_object:
                walk(prop.schema, prop.path, depth + 1)

    for root in model.payload_roots:
        schema = model.roots[root]
        props[root] = Prop(root, root, f"object {root}", True, schema, schema, root,
                           description=schema.get("description"), title=root)
        walk(schema, root, 0)
    return props


def _prop(model: InternalModel, parent: str, name: str, raw: dict, required: bool, owner: str) -> Prop:
    schema = model.deref(raw)
    is_list = schema.get("type") == "array"
    item = model.deref(schema.get("items", {})) if is_list else schema
    kind = _kind(item)
    path = f"{parent}.{name}{'[]' if is_list else ''}"
    return Prop(path, name, f"list of {kind}" if is_list else kind, required, raw, item, owner,
                item.get("enum"), item.get("format"), item.get("pattern"), raw.get("description"),
                item.get("title") if kind.startswith("object") else None)


def _kind(schema: dict) -> str:
    kind = schema.get("type", "object")
    if isinstance(kind, list):
        return "/".join(kind)
    if kind == "object":
        return f"object {schema.get('title', '?')}"
    if kind == "string":
        if schema.get("enum"):
            return "enum"
        if schema.get("format") in ("date", "date-time", "email"):
            return schema["format"]
        if schema.get("pattern") == "^[A-Z]{3}$":
            return "currency"
        if schema.get("pattern") == "^[A-Z]{2}$":
            return "country"
    return kind


def parent_path(path: str) -> str:
    return path.rsplit(".", 1)[0] if "." in path else ""


# --- Comparing two versions ----------------------------------------------------------------------------------------

def diff_models(base_dir_: Path, model_dir: Path, config: Config | None = None) -> ModelDiff:
    layout = config.model_layout if config is not None else ModelLayout()
    base_model, model = load_model(base_dir_, layout), load_model(model_dir, layout)
    base, now = flatten(base_model), flatten(model)
    changes: list[Change] = []

    existing = {p.title for p in base.values() if p.is_object}
    for path in sorted(now.keys() - base.keys(), key=_path_order(now)):
        prop = now[path]
        new_parent = parent_path(path) in now and parent_path(path) not in base
        if new_parent and _reuses_object(now, base, parent_path(path), existing):
            continue
        if new_parent:
            changes.append(Change(path, "added", "minor", f"{_describe(prop)}, in the new object",
                                  within_new=True))
        elif not prop.required:
            changes.append(Change(path, "added", "minor", f"New optional field: {_describe(prop)}"))
        elif prop.is_list:
            changes.append(Change(path, "added", "minor", f"New list: {_describe(prop)}",
                                  risk="A required list: payloads from producers still on an older version have no "
                                       "such list, and consumers on this version reject them"))
        elif prop.is_object and (prop.title or "").endswith("Slot"):
            changes.append(Change(path, "added", "major", f"New slot: {_describe(prop)}",
                                  risk="A whole new part of the payload, from a new upstream: the data collection "
                                       "service must collect and fill it, and payloads from producers still on an "
                                       "older version don't have it"))
        elif "." not in path:
            changes.append(Change(path, "added", "minor", f"A new schema nothing refers to: {prop.title}",
                                  risk="Not part of the payload until a schema refers to it"))
        else:
            changes.append(Change(path, "added", "major", f"New required field: {_describe(prop)}"))

    for path in sorted(base.keys() - now.keys(), key=_path_order(base)):
        if parent_path(path) in base and parent_path(path) not in now:
            continue
        changes.append(Change(path, "removed", "major", f"Removed: {_describe(base[path])}"))

    for path in sorted(base.keys() & now.keys(), key=_path_order(now)):
        changes += _compare(path, base[path], now[path])

    result = ModelDiff(base_model.version, model.version, model_versions(model_dir, layout), changes)
    if config is not None:
        for change in changes:
            if change.bump == "major":
                prop = now.get(change.path) or base[change.path]
                result.consumers[change.path] = find_consumers(config, prop)
    return result


def _compare(path: str, old: Prop, new: Prop) -> list[Change]:
    if old.kind != new.kind:
        if old.kind == "string" and new.kind == "enum":
            detail = f"A free string becomes a coded value: {', '.join(new.enum or [])}"
        else:
            detail = f"Type changed from {old.kind} to {new.kind}"
        return [Change(path, "type", "major", detail)]
    found = []
    if not old.required and new.required:
        found.append(Change(path, "required", "major", "An optional field becomes required"))
    if old.required and not new.required:
        found.append(Change(path, "optional", "major", "A required field becomes optional: consumers may rely on it "
                                                       "being there"))
    if old.enum or new.enum:
        added = [v for v in new.enum or [] if v not in (old.enum or [])]
        removed = [v for v in old.enum or [] if v not in (new.enum or [])]
        if removed:
            found.append(Change(path, "enum-removed", "major", f"Values removed: {', '.join(removed)}"))
        if added:
            found.append(Change(path, "enum-added", "minor", f"Values added: {', '.join(added)}",
                                risk="Consumers that handle every value need the new ones"))
    if (old.format, old.pattern) != (new.format, new.pattern):
        found.append(Change(path, "format", "major",
                            f"Format changed from {old.format or old.pattern or 'none'} to "
                            f"{new.format or new.pattern or 'none'}"))
    if (old.description or "") != (new.description or "") or \
            (old.schema.get("description") or "") != (new.schema.get("description") or ""):
        found.append(Change(path, "description", "patch", "Description changed"))
    return found


def _reuses_object(now: dict[str, Prop], base: dict[str, Prop], path: str, existing: set[str | None]) -> bool:
    """The added path, or an added object above it, is an object the model already had (such as Amount), reused in
    a new place: its fields aren't new."""
    while path in now and path not in base:
        if now[path].is_object and now[path].title in existing:
            return True
        path = parent_path(path)
    return False


def _describe(prop: Prop) -> str:
    kind = prop.kind
    if prop.enum:
        kind += f" ({', '.join(prop.enum)})"
    return f"{prop.name}, {kind}"


def _path_order(props: dict[str, Prop]):
    order = {path: i for i, path in enumerate(props)}
    return lambda path: order.get(path, len(order))


# --- Who a breaking change hits ------------------------------------------------------------------------------------

def find_consumers(config: Config, prop: Prop) -> list[Usage]:
    """Every consumer of the model, and where the checked-out ones use the property. Java code is searched for the
    generated accessors (getX, setX, withX, isX), Python code for the snake_case attribute, in files that name the
    class holding it: accessors such as getType are just as common on the upstreams' own classes."""
    usages = []
    for consumer in config.consumers:
        repo = _consumer_repo(config, consumer)
        usage = Usage(consumer.component, consumer.uses, repo is not None)
        if repo is not None:
            usage.references = _search(repo, consumer.uses, prop)
        usages.append(usage)
    return usages


def _consumer_repo(config: Config, consumer: Consumer) -> Path | None:
    if not consumer.repo:
        return None
    try:
        path = config.repo(consumer.repo).path
    except ConfigError:
        return None
    return path if path.is_dir() else None


def _search(repo: Path, uses: str, prop: Prop) -> list[str]:
    name = prop.name
    if uses == "python":
        pattern, suffix = re.compile(rf"\.{re.escape(_snake(name))}\b"), "*.py"
    else:
        pattern, suffix = re.compile(rf"\b(get|set|with|is){re.escape(name[0].upper() + name[1:])}\("), "*.java"
    owner = re.compile(rf"\b{re.escape(prop.owner)}\b")
    found = []
    for file in sorted(repo.rglob(suffix)):
        if NOT_SEARCHED & set(file.relative_to(repo).parts):
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        if not owner.search(text):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                found.append(f"{file.relative_to(repo).as_posix()}:{number}")
    return found


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# --- Readable output -----------------------------------------------------------------------------------------------

def format_diff(diff: ModelDiff) -> str:
    lines = []
    if not diff.changes:
        lines.append("No changes to the model.")
    for change in diff.changes:
        indent = "    " if change.within_new else "  "
        lines.append(f"{indent}{change.bump:5} {change.path}: {change.detail}")
        if change.risk:
            lines.append(f"{indent}      risk: {change.risk}")
    says = ", ".join(f"{file} says {version}" for file, version in diff.versions.items()) or "no version file"
    lines.append(f"Change: {diff.change_kind} ({diff.bump}). Version {diff.base_version} -> "
                 f"{diff.expected_version}; {says}.")
    affected = diff.affected_consumers()
    if diff.consumers:
        lines.append("Consumers the breaking changes hit:")
        for component, files in affected.items():
            usage = next(u for us in diff.consumers.values() for u in us if u.component == component)
            where = ", ".join(files) if files else "not checked out: uses the " + \
                ("Pydantic models" if usage.uses == "python" else "Java classes")
            lines.append(f"  {component}: {where}")
        unaffected = sorted({u.component for us in diff.consumers.values() for u in us} - affected.keys())
        if unaffected:
            lines.append(f"  No use found in: {', '.join(unaffected)}")
    return "\n".join(lines)
