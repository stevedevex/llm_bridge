"""`bridge-kit model profile`: the internal model's layout and conventions as its own files show them, as a `model:`
block for `bridge-kit.yaml`, for a person to review.

The layout: where the schemas are (the folder holding the most JSON Schemas) and whether in subfolders, the examples
folder (`<schema>.example.json` files) or none, and the files that hold the model's version. The conventions: each
rule `validate model` checks, run over every field of the model (and every schema file, for the file rules) with each
setting the rule allows, through the same checks, and counted. A setting is proposed when at least 90% of what it
applies to already follows it; below that, or with nothing to go by, the rule is proposed off, with the counts.
`validate model` checks only what a change adds, so old exceptions don't fail it. When two settings fit as well
(single-word names are both camelCase and snake_case), the kit's default wins.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bridge_kit.config import CONVENTIONS
from bridge_kit.internal_model import ModelLayout, read_version

THRESHOLD = 0.9
SKIPPED = {".git", "target", "node_modules", "build", "dist", ".venv", "__pycache__"}
VERSION_FILES = ("pom.xml", "pyproject.toml", "package.json")
# Each rule's settings to try, and whether it's an error rule (counted by errors) or a warning rule
SETTINGS = {
    "field_names": ["camelCase", "snake_case"], "booleans": ["no-prefix", "is-prefix"],
    "enum_values": ["UPPER_SNAKE_CASE"], "lists": ["required"], "nulls": ["forbidden"], "objects": ["closed"],
    "descriptions": ["required"], "dates": ["on"], "currencies": ["on"], "countries": ["on"],
}
WARNING_RULES = {"dates", "currencies", "countries", "money"}


def applies(rule: str, prop) -> bool:
    """Whether a rule has anything to say about this field: the same conditions `validate model` uses."""
    nested = "." in prop.path
    return {
        "field_names": nested, "descriptions": nested, "booleans": prop.kind == "boolean",
        "lists": prop.is_list and nested, "enum_values": bool(prop.enum), "nulls": True,
        "objects": prop.is_object and nested, "dates": prop.name.endswith("Date"),
        "currencies": prop.name == "currency" or prop.name.endswith("Currency"),
        "countries": bool(re.search(r"(^c|C)ountry(Code)?$", prop.name)),
        "money": _money_like(prop),
    }[rule]


def _money_like(prop) -> bool:
    fields = set(prop.schema.get("properties", {})) if prop.is_object else set()
    return "." in prop.path and "currency" in fields and bool(fields & {"value", "amount"}) and len(fields) <= 3


@dataclass
class Rule:
    name: str
    proposed: str  # a setting, or "off"
    applies_to: int  # how many fields (or files) it has something to say about
    follow: dict[str, int] = field(default_factory=dict)  # setting -> how many of those follow it
    examples: list[str] = field(default_factory=list)  # a few that don't follow the proposed setting, or the best one

    @property
    def comment(self) -> str:
        if not self.applies_to:
            return "nothing to go by"
        counts = ", ".join(f"{s} {n} of {self.applies_to}" for s, n in self.follow.items())
        return counts if self.proposed != "off" else f"off: {counts}"


@dataclass
class Profile:
    folder: str
    layout: dict
    schemas: int = 0
    fields: int = 0
    rules: list[Rule] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def conventions(self) -> dict[str, str]:
        return {r.name: r.proposed for r in self.rules}

    def to_dict(self) -> dict:
        return {"folder": self.folder, "schemas": self.schemas, "fields": self.fields,
                "model": {"layout": self.layout, "conventions": self.conventions},
                "rules": [asdict(r) for r in self.rules], "notes": self.notes}


class ProfileError(Exception):
    """The folder has no model to profile."""


def find_layout(checkout: Path) -> ModelLayout:
    """Where the schemas, the examples and the version are, in a model's checkout."""
    folders: dict[Path, int] = {}
    examples: dict[Path, int] = {}
    for file in sorted(checkout.rglob("*.json")):
        relative = file.relative_to(checkout)
        if set(relative.parts) & SKIPPED or len(relative.parts) > 6:
            continue
        if file.name.endswith(".example.json"):
            examples[file.parent] = examples.get(file.parent, 0) + 1
            continue
        try:
            head = file.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            continue
        if re.search(r'"\$schema"\s*:', head):
            folders[file.parent] = folders.get(file.parent, 0) + 1
    if not folders:
        raise ProfileError(f"No JSON Schemas in {checkout}: is it the model's checkout?")
    # The schemas folder: the one whose tree holds the most schemas, the shallowest when they tie
    totals = {f: sum(n for g, n in folders.items() if g == f or f in g.parents) for f in folders}
    top = max(totals, key=lambda f: (totals[f], -len(f.parts)))
    nested = any(top in f.parents for f in folders)
    example = max(examples, key=examples.get) if examples else None
    versions = []
    for name in VERSION_FILES:
        for found in sorted(checkout.glob(name)) + sorted(checkout.glob(f"*/{name}")):
            relative = found.relative_to(checkout)
            if not set(relative.parts) & SKIPPED and read_version(found):
                versions.append(relative.as_posix())
    return ModelLayout(top.relative_to(checkout).as_posix() or ".", nested,
                       example.relative_to(checkout).as_posix() if example else None, versions)


