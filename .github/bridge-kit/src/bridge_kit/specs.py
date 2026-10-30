"""Upstream specs inside spec jars, and resolving mapping source paths against them.

One resolver per category: OpenAPI for REST, the XSDs for SOAP, the compiled classes (through `javap`) for MAP.
JDBC upstreams publish no model, so their sources can't be resolved from the BA repo.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml


class SourceError(Exception):
    """A source path doesn't exist in the spec, or the spec can't be read."""


@dataclass
class SourceNode:
    """A point in an upstream model: an object, a list item or a scalar."""

    name: str  # the type's name, for messages
    is_list: bool = False  # the property it was reached through is a list
    enum: list[str] | None = None  # allowed codes, when the spec lists them
    handle: object = None  # resolver-specific
    pattern: str | None = None  # a regular expression every value matches, when the spec gives one


def find_jar(coordinates: str, repositories: list[Path]) -> Path | None:
    """The jar for `group:artifact:version` in the first Maven repository folder that has it."""
    parts = coordinates.strip().split(":")
    if len(parts) != 3:
        return None
    group, artifact, version = parts
    for repo in repositories:
        jar = repo.joinpath(*group.split("."), artifact, version, f"{artifact}-{version}.jar")
        if jar.exists():
            return jar
    return None


def resolver_for(header: dict, repositories: list[Path] | None = None, location: Path | None = None):
    """A source resolver for a mapping spec's header, or None when its sources can't be checked here.

    The spec comes from `location` (a jar, or the folder `bridge-kit spec resolve` unpacked it into), or else from the
    jar for the header's coordinates in one of the Maven repository folders.
    """
    category = str(header.get("category", ""))
    if category == "JDBC":
        return None
    if location is None:
        location = find_jar(str(header.get("spec", "")), repositories or [])
        if location is None:
            raise SourceError(f"Spec jar {header.get('spec')} isn't in "
                              f"{', '.join(map(str, repositories or [])) or 'any repository'}")
    if category == "REST":
        return OpenApiSource.from_location(location, str(header.get("operation", "")))
    if category == "SOAP":
        return XsdSource.from_location(location)
    if category == "MAP":
        return JavaClassSource(location)
    return None


def _files(location: Path, suffixes: tuple[str, ...]) -> list[tuple[str, bytes]]:
    """(name, content) of the files with these suffixes in a jar, an unpacked folder or one file, leaving out
    META-INF."""
    if location.is_dir():
        return [(str(p.relative_to(location)), p.read_bytes()) for p in sorted(location.rglob("*"))
                if p.is_file() and p.name.endswith(suffixes) and "META-INF" not in p.parts]
    if not zipfile.is_zipfile(location):
        return [(location.name, location.read_bytes())] if location.name.endswith(suffixes) else []
    with zipfile.ZipFile(location) as z:
        return [(n, z.read(n)) for n in z.namelist() if n.endswith(suffixes) and not n.startswith("META-INF")]


def _split(segment: str) -> tuple[str, bool]:
    return (segment[:-2], True) if segment.endswith("[]") else (segment, False)


def _list_warning(name: str, is_list: bool, marked: bool) -> list[str]:
    if is_list and not marked:
        return [f"{name} is a list in the spec: write {name}[]"]
    if marked and not is_list:
        return [f"{name} isn't a list in the spec: write {name}"]
    return []


class OpenApiSource:
    """Resolves `Data.Account[].Identification`-style paths in an operation's success response."""

    def __init__(self, spec: dict, operation: str | None):
        self.spec = spec
        self.operation = operation
        self.response = self.response_schema(operation) if operation else None

    @classmethod
    def from_location(cls, location: Path, operation: str) -> OpenApiSource:
        for _, content in _files(location, (".yaml", ".yml", ".json")):
            spec = yaml.safe_load(content)
            if isinstance(spec, dict) and "paths" in spec:
                try:
                    return cls(spec, operation)
                except SourceError:
                    continue
        raise SourceError(f"No OpenAPI spec in {location.name} has the operation {operation}")

    def _pointer(self, ref: str) -> dict:
        if not ref.startswith("#/"):
            raise SourceError(f"External $ref {ref} isn't supported")
        node = self.spec
        for part in ref[2:].split("/"):
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node

    def deref(self, schema: dict) -> tuple[dict, str]:
        name = ""
        while "$ref" in schema:
            name = schema["$ref"].rsplit("/", 1)[-1]
            schema = self._pointer(schema["$ref"])
        return schema, name

    def properties(self, schema: dict) -> dict:
        props = dict(schema.get("properties", {}))
        for key in ("allOf", "oneOf", "anyOf"):
            for part in schema.get(key, []):
                props.update(self.properties(self.deref(part)[0]))
        return props

    def response_schema(self, operation: str) -> dict:
        try:
            method, path = operation.split(None, 1)
            item = self.spec["paths"][path.strip()][method.lower()]
        except (ValueError, KeyError) as e:
            raise SourceError(f"The spec has no operation {operation}") from e
        responses = item.get("responses", {})
        code = next((c for c in ("200", "201") if c in responses),
                    next((c for c in responses if c.startswith("2")), None))
        if code is None:
            raise SourceError(f"{operation} has no success response")
        response, _ = self.deref(responses[code])
        content = response.get("content", {})
        media = next((m for m in content if "json" in m), None)
        if media is None:
            raise SourceError(f"{operation} has no JSON response body")
        return content[media]["schema"]

    def root(self, path: str) -> tuple[SourceNode, list[str]]:
        """The node at `path` from the top of the response body; an empty path is the body itself."""
        schema, name = self.deref(self.response)
        body = SourceNode(name or "response body", handle=schema)
        return self.child(body, path) if path else (body, [])

    def child(self, node: SourceNode, path: str) -> tuple[SourceNode, list[str]]:
        warnings: list[str] = []
        for segment in path.split("."):
            name, marked = _split(segment)
            props = self.properties(node.handle)
            if name not in props:
                raise SourceError(f"{name} isn't a property of {node.name}")
            schema, type_name = self.deref(props[name])
            is_list = schema.get("type") == "array"
            warnings += _list_warning(name, is_list, marked)
            if is_list:
                schema, type_name = self.deref(schema.get("items", {}))
            node = SourceNode(type_name or name, is_list, schema.get("enum"), schema)
        return node, warnings


