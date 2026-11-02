"""What a component's own team has written down for its AI tools, and where BRIDGE reads it.

A component's repo often has an AI layer of its own in `.github/`: instructions, skills, agents and prompts, kept by
its team. Much of it is what BRIDGE would otherwise infer from the code: the domain's words, which upstream fills
which field, where each kind of change goes, how it's built and tested. The catalog points to it, by kind, under each
component's `knowledge:`, a path in the component's checkout or `wiki:<page>`; people set it, and `components build`
never changes it.

- `bridge-kit components scan [<component>]`: each declared checkout's AI layer, every item with the kind its name
  and description suggest, the pointers proposed, and every pointer whose file isn't there. `--write` adds the
  proposed pointers to a component that has none.
- `bridge-kit knowledge show <component> [<kind>]`: the component's pointers, or what one kind's point to.

It only reads the components' repos, and never runs their agents.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from bridge_kit.components import CATALOG, _dump, _header
from bridge_kit.config import Config, ConfigError

KINDS = ("glossary", "lineage", "anatomy", "contracts", "build-and-test", "playbooks", "privacy", "versions", "intake",
         "other")
# The kind an item's name and description suggest, the first that matches; prompts and agents that edit are playbooks
GUESSES = (
    ("intake", r"spec-driven|write-spec|\bticket"),
    ("privacy", r"privacy|redact|sensitive|personal data|\bpii\b"),
    ("glossary", r"glossary|vocabulary|acronym|what .* mean"),
    ("versions", r"version|reference[- ]checkout|resolves"),
    ("build-and-test", r"\btests?\b|testing|\bbuild|codegen|troubleshoot"),
    ("contracts", r"contract|breaking|\bbreaks?\b|compatib|generator"),
    ("lineage", r"lineage|data[- ]model[- ]map|consum|which upstream|fills? which|usage|\bimpact\b|affected"),
    ("anatomy", r"anatomy|structure|layout|pipeline|architecture|where .* goes?|chain"),
)


@dataclass
class Item:
    type: str  # instructions, skill, agent or prompt
    name: str
    description: str
    path: str  # in the checkout
    kind: str
    edits: bool | None = None  # an agent: whether its tools can change files


@dataclass
class Scanned:
    component: str
    checkout: str | None
    items: list[Item] = field(default_factory=list)
    proposed: dict[str, list[str]] = field(default_factory=dict)
    pointers: dict[str, list[str]] = field(default_factory=dict)  # what the catalog has
    broken: list[str] = field(default_factory=list)  # pointers whose file isn't there
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def catalog(repo: Path) -> dict:
    file = repo / CATALOG
    return (yaml.safe_load(file.read_text(encoding="utf-8")) or {}) if file.is_file() else {}


def pointers(entry: dict) -> dict[str, list[str]]:
    """A catalog entry's knowledge, each kind's pointers as a list."""
    found = {}
    for kind, value in (entry.get("knowledge") or {}).items():
        found[str(kind)] = [str(v) for v in value] if isinstance(value, list) else [str(value)]
    return found


def checkout(config: Config, entry: dict) -> Path | None:
    """The component's checkout, when the catalog names its repo and bridge-kit.yaml declares it."""
    try:
        path = config.repo(str(entry["repo"])).path if entry.get("repo") else None
    except ConfigError:
        return None
    return path if path and path.is_dir() else None


def scan(repo: Path, config: Config, only: str | None = None) -> list[Scanned]:
    components = catalog(repo).get("components") or {}
    if only and only not in components:
        raise ConfigError(f"architecture/components.yaml has no component {only}")
    results = []
    for name, entry in components.items():
        if only and name != only:
            continue
        entry = entry or {}
        root = checkout(config, entry)
        found = Scanned(name, str(root) if root else None, pointers=pointers(entry))
        if root is None:
            found.note = "no checkout: its repo isn't named in the catalog or declared in bridge-kit.yaml"
        else:
            found.items = inventory(root)
            for item in found.items:
                if item.kind != "other":
                    found.proposed.setdefault(item.kind, []).append(item.path)
            found.broken = [p for ps in found.pointers.values() for p in ps
                            if not p.startswith("wiki:") and not (root / p).is_file()]
        results.append(found)
    return results


def inventory(root: Path) -> list[Item]:
    """The AI layer in a checkout's `.github/`, each item with the kind its name and description suggest."""
    github, items = root / ".github", []
    if (github / "copilot-instructions.md").is_file():
        items.append(_item(root, "instructions", github / "copilot-instructions.md", "copilot-instructions"))
    for path in sorted((github / "instructions").glob("*.instructions.md")):
        items.append(_item(root, "instructions", path, path.name.removesuffix(".instructions.md")))
    for path in sorted((github / "skills").glob("*/SKILL.md")):
        items.append(_item(root, "skill", path, path.parent.name))
    for path in sorted((github / "agents").glob("*.agent.md")):
        items.append(_item(root, "agent", path, path.name.removesuffix(".agent.md")))
    for path in sorted((github / "prompts").glob("*.prompt.md")):
        items.append(_item(root, "prompt", path, path.name.removesuffix(".prompt.md")))
    return items


