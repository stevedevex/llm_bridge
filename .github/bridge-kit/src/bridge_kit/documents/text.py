"""Plain text and Markdown as they are; CSV and TSV as a table. UTF-8 first, then Windows-1252, with a warning."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from bridge_kit.documents import Document, Options, personal, tables


def decode(path: Path) -> tuple[str, list[str]]:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig").replace("\r\n", "\n"), []
    except UnicodeDecodeError:
        return (data.decode("cp1252", errors="replace").replace("\r\n", "\n"),
                [f"{path.name} isn't UTF-8: read as Windows-1252, so check its accented letters"])


def read_text(path: Path, options: Options) -> Document:
    text, warnings = decode(path)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headings = [line.lstrip("#").strip() for line in lines if line.startswith("# ")]
    title = (headings or lines or [path.stem])[0][:80]
    if found := personal.warning(path.name, [text]):
        warnings.append(found)
    return Document("text", title, text, warnings)


def read_csv(path: Path, options: Options) -> Document:
    text, warnings = decode(path)
    tab = path.suffix.lower() == ".tsv"
    try:
        delimiter = "\t" if tab else csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    rows = [(n, row) for n, row in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), 1)
            if any(value.strip() for value in row)]
    what = "a TSV file" if tab else "a CSV file"
    if not rows:
        return Document("csv", path.stem, f"# {path.stem}\n\n`{path.name}`: {what} with nothing in it.\n", warnings)
    (first, header), body = rows[0], rows[1:]
    heads = tables.headings(header, tables.width([row for _, row in rows]))
    shown, note = tables.limit(body, options)
    markdown = (f"# {path.stem}\n\n`{path.name}`: {what}, {len(heads)} column(s), {len(body)} row(s) below its "
                f"heading row (row {first}).\n\n" + tables.table(heads, shown) + note)
    for i, head in enumerate(heads):
        if found := personal.warning(f"Column {head}", [row[i] for _, row in shown if i < len(row)]):
            warnings.append(found)
    return Document("csv", path.stem, markdown, warnings)