_XS = "{http://www.w3.org/2001/XMLSchema}"
_WSDL = "{http://schemas.xmlsoap.org/wsdl/}"


def inline_schemas(wsdl: bytes) -> list[bytes]:
    """The XSDs written inside a WSDL's types section, as documents of their own."""
    root = ET.fromstring(wsdl)
    return [ET.tostring(schema) for schema in root.findall(f"{_WSDL}types/{_XS}schema")]


class XsdSource:
    """Resolves `GetCustomerResponse/ContactPreference[]`-style element paths in a jar's XSDs,
    including any written inside its WSDLs."""

    def __init__(self, documents: list[bytes]):
        self.elements: dict[str, ET.Element] = {}
        self.complex: dict[str, ET.Element] = {}
        self.simple: dict[str, ET.Element] = {}
        for document in documents:
            for child in ET.fromstring(document):
                name = child.get("name")
                if child.tag == f"{_XS}element":
                    self.elements[name] = child
                elif child.tag == f"{_XS}complexType":
                    self.complex[name] = child
                elif child.tag == f"{_XS}simpleType":
                    self.simple[name] = child

    @classmethod
    def from_location(cls, location: Path) -> XsdSource:
        documents = [content for _, content in _files(location, (".xsd",))]
        for _, wsdl in _files(location, (".wsdl",)):
            documents += inline_schemas(wsdl)
        if not documents:
            raise SourceError(f"{location.name} has no XSDs")
        return cls(documents)

    @staticmethod
    def _local(qname: str | None) -> str | None:
        return qname.split(":", 1)[-1] if qname else None

    def node(self, element: ET.Element) -> SourceNode:
        if element.get("ref"):
            element = self.elements.get(self._local(element.get("ref")), element)
        is_list = element.get("maxOccurs", "1") not in ("0", "1")
        inline = element.find(f"{_XS}complexType")
        if inline is not None:
            return SourceNode(element.get("name"), is_list, None, inline)
        type_name = self._local(element.get("type"))
        if type_name in self.complex:
            return SourceNode(type_name, is_list, None, self.complex[type_name])
        enum, pattern = None, None
        if type_name in self.simple:
            enum = [e.get("value") for e in self.simple[type_name].iter(f"{_XS}enumeration")] or None
            pattern = next((p.get("value") for p in self.simple[type_name].iter(f"{_XS}pattern")), None)
        return SourceNode(type_name or element.get("name"), is_list, enum, None, pattern)

    def children(self, complex_type: ET.Element) -> dict[str, ET.Element]:
        children: dict[str, ET.Element] = {}
        for child in complex_type:
            if child.tag in (f"{_XS}sequence", f"{_XS}choice", f"{_XS}all"):
                children.update(self.children(child))
            elif child.tag == f"{_XS}element":
                children[child.get("name") or self._local(child.get("ref"))] = child
            elif child.tag in (f"{_XS}complexContent", f"{_XS}simpleContent"):
                for derivation in child:
                    base = self._local(derivation.get("base"))
                    if base in self.complex:
                        children.update(self.children(self.complex[base]))
                    children.update(self.children(derivation))
        return children

    def root(self, path: str) -> tuple[SourceNode, list[str]]:
        first, *rest = path.split("/")
        name, _ = _split(first)
        if name not in self.elements:
            raise SourceError(f"{name} isn't a global element of the spec")
        node = self.node(self.elements[name])
        if not rest:
            return node, []
        return self.child(node, "/".join(rest))

    def child(self, node: SourceNode, path: str) -> tuple[SourceNode, list[str]]:
        warnings: list[str] = []
        for segment in path.split("/"):
            name, marked = _split(segment)
            if node.handle is None:
                raise SourceError(f"{node.name} has no child elements, so {name} can't be one")
            children = self.children(node.handle)
            if name not in children:
                raise SourceError(f"{name} isn't an element of {node.name}")
            node = self.node(children[name])
            warnings += _list_warning(name, node.is_list, marked)
        return node, warnings


