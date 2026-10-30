"""User stories, as defined in templates/story.md, and the component catalog they're written against
(architecture/components.yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bridge_kit.markdown import FormatError, read_markdown
from bridge_kit.schema import problems

# The body's sections, in order; the component's own is headed "Component details: <component>"
SECTIONS = ("Story", "Context", "Scope", "Contracts and data", "Acceptance criteria", "Component details",
            "Dependencies", "Non-functional", "Open questions")
OPTIONAL_SECTIONS = ("Non-functional",)
CATALOG = Path("architecture") / "components.yaml"
HEADER_SCHEMA = Path("templates") / "story.schema.json"


class CatalogError(Exception):
    """The component catalog can't be read."""


@dataclass
class Catalog:
    components: dict[str, dict]
    contracts: dict[str, dict]

    def order(self, component: str) -> int | None:
        return (self.components.get(component) or {}).get("order")

    def owns(self, component: str) -> list[str]:
        return list((self.components.get(component) or {}).get("owns") or [])

    def consumes(self, component: str) -> list[str]:
        return list((self.components.get(component) or {}).get("consumes") or [])

    def labels(self, component: str) -> list[str]:
        return list(((self.components.get(component) or {}).get("stories") or {}).get("labels") or [])

    def owner(self, contract: str) -> str | None:
        return (self.contracts.get(contract) or {}).get("source")

    def is_schema(self, contract: str) -> bool:
        return (self.contracts.get(contract) or {}).get("kind") == "json-schema"

    def blocked_by(self, component: str, changed: set[str]) -> set[str]:
        """The components a story waits for: the owners of the changed contracts it consumes."""
        return {self.owner(c) for c in self.consumes(component) if c in changed} - {component, None}


def load_catalog(repo: Path) -> Catalog:
    file = repo / CATALOG
    if not file.exists():
        raise CatalogError(f"No component catalog at {CATALOG}")
    data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    return Catalog(data.get("components") or {}, data.get("contracts") or {})


@dataclass
class Criterion:
    number: int
    title: str
    line: int
    steps: list[str] = field(default_factory=list)  # the gherkin block's lines


@dataclass
class Section:
    heading: str
    line: int
    lines: list[tuple[int, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line for _, line in self.lines).strip()

    @property
    def name(self) -> str:
        """The heading without what follows a colon: "Component details: ui-react" is "Component details"."""
        return self.heading.split(":", 1)[0].strip()


@dataclass
class Story:
    file: Path
    header: dict
    sections: list[Section]
    criteria: list[Criterion]
    error: str | None = None  # why the file couldn't be read as a story

    @property
    def component(self) -> str:
        return str(self.header.get("component") or "")

    @property
    def order(self) -> int | None:
        order = self.header.get("order")
        return order if isinstance(order, int) else None

    @property
    def ref(self) -> str:
        return f"S{self.order}" if self.order is not None else ""

    @property
    def blocked_by(self) -> list[str]:
        return [str(b) for b in self.header.get("blocked_by") or []]

    @property
    def contracts(self) -> dict[str, str]:
        return {str(c.get("contract")): str(c.get("change")) for c in self.header.get("contracts") or []
                if isinstance(c, dict)}

    @property
    def implements(self) -> list[str]:
        """The package files, without the commit a path may be pinned to."""
        return [str(p).split("@", 1)[0] for p in self.header.get("implements") or []]

    def section(self, name: str) -> Section | None:
        return next((s for s in self.sections if s.name == name), None)

    @property
    def body(self) -> str:
        return "\n".join(f"## {s.heading}\n{s.text}" for s in self.sections)

    @property
    def open_questions(self) -> str:
        """The Open questions section's text; empty when it says "None"."""
        section = self.section("Open questions")
        text = section.text if section else ""
        return "" if text.rstrip(".").strip().lower() in ("", "none") else text


def load_story(path: Path) -> Story:
    text = path.read_text(encoding="utf-8")
    try:
        header = read_markdown(text).front_matter
    except FormatError as e:
        return Story(path, {}, [], [], f"The header can't be read: {e}")
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        start = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), len(lines) - 1) + 1
    sections: list[Section] = []
    criteria: list[Criterion] = []
    fenced = False
    for index in range(start, len(lines)):
        line, number = lines[index], index + 1
        if line.strip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            sections.append(Section(line[3:].strip(), number))
            continue
        elif not fenced and sections and sections[-1].name == "Acceptance criteria":
            criterion = re.match(r"^###\s+AC-(\d+):\s*(.*)$", line)
            if criterion:
                criteria.append(Criterion(int(criterion.group(1)), criterion.group(2).strip(), number))
        elif fenced and criteria and sections and sections[-1].name == "Acceptance criteria":
            criteria[-1].steps.append(line.strip())
        if sections:
            sections[-1].lines.append((number, line))
    return Story(path, header, sections, criteria)


def story_files(paths: list[Path]) -> list[Path]:
    """The story files among these paths: files as given, and every .md file directly in a folder."""
    files = []
    for path in paths:
        files += sorted(path.glob("*.md")) if path.is_dir() else [path]
    return files


def check_header(header: dict, schema: dict) -> list[str]:
    """The header against templates/story.schema.json."""
    return problems(header, schema, unknown="isn't a header field")
