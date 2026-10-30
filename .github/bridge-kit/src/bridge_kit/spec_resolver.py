"""`bridge-kit spec resolve`: one entry point for every way an upstream spec is handed over.

A file or folder in the workspace is used as it is. Pasted content is saved to a working file. A URL is downloaded.
Maven coordinates, or a pasted `<dependency>` or `<artifactItem>` block, are resolved from Nexus by running Maven on
the spec-resolver skill's POM, which unpacks the jar exactly as the collector modules do. Everything fetched lands in
the git-ignored `.work/specs/` cache and is reused from there. Fetched files are only read, never run.

The result lists the specs found and classifies each: OpenAPI 3, Swagger 2, WSDL (with the XSDs it imports), XSD, or
compiled classes (a MAP vendor jar, read with javap).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from bridge_kit.paths import kit_dir, work_dir

SPEC_SUFFIXES = (".yaml", ".yml", ".json", ".wsdl", ".xsd")
_XS = "{http://www.w3.org/2001/XMLSchema}"
_WSDL = "{http://schemas.xmlsoap.org/wsdl/}"


class ResolveError(Exception):
    """The input can't be resolved: unreadable, unreachable, or Maven failed."""


@dataclass
class Coordinates:
    group_id: str
    artifact_id: str
    version: str
    type: str = "jar"
    classifier: str = ""

    def __str__(self) -> str:
        return f"{self.group_id}:{self.artifact_id}:{self.version}"


@dataclass
class SpecFile:
    path: str
    format: str  # openapi-3 | swagger-2 | wsdl | xsd | classes
    title: str = ""
    version: str = ""
    detail: str = ""
    includes: list[str] = field(default_factory=list)  # XSDs a WSDL imports, directly or through other XSDs