_SCALARS = {"boolean", "byte", "char", "short", "int", "long", "float", "double"}
_LISTS = ("java.util.List<", "java.util.Collection<", "java.util.Set<")


class JavaClassSource:
    """Resolves `ContactLookupResult.records[].fullNm`-style property paths on a jar's classes, or on classes
    unpacked into a folder, through javap."""

    def __init__(self, classpath: Path):
        self.jar = classpath
        self.javap = shutil.which("javap")
        if self.javap is None:
            raise SourceError("javap isn't on the PATH, so MAP sources can't be checked")
        names = [name for name, _ in _files(classpath, (".class",))] if classpath.is_dir() else \
            zipfile.ZipFile(classpath).namelist()
        self.classes = {n[:-6].replace("/", "."): n for n in names if n.endswith(".class") and "$" not in n}
        self._members: dict[str, dict[str, str]] = {}

    def _properties(self, fqcn: str) -> dict[str, str]:
        if fqcn not in self._members:
            result = subprocess.run([self.javap, "-cp", str(self.jar), "-public", fqcn],
                                    capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise SourceError(f"javap can't read {fqcn}: {result.stderr.strip()}")
            props = {}
            for line in result.stdout.splitlines():
                match = re.match(r"^\s*public\s+(?!static)(?:final\s+)?(.+?)\s+(get|is)(\w+)\(\);", line)
                if match:
                    prop = match.group(3)
                    prop = prop if len(prop) > 1 and prop[:2].isupper() else prop[0].lower() + prop[1:]
                    props[prop] = match.group(1).strip()
            self._members[fqcn] = props
        return self._members[fqcn]

    def _node(self, name: str, type_name: str) -> SourceNode:
        is_list = type_name.startswith(_LISTS)
        if is_list:
            type_name = type_name[type_name.index("<") + 1:-1].strip()
        if type_name in self.classes:
            return SourceNode(type_name.rsplit(".", 1)[-1], is_list, None, type_name)
        return SourceNode(type_name.rsplit(".", 1)[-1], is_list, None, None)

    def root(self, path: str) -> tuple[SourceNode, list[str]]:
        first, *rest = path.split(".")
        name, _ = _split(first)
        matches = [fq for fq in self.classes if fq.rsplit(".", 1)[-1] == name]
        if len(matches) != 1:
            raise SourceError(f"{name} isn't a class in {self.jar.name}" if not matches
                              else f"{name} names {len(matches)} classes in {self.jar.name}")
        node = SourceNode(name, False, None, matches[0])
        if not rest:
            return node, []
        return self.child(node, ".".join(rest))

    def child(self, node: SourceNode, path: str) -> tuple[SourceNode, list[str]]:
        warnings: list[str] = []
        for segment in path.split("."):
            name, marked = _split(segment)
            if node.handle is None or name in _SCALARS:
                raise SourceError(f"{node.name} has no properties, so {name} can't be one")
            props = self._properties(node.handle)
            if name not in props:
                raise SourceError(f"{name} isn't a property of {node.name}")
            node = self._node(name, props[name])
            warnings += _list_warning(name, node.is_list, marked)
        return node, warnings
