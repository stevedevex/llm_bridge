"""Test cases, as defined in templates/test-case.md (`test-case@1`): one read from its file, its sections and their
tables, the data it names in braces (`{entity}`), and the stories and criteria it verifies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from bridge_kit.markdown import FormatError, MdTable, read_markdown

# The body's sections, in order
SECTIONS = ("Objective", "Preconditions", "Test data", "Steps", "Checks along the data path", "Pass criteria",
            "Cleanup", "Automation notes", "Open questions")
OPTIONAL_SECTIONS = ("Checks along the data path", "Automation notes")
HEADER_SCHEMA = Path("templates") / "test-case.schema.json"
DATA_NAME = re.compile(r"\{([a-z][a-z0-9-]*)\}")
FILE_NAME = re.compile(r"tc-(\d{2,})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")


@dataclass
class Section:
    heading: str
    line: int
    lines: list[tuple[int, str]] = field(default_factory=list)
    tables: list[MdTable] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line for _, line in self.lines).strip()


@dataclass
class Verified:
    story: str  # its path in the BA repo, without the commit it may be pinned to
    criteria: list[str]  # AC-<n>


@dataclass
class TestCase:
    __test__ = False  # not a pytest class

    file: Path
    header: dict
    sections: list[Section]
    error: str | None = None  # why the file couldn't be read as a test case

    @property
    def number(self) -> int | None:
        found = re.fullmatch(r"TC-(\d+)", str(self.header.get("case") or ""))
        return int(found.group(1)) if found else None

    @property
    def label(self) -> str:
        return str(self.header.get("case") or self.file.name)

    @property
    def status(self) -> str:
        return str(self.header.get("status") or "")

    @property
    def verifies(self) -> list[Verified]:
        return [Verified(str(v.get("story") or "").split("@", 1)[0], [str(c) for c in v.get("criteria") or []])
                for v in self.header.get("verifies") or [] if isinstance(v, dict)]

    def section(self, heading: str) -> Section | None:
        return next((s for s in self.sections if s.heading == heading), None)

    def table(self, heading: str) -> MdTable | None:
        section = self.section(heading)
        return section.tables[0] if section and section.tables else None

    @property
    def body(self) -> str:
        return "\n".join(f"## {s.heading}\n{s.text}" for s in self.sections)

    @property
    def open_questions(self) -> str:
        """The Open questions section's text; empty when it says "None"."""
        section = self.section("Open questions")
        text = section.text if section else ""
        return "" if text.rstrip(".").strip().lower() in ("", "none") else text


def load_test_case(path: Path) -> TestCase:
    text = path.read_text(encoding="utf-8")
    try:
        document = read_markdown(text)
    except FormatError as e:
        return TestCase(path, {}, [], f"The file can't be read: {e}")
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        start = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), len(lines) - 1) + 1
    sections: list[Section] = []
    fenced = False
    for index in range(start, len(lines)):
        line, number = lines[index], index + 1
        if line.strip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            heading = line[3:].strip()
            parsed = document.section(heading)
            sections.append(Section(heading, number, tables=list(parsed.tables) if parsed else []))
            continue
        if sections:
            sections[-1].lines.append((number, line))
    return TestCase(path, document.front_matter, sections)


def case_files(paths: list[Path]) -> list[Path]:
    """The test case files among these paths: files as given, and every .md file directly in a folder."""
    files = []
    for path in paths:
        files += sorted(path.glob("*.md")) if path.is_dir() else [path]
    return files


def cell_name(cell: str) -> str | None:
    """The data name a Test data row defines: `{entity}` is entity."""
    found = re.fullmatch(r"`?\{([a-z][a-z0-9-]*)\}`?", cell.strip())
    return found.group(1) if found else None