def _front_matter(text: str) -> dict:
    """A file's front matter, or nothing: only it is read, so a team's file that's otherwise malformed still counts."""
    match = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(\n|$)", text, re.DOTALL)
    try:
        data = yaml.safe_load(match.group(1)) if match else {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _item(root: Path, type: str, path: Path, name: str) -> Item:
    front = _front_matter(path.read_text(encoding="utf-8", errors="replace"))
    name = str(front.get("name") or name)
    description = " ".join(str(front.get("description") or "").split())
    edits = None
    if type == "agent":
        tools = front.get("tools")
        edits = tools is None or any(re.search(r"edit|write|create", str(t), re.I) for t in tools or [])
    text = f"{name.replace('-', ' ')} {name} {description}".lower()
    kind = next((k for k, pattern in GUESSES if re.search(pattern, text)), None)
    if (type == "prompt" and kind != "intake") or (type == "agent" and edits):
        kind = "playbooks"
    kind = kind or "other"
    return Item(type, name, description, path.relative_to(root).as_posix(), kind, edits)


def write_proposed(repo: Path, results: list[Scanned]) -> list[str]:
    """Adds the proposed pointers to each scanned component the catalog has no knowledge for; returns them."""
    file = repo / CATALOG
    current = file.read_text(encoding="utf-8")
    data = yaml.safe_load(current) or {}
    components = {name: dict(entry or {}) for name, entry in (data.get("components") or {}).items()}
    added = []
    for result in results:
        if result.proposed and not result.pointers and result.component in components:
            components[result.component]["knowledge"] = {
                kind: paths[0] if len(paths) == 1 else paths for kind, paths in result.proposed.items()}
            added.append(result.component)
    if added:
        file.write_text(_dump(components, dict(data.get("contracts") or {}), _header(current)), encoding="utf-8")
    return added


def render(results: list[Scanned]) -> str:
    lines = []
    for result in (r for r in results if r.checkout):
        lines.append(f"{result.component}: {result.checkout}")
        if not result.items:
            lines.append("  No AI layer in its .github/")
        for item in result.items:
            can = "" if item.edits is None else " (edits)" if item.edits else " (read-only)"
            about = item.description if len(item.description) <= 90 else \
                item.description[:90].rsplit(" ", 1)[0].rstrip(",;:") + " …"
            lines.append(f"  {item.kind:14} {item.type} {item.name}{can}: {about or item.path}")
        if result.proposed and not result.pointers:
            lines.append("  Proposed knowledge, for the catalog (components scan --write adds it):")
            lines += [f"    {kind}: {', '.join(paths)}" for kind, paths in result.proposed.items()]
        lines += [f"  The catalog's pointer {p} isn't in the checkout: point it again" for p in result.broken]
        lines.append("")
    if unscanned := [r.component for r in results if not r.checkout]:
        lines.append(f"Not scanned, no checkout (the catalog names no repo, or bridge-kit.yaml doesn't declare it): "
                     f"{', '.join(unscanned)}")
    return "\n".join(lines) + "\n"


def show(repo: Path, config: Config, component: str, kind: str | None = None) -> tuple[str, int]:
    """The component's knowledge: its pointers, or what one kind's point to. The text, and 1 when a pointer is
    broken."""
    entry = (catalog(repo).get("components") or {}).get(component)
    if entry is None:
        raise ConfigError(f"architecture/components.yaml has no component {component}")
    found, root = pointers(entry), checkout(config, entry)
    if not found:
        return (f"{component} has no knowledge in architecture/components.yaml: `bridge-kit components scan "
                f"{component}` proposes it\n"), 0
    if kind is None:
        lines = [f"{component}'s knowledge ({root or 'no checkout'}):"]
        lines += [f"  {k}: {', '.join(ps)}" for k, ps in found.items()]
        return "\n".join(lines) + "\n", 0
    if kind not in found:
        return f"{component} has no {kind} knowledge; it has {', '.join(found)}\n", 0
    parts, code = [], 0
    for pointer in found[kind]:
        if pointer.startswith("wiki:"):
            parts.append(f"## {pointer}\n\nA wiki page: `bridge-kit gitlab wiki get {pointer[5:]}` reads it.\n")
        elif root is None or not (root / pointer).is_file():
            parts.append(f"## {pointer}\n\nNot there: {component}'s checkout isn't declared, or the file moved.\n")
            code = 1
        else:
            parts.append(f"## {component}: {pointer}\n\n{(root / pointer).read_text(encoding='utf-8').strip()}\n")
    return "\n".join(parts), code


def team_glossaries(repo: Path, config: Config | None) -> list[tuple[str, Path]]:
    """Each component's glossary files the catalog points to, in its checkout."""
    if config is None:
        return []
    found = []
    for name, entry in (catalog(repo).get("components") or {}).items():
        root = checkout(config, entry or {})
        for pointer in pointers(entry or {}).get("glossary", []):
            if root and not pointer.startswith("wiki:") and (root / pointer).is_file():
                found.append((name, root / pointer))
    return found
