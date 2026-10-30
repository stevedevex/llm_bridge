"""The BA's rough mapping: a work item's input holding the mapping the BA worked out on their own, which a mapping
request names (`rough_mapping`, and `rough_mapping_table` when it has several tables) and the Mapping Drafter drafts
from.

Its tables are as bridge-kit's document readers write them: an Excel sheet's under `## Sheet: <name>`, a Word
document's, a deck's or a page's after `Table N:`, a CSV's alone. Each has a `Row` column with the source's row numbers
and, for Excel and CSV, each heading's column letter; a table without them (one the BA wrote in Markdown) is numbered as
a spreadsheet would be, its heading row 1.

A spec drafted from it cites the cell each row's decision comes from: "From the BA's rough mapping, `Mapping!C12`"
(a sheet, or `Table 2`, then a cell; a CSV's cell alone). `cited()` finds those, `check()` says whether the cell is
there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bridge_kit.documents.tables import column_letter
from bridge_kit.markdown import read_markdown

CITATION = re.compile(r"From the BA's rough mapping, ((?:`[^`]+`(?:,\s*|\s+and\s+)?)+)")


class RoughMappingError(Exception):
    """The rough mapping, or the table the request names, isn't there or isn't a table."""


@dataclass
class RoughTable:
    name: str  # the sheet's name, `Table N`, or "" for a file's only table
    letters: list[str]  # each column's letter, after the Row column
    rows: dict[str, list[str]] = field(default_factory=dict)  # by the source's row number
    line: int = 0

    @property
    def label(self) -> str:
        return self.name or "its table"


def tables(text: str) -> list[RoughTable]:
    """Every table in the input, named as a request names it."""
    found = []
    for section in read_markdown(text).sections:
        heading = section.heading or ""
        sheet = re.sub(r" \(hidden\)$", "", heading.removeprefix("Sheet: ")) if heading.startswith("Sheet: ") else None
        captions = {line: m.group(1) for line, text in section.paragraphs
                    if (m := re.fullmatch(r"(Table \d+):.*", text))}
        for table in section.tables:
            caption = max((line for line in captions if line < table.line), default=None)
            name = sheet if sheet is not None else captions[caption] if caption is not None else ""
            numbered = table.columns[:1] == ["Row"]
            headings = table.columns[1:] if numbered else table.columns
            letters = [m.group(1) if (m := re.search(r"\(([A-Z]{1,3})(?:, hidden)?\)$", h)) else column_letter(i)
                       for i, h in enumerate(headings)]
            rows = {}
            for n, (_, cells) in enumerate(table.rows, 2):
                number = cells[0].split()[0] if numbered and cells[0] else str(n)
                rows[number] = cells[1:] if numbered else cells
            found.append(RoughTable(name, letters, rows, table.line))
    return found


def find(found: list[RoughTable], name: str | None) -> RoughTable:
    """The table a request names, by a sheet's name in any case or `Table N`; the only one when none is named."""
    if not found:
        raise RoughMappingError("holds no table: a rough mapping is a table, an Excel sheet, a CSV or a table in a "
                                "Word document")
    if not name:
        if len(found) == 1:
            return found[0]
        raise RoughMappingError(f"has {len(found)} tables ({', '.join(t.label for t in found)}): name the one to "
                                "draft from in rough_mapping_table")
    table = next((t for t in found if t.name.casefold() == name.casefold()), None)
    if table is None:
        raise RoughMappingError(f"has no table {name}: its tables are {', '.join(t.label for t in found)}")
    return table


def cited(notes: str) -> list[str]:
    """The cells a row's Notes cite from the rough mapping: `Mapping!C12`, `Table 2!B4`, `C12`."""
    return [ref for m in CITATION.finditer(notes) for ref in re.findall(r"`([^`]+)`", m.group(1))]


def check(found: list[RoughTable], ref: str, named: str | None) -> str | None:
    """Why a cited cell isn't in the rough mapping, or None when it is. A cell without a table's name is in the
    table the request names."""
    table_name, _, cell = ref.rpartition("!")
    cell_match = re.fullmatch(r"([A-Z]{1,3})?(\d+)", cell.strip())
    if cell_match is None:
        return f"{ref} isn't a cell: a sheet or a table, then a column's letter and a row's number (Mapping!C12)"
    try:
        table = find(found, table_name or named)
    except RoughMappingError as e:
        return f"the rough mapping {e}"
    column, row = cell_match.groups()
    if row not in table.rows:
        return f"{table.label} has no row {row}"
    if column and column not in table.letters:
        return f"{table.label} has no column {column}"
    return None
