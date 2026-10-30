"""Excel workbooks (`.xlsx`, `.xlsm`), on openpyxl. Rough mappings are mostly in Excel, so the Markdown keeps what a BA
means by a sheet's look as well as its values:

- each sheet under `## Sheet: <name>`, hidden ones marked; a chart sheet named, not read;
- its heading row: the first of its first 20 rows filled at least half as much as the fullest of them, so a title
  above the table isn't taken for it; the rows above it listed;
- a table of the rows below: each row's number, each heading with its column letter, hidden rows and columns kept
  and marked;
- values as Excel last saved them (a formula's result, or its formula when none was saved), dates as ISO dates,
  percentages as percentages, a merged cell's value in each cell it covers, struck-through text as `~~text~~`;
- under the table: its comments, its formulas (a column of the same formula as one line), and its coloured cells
  and text as ranges, since BAs colour rows to mean something.
"""

from __future__ import annotations

import re
import warnings
from collections import defaultdict
from datetime import date, datetime, time
from itertools import groupby
from pathlib import Path

from bridge_kit.documents import Document, DocumentError, Options, personal, tables

LISTED = 50  # at most this many comments, formulas or coloured ranges under a table
COLOURS = {
    "FFFF00": "yellow", "FFFF99": "light yellow", "FFEB9C": "light yellow", "FFF2CC": "light yellow",
    "FF0000": "red", "C00000": "dark red", "FFC7CE": "light red", "FFC000": "orange", "F4B084": "light orange",
    "00FF00": "bright green", "00B050": "green", "92D050": "light green", "C6EFCE": "light green",
    "E2EFDA": "light green", "00B0F0": "light blue", "BDD7EE": "light blue", "DDEBF7": "light blue",
    "0070C0": "blue", "0000FF": "blue", "002060": "dark blue", "7030A0": "purple", "D9D9D9": "grey",
    "BFBFBF": "grey", "A6A6A6": "grey", "808080": "grey",
}
THREADED = "[Threaded comment]"  # the note Excel keeps beside a threaded comment, for older versions
REF = re.compile(r"(?<![A-Za-z_$])(\$?[A-Z]{1,3})(\$?)(\d+)(?![\d(])")


def read_excel(path: Path, options: Options) -> Document:
    import openpyxl
    from openpyxl.chartsheet import Chartsheet

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # openpyxl warns about the extensions it drops (data validation, slicers)
        try:
            values = openpyxl.load_workbook(path, data_only=True)
            formulas = openpyxl.load_workbook(path, data_only=False)
        except Exception as e:  # a broken workbook raises any of a dozen kinds
            raise DocumentError(f"{path.name} can't be read as a workbook ({type(e).__name__}): open it in Excel "
                                "and save it again") from None
    names = values.sheetnames
    chosen = names
    if options.sheets:
        by_name = {name.casefold(): name for name in names}
        missing = [sheet for sheet in options.sheets if sheet.casefold() not in by_name]
        if missing:
            raise DocumentError(f"{path.name} has no sheet {', '.join(missing)}: its sheets are {', '.join(names)}")
        chosen = [by_name[sheet.casefold()] for sheet in options.sheets]
    listing = [f"{name} (a chart, not read)" if isinstance(values[name], Chartsheet) else
               f"{name} (hidden)" if values[name].sheet_state != "visible" else name for name in names]
    sections, found = [], []
    for name in chosen:
        if isinstance(values[name], Chartsheet):
            sections.append(f"## Sheet: {name}\n\nA chart sheet, not read.\n")
            continue
        markdown, sheet_warnings = _sheet(values[name], formulas[name], options)
        sections.append(markdown)
        found += sheet_warnings
    title = (values.properties.title or "").strip() or path.stem
    head = f"# {title}\n\n`{path.name}`: an Excel workbook, {len(names)} sheet(s): {', '.join(listing)}."
    if options.sheets:
        head += f" Read here: {', '.join(chosen)}."
    return Document("xlsx", title, head + "\n\n" + "\n".join(sections), found)


