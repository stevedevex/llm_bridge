"""The internal data model's JSON schemas: resolving payload paths and describing their fields.

Where the schemas are, and which files hold the model's version, is the model's layout: `bridge-kit.yaml`'s
`model.layout`, by default a flat `schemas/`, `examples/`, the version in `pom.xml` and
`python/pyproject.toml`. `open_model` reads a checkout by its layout.
"""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


class ModelError(Exception):
    """A path doesn't exist in the internal model."""


@dataclass
class ModelLayout:
    schemas: str = "schemas"  # the folder of JSON schemas, in the model's checkout
    nested: bool = False  # whether schemas may sit in subfolders of it
    examples: str | None = "examples"  # the folder of examples, `<schema>.example.json` each; None for none
    version_files: list[str] = field(default_factory=lambda: ["pom.xml", "python/pyproject.toml"])

    @property
    def files(self) -> list[str]:
        """What a change's base records: the schemas, the examples, the version files."""
        return [self.schemas, *([self.examples] if self.examples else []), *self.version_files]


def read_version(file: Path) -> str | None:
    """The version a build file gives, by its kind: `pom.xml`, `pyproject.toml` (the project's or Poetry's),
    `package.json`; None when it isn't there or has none."""
    if not file.is_file():
        return None
    try:
        if file.name == "package.json":
            return str(json.loads(file.read_text(encoding="utf-8")).get("version") or "") or None
        if file.suffix == ".toml":
            data = tomllib.loads(file.read_text(encoding="utf-8"))
            version = (data.get("project") or {}).get("version") or \
                ((data.get("tool") or {}).get("poetry") or {}).get("version")
            return str(version or "") or None
        root = ET.parse(file).getroot()
    except (ValueError, ET.ParseError, OSError):
        return None
    namespace = re.match(r"\{.*\}", root.tag)
    version = root.find(f"{namespace.group(0) if namespace else ''}version")
    return version.text.strip() if version is not None and version.text else None


def open_model(model_dir: Path, layout: ModelLayout | None = None) -> InternalModel:
    """The model in a checkout, read by its layout, its version from the first version file."""
    layout = layout or ModelLayout()
    model = InternalModel(model_dir / layout.schemas, nested=layout.nested)
    model.version = read_version(model_dir / layout.version_files[0]) if layout.version_files else None
    return model


@dataclass
class Field:
    name: str
    schema: dict  # with $refs resolved, and for lists the list's own schema
    item: dict | None  # for lists: the item schema, with $refs resolved
    required: bool

    @property
    def is_list(self) -> bool:
        return self.schema.get("type") == "array"

    @property
    def is_object(self) -> bool:
        return (self.item if self.is_list else self.schema).get("type") == "object"

    @property
    def kind(self) -> str:
        """object, array, string, number, integer or boolean."""
        return self.schema.get("type", "object")

    @property
    def enum(self) -> list[str] | None:
        return (self.item if self.is_list else self.schema).get("enum")


class InternalModel:
    def __init__(self, schema_dir: Path, nested: bool = False):
        self.dir = schema_dir
        found = sorted(schema_dir.rglob("*.json") if nested else schema_dir.glob("*.json"))
        self.files = {p.relative_to(schema_dir).as_posix(): json.loads(p.read_text(encoding="utf-8")) for p in found}
        if not self.files:
            raise ModelError(f"No JSON schemas in {schema_dir}")
        self.roots = {s["title"]: s for s in self.files.values() if "title" in s}
        self.version = _model_version(schema_dir)

    def resolve(self, path: str) -> dict:
        """The object schema at a payload path such as `CustomerRecord.contacts[].phones[]`."""
        parts = path.strip().split(".")
        root = parts[0]
        if root not in self.roots:
            raise ModelError(f"{root} isn't a schema of the internal model")
        node = self.roots[root]
        walked = root
        for part in parts[1:]:
            name, marked_list = (part[:-2], True) if part.endswith("[]") else (part, False)
            fields = self.fields(node)
            if name not in fields:
                raise ModelError(f"{name} isn't a field of {walked}")
            field = fields[name]
            if field.is_list != marked_list:
                hint = f"{name}[]" if field.is_list else name
                raise ModelError(f"{walked}.{name} {'is' if field.is_list else 'is not'} a list: write {hint}")
            node = field.item if field.is_list else field.schema
            walked = f"{walked}.{part}"
        if node.get("type", "object") != "object":
            raise ModelError(f"{path} isn't an object")
        return node

    @property
    def payload_roots(self) -> list[str]:
        """Titles of the schemas no other schema refers to: the roots payload paths start from."""
        referenced = set()

        def collect(node) -> None:
            if isinstance(node, dict):
                if isinstance(node.get("$ref"), str):
                    referenced.add(node["$ref"])
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)

        for schema in self.files.values():
            collect(schema)
        names = {Path(ref).name for ref in referenced}  # a ref may be written relative to its file
        return [s["title"] for name, s in self.files.items()
                if name not in referenced and Path(name).name not in names and "title" in s]

    def canonical(self, path: str) -> str:
        """The same path written from the payload root, e.g. `ContactPreference.channel` becomes
        `CustomerRecord.contactPreference.channel`. Returned unchanged when it already starts at a
        root, or when the object is reached from the root in more than one way."""
        first, _, rest = path.strip().partition(".")
        roots = self.payload_roots
        if first in roots or first not in self.roots:
            return path.strip()
        found = []
        for root in roots:
            queue = [(self.roots[root], root, 0)]
            while queue:
                schema, walked, depth = queue.pop(0)
                if depth > 10:
                    continue
                for name, field in self.fields(schema).items():
                    child = field.item if field.is_list else field.schema
                    if child.get("type", "object") != "object":
                        continue
                    child_path = f"{walked}.{name}{'[]' if field.is_list else ''}"
                    if child.get("title") == first:
                        found.append(child_path)
                    else:
                        queue.append((child, child_path, depth + 1))
        if len(found) != 1:
            return path.strip()
        return f"{found[0]}.{rest}" if rest else found[0]

    def fields(self, obj: dict) -> dict[str, Field]:
        required = set(obj.get("required", []))
        fields = {}
        for name, prop in obj.get("properties", {}).items():
            schema = self.deref(prop)
            item = self.deref(schema["items"]) if schema.get("type") == "array" and "items" in schema else None
            fields[name] = Field(name, schema, item, name in required)
        return fields

    def deref(self, schema: dict) -> dict:
        seen = set()
        while "$ref" in schema:
            ref = schema["$ref"]
            name = ref if ref in self.files else self._by_name(ref)
            if ref in seen or name is None:
                raise ModelError(f"Can't resolve $ref {ref}")
            seen.add(ref)
            schema = self.files[name]
        return schema

    def _by_name(self, ref: str) -> str | None:
        """A ref written relative to its file, in a model with subfolders: the one schema of that file name."""
        found = [name for name in self.files if Path(name).name == Path(ref).name]
        return found[0] if len(found) == 1 else None


def _model_version(schema_dir: Path) -> str | None:
    """The model's version from the pom.xml next to the schemas folder, if there is one: `open_model` reads it by the
    layout instead."""
    return read_version(schema_dir.parent / "pom.xml")
