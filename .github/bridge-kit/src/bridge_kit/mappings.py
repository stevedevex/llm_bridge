"""Mapping specs, lookups and the assembly spec, as defined in mappings/FORMAT.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from bridge_kit.markdown import FormatError, MdTable, code_spans, read_markdown

NOT_MAPPED_SECTION = "Upstream fields not mapped"
MODEL_CHANGES_SECTION = "Proposed internal model changes"
QUESTIONS_SECTION = "Open questions"
END_SECTIONS = (NOT_MAPPED_SECTION, MODEL_CHANGES_SECTION, QUESTIONS_SECTION)

RULES = ("copy", "constant", "lookup", "format", "combine", "condition", "list", "derive", "not mapped", "tbd")
CATEGORIES = ("REST", "SOAP", "JDBC", "MAP")
STATUSES = ("draft", "approved", "implemented")
HEADER_KEYS = ("upstream", "category", "spec", "operation", "target", "target_schema_version", "status")

REQUIRED_COLUMNS = ("#", "Target field", "Source", "Rule", "Details", "If missing", "Notes")
REVERSE_ENGINEERED_COLUMNS = ("Code", "Confidence")
_COLUMN_KEYS = {
    "#": "number", "target field": "field", "source": "source", "rule": "rule", "details": "details",
    "if missing": "if_missing", "notes": "notes", "code": "code", "confidence": "confidence",
}


@dataclass
class Row:
    number: str
    field: str
    source: str
    rule: str  # lower case; a blank rule is "copy"
    details: str
    if_missing: str
    notes: str
    code: str | None
    confidence: str | None
    line: int

    @property
    def sources(self) -> list[str]:
        """The source paths in the Source cell, without backticks; several are joined by `+`."""
        return [part.strip().strip("`").strip() for part in self.source.split("+") if part.strip().strip("`").strip()]

    @property
    def lookup_name(self) -> str | None:
        spans = code_spans(self.details)
        return spans[0] if self.rule == "lookup" and spans else None

    @property
    def proposed(self) -> bool:
        """Notes mark the row `proposed`: the word, plain or as FORMAT writes it, `proposed`. Any other `code`, such
        as an upstream state named `Proposed`, isn't the marker."""
        if re.search(r"\bproposed\b", re.sub(r"`[^`]*`", "", self.notes), re.IGNORECASE):
            return True
        return any(span.strip() == "proposed" for span in code_spans(self.notes))


@dataclass
class Table:
    path: str
    line: int
    columns: list[str]
    rows: list[Row]
    source_root: str | None = None
    source_root_line: int | None = None
    filter: str | None = None

    @property
    def source_root_path(self) -> str | None:
        """The path in the Source root line: its first code span."""
        spans = code_spans(self.source_root or "")
        return spans[0] if spans else None

    def row(self, field_name: str) -> Row | None:
        return next((r for r in self.rows if r.field == field_name), None)


@dataclass
class MappingSpec:
    file: Path
    header: dict
    tables: list[Table]
    sections: dict[str, tuple[int, str]]  # end section heading -> (line, text)

    @property
    def reverse_engineered(self) -> bool:
        return str(self.header.get("origin", "")).strip() == "reverse-engineered"

    def table(self, path: str) -> Table | None:
        wanted = normalize_path(path)
        return next((t for t in self.tables if normalize_path(t.path) == wanted), None)

    def parent_row(self, table: Table) -> tuple[Table, Row] | None:
        """The row one table up that names this table's field."""
        parent_path, _, last = normalize_path(table.path).rpartition(".")
        parent = self.table(parent_path)
        if parent is None:
            return None
        row = parent.row(last.removesuffix("[]"))
        return (parent, row) if row else None

    def full_path(self, table: Table, source: str) -> str:
        """A source path from the top of the response, as FORMAT defines it: the first table's paths start at its
        Source root (the response itself when the root names no path in `code`), and a nested table's at its parent
        row's source. A `request:` value stays as it is."""
        base = None
        if self.tables and table is not self.tables[0]:
            parent = self.parent_row(table)
            if parent is not None and len(parent[1].sources) == 1:
                base = self.full_path(parent[0], parent[1].sources[0])
        if base is None:
            base = table.source_root_path or ""
        if not base or source.startswith("request:"):
            return source
        return base + ("/" if self.header.get("category") == "SOAP" else ".") + source


@dataclass
class Lookup:
    file: Path
    name: str
    target: str
    entries: dict[str, str]  # source code -> target value
    entry_lines: dict[str, int]
    otherwise: str | None
    otherwise_line: int | None


