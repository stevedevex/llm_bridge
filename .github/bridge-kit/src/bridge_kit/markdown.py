"""Reads the Markdown that bridge-kit's formats are written in: front matter, level-2 sections, paragraphs and pipe tables."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml


class FormatError(Exception):
    """A file doesn't follow the expected Markdown shape."""

    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


@dataclass
class MdTable:
    columns: list[str]
    rows: list[tuple[int, list[str]]]  # (line number, cells)
    line: int


@dataclass
class MdSection:
    heading: str | None  # None for the text before the first level-2 heading
    line: int
    paragraphs: list[tuple[int, str]] = field(default_factory=list)  # (first line, text joined into one line)
    tables: list[MdTable] = field(default_factory=list)


@dataclass
class MdDocument:
    front_matter: dict
    sections: list[MdSection]

    def section(self, heading: str) -> MdSection | None:
        return next((s for s in self.sections if s.heading == heading), None)


def code_spans(text: str) -> list[str]:
    """The contents of every `code span` in the text, in order."""
    return re.findall(r"`([^`]+)`", text)


def split_cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", body)]


def read_markdown(text: str) -> MdDocument:
    lines = text.splitlines()
    front: dict = {}
    start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            raise FormatError("The front matter isn't closed with ---", 1)
        try:
            front = yaml.safe_load("\n".join(lines[1:end])) or {}
        except yaml.YAMLError as e:
            raise FormatError(f"The front matter isn't valid YAML: {e}", 1) from e
        if not isinstance(front, dict):
            raise FormatError("The front matter must be a mapping", 1)
        start = end + 1

    sections = [MdSection(None, start + 1)]
    paragraph: list[str] = []
    paragraph_line = 0

    def flush() -> None:
        nonlocal paragraph
        if paragraph:
            sections[-1].paragraphs.append((paragraph_line, " ".join(paragraph)))
            paragraph = []

    i = start
    while i < len(lines):
        line, number = lines[i], i + 1
        heading = re.match(r"^(#+)\s+(.*)$", line)
        if heading:
            flush()
            if len(heading.group(1)) == 2:
                sections.append(MdSection(heading.group(2).strip(), number))
            i += 1
        elif line.lstrip().startswith("|"):
            flush()
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append((i + 1, lines[i]))
                i += 1
            sections[-1].tables.append(_table(block))
        else:
            if not line.strip():
                flush()
            else:
                if not paragraph:
                    paragraph_line = number
                paragraph.append(line.strip())
            i += 1
    flush()
    return MdDocument(front, sections)


def _table(block: list[tuple[int, str]]) -> MdTable:
    first_line, header = block[0]
    columns = split_cells(header)
    if len(block) < 2 or not all(re.fullmatch(r":?-+:?", cell) for cell in split_cells(block[1][1])):
        raise FormatError("A table needs a header row followed by a separator row", first_line)
    rows = []
    for number, line in block[2:]:
        cells = split_cells(line)
        if len(cells) != len(columns):
            raise FormatError(f"The row has {len(cells)} cells but the header has {len(columns)}", number)
        rows.append((number, cells))
    return MdTable(columns, rows, first_line)
