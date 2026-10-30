"""The checks on a change to the internal model, run by the Model Designer before it finishes.

What the change adds or changes must follow the model's conventions, as `bridge-kit.yaml`'s `model.conventions` states
them from its CONVENTIONS.md (each with a default, and off when set so); the version must be the one the
change needs, in every version file the layout names; the example must use every object; the merge request
description must say what the diff says, and for a breaking change name every consumer it hits; and the model's
build, which generates the Java classes and the Pydantic models and tests both, must pass. Where the files are is
the layout, `model.layout`.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path

from bridge_kit.config import Config
from bridge_kit.internal_model import InternalModel, ModelError, ModelLayout
from bridge_kit.markdown import FormatError, MdDocument, code_spans, read_markdown
from bridge_kit.model_change import ChangeError, ModelDiff, Prop, base_dir, diff_models, flatten, load_model
from bridge_kit.validators import Finding

MR_FILE = "model-change.md"
MR_FRONT_MATTER = ("work_item", "repo", "branch", "base_version", "version", "change")
MR_SECTIONS = ("Summary", "Changes", "Reused", "Consumers affected", "Open questions")
CHANGES_COLUMNS = ["Path", "Change", "Kind"]
REUSED_COLUMNS = ["Asked for", "Path"]
CHANGE_VALUES = ("additive", "breaking", "patch", "none")
NOTHING = {"", "-", "—", "none", "n/a"}
JSON_SCHEMAS = {"draft-07": "json-schema.org/draft-07/schema", "2019-09": "json-schema.org/draft/2019-09/schema",
                "2020-12": "json-schema.org/draft/2020-12/schema"}
FILE_NAMES = {"kebab-case": (r"[a-z0-9]+(-[a-z0-9]+)*", "kebab-case, e.g. tax-registration.json"),
              "snake_case": (r"[a-z0-9]+(_[a-z0-9]+)*", "snake_case, e.g. tax_registration.json")}
FIELD_NAMES = {"camelCase": r"[a-z][a-zA-Z0-9]*", "snake_case": r"[a-z][a-z0-9]*(_[a-z0-9]+)*"}


def mr_file(ba_repo: Path, work_item: str) -> Path:
    """Where the merge request description is, or should be: the work item's folder, with or without its slug."""
    found = sorted(p for p in (ba_repo / "work").glob(f"{work_item}*/{MR_FILE}")
                   if p.parent.name == work_item or p.parent.name.startswith(f"{work_item}-"))
    return found[0] if found else ba_repo / "work" / work_item / MR_FILE


def validate_model(work_item: str, config: Config, work: Path, ba_repo: Path, build: bool = True) -> list[Finding]:
    """Checks the change recorded for the work item: the model now, against the base `bridge-kit model start` kept."""
    base = base_dir(work, work_item)
    if not (base / config.model_layout.schemas).is_dir():
        return [Finding("error", "base", f"No base recorded for {work_item}: run `bridge-kit model start {work_item}` "
                                         f"before changing the model", _short(config.model.path, ba_repo.parent))]
    return check_change(base, work_item, config, ba_repo, build)


def check_change(base: Path, work_item: str, config: Config, ba_repo: Path, build: bool = True) -> list[Finding]:
    """Checks the model in the checkout against a base folder holding the model before the change."""
    findings: list[Finding] = []
    model_dir, layout, conventions = config.model.path, config.model_layout, config.conventions

    def add(severity: str, check: str, message: str, file: Path | str = model_dir, line: int | None = None) -> None:
        findings.append(Finding(severity, check, message, _short(Path(file), ba_repo.parent), line))

    try:
        diff = diff_models(base, model_dir, config)
        model = load_model(model_dir, layout)
    except (ChangeError, ModelError) as e:  # a broken schema file stops every other check
        add("error", "schemas", str(e))
        return findings

    _check_files(model, load_model(base, layout), layout, conventions, add)
    _check_conventions(diff, flatten(model), conventions, add)
    _check_versions(diff, model_dir, add)
    _check_example(model, diff, model_dir, layout, add)
    _check_merge_request(mr_file(ba_repo, work_item), work_item, config, diff, model, add)
    if build and not any(f.severity == "error" and f.check == "schemas" for f in findings):
        _check_build(config, add)
    return findings