@dataclass
class Branch:
    number: str
    path: str
    mapping: str
    called: str
    called_with: str
    attaches: str
    if_fails: str
    line: int


@dataclass
class AssemblySpec:
    file: Path
    root: str
    branches: list[Branch] = field(default_factory=list)


def normalize_path(path: str) -> str:
    return re.sub(r"\s+", "", path.strip().strip("`"))


def clean(text: str) -> str:
    """A cell's value without surrounding backticks or spaces."""
    return text.strip().strip("`").strip()


def load_mapping(path: Path) -> MappingSpec:
    doc = read_markdown(path.read_text(encoding="utf-8"))
    tables: list[Table] = []
    sections: dict[str, tuple[int, str]] = {}
    for section in doc.sections:
        if section.heading is None:
            continue
        if section.heading in END_SECTIONS:
            sections[section.heading] = (section.line, " ".join(text for _, text in section.paragraphs))
            continue
        if len(section.tables) > 1:
            raise FormatError(f"Section '{section.heading}' has more than one table", section.tables[1].line)
        table = Table(section.heading, section.line, [], [])
        for line, text in section.paragraphs:
            if text.startswith("**Source root:**"):
                table.source_root, table.source_root_line = text.removeprefix("**Source root:**").strip(), line
            elif text.startswith("**Filter:**"):
                table.filter = text.removeprefix("**Filter:**").strip()
        if section.tables:
            table.columns, table.rows = _rows(section.tables[0])
        tables.append(table)
    return MappingSpec(path, doc.front_matter, tables, sections)


def _rows(md: MdTable) -> tuple[list[str], list[Row]]:
    keys = [_COLUMN_KEYS.get(column.strip().lower()) for column in md.columns]
    rows = []
    for line, cells in md.rows:
        values = {key: cell for key, cell in zip(keys, cells) if key}
        rule = clean(values.get("rule", "")).lower()
        rows.append(Row(
            number=clean(values.get("number", "")),
            field=clean(values.get("field", "")),
            source=values.get("source", "").strip(),
            rule=rule or "copy",
            details=values.get("details", "").strip(),
            if_missing=values.get("if_missing", "").strip(),
            notes=values.get("notes", "").strip(),
            code=values.get("code"),
            confidence=clean(values["confidence"]).lower() if "confidence" in values else None,
            line=line,
        ))
    return md.columns, rows


def load_lookup(path: Path) -> Lookup:
    doc = read_markdown(path.read_text(encoding="utf-8"))
    entries, entry_lines = {}, {}
    otherwise = otherwise_line = None
    for section in doc.sections:
        for md in section.tables:
            columns = [c.strip().lower() for c in md.columns]
            if "source code" not in columns or "target value" not in columns:
                raise FormatError("A lookup table needs 'Source code' and 'Target value' columns", md.line)
            for line, cells in md.rows:
                code = clean(cells[columns.index("source code")])
                if code in entries:
                    raise FormatError(f"Source code {code} appears twice", line)
                entries[code] = clean(cells[columns.index("target value")])
                entry_lines[code] = line
        for line, text in section.paragraphs:
            match = re.match(r"^-?\s*\*\*Otherwise:\*\*\s*(.+)$", text)
            if match:
                otherwise, otherwise_line = clean(match.group(1)), line
    return Lookup(path, str(doc.front_matter.get("name", "")), str(doc.front_matter.get("target", "")),
                  entries, entry_lines, otherwise, otherwise_line)


def load_assembly(path: Path) -> AssemblySpec:
    doc = read_markdown(path.read_text(encoding="utf-8"))
    spec = AssemblySpec(path, str(doc.front_matter.get("root", "")))
    for section in doc.sections:
        for md in section.tables:
            columns = [c.strip().lower() for c in md.columns]
            if "branch" not in columns or "mapping" not in columns:
                continue

            def cell(cells: list[str], name: str) -> str:
                return cells[columns.index(name)].strip() if name in columns else ""

            for line, cells in md.rows:
                spec.branches.append(Branch(
                    number=clean(cell(cells, "#")),
                    path=normalize_path(cell(cells, "branch")),
                    mapping=clean(cell(cells, "mapping")),
                    called=cell(cells, "called"),
                    called_with=cell(cells, "called with"),
                    attaches=cell(cells, "attaches"),
                    if_fails=cell(cells, "if the call fails"),
                    line=line,
                ))
    return spec


def repo_root(mapping_file: Path) -> Path | None:
    """The repo a mapping file belongs to: the parent of its `mappings` folder."""
    for parent in mapping_file.resolve().parents:
        if parent.name == "mappings":
            return parent.parent
    return None