@dataclass
class Resolution:
    input: str
    kind: str  # file | pasted | url | maven
    status: str  # resolved | choose | ask
    message: str = ""
    coordinates: str | None = None
    location: str | None = None
    specs: list[SpecFile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _configured_nexus() -> str | None:
    """bridge-kit.yaml's Nexus URL, when there's a bridge-kit.yaml to read; a broken one is the preflight's to
    report."""
    from bridge_kit.config import ConfigError, load_config

    try:
        return load_config().nexus_url
    except ConfigError:
        return None


def resolve(given: str, *, pasted: str | None = None, repository_url: str | None = None, pick: str | None = None,
            cache: Path | None = None, maven: str = "mvn") -> Resolution:
    """Resolves what the BA gave. `given` is a path, URL, coordinates or snippet; `pasted` is pasted spec content.

    The Nexus URL comes from `repository_url`, else BRIDGE_KIT_NEXUS_URL (which may name a
    folder), else bridge-kit.yaml's `integrations.nexus.url`, else a mirror in the person's settings.xml.
    """
    cache = cache or work_dir() / "specs"
    repository_url = repository_url or os.environ.get("BRIDGE_KIT_NEXUS_URL") or _configured_nexus()
    if pasted is not None:
        return _finish(_pasted(pasted, cache), pick)
    text = given.strip()
    if text.startswith(("http://", "https://")):
        return _finish(_url(text, cache), pick)
    if "<dependency" in text or "<artifactItem" in text:
        coordinates, question = _snippet(text)
        if question:
            return Resolution(text, "maven", "ask", question)
        return _finish(_maven(text, coordinates, cache, repository_url, maven), pick)
    if re.fullmatch(r"[\w.-]+:[\w.-]+:[\w.${}-]+", text) and not Path(text).exists():
        group, artifact, version = text.split(":")
        if "${" in version:
            return Resolution(text, "maven", "ask", f"The version {version} is a property: which version is it?")
        return _finish(_maven(text, Coordinates(group, artifact, version), cache, repository_url, maven), pick)
    path = Path(text).expanduser()
    if path.exists():
        return _finish(Resolution(text, "file", "resolved", location=str(path.resolve())), pick)
    raise ResolveError(f"{text} isn't a file, a URL, Maven coordinates or a dependency block")


def _finish(resolution: Resolution, pick: str | None) -> Resolution:
    resolution.specs = classify(Path(resolution.location))
    if pick:
        chosen = [s for s in resolution.specs if s.path == pick or s.path.endswith("/" + pick.lstrip("/"))]
        if len(chosen) != 1:
            raise ResolveError(f"--pick {pick} matches {len(chosen)} of the specs found")
        resolution.specs = chosen
    if not resolution.specs:
        resolution.status = "ask"
        resolution.message = "No spec found: ask the BA what the spec is"
    elif len(resolution.specs) > 1:
        resolution.status = "choose"
        resolution.message = "Several specs found: ask the BA which one, then resolve again with --pick"
    return resolution


# Inputs

def _digest(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()[:12]


def _pasted(content: str, cache: Path) -> Resolution:
    stripped = content.lstrip()
    if stripped.startswith("<"):
        try:
            root = ET.fromstring(stripped)
        except ET.ParseError as e:
            raise ResolveError(f"The pasted XML can't be read: {e}") from e
        suffix = ".wsdl" if root.tag == f"{_WSDL}definitions" else ".xsd"
    else:
        try:
            yaml.safe_load(stripped)
        except yaml.YAMLError as e:
            raise ResolveError(f"The pasted content is neither XML nor YAML/JSON: {e}") from e
        suffix = ".yaml"
    target = cache / "pasted" / f"{_digest(content)}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return Resolution("(pasted)", "pasted", "resolved", location=str(target))


def _url(url: str, cache: Path) -> Resolution:
    folder = cache / "url" / _digest(url)
    name = Path(urllib.parse.urlparse(url).path).name or "spec"
    target = folder / name
    if not target.exists():
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                target.write_bytes(response.read())
        except OSError as e:
            shutil.rmtree(folder, ignore_errors=True)
            raise ResolveError(f"Can't download {url}: {e}") from e
    if zipfile.is_zipfile(target):
        _unzip(target, folder / "unpacked")
        return Resolution(url, "url", "resolved", location=str(folder / "unpacked"))
    return Resolution(url, "url", "resolved", location=str(target))


def _snippet(text: str) -> tuple[Coordinates | None, str | None]:
    match = re.search(r"<(dependency|artifactItem)\b.*?</\1>", text, re.S)
    if not match:
        return None, "The dependency block isn't complete: paste it from <dependency> to </dependency>"
    try:
        element = ET.fromstring(re.sub(r"\sxmlns(:\w+)?=\"[^\"]*\"", "", match.group(0)))
    except ET.ParseError as e:
        return None, f"The block isn't valid XML ({e}): paste it again"

    def child(name: str) -> str:
        found = element.find(name)
        return (found.text or "").strip() if found is not None else ""

    group, artifact, version = child("groupId"), child("artifactId"), child("version")
    if not group or not artifact:
        return None, "The block has no groupId or artifactId: paste the whole block"
    if not version:
        return None, f"{group}:{artifact} has no version (a BOM probably manages it): which version is it?"
    if "${" in version:
        return None, f"The version of {group}:{artifact} is the property {version}: which version is it?"
    return Coordinates(group, artifact, version, child("type") or "jar", child("classifier")), None


def _maven(given: str, coordinates: Coordinates, cache: Path, repository_url: str | None, maven: str) -> Resolution:
    folder = cache / coordinates.group_id / coordinates.artifact_id / coordinates.version
    if not (folder.is_dir() and any(folder.iterdir())):
        if shutil.which(maven) is None:
            raise ResolveError(f"{maven} isn't on the PATH")
        folder.mkdir(parents=True, exist_ok=True)
        command = [maven, "-q", "-f", str(kit_dir().parent / "skills" / "spec-resolver" / "pom.xml"),
                   "generate-resources",
                   f"-Dspec.groupId={coordinates.group_id}", f"-Dspec.artifactId={coordinates.artifact_id}",
                   f"-Dspec.version={coordinates.version}", f"-Dspec.type={coordinates.type}",
                   f"-Dspec.classifier={coordinates.classifier}", f"-Dspec.outputDirectory={folder}"]
        if repository_url:
            command.append(f"-Dspec.repositoryUrl={repository_url}")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            shutil.rmtree(folder, ignore_errors=True)
            lines = [l for l in (result.stdout + result.stderr).splitlines() if "ERROR" in l][:3]
            raise ResolveError(f"Maven couldn't resolve {coordinates}: " + (" ".join(lines) or "see mvn output"))
    return Resolution(given, "maven", "resolved", coordinates=str(coordinates), location=str(folder))


def _unzip(archive: Path, target: Path) -> None:
    """Unpacks without letting entries escape the target folder."""
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            destination = (target / member).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ResolveError(f"{archive.name} has an entry outside its folder: {member}")
        z.extractall(target)


# Classifying

def classify(location: Path) -> list[SpecFile]:
    location = location.resolve()
    files = [location] if location.is_file() else sorted(p for p in location.rglob("*") if p.is_file())
    files = [f for f in files if "META-INF" not in f.parts]
    base = location.parent if location.is_file() else location
    specs, imported = [], set()
    for file in files:
        if file.suffix not in SPEC_SUFFIXES:
            continue
        spec = _classify_file(file, base)
        if spec:
            specs.append(spec)
            imported.update(spec.includes)
    specs = [s for s in specs if not (s.format == "xsd" and s.path in imported)]
    classes = [f for f in files if f.suffix == ".class" and "$" not in f.name]
    if not specs and classes:
        specs.append(SpecFile(str(base), "classes", detail=f"{len(classes)} classes; read them with javap"))
    return specs


def _classify_file(file: Path, base: Path) -> SpecFile | None:
    relative = str(file.relative_to(base)) if file.is_relative_to(base) else str(file)
    if file.suffix in (".yaml", ".yml", ".json"):
        try:
            data = (json.loads if file.suffix == ".json" else yaml.safe_load)(file.read_text(encoding="utf-8"))
        except (yaml.YAMLError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict) or not ("openapi" in data or "swagger" in data):
            return None
        info = data.get("info") or {}
        operations = sum(1 for item in (data.get("paths") or {}).values() if isinstance(item, dict)
                         for method in item if method in ("get", "put", "post", "delete", "patch", "head", "options"))
        kind = "openapi-3" if str(data.get("openapi", "")).startswith("3") else "swagger-2"
        return SpecFile(str(file), kind, str(info.get("title", "")), str(info.get("version", "")),
                        f"{operations} operations")
    try:
        root = ET.parse(file).getroot()
    except ET.ParseError:
        return None
    if root.tag == f"{_WSDL}definitions":
        operations = len(root.findall(f"{_WSDL}portType/{_WSDL}operation"))
        includes = sorted(str(p) for p in _imports(file, root, set()))
        return SpecFile(str(file), "wsdl", root.get("name", file.stem), "", f"{operations} operations", includes)
    if root.tag == f"{_XS}schema":
        includes = sorted(str(p) for p in _imports(file, root, set()))
        return SpecFile(str(file), "xsd", root.get("targetNamespace", ""), root.get("version", ""),
                        f"{len(root.findall(f'{_XS}element'))} global elements", includes)
    return None


def _imports(file: Path, root: ET.Element, seen: set[Path]) -> set[Path]:
    """Every XSD a WSDL or XSD pulls in through import or include, followed transitively."""
    found = set()
    for element in root.iter():
        if element.tag in (f"{_XS}import", f"{_XS}include") and element.get("schemaLocation"):
            target = (file.parent / element.get("schemaLocation")).resolve()
            if target.exists() and target not in seen:
                seen.add(target)
                found.add(target)
                try:
                    found |= _imports(target, ET.parse(target).getroot(), seen)
                except ET.ParseError:
                    pass
    return found


def format_resolution(resolution: Resolution) -> str:
    lines = [f"{resolution.status}: {resolution.input}"]
    if resolution.coordinates:
        lines.append(f"  coordinates {resolution.coordinates}")
    if resolution.location:
        lines.append(f"  location {resolution.location}")
    for spec in resolution.specs:
        title = " ".join(part for part in (spec.title, spec.version) if part)
        lines.append(f"  {spec.format:9} {spec.path}" + (f" ({title}; {spec.detail})" if title else f" ({spec.detail})"))
        lines += [f"            imports {include}" for include in spec.includes]
    if resolution.message:
        lines.append(f"  {resolution.message}")
    return "\n".join(lines)
