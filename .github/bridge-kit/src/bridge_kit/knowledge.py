"""The component knowledge's first piece, the glossary: `architecture/glossary/<area>.yaml`, BAs' business terms and the
data elements (internal model paths) they mean.

- `bridge-kit knowledge term "<words>"`: the glossary's terms that match, by name or synonym, each with its data
  elements; then the internal model's fields whose names or descriptions hold the words; then the business terms
  in the components' profiles. Best first, a few of each.
- `bridge-kit knowledge check`: each file in the glossary's shape, each term defined once (a synonym counts), each with
  a definition, and each data element a path of the model.

    terms:
      preferred contact channel:
        definition: How the customer asked to be contacted.
        synonyms: [contact preference, preferred channel]
        data:
          - CustomerRecord.contactPreference.channel
        source: schemas/contact-preference.json, channel's description

Data elements go one a line: a path's `[]` inside `[ ]` would read as a list. `source`, where the definition comes
from, and `note` are optional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bridge_kit.validators import Finding

GLOSSARY = Path("architecture") / "glossary"
PROFILES = Path("architecture") / "components"
SHOWN = 10  # at most this many of each kind of match


@dataclass
class Term:
    name: str
    area: str
    definition: str
    synonyms: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    note: str = ""
    source: str = ""  # where the definition comes from: a schema's description, a profile, a wiki page, a document


def load_glossary(repo: Path, findings: list[Finding] | None = None) -> list[Term]:
    """Every term of every area file; what isn't in the glossary's shape goes to `findings`, when given."""
    def add(message: str, file: Path) -> None:
        if findings is not None:
            findings.append(Finding("error", "glossary", message, file.relative_to(repo).as_posix()))

    terms = []
    for file in sorted((repo / GLOSSARY).glob("*.yaml")):
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            add(f"isn't YAML: {str(e).splitlines()[0]}", file)
            continue
        entries = data.get("terms") if isinstance(data, dict) else None
        if not isinstance(entries, dict):
            add("has no terms: a mapping of each term to its definition, synonyms and data", file)
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                add(f"{name}: a term is a mapping (definition, synonyms, data)", file)
                continue
            terms.append(Term(str(name), file.stem, str(entry.get("definition") or "").strip(),
                              [str(s) for s in entry.get("synonyms") or []], [str(d) for d in entry.get("data") or []],
                              str(entry.get("note") or ""), str(entry.get("source") or "").strip()))
    return terms


def _words(text: str) -> list[str]:
    """Lower-case words; a camelCase name split into its words."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return re.findall(r"[a-z0-9]+", spaced.lower())


def _matches(query: str, *texts: str) -> bool:
    wanted = _words(query)
    found = set(w for text in texts for w in _words(text))
    return bool(wanted) and all(any(f == w or f.startswith(w) for f in found) for w in wanted)


@dataclass
class Found:
    terms: list[Term] = field(default_factory=list)
    fields: list[tuple[str, str]] = field(default_factory=list)  # (path, description)
    profiles: list[tuple[str, str, str]] = field(default_factory=list)  # (component, term, what it is there)
    teams: list[tuple[str, str, str]] = field(default_factory=list)  # (component, its glossary's file, the line)

    def to_dict(self) -> dict:
        return {"terms": [t.__dict__ for t in self.terms],
                "fields": [{"path": p, "description": d} for p, d in self.fields],
                "profiles": [{"component": c, "term": t, "there": w} for c, t, w in self.profiles],
                "teams": [{"component": c, "file": f, "line": line} for c, f, line in self.teams]}


def find_term(query: str, repo: Path, model=None, teams: list[tuple[str, Path]] = ()) -> Found:
    """The glossary's terms, then the model's fields, the profiles' business terms, and the lines of the components'
    own glossaries (`teams`: each component and the glossary file its catalog entry points to)."""
    found = Found()
    terms = load_glossary(repo)
    exact = [t for t in terms if query.strip().lower() in [t.name.lower(), *(s.lower() for s in t.synonyms)]]
    found.terms = exact + [t for t in terms if t not in exact and _matches(query, t.name, *t.synonyms)]
    if model is not None:
        from bridge_kit.model_change import flatten

        for path, prop in flatten(model).items():
            if "." in path and _matches(query, prop.name, prop.description or ""):
                found.fields.append((path, prop.description or ""))
    for profile in sorted((repo / PROFILES).glob("*.md")):
        for term, there in _profile_terms(profile.read_text(encoding="utf-8")):
            if _matches(query, term):
                found.profiles.append((profile.stem, term, there))
    for component, file in teams:
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            if _matches(query, line):
                found.teams.append((component, file.name, " ".join(line.strip("|-* ").split())[:200]))
    found.terms, found.fields, found.profiles = found.terms[:SHOWN], found.fields[:SHOWN], found.profiles[:SHOWN]
    found.teams = found.teams[:SHOWN]
    return found


def _profile_terms(text: str) -> list[tuple[str, str]]:
    """A profile's Business areas and data table: each business term, and what and where it is."""
    section = re.search(r"^## Business areas and data\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    rows = []
    for line in (section.group(1) if section else "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and line.lstrip().startswith("|") and not set(cells[0]) <= set("-: ") and \
                cells[0].lower() != "business term":
            rows.append((cells[0], " ".join(c for c in cells[1:3] if c)))
    return rows


def format_found(query: str, found: Found) -> str:
    lines = []
    if found.terms:
        lines.append("Glossary:")
        for term in found.terms:
            source = f" (source: {term.source})" if term.source else ""
            lines.append(f"  {term.name} ({term.area}): {term.definition or 'no definition'}{source}")
            lines += [f"    → {path}" for path in term.data] or ["    → no data element"]
    if found.fields:
        lines += ["Model fields:"] + [f"  {path}: {description}".rstrip(": ") for path, description in found.fields]
    if found.profiles:
        lines += ["Profiles:"] + [f"  {component}: {term}: {there}" for component, term, there in found.profiles]
    if found.teams:
        lines += ["The components' own glossaries:"] + [f"  {component} ({file}): {line}"
                                                         for component, file, line in found.teams]
    if not lines:
        return (f"Nothing matches \"{query}\": not in the glossary, the model's fields, the profiles or the components' "
                "own glossaries. Ask the BA what it means, and add it to architecture/glossary/ once it's settled.\n")
    return "\n".join(lines) + "\n"


def check_glossary(repo: Path, model=None) -> list[Finding]:
    findings: list[Finding] = []
    terms = load_glossary(repo, findings)
    seen: dict[str, Term] = {}
    paths = None
    if model is not None:
        from bridge_kit.model_change import flatten
        from bridge_kit.mappings import normalize_path

        paths = {normalize_path(p) for p in flatten(model)}
    for term in terms:
        where = f"architecture/glossary/{term.area}.yaml"
        for name in [term.name, *term.synonyms]:
            other = seen.get(name.lower())
            if other is not None and other is not term:
                findings.append(Finding("error", "glossary", f"{name} is defined twice: under {other.name} "
                                                             f"({other.area}) and {term.name} ({term.area})", where))
            seen.setdefault(name.lower(), term)
        if not term.definition:
            findings.append(Finding("error", "glossary", f"{term.name} has no definition", where))
        if not term.data:
            findings.append(Finding("warning", "glossary", f"{term.name} names no data element: say where it is in "
                                                           "the model, or that it isn't data", where))
        for path in term.data if paths is not None else []:
            from bridge_kit.mappings import normalize_path

            if normalize_path(path) not in paths:
                findings.append(Finding("error", "glossary", f"{term.name}: {path} isn't a path of the model", where))
    return findings
