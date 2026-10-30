"""Tables as Markdown, the same for every kind: a `Row` column with the source's row number, and each heading with
its column letter (`Source field (B)`), so an agent can cite a cell as `Mapping!B12`. A long table shows its first
rows, and says how many it has."""

from __future__ import annotations

from bridge_kit.documents import Options

LONG, SHOWN = 500, 200  # a table of over LONG rows shows its first SHOWN, unless --rows says otherwise


def column_letter(index: int) -> str:
    """0 is A, 25 is Z, 26 is AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def cell(value: object) -> str:
    """A value as a table cell: pipes escaped, line breaks as <br>."""
    text = "" if value is None else str(value)
    return text.strip().replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def headings(row: list, width: int, start: int = 0) -> list[str]:
    """Each heading row cell with its column letter, the first column being `start` (0 is A); an empty one is its
    letter alone."""
    return [f"{cell(row[i]) if i < len(row) else ''} ({column_letter(start + i)})".lstrip() for i in range(width)]


def width(rows: list[list]) -> int:
    """The number of columns, up to the last one with anything in it."""
    return max((i + 1 for row in rows for i, value in enumerate(row) if cell(value)), default=0)


def table(heads: list[str], rows: list[tuple[int | str, list]]) -> str:
    lines = ["| Row | " + " | ".join(heads) + " |", "|---" * (len(heads) + 1) + "|"]
    for number, values in rows:
        values = [cell(v) for v in values[:len(heads)]] + [""] * (len(heads) - len(values))
        lines.append(f"| {number} | " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def limit(rows: list, options: Options) -> tuple[list, str]:
    """The rows to show, and a line saying what was left out (empty when nothing was)."""
    total = len(rows)
    if options.headers_only:
        return [], f"\nThe heading row only (--headers-only): {total} row(s) not shown.\n"
    if options.rows == "all":
        return rows, ""
    most = options.rows if isinstance(options.rows, int) else (SHOWN if total > LONG else total)
    if total <= most:
        return rows, ""
    return rows[:most], f"\nThe first {most} of {total} rows shown: --rows all shows every one.\n"
