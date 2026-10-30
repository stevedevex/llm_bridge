"""`bridge-kit components build`: the component catalog, `architecture/components.yaml`, assembled from the components'
profiles, `architecture/components/<name>.md`, which the `/profile-component` prompt writes.

- Each profile's proposed entry (the YAML block under "Proposed catalog entry") is merged into its component's entry:
  the `summary`, `stack`, `owns`, `consumes` and `external` it gives replace the catalog's, and `profile` names the
  file. What only people set (`repo`, `stories`, `team`, `defines_schemas`, `note`) is never touched; a profile that
  gives it is told so. The contracts it owns gain the `kind`, `file` and `root` it gives.
- What no profile can say alone: `order`, from the contracts (each contract's owner before its consumers; otherwise as
  before, then by name), and each contract's owner, its `source`.
- Checks: a profile whose block isn't the catalog's shape (an error, and it isn't merged); a contract owned twice, or
  a cycle among them (errors); a contract consumed that nobody owns, or owned without a kind (warnings); an entry whose
  profile isn't there (an error).

The file is written only with `--write`, and only without errors, in a fixed shape with its leading comment kept, so
the diff an architect reviews shows only what changed. Comments elsewhere aren't kept: a note goes in `note`.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bridge_kit.markdown import FormatError, read_markdown
from bridge_kit.validators import Finding

CATALOG = Path("architecture") / "components.yaml"
PROFILES = Path("architecture") / "components"
FROM_PROFILE = ("summary", "stack", "owns", "consumes", "external")
FROM_PEOPLE = ("repo", "stories", "team", "defines_schemas", "note")
COMPONENT_KEYS = ("order", "summary", "repo", "stack", "owns", "consumes", "external", "defines_schemas", "stories",
                  "team", "profile", "note")
CONTRACT_KEYS = ("kind", "source", "root", "file", "external", "note")
HEADER = ("# The components and their contracts: the map the requirement agents use to work out which components a\n"
          "# requirement touches and in what order their stories go. Built from the components'\n"
          "# profiles by `bridge-kit components build`; architects review its changes.\n")


@dataclass
class Built:
    current: str  # the catalog as it is
    text: str  # as the build would write it
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    @property
    def diff(self) -> str:
        return "".join(difflib.unified_diff(self.current.splitlines(keepends=True), self.text.splitlines(keepends=True),
                                            f"a/{CATALOG.as_posix()}", f"b/{CATALOG.as_posix()}"))


def build(repo: Path) -> Built:
    file = repo / CATALOG
    current = file.read_text(encoding="utf-8") if file.exists() else ""
    findings: list[Finding] = []

    def add(severity: str, check: str, message: str, where: Path = file, line: int | None = None) -> None:
        findings.append(Finding(severity, check, message, where.relative_to(repo).as_posix(), line))

    try:
        data = yaml.safe_load(current) or {}
    except yaml.YAMLError as e:
        add("error", "catalog", f"isn't YAML: {e}")
        return Built(current, current, findings)
    components = {name: dict(entry or {}) for name, entry in (data.get("components") or {}).items()}
    contracts = {name: dict(entry or {}) for name, entry in (data.get("contracts") or {}).items()}

    for path in sorted((repo / PROFILES).glob("*.md")):
        proposed = _proposed(path, lambda *a: add(*a[:3], path, *a[3:]))
        if proposed is None:
            continue
        name, entry, owned = proposed
        target = components.setdefault(name, {})
        target.update({key: entry[key] for key in FROM_PROFILE if key in entry})
        target["profile"] = path.relative_to(repo).as_posix()
        for contract, spec in owned.items():
            contracts.setdefault(contract, {}).update({k: spec[k] for k in ("kind", "file", "root") if k in spec})

    for name, entry in components.items():
        profile = entry.get("profile")
        if profile and not (repo / str(profile)).is_file():
            add("error", "profile", f"{name}'s profile {profile} isn't there: profile it again, or take `profile` out")

    owners: dict[str, list[str]] = {}
    for name, entry in components.items():
        for contract in _names(entry.get("owns")):
            owners.setdefault(contract, []).append(name)
    for contract, names in owners.items():
        if len(names) > 1:
            add("error", "contracts", f"{contract} is owned by {' and '.join(names)}: a contract has one owner")
            continue
        found = contracts.setdefault(contract, {})
        found["source"] = names[0]
        if not found.get("kind"):
            add("warning", "contracts", f"{contract}, owned by {names[0]}, has no kind")
    for contract, found in contracts.items():
        if contract not in owners and found.get("source") in components:
            add("warning", "contracts", f"{contract} names {found['source']} as its source, which doesn't own it")
    for name, entry in components.items():
        for contract in _names(entry.get("consumes")):
            if not (contracts.get(contract) or {}).get("source"):
                add("warning", "contracts", f"{name} consumes {contract}, which no component owns yet")

    order = _order(components, contracts)
    if order is None:
        add("error", "order", "the components consume each other's contracts in a cycle: their order can't be worked "
                              "out")
    else:
        for n, name in enumerate(order, 1):
            components[name]["order"] = n
    return Built(current, _dump(components, contracts, _header(current)), findings)


def _proposed(path: Path, add) -> tuple[str, dict, dict] | None:
    """The profile's component, its proposed entry, and the contracts it owns; None when it can't be merged."""
    text = path.read_text(encoding="utf-8")
    try:
        front = read_markdown(text).front_matter
    except FormatError:
        front = {}
    name = str(front.get("component") or path.stem)
    section = re.search(r"^## Proposed catalog entry[ \t]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    block = section and re.search(r"```ya?ml[ \t]*\n(.*?)```", section.group(1), re.DOTALL)
    line = text[:section.start()].count("\n") + 1 if section else None
    if not block:
        add("error", "profile", "has no Proposed catalog entry with a yaml block: not merged", line)
        return None
    try:
        data = yaml.safe_load(block.group(1))
    except yaml.YAMLError as e:
        add("error", "profile", f"its proposed entry isn't YAML ({str(e).splitlines()[0]}): not merged", line)
        return None
    if not isinstance(data, dict) or not isinstance(data.get(name), dict):
        add("error", "profile", f"its proposed entry has no entry for {name}: not merged", line)
        return None
    if others := sorted(str(k) for k in data if k not in (name, "contracts")):
        add("error", "profile", f"its proposed entry is for {name} only, and names {', '.join(others)} too: not merged",
            line)
        return None
    entry, problems = {}, []
    for key, value in data[name].items():
        if key in FROM_PEOPLE or key in ("order", "profile"):
            add("warning", "profile", f"{key} is for people to set in the catalog, not a profile: left as it is", line)
        elif key not in FROM_PROFILE:
            add("warning", "profile", f"{key} isn't a field of the catalog: left out", line)
        elif key in ("owns", "consumes") and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            problems.append(f"{key} isn't a list of contracts")
        elif key == "external" and not isinstance(value, bool):
            problems.append("external isn't true or false")
        elif key in ("summary", "stack") and not (isinstance(value, str) and value.strip() and "\n" not in value
                                                   and "<" not in value):
            problems.append(f"{key} isn't one line of text")
        else:
            entry[key] = value
    if problems:
        add("error", "profile", f"its proposed entry is wrong: {'; '.join(problems)}: not merged", line)
        return None
    owned = {}
    for contract, spec in (data.get("contracts") or {}).items():
        if contract not in entry.get("owns", []):
            add("warning", "profile", f"its contracts name {contract}, which it doesn't own: left out", line)
        elif isinstance(spec, dict):
            owned[contract] = spec
    return name, entry, owned


def _names(value) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _order(components: dict, contracts: dict) -> list[str] | None:
    """Each contract's owner before its consumers; otherwise as the catalog had them, then by name. None for a
    cycle."""
    after = {name: set() for name in components}  # a component, and the components it comes after
    for name, entry in components.items():
        for contract in _names(entry.get("consumes")):
            owner = (contracts.get(contract) or {}).get("source")
            if owner in components and owner != name:
                after[name].add(owner)
    order, placed = [], set()
    while len(order) < len(components):
        ready = [n for n in components if n not in placed and after[n] <= placed]
        if not ready:
            return None
        first = min(ready, key=lambda n: (components[n].get("order") if isinstance(components[n].get("order"), int)
                                          else 10 ** 6, n))
        order.append(first)
        placed.add(first)
    return order


def _header(current: str) -> str:
    lines = []
    for line in current.splitlines():
        if line.startswith("#") or (not line.strip() and lines):
            lines.append(line)
        else:
            break
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n" if lines else HEADER


def _dump(components: dict, contracts: dict, header: str) -> str:
    def ordered(entry: dict, keys: tuple) -> dict:
        return {**{k: entry[k] for k in keys if k in entry}, **{k: v for k, v in entry.items() if k not in keys}}

    names = sorted(components, key=lambda n: (components[n].get("order", 10 ** 6), n))
    body = {"components": {n: ordered(components[n], COMPONENT_KEYS) for n in names},
            "contracts": {n: ordered(c, CONTRACT_KEYS) for n, c in contracts.items()}}
    text = yaml.safe_dump(body, sort_keys=False, default_flow_style=None, width=1000, allow_unicode=True)
    text = re.sub(r"\n(?=  [^ \n][^\n]*:\n)", "\n\n", text).replace("components:\n\n", "components:\n")
    return header + "\n" + text.replace("\ncontracts:", "\n\ncontracts:")  # a blank line before each component
