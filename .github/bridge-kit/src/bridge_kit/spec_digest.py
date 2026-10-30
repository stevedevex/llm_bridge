"""`bridge-kit spec digest`: every operation an upstream spec offers, with every field it takes and returns.

The listing is generated from the spec, so it's complete by construction. The Spec Explorer writes the judgement on
top of it (a summary, where the data the BA asked about is, what isn't there, open questions), and
`bridge-kit validate digest` checks that judgement against the spec: every operation and path it names must exist.

Paths are written as mapping specs write source paths (mappings/FORMAT.md): for REST, property paths in the response
body with `.` between levels; for SOAP, element paths from the response element with `/` between levels. `[]` marks
a list.
"""

from __future__ import annotations

import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bridge_kit.spec_resolver import Resolution, SpecFile, classify
from bridge_kit.specs import OpenApiSource, SourceError, XsdSource, inline_schemas

MAX_DEPTH = 12
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
MAX_CODES = 40
PLACEHOLDER = "_To be written._"
JUDGEMENT_SECTIONS = ("Summary", "Where the data is", "Not available", "Open questions")
ANSWER_COLUMNS = ["#", "Asked for", "Operation", "Path", "Type", "Notes"]
FIELD_COLUMNS = ["Path", "Type", "Required", "Allowed values", "Description"]

_XS = "{http://www.w3.org/2001/XMLSchema}"
_WSDL = "{http://schemas.xmlsoap.org/wsdl/}"


class DigestError(Exception):
    """The spec can't be digested: a format not supported yet, several specs to choose from, or unreadable."""


@dataclass
class Field:
    path: str
    type: str
    required: bool
    allowed: list[str] = field(default_factory=list)
    description: str = ""
    pattern: str = ""  # a regular expression every value matches


@dataclass
class Operation:
    name: str  # as mapping specs name it: `GET /customers/{id}`, `GetCustomer`
    summary: str
    reads_only: bool | None  # REST: the method only reads; SOAP: can't be told from the WSDL
    takes: str  # where the inputs come from, in words
    inputs: list[Field]
    returns: str  # where the outputs come from, in words
    outputs: list[Field]


@dataclass
class Digest:
    title: str
    version: str
    format: str  # openapi-3 | wsdl
    category: str  # REST | SOAP
    operations: list[Operation]

    def operation(self, name: str) -> Operation | None:
        key = operation_key(name)
        return next((op for op in self.operations if operation_key(op.name) == key), None)

    def has_path(self, operation: Operation, path: str) -> bool:
        return path_key(path) in {path_key(f.path) for f in operation.outputs}


def operation_key(name: str) -> str:
    """Operations compare without backticks, extra spaces or case differences in the HTTP method."""
    text = " ".join(name.replace("`", "").split())
    match = re.fullmatch(r"(?i)(get|put|post|delete|patch|head|options) (\S+)", text)
    return f"{match.group(1).upper()} {match.group(2)}" if match else text


def path_key(path: str) -> str:
    """Paths compare without backticks, spaces or list markers."""
    return re.sub(r"\s+", "", path.replace("`", "").replace("[]", ""))


# Digesting

def digest_spec(spec: SpecFile) -> Digest:
    """Digests one spec the spec resolver found."""
    path = Path(spec.path)
    if spec.format == "openapi-3":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return _openapi(data, spec)
    if spec.format == "wsdl":
        return _wsdl(path, spec)
    if spec.format == "xsd":
        raise DigestError(f"{path.name} is an XSD on its own, which has no operations: ask the BA for the WSDL")
    raise DigestError(f"{path.name} is a {spec.format} spec, which `bridge-kit spec digest` can't read yet")


def pick_spec(specs: list[SpecFile], pick: str | None = None) -> SpecFile:
    if pick:
        specs = [s for s in specs if s.path == pick or s.path.endswith("/" + pick.lstrip("/"))]
    if not specs:
        raise DigestError("No spec found" + (f" matching {pick}" if pick else ""))
    if len(specs) > 1:
        raise DigestError("Several specs found: " + ", ".join(Path(s.path).name for s in specs) + "; choose one with "
                          "--pick")
    return specs[0]


