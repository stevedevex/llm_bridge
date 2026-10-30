"""A real payload against the internal model (`payload check`), and the shape of several (`payload profile`). Both
walk the payload by the model's paths (`CustomerRecord.accounts[].status`), a list's items as one path, so what they
find reads like the rest of the kit.

`check` finds, against the root schema the service's contract names: fields the model doesn't have, required fields
missing, nulls, values of the wrong type, values outside a code list, and values that don't meet a format or pattern.
A stored payload has MongoDB's types, made plain by `payloads.plain`, so a date the model calls a `date` may come back
as midnight UTC (`2026-03-31T00:00:00Z`): `check` takes that for the date it is. `profile` gives, per path across the
payloads: how often it's there and how often null, the types seen, list sizes, and the values a coded field takes.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from bridge_kit.internal_model import InternalModel

KINDS = {  # in the order a report lists them
    "unknown": "not in the model", "missing": "required, missing", "null": "null", "type": "wrong type",
    "code": "not one of its codes", "format": "not its format",
}
FORMATS = {
    "date": re.compile(r"\d{4}-\d{2}-\d{2}(T00:00:00(\.0+)?Z)?"),
    "date-time": re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})"),
    "email": re.compile(r"[^@\s]+@[^@\s]+"),
}
FEW_VALUES = 8  # a field with no more distinct short text values than this has them listed


@dataclass
class Finding:
    kind: str
    path: str
    count: int = 0
    seen: list = field(default_factory=list)  # a few of the values found, for code, type and format

    @property
    def text(self) -> str:
        values = f": {', '.join(map(_shown, self.seen))}" if self.seen else ""
        times = f" ({self.count} times)" if self.count > 1 else ""
        return f"{self.path}: {KINDS[self.kind]}{values}{times}"


def kind_of(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def check(model: InternalModel, root: str, payload, ignore: tuple[str, ...] = ()) -> list[Finding]:
    """What's wrong with a payload against the model's `root` schema; `ignore` names root fields that aren't the
    payload's own, such as the request id a stored document carries."""
    found: dict[tuple[str, str], Finding] = {}

    def add(kind: str, path: str, value=None) -> None:
        finding = found.setdefault((kind, path), Finding(kind, path))
        finding.count += 1
        if kind in ("code", "type", "format") and value not in finding.seen and len(finding.seen) < 3:
            finding.seen.append(value if kind != "type" else kind_of(value))

    def walk(value, schema: dict, path: str, top: bool = False) -> None:
        schema = model.deref(schema)
        types = schema.get("type")
        types = [types] if isinstance(types, str) else list(types or [])
        if value is None:
            if "null" not in types:
                add("null", path)
            return
        if not types and "properties" in schema:
            types = ["object"]
        if types and not any(_is(value, t) for t in types):
            add("type", path, value)
            return
        if "const" in schema and value != schema["const"]:
            add("code", path, value)
        if "enum" in schema and value not in schema["enum"]:
            add("code", path, value)
        if isinstance(value, str):
            pattern = FORMATS.get(schema.get("format", ""))
            if (pattern and not pattern.fullmatch(value)) or \
                    ("pattern" in schema and not re.search(schema["pattern"], value)):
                add("format", path, value)
        if isinstance(value, dict):
            properties = schema.get("properties") or {}
            extra = schema.get("additionalProperties", True)
            for name, child in value.items():
                if top and name in ignore:
                    continue
                if name in properties:
                    walk(child, properties[name], f"{path}.{name}")
                elif extra is False:
                    add("unknown", f"{path}.{name}")
                elif isinstance(extra, dict):
                    walk(child, extra, f"{path}.{name}")
            for name in schema.get("required") or []:
                if name not in value:
                    add("missing", f"{path}.{name}")
        if isinstance(value, list) and "items" in schema:
            for item in value:
                walk(item, schema["items"], f"{path}[]")

    walk(payload, model.roots[root], root, top=True)
    order = list(KINDS)
    return sorted(found.values(), key=lambda f: (order.index(f.kind), f.path))


def _is(value, kind: str) -> bool:
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or \
            (isinstance(value, float) and value.is_integer())
    return kind_of(value) == kind


def wrapped(findings: list[Finding], root: str) -> bool:
    """Whether a payload looks wrapped in a field of its own: every field at its root unknown, and the root's
    required fields missing."""
    top = [f for f in findings if f.path.count(".") == 1]
    return bool(top) and all(f.kind in ("unknown", "missing") for f in top) and \
        {f.kind for f in top} == {"unknown", "missing"}


@dataclass
class Shape:
    path: str
    present: int = 0
    nulls: int = 0
    types: Counter = field(default_factory=Counter)
    sizes: list[int] = field(default_factory=list)  # for lists
    values: Counter = field(default_factory=Counter)  # short text values

    @property
    def coded(self) -> bool:
        return 0 < len(self.values) <= FEW_VALUES and sum(self.values.values()) == self.types.get("string", 0)


def profile(root: str, payloads: list) -> list[Shape]:
    """Per path across the payloads: how often it's there and null, the types seen, list sizes, short text values."""
    shapes: dict[str, Shape] = {}

    def walk(value, path: str) -> None:
        shape = shapes.setdefault(path, Shape(path))
        shape.present += 1
        if value is None:
            shape.nulls += 1
            return
        shape.types[kind_of(value)] += 1
        if isinstance(value, str) and len(value) <= 40:
            shape.values[value] += 1
        if isinstance(value, dict):
            for name, child in value.items():
                walk(child, f"{path}.{name}")
        elif isinstance(value, list):
            shape.sizes.append(len(value))
            for item in value:
                walk(item, f"{path}[]")

    for payload in payloads:
        walk(payload, root)
    return [shapes[p] for p in sorted(shapes)]


def render_check(service: str, request: str, root: str, findings: list[Finding]) -> str:
    lines = [f"{service} payload {request} against the model's {root}"]
    lines += [f"- {f.text}" for f in findings] or ["Nothing: it matches the model."]
    if wrapped(findings, root):
        lines.append(f"Every field at its root is unknown and {root}'s own are missing: is the stored document a "
                     "wrapper? Then name the payload's field as payload_field in bridge-kit.yaml.")
    return "\n".join(lines) + "\n"


def render_profile(service: str, requests: list[str], shapes: list[Shape]) -> str:
    lines = [f"{service}: {len(requests)} payload(s)", "",
             "| Path | Present | Null | Types | List sizes | Values |", "|---|---|---|---|---|---|"]
    for s in shapes:
        types = ", ".join(f"{t} {n}" if len(s.types) > 1 else t for t, n in s.types.most_common())
        sizes = (f"{min(s.sizes)}" if min(s.sizes) == max(s.sizes) else f"{min(s.sizes)}–{max(s.sizes)}") \
            if s.sizes else ""
        values = ", ".join(f"{v} ({n})" for v, n in s.values.most_common()) if s.coded else \
            (f"{len(s.values)} distinct" if len(s.values) > FEW_VALUES else "")
        lines.append(f"| `{s.path}` | {s.present} | {s.nulls or ''} | {types} | {sizes} | {values} |")
    return "\n".join(lines) + "\n"


def _shown(value) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= 40 else text[:37] + "..."