def _check_files(model: InternalModel, base: InternalModel, layout: ModelLayout, conventions: dict, add) -> None:
    wanted = JSON_SCHEMAS.get(conventions["json_schema"])
    for name, schema in model.files.items():
        file = model.dir / name
        declared = str(schema.get("$schema") or "").removeprefix("https://").removeprefix("http://").rstrip("#")
        if wanted and declared != wanted:
            add("error", "files", f"Every schema is JSON Schema {conventions['json_schema']}: set $schema to "
                                  f"{'http' if conventions['json_schema'] == 'draft-07' else 'https'}://{wanted}"
                                  f"{'#' if conventions['json_schema'] == 'draft-07' else ''}", file)
        if conventions["objects"] != "off" and not schema.get("title"):
            add("error", "files", "The schema needs a title: it's the class name in Java and Python", file)
        if name not in base.files:
            pattern = FILE_NAMES.get(conventions["file_names"])
            if pattern and not re.fullmatch(pattern[0] + r"\.json", Path(name).name):
                add("error", "files", f"Schema file names are {pattern[1]}", file)
            if conventions["descriptions"] != "off" and not schema.get("description"):
                add("error", "description", "The new schema needs a description", file)
    if not layout.nested:
        for folder in model.dir.iterdir():
            if folder.is_dir():
                add("error", "files", f"No subfolders in {layout.schemas}/: the Java generator turns them into "
                                      "packages (or set model.layout.nested in bridge-kit.yaml)", folder)


def _check_conventions(diff: ModelDiff, now: dict[str, Prop], conventions: dict, add) -> None:
    """The conventions, on what the change adds or changes; what was there before is the reviewers' business. Each
    is bridge-kit.yaml's, or the default; off turns it off."""
    on = {name: value != "off" for name, value in conventions.items()}
    money = "Amount" if conventions["money"] == "on" else conventions["money"]
    checked = {c.path for c in diff.changes if c.change != "removed" and c.path in now}
    for path in sorted(checked):
        prop = now[path]
        where = f"{path}:"
        if on["descriptions"] and "." in path and not prop.description:
            add("error", "description", f"{where} every property has a description, written for a business reader")
        names = FIELD_NAMES.get(conventions["field_names"])
        if names and not re.fullmatch(names, prop.name) and "." in path:
            add("error", "names", f"{where} field names are {conventions['field_names']}")
        prefixed = re.match(r"(is|has)([A-Z_]|$)", prop.name) is not None
        if prop.kind == "boolean" and conventions["booleans"] == "no-prefix" and prefixed:
            add("error", "names", f"{where} booleans are plain adjectives or nouns, without is or has")
        if prop.kind == "boolean" and conventions["booleans"] == "is-prefix" and not prefixed:
            add("error", "names", f"{where} booleans start with is or has, e.g. isActive")
        if on["lists"] and prop.is_list and "." in path:
            if not prop.required:
                add("error", "lists", f"{where} lists are always present and required; an empty list means none")
            if not prop.name.endswith("s"):
                add("warning", "names", f"{where} lists are plural")
        for value in prop.enum or [] if on["enum_values"] else []:
            if not re.fullmatch(r"[A-Z][A-Z0-9]*(_[A-Z0-9]+)*", str(value)):
                add("error", "enums", f"{where} enum values are UPPER_SNAKE_CASE: {value}")
        types = prop.schema.get("type")
        if on["nulls"] and ("null" in (types if isinstance(types, list) else [types]) or prop.schema.get("nullable")):
            add("error", "types", f"{where} nothing is null: leave the field out when it's unknown")
        if prop.is_object and "." in path:
            if on["objects"] and prop.schema.get("additionalProperties") is not False:
                add("error", "objects", f"{where} every object has additionalProperties: false")
            if on["objects"] and not prop.schema.get("title"):
                add("error", "objects", f"{where} an object needs a title, its class name")
            fields = set(prop.schema.get("properties", {}))
            if (on["money"] and prop.title != money and "currency" in fields and fields & {"value", "amount"}
                    and len(fields) <= 3):
                add("warning", "types", f"{where} money is the {money} schema: a value and an ISO 4217 currency")
        if on["dates"] and prop.name.endswith("Date") and prop.kind.removeprefix("list of ") not in ("date",
                                                                                                    "date-time"):
            add("warning", "types", f"{where} a date is a string with format date")
        if on["currencies"] and (prop.name == "currency" or prop.name.endswith("Currency")) and \
                prop.kind != "currency":
            add("warning", "types", f"{where} a currency is ISO 4217, with the pattern ^[A-Z]{{3}}$")
        if on["countries"] and re.search(r"(^c|C)ountry(Code)?$", prop.name) and prop.kind != "country":
            add("warning", "types", f"{where} a country is ISO 3166-1 alpha-2, with the pattern ^[A-Z]{{2}}$")