def digest_location(location: Path, pick: str | None = None) -> Digest:
    """Digests the spec in a jar, an unpacked folder or a single file."""
    if location.is_file() and zipfile.is_zipfile(location):
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(location) as z:
                z.extractall(folder)
            return digest_spec(pick_spec(classify(Path(folder)), pick))
    return digest_spec(pick_spec(classify(location), pick))


def _one_line(text: object, limit: int = 220) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _codes(values: list | None) -> list[str]:
    return [str(v) for v in values] if values else []


def _openapi_codes(schema: dict) -> list[str]:
    """The allowed codes: `enum`, or Open Banking's `x-namespaced-enum` (`UK.OBIE.Charity` …)."""
    return _codes(schema.get("enum") or schema.get("x-namespaced-enum"))


# OpenAPI

def _openapi(spec: dict, file: SpecFile) -> Digest:
    source = OpenApiSource(spec, None)
    operations = []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        shared = item.get("parameters") or []
        for method, op in item.items():
            if method not in METHODS or not isinstance(op, dict):
                continue
            name = f"{method.upper()} {path}"
            inputs = [_parameter(source, p) for p in [*shared, *(op.get("parameters") or [])]]
            inputs += _request_body(source, op)
            try:
                response, response_name = source.deref(source.response_schema(name))
                outputs = _walk_openapi(source, response, "", 0, {response_name} - {""})
                # The schema's name is a type, never the first step of a path (a property may share it)
                returns = f"response body (schema {response_name}, not part of the paths)" if response_name \
                    else "response body"
            except SourceError as e:
                outputs, returns = [], str(e)
            operations.append(Operation(name, _one_line(op.get("summary") or op.get("description")),
                                        method in ("get", "head", "options"), "parameters and request body (top level)",
                                        inputs, returns, outputs))
    info = spec.get("info") or {}
    return Digest(str(info.get("title", "")), str(info.get("version", "")), "openapi-3", "REST", operations)


def _is_object(schema: dict) -> bool:
    return schema.get("type") == "object" or any(k in schema for k in ("properties", "allOf", "oneOf", "anyOf"))


def _openapi_type(schema: dict, name: str, is_list: bool) -> str:
    if _is_object(schema):
        base = name or "object"
    else:
        base = str(schema.get("type") or "any")
        if schema.get("format"):
            base += f" ({schema['format']})"
    return f"list of {base}" if is_list else base


def _parameter(source: OpenApiSource, raw: dict) -> Field:
    parameter, _ = source.deref(raw)
    schema, _ = source.deref(parameter.get("schema") or {})
    return Field(str(parameter.get("name", "")), f"{_openapi_type(schema, '', False)}, in {parameter.get('in', '?')}",
                 bool(parameter.get("required")), _openapi_codes(schema),
                 _one_line(parameter.get("description") or schema.get("description")), str(schema.get("pattern") or ""))


def _request_body(source: OpenApiSource, op: dict) -> list[Field]:
    if "requestBody" not in op:
        return []
    body, _ = source.deref(op["requestBody"])
    media = next((m for m in body.get("content") or {} if "json" in m), None)
    if media is None:
        return []
    schema, name = source.deref(body["content"][media].get("schema") or {})
    return [Field(f.path, f"{f.type}, in body", f.required, f.allowed, f.description, f.pattern)
            for f in _walk_openapi(source, schema, "", 0, {name} - {""}, max_depth=1)]


def _walk_openapi(source: OpenApiSource, schema: dict, prefix: str, depth: int, seen: set[str],
                  max_depth: int = MAX_DEPTH) -> list[Field]:
    required = set(schema.get("required") or [])
    for part in schema.get("allOf") or []:
        required |= set(source.deref(part)[0].get("required") or [])
    rows = []
    for name, raw in source.properties(schema).items():
        prop, prop_name = source.deref(raw)
        is_list = prop.get("type") == "array"
        item, item_name = source.deref(prop.get("items") or {}) if is_list else (prop, prop_name)
        path = (f"{prefix}.{name}" if prefix else name) + ("[]" if is_list else "")
        description = raw.get("description") or prop.get("description") or item.get("description")
        rows.append(Field(path, _openapi_type(item, item_name, is_list), name in required, _openapi_codes(item),
                          _one_line(description), str(item.get("pattern") or "")))
        if _is_object(item) and depth + 1 < max_depth and item_name not in seen:
            rows += _walk_openapi(source, item, path, depth + 1, seen | {item_name} - {""}, max_depth)
    return rows