def _sheet(sheet, formula_sheet, options: Options) -> tuple[str, list[str]]:
    name, letter = sheet.title, tables.column_letter
    mark = " (hidden)" if sheet.sheet_state != "visible" else ""
    found = [f"Sheet {name} is hidden: read too, and marked"] if mark else []
    cells, struck, fills, inks, comments = {}, set(), {}, {}, {}
    formulas = {(c.row, c.column): f for row in formula_sheet.iter_rows() for c in row if (f := _formula(c.value))}
    unsaved = 0
    for row in sheet.iter_rows():
        for c in row:
            where = (c.row, c.column)
            text = _value(c)
            if not text and where in formulas:
                text, unsaved = formulas[where], unsaved + 1
            if text:
                cells[where] = text
                if c.font is not None and c.font.strike:
                    struck.add(where)
                    cells[where] = f"~~{text}~~"
                if c.font is not None and (ink := _colour(c.font.color, text=True)):
                    inks[where] = ink
            if c.fill is not None and c.fill.fill_type == "solid" and (fill := _colour(c.fill.fgColor)):
                fills[where] = fill
            if getattr(c, "comment", None) is not None:
                comments[where] = c.comment
    for merged in sheet.merged_cells.ranges:
        if anchor := cells.get((merged.min_row, merged.min_col)):
            for r in range(merged.min_row, merged.max_row + 1):
                for col in range(merged.min_col, merged.max_col + 1):
                    cells[(r, col)] = anchor
    if not cells:
        return f"## Sheet: {name}{mark}\n\nEmpty.\n", found

    rows = sorted({r for r, _ in cells})
    first, last = min(col for _, col in cells), max(col for _, col in cells)
    columns = range(first, last + 1)
    filled = {r: sum(bool(cells.get((r, col))) for col in columns) for r in rows[:20]}
    fullest = max(filled.values())
    need = 1 if fullest < 2 else max(2, -(-fullest // 2))
    heading = next(r for r in rows[:20] if filled[r] >= need)
    above = [r for r in rows if r < heading]
    body = [r for r in rows if r > heading]

    hidden_rows = {r for r, d in sheet.row_dimensions.items() if d.hidden}
    hidden_columns = set()
    for key, d in sheet.column_dimensions.items():
        if d.hidden:
            from openpyxl.utils import column_index_from_string

            start = d.min or column_index_from_string(key)
            hidden_columns.update(range(start, (d.max or start) + 1))
    heads = tables.headings([cells.get((heading, col), "") for col in columns], len(columns), first - 1)
    heads = [h[:-1] + ", hidden)" if col in hidden_columns else h for h, col in zip(heads, columns)]
    shown, note = tables.limit([(f"{r} (hidden)" if r in hidden_rows else r, [cells.get((r, col), "")
                                                                               for col in columns]) for r in body],
                               options)
    shown_rows = {int(str(label).split()[0]) for label, _ in shown}
    listed_rows = shown_rows | set(above) | {heading}

    lines = [f"## Sheet: {name}{mark}", "",
             f"{letter(first - 1)}{rows[0]}:{letter(last - 1)}{rows[-1]}: {len(body)} row(s) below its heading row "
             f"(row {heading}).", ""]
    if above:
        lines += ["Above the table:", ""] + [
            f"- Row {r}: " + " | ".join(cells[(r, col)] for col in columns if cells.get((r, col))) for r in above] + [""]
    lines.append(tables.table(heads, shown).rstrip("\n"))
    if note:
        lines.append(note.rstrip("\n"))
    notes = [f"- {letter(col - 1)}{r} ({_author(comment)}): {_comment(comment)}"
             for (r, col), comment in sorted(comments.items()) if r in listed_rows]
    for heading_text, listed in (("Comments", notes),
                                 ("Formulas", _formula_lines({k: v for k, v in formulas.items() if k[0] in listed_rows})),
                                 ("Coloured cells", _ranges({k: v for k, v in fills.items() if k[0] in shown_rows})),
                                 ("Coloured text", _ranges({k: v for k, v in inks.items() if k[0] in shown_rows}))):
        if listed:
            lines += ["", f"### {heading_text}", ""] + listed[:LISTED]
            if len(listed) > LISTED:
                lines.append(f"- and {len(listed) - LISTED} more")

    hidden = (len([r for r in rows if r in hidden_rows]), len([col for col in columns if col in hidden_columns]))
    if any(hidden):
        found.append(f"Sheet {name} has {hidden[0]} hidden row(s) and {hidden[1]} hidden column(s): read too, and "
                     "marked (hidden)")
    if any(k[0] in shown_rows for k in [*fills, *inks]):
        found.append(f"Sheet {name} has coloured cells or text, listed under its table: ask the BA what the colours "
                     "mean, unless the sheet has a legend")
    if any(r in shown_rows for r, _ in struck):
        found.append(f"Sheet {name} has struck-through text, shown as ~~text~~: often a row or a rule that was "
                     "dropped")
    if unsaved:
        found.append(f"Sheet {name}: {unsaved} formula(s) have no value saved, as when the file wasn't last saved by "
                     "Excel: their formulas are shown in their cells")
    for i, head in enumerate(heads):
        if warning := personal.warning(f"Sheet {name}, column {head}", [values[i] for _, values in shown]):
            found.append(warning)
    return "\n".join(lines) + "\n", found


def _value(cell) -> str:
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        if value.time() == time():
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="minutes" if value.second == 0 else "seconds")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (int, float)):
        if "%" in (cell.number_format or ""):
            return f"{value * 100:.10g}%"
        return f"{value:.15g}" if isinstance(value, float) else str(value)  # Excel keeps 15 digits
    return str(value).strip()