def _check_versions(diff: ModelDiff, model_dir: Path, add) -> None:
    if not diff.versions:
        return  # the layout names no version file
    first = next(iter(diff.versions))
    if len(set(diff.versions.values())) > 1:
        says = " and ".join(f"{file} says {version}" for file, version in diff.versions.items())
        add("error", "version", f"{says}: they must be equal", model_dir / first)
    if diff.expected_version and diff.version != diff.expected_version:
        reason = f"the change is {diff.change_kind} ({diff.bump})" if diff.changes else "nothing changed"
        add("error", "version", f"The version should be {diff.expected_version}: {reason}, from "
                                f"{diff.base_version}", model_dir / first)


def example_paths(model: InternalModel, example: dict, root: str) -> set[str]:
    """Every payload path the example has a value for; an empty list has none."""
    found = {root}

    def walk(schema: dict, value: dict, path: str) -> None:
        for name, field in model.fields(schema).items():
            if name not in value or value[name] == []:
                continue
            child = f"{path}.{name}{'[]' if field.is_list else ''}"
            found.add(child)
            if field.is_object:
                for item in (value[name] if field.is_list else [value[name]]):
                    if isinstance(item, dict):
                        walk(field.item if field.is_list else field.schema, item, child)

    walk(model.roots[root], example, root)
    return found


def _check_example(model: InternalModel, diff: ModelDiff, model_dir: Path, layout: ModelLayout, add) -> None:
    if not layout.examples:
        return  # the layout says the model has none
    examples = model_dir / layout.examples
    now = flatten(model)
    present: set[str] = set()
    for root in model.payload_roots:
        file = next((f for f, s in model.files.items() if s.get("title") == root), "")
        example = examples / Path(file).name.replace(".json", ".example.json")
        if not example.exists():
            add("warning", "example", f"{root} has no example: {example.name}", example)
            continue
        try:
            present |= example_paths(model, json.loads(example.read_text(encoding="utf-8")), root)
        except json.JSONDecodeError as e:
            add("error", "example", f"The example isn't valid JSON: {e}", example)
    titles = {p.title for p in now.values() if p.is_object}
    used = {now[p].title for p in present if p in now and now[p].is_object}
    for title in sorted(titles - used):
        add("error", "example", f"The example doesn't use {title}: it uses every object", examples)
    for change in diff.changes:
        if change.change == "added" and change.path in now and change.path not in present:
            add("warning", "example", f"{change.path} isn't in the example", examples)


def _check_merge_request(path: Path, work_item: str, config: Config, diff: ModelDiff, model: InternalModel,
                         add) -> None:
    if not path.exists():
        add("error", "merge-request", f"Write the merge request description to work/{work_item}/{MR_FILE}", path)
        return
    try:
        doc = read_markdown(path.read_text(encoding="utf-8"))
    except FormatError as e:
        add("error", "merge-request", str(e), path, e.line)
        return
    front = doc.front_matter
    for key in MR_FRONT_MATTER:
        if key not in front:
            add("error", "merge-request", f"The front matter has no {key}", path, 1)
    if str(front.get("work_item", work_item)) != work_item:
        add("error", "merge-request", f"work_item should be {work_item}", path, 1)
    if "repo" in front and front["repo"] != config.model.name:
        add("error", "merge-request", f"repo should be {config.model.name}", path, 1)
    if "change" in front and front["change"] not in CHANGE_VALUES:
        add("error", "merge-request", f"change is one of {', '.join(CHANGE_VALUES)}", path, 1)
    elif "change" in front and front["change"] != diff.change_kind:
        add("error", "merge-request", f"change says {front['change']}, but the diff is {diff.change_kind}", path, 1)
    for key, actual in (("version", diff.version), ("base_version", diff.base_version)):
        if key in front and str(front[key]) != str(actual):
            add("error", "merge-request", f"{key} says {front[key]}, but the model's is {actual}", path, 1)
    for heading in MR_SECTIONS:
        if doc.section(heading) is None:
            add("error", "merge-request", f"The section {heading} is missing", path)
    _check_changes_table(doc, diff, path, add)
    _check_reused(doc, model, path, add)
    _check_consumers(doc, diff, path, add)