# WSDL

def _local(qname: str | None) -> str:
    return qname.split(":", 1)[-1] if qname else ""


def _wsdl(path: Path, file: SpecFile) -> Digest:
    root = ET.parse(path).getroot()
    xsd = XsdSource([Path(p).read_bytes() for p in file.includes] + inline_schemas(path.read_bytes()))
    messages = {m.get("name"): [(part.get("name"), _local(part.get("element") or part.get("type")))
                                for part in m.findall(f"{_WSDL}part")]
                for m in root.findall(f"{_WSDL}message")}
    headers: dict[str, list[str]] = {}
    for binding_op in root.iter(f"{_WSDL}operation"):
        given = binding_op.find(f"{_WSDL}input")
        for header in (given if given is not None else []):
            if header.tag.endswith("}header"):
                parts = messages.get(_local(header.get("message")), [])
                headers.setdefault(binding_op.get("name"), []).extend(
                    element for name, element in parts if header.get("part") in (None, name))
    operations, names = [], set()
    for op in root.findall(f"{_WSDL}portType/{_WSDL}operation"):
        name = op.get("name")
        if name in names:
            continue
        names.add(name)
        given, result = op.find(f"{_WSDL}input"), op.find(f"{_WSDL}output")
        requests = [e for _, e in messages.get(_local(given.get("message")), [])] if given is not None else []
        responses = [e for _, e in messages.get(_local(result.get("message")), [])] if result is not None else []
        header_elements = list(dict.fromkeys(headers.get(name, [])))
        inputs = [f for element in [*header_elements, *requests] for f in _walk_element(xsd, element)]
        outputs = [f for element in responses for f in _walk_element(xsd, element)]
        takes = ", ".join([f"request element `{e}`" for e in requests] + [f"header `{e}`" for e in header_elements])
        returns = ", ".join(f"response element `{e}`" for e in responses) or "nothing"
        operations.append(Operation(name, _one_line(op.findtext(f"{_WSDL}documentation")), None, takes or "nothing",
                                    inputs, returns, outputs))
    version = next((s.get("version") for s in [*_schemas(file), *root.findall(f"{_WSDL}types/{_XS}schema")]
                    if s.get("version")), "")
    return Digest(root.get("name") or path.stem, version, "wsdl", "SOAP", operations)


def _schemas(file: SpecFile) -> list[ET.Element]:
    found = []
    for include in file.includes:
        try:
            found.append(ET.parse(include).getroot())
        except ET.ParseError:
            pass
    return found


def _walk_element(xsd: XsdSource, element_name: str) -> list[Field]:
    if element_name not in xsd.elements:
        return [Field(element_name, "not found in the spec's schemas", True)]
    node = xsd.node(xsd.elements[element_name])
    if node.handle is None:
        return [Field(element_name, node.name, True, node.enum or [], _documentation(xsd, xsd.elements[element_name]),
                      node.pattern or "")]
    return _walk_xsd(xsd, node.handle, element_name, 0, {node.name})


def _walk_xsd(xsd: XsdSource, complex_type: ET.Element, prefix: str, depth: int, seen: set[str]) -> list[Field]:
    rows = []
    for name, element in xsd.children(complex_type).items():
        node = xsd.node(element)
        path = f"{prefix}/{name}" + ("[]" if node.is_list else "")
        type_name = f"list of {node.name}" if node.is_list else node.name
        rows.append(Field(path, type_name, element.get("minOccurs", "1") != "0", node.enum or [],
                          _documentation(xsd, element), node.pattern or ""))
        if node.handle is not None and depth + 1 < MAX_DEPTH and node.name not in seen:
            rows += _walk_xsd(xsd, node.handle, path, depth + 1, seen | {node.name})
    return rows