def profile(checkout: Path) -> Profile:
    from bridge_kit.model_change import Change, ChangeError, ModelDiff, flatten, load_model
    from bridge_kit.validators.model import FILE_NAMES, JSON_SCHEMAS, _check_conventions

    layout = find_layout(checkout)
    try:
        model = load_model(checkout, layout)
    except ChangeError as e:
        raise ProfileError(str(e)) from None
    props = flatten(model)
    result = Profile(str(checkout), {"schemas": layout.schemas, "nested": layout.nested,
                                     "examples": layout.examples or "none", "version_files": layout.version_files},
                     len(model.files), len(props))
    if not layout.version_files:
        result.notes.append("No file gives the model's version (pom.xml, pyproject.toml, package.json): validate "
                            "model can't check a change's version until model.layout.version_files names one")
    if not layout.examples:
        result.notes.append("No examples folder (<schema>.example.json): examples is none")

    # File rules: the JSON Schema draft and the file names, counted over the schema files
    files = model.files
    declared = [str(s.get("$schema") or "").removeprefix("https://").removeprefix("http://").rstrip("#")
                for s in files.values()]
    drafts = {name: sum(d == url for d in declared) for name, url in JSON_SCHEMAS.items()}
    best = _best("json_schema", drafts)
    result.rules.append(_choose("json_schema", len(files), drafts,
                                [n for n, d in zip(files, declared) if d != JSON_SCHEMAS[best]]))
    names = {setting: sum(bool(re.fullmatch(pattern + r"\.json", Path(n).name)) for n in files)
             for setting, (pattern, _) in FILE_NAMES.items()}
    best = _best("file_names", names)
    result.rules.append(_choose("file_names", len(files), names,
                                [n for n in files if not re.fullmatch(FILE_NAMES[best][0] + r"\.json", Path(n).name)]))

    # Field rules: each through validate model's own checks, every field as if a change had added it
    diff = ModelDiff(None, None, {}, [Change(path, "added", "minor", "") for path in props])
    for rule, settings in SETTINGS.items():
        applicable = [p for p in props.values() if applies(rule, p)]
        follow, failing = {}, {}
        for setting in settings:
            failed = _failures(diff, props, rule, setting, _check_conventions)
            failing[setting] = [p.path for p in applicable if p.path in failed]
            follow[setting] = len(applicable) - len(failing[setting])
        best = _best(rule, follow)
        result.rules.append(_choose(rule, len(applicable), follow, failing[best]))
    money_titles: dict[str, int] = {}
    for prop in props.values():
        if applies("money", prop):
            money_titles[prop.title or "(untitled)"] = money_titles.get(prop.title or "(untitled)", 0) + 1
    money_count = sum(money_titles.values())
    titled = {t: n for t, n in money_titles.items() if t != "(untitled)"}
    result.rules.append(_choose("money", money_count, titled or {"Amount": 0},
                                [p.path for p in props.values() if applies("money", p)
                                 and p.title != max(titled or {"Amount": 0}, key=(titled or {"Amount": 0}).get)]))
    order = list(CONVENTIONS)
    result.rules.sort(key=lambda r: order.index(r.name))
    return result


def _failures(diff, props, rule: str, setting: str, check) -> set[str]:
    """The paths that don't follow one rule at one setting, every other rule off."""
    conventions = {name: "off" for name in CONVENTIONS}
    conventions[rule] = setting
    severity = "warning" if rule in WARNING_RULES else "error"
    found: set[str] = set()

    def add(level: str, _check: str, message: str, *args) -> None:
        if level == severity:
            found.add(message.split(":", 1)[0])

    check(diff, props, conventions, add)
    return found


def _best(rule: str, follow: dict[str, int]) -> str:
    """The setting most follow; the kit's default when two tie."""
    default = CONVENTIONS.get(rule)
    return max(follow, key=lambda s: (follow[s], s == default))


def _choose(rule: str, applies_to: int, follow: dict[str, int], failing: list[str]) -> Rule:
    best = _best(rule, follow)
    proposed = best if applies_to and follow[best] >= THRESHOLD * applies_to else "off"
    return Rule(rule, proposed, applies_to, follow, failing[:3])


def render(result: Profile) -> str:
    lines = [f"The model in {result.folder}: {result.schemas} schema(s), {result.fields} field(s)", "", "model:",
             "  layout:", f"    schemas: {result.layout['schemas']}",
             f"    nested: {str(result.layout['nested']).lower()}",
             f"    examples: {result.layout['examples']}",
             f"    version_files: [{', '.join(result.layout['version_files'])}]", "  conventions:"]
    width = max(len(f"    {r.name}: {r.proposed}") for r in result.rules)
    lines += [f"{f'    {r.name}: {r.proposed}':<{width}}  # {r.comment}" for r in result.rules]
    exceptions = [r for r in result.rules if r.examples]
    if exceptions:
        lines += ["", "Not following the proposed setting (or the closest, when it's off), a few each:"]
        lines += [f"- {r.name}: {', '.join(r.examples)}" for r in exceptions]
    lines += ([""] + [f"Note: {n}" for n in result.notes]) if result.notes else []
    return "\n".join(lines) + "\n"


def profile_json(result: Profile) -> str:
    return json.dumps(result.to_dict(), indent=2)