def _rows(doc: MdDocument, heading: str, columns: list[str], path: Path, add) -> list[tuple[int, list[str]]] | None:
    section = doc.section(heading)
    if section is None:
        return None
    if not section.tables:
        return []
    table = section.tables[0]
    if table.columns[:len(columns)] != columns:
        add("error", "merge-request", f"{heading} needs a table with the columns {', '.join(columns)}", path,
            table.line)
        return None
    return [(line, cells) for line, cells in table.rows if not all(c.strip() in NOTHING for c in cells)]


def _check_changes_table(doc: MdDocument, diff: ModelDiff, path: Path, add) -> None:
    rows = _rows(doc, "Changes", CHANGES_COLUMNS, path, add)
    if rows is None:
        return
    listed = {_bare(span): (line, cells) for line, cells in rows for span in code_spans(cells[0])[:1]}
    for change in diff.top_changes:
        row = listed.get(_bare(change.path))
        if row is None:
            add("error", "merge-request", f"Changes has no row for {change.path} ({change.detail})", path)
        elif change.bump not in row[1][2].lower():
            add("warning", "merge-request", f"{change.path} is {change.bump}, the row says {row[1][2]}", path, row[0])
    if not diff.changes and rows:
        add("error", "merge-request", "Changes lists rows, but the model hasn't changed", path, rows[0][0])


def _check_reused(doc: MdDocument, model: InternalModel, path: Path, add) -> None:
    rows = _rows(doc, "Reused", REUSED_COLUMNS, path, add)
    now = {_bare(p) for p in flatten(model)}
    for line, cells in rows or []:
        named = code_spans(cells[1])
        if not named or _bare(named[0]) not in now:
            add("error", "merge-request", f"Reused names {cells[1]}, which isn't a path of the model", path, line)


def _check_consumers(doc: MdDocument, diff: ModelDiff, path: Path, add) -> None:
    section = doc.section("Consumers affected")
    if section is None:
        return
    text = " ".join(t for _, t in section.paragraphs)
    text += " " + " ".join(" ".join(cells) for table in section.tables for _, cells in table.rows)
    for component, files in diff.affected_consumers().items():
        if component not in text:
            add("error", "consumers", f"A breaking change hits {component}: Consumers affected must name it", path,
                section.line)
        for file in files:
            name = Path(file.split(":")[0]).name
            if name not in text:
                add("error", "consumers", f"{component} uses a changed field in {name}: name it", path, section.line)


def _check_build(config: Config, add) -> None:
    repo = config.model
    if not repo.build:
        add("warning", "build", f"bridge-kit.yaml gives no build command for {repo.name}, so it isn't built")
        return
    try:
        result = subprocess.run(shlex.split(repo.build), cwd=repo.path, capture_output=True, text=True,
                                timeout=900, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        add("error", "build", f"`{repo.build}` didn't run: {e}", repo.path)
        return
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-30:])
        add("error", "build", f"`{repo.build}` failed: Java or Pydantic generation, or a test of the schemas or the "
                              f"example\n{tail}", repo.path)


def _short(file: Path, projects: Path) -> str:
    """The file's path from the folder the repos are checked out in, e.g. shared-model/pom.xml."""
    try:
        return file.resolve().relative_to(projects.resolve()).as_posix()
    except ValueError:
        return str(file)


def _bare(path: str) -> str:
    return path.replace("`", "").strip()