def _formula(value) -> str | None:
    if isinstance(value, str):
        return value if value.startswith("=") else None
    text = getattr(value, "text", None)  # an array formula
    if isinstance(text, str) and text:
        return text if text.startswith("=") else f"={text}"
    return None


def _shape(formula: str, row: int) -> str:
    """The formula with each relative row number as an offset from its own row, so a column of the same formula
    has one shape."""
    return REF.sub(lambda m: m.group(0) if m.group(2) else f"{m.group(1)}[{int(m.group(3)) - row}]", formula)


def _formula_lines(formulas: dict[tuple[int, int], str]) -> list[str]:
    lines = []
    for col, group in groupby(sorted(((c, r, f) for (r, c), f in formulas.items())), key=lambda x: x[0]):
        runs = []
        for _, r, f in group:
            shape = _shape(f, r)
            if runs and runs[-1][2] == shape:
                runs[-1][1] = r
            else:
                runs.append([r, r, shape, f])
        where = tables.column_letter(col - 1)
        for first, last, _, f in runs:
            lines.append((first, col, f"- {where}{first}: {f}" if first == last else
                          f"- {where}{first}:{where}{last}: {f}, and alike down to row {last}"))
    return [line for *_, line in sorted(lines)]


def _ranges(colours: dict[tuple[int, int], str]) -> list[str]:
    """Cells of one colour as ranges: each row's runs of adjacent cells, then the same run over adjacent rows."""
    runs = defaultdict(list)
    by_row = defaultdict(list)
    for (r, col), colour in colours.items():
        by_row[r].append((col, colour))
    for r, found in sorted(by_row.items()):
        found.sort()
        start, end, colour = found[0][0], found[0][0], found[0][1]
        for col, other in found[1:] + [(None, None)]:
            if col is not None and col == end + 1 and other == colour:
                end = col
                continue
            runs[(start, end, colour)].append(r)
            if col is not None:
                start, end, colour = col, col, other
    lines = []
    letter = tables.column_letter
    for (start, end, colour), rows in runs.items():
        top = bottom = rows[0]
        for r in rows[1:] + [None]:
            if r is not None and r == bottom + 1:
                bottom = r
                continue
            where = f"{letter(start - 1)}{top}"
            if (start, top) != (end, bottom):
                where += f":{letter(end - 1)}{bottom}"
            lines.append(((top, start), f"- {where}: {colour}"))
            if r is not None:
                top = bottom = r
    return [line for _, line in sorted(lines)]


def _colour(color, text: bool = False) -> str | None:
    """A cell's fill or font colour, by name where it's a common one; None for none, white fill, black text."""
    kind = getattr(color, "type", None)
    if kind == "theme":
        if color.theme == (1 if text else 0):  # the theme's text and background colours: black and white by default
            return None
        return f"theme colour {color.theme}" + (", tinted" if color.tint else "")
    if kind == "indexed":
        from openpyxl.styles.colors import COLOR_INDEX

        if color.indexed >= 64:  # the system's foreground and background
            return None
        rgb = COLOR_INDEX[color.indexed][-6:]
    elif kind == "rgb" and isinstance(color.rgb, str) and re.fullmatch(r"[0-9A-Fa-f]{6,8}", color.rgb):
        rgb = color.rgb[-6:]
    else:
        return None
    rgb = rgb.upper()
    if rgb == ("000000" if text else "FFFFFF"):
        return None
    return f"{COLOURS[rgb]} (#{rgb})" if rgb in COLOURS else f"#{rgb}"


def _author(comment) -> str:
    author = (comment.author or "").strip()
    return "a threaded comment" if author.startswith("tc=") else author or "no author"


def _comment(comment) -> str:
    text = comment.text or ""
    if text.startswith(THREADED):
        text = text.split("Comment:", 1)[-1]
    return " ".join(text.split())