def _documentation(xsd: XsdSource, element: ET.Element) -> str:
    """The element's own documentation, else its type's."""
    def text(of: ET.Element | None) -> str:
        if of is None:
            return ""
        return " ".join((d.text or "") for d in of.findall(f"{_XS}annotation/{_XS}documentation"))

    if element.get("ref"):
        element = xsd.elements.get(_local(element.get("ref")), element)
    type_name = _local(element.get("type"))
    return _one_line(text(element) or text(element.find(f"{_XS}complexType"))
                     or text(xsd.complex.get(type_name)) or text(xsd.simple.get(type_name)))


# Writing

def render(digest: Digest, resolution: Resolution, spec: SpecFile, upstream: str, repo: Path | None = None) -> str:
    """The digest file: the Spec Explorer's sections, still to be written, above the generated listing."""
    front = {"upstream": upstream, "category": digest.category, "spec": resolution.coordinates or ""}
    location = Path(resolution.location or spec.path)
    if resolution.kind == "url":
        front["url"] = resolution.input
    elif resolution.kind in ("file", "pasted"):
        front["file"] = _relative(location, repo)
    front.update({"spec_file": _relative(Path(spec.path), location if location.is_dir() else location.parent),
                  "format": digest.format, "title": digest.title, "version": digest.version,
                  "operations": len(digest.operations), "generated_by": "bridge-kit spec digest"})
    root = "the response body, `.` between levels" if digest.category == "REST" else \
        "the response element, `/` between levels"
    lines = ["---", yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip(), "---", "",
             f"# Spec digest: {' '.join(p for p in (digest.title, digest.version) if p)}", "",
             "The Spec Explorer writes the sections down to Open questions. Everything under Operations is generated "
             "by `bridge-kit spec digest` from the spec: don't edit it.", ""]
    for heading in JUDGEMENT_SECTIONS:
        lines += [f"## {heading}", ""]
        if heading == "Where the data is":
            lines += ["| " + " | ".join(ANSWER_COLUMNS) + " |", "|" + "---|" * len(ANSWER_COLUMNS), ""]
        else:
            lines += [PLACEHOLDER, ""]
    lines += ["## Operations", "",
              f"{len(digest.operations)} operations. Paths start at {root}, as mapping specs write source paths; "
              "`[]` marks a list.", "",
              "| Operation | Reads only | Summary |", "|---|---|---|"]
    for op in digest.operations:
        reads = {True: "yes", False: "no", None: "?"}[op.reads_only]
        lines.append(f"| `{op.name}` | {reads} | {_cell(op.summary)} |")
    lines.append("")
    first_with: dict[tuple, str] = {}  # many operations return the same fields: list them once
    for op in digest.operations:
        lines += [f"### `{op.name}`", ""]
        if op.summary:
            lines += [op.summary, ""]
        lines += [f"**Takes:** {op.takes}", ""] + _field_table(op.inputs)
        same = tuple((f.path, f.type) for f in op.outputs)
        if same and same in first_with:
            lines += [f"**Returns:** {op.returns}: the same fields as `{first_with[same]}`", ""]
        else:
            first_with.setdefault(same, op.name)
            lines += [f"**Returns:** {op.returns}", ""] + _field_table(op.outputs)
    return "\n".join(lines).rstrip() + "\n"


def _relative(path: Path, base: Path | None) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve())) if base else str(path)
    except ValueError:
        return str(path)


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _field_table(fields: list[Field]) -> list[str]:
    if not fields:
        return ["None.", ""]
    lines = ["| " + " | ".join(FIELD_COLUMNS) + " |", "|" + "---|" * len(FIELD_COLUMNS)]
    for f in fields:
        codes = f.allowed if len(f.allowed) <= MAX_CODES else f.allowed[:MAX_CODES] + [f"… ({len(f.allowed)} in all)"]
        allowed = "; ".join(part for part in (", ".join(codes), f"matches `{f.pattern}`" if f.pattern else "") if part)
        lines.append(f"| `{f.path}` | {_cell(f.type)} | {'yes' if f.required else 'no'} | "
                     f"{_cell(allowed)} | {_cell(f.description)} |")
    return lines + [""]
