"""HTML as Markdown, on Python's own parser: a saved page (a wiki's, or an email Outlook saved as HTML), and an email's
HTML body (`mail.py`).

- Headings (`h1` is `##`, the page's title being `#`), paragraphs, line breaks, lists at their levels (an ordered
  one's items numbered), quotes as `>`, preformatted text in a code block, a rule as `---`.
- Links as Markdown links; struck-through text as `~~text~~`.
- A table of data as `Table N:` with its row numbers, cells spanning rows and columns spread. A table used for
  layout, as emails and older pages use them (a cell holding paragraphs, lists or another table; a single column),
  is read as the blocks in its cells, in order.
- Images: kept as the document's images where the file can be had (a data URL; a file beside a saved page), marked
  `[Image N: <alt text>]`; another with alt text as `[Image: <alt text>]`; one without, left out.
- Scripts, styles and hidden elements left out.
"""

from __future__ import annotations

import base64
import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

from bridge_kit.documents import Document, Options, join_blocks, personal, tables

SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object", "select", "button", "canvas"}
BLOCKS = {"p", "div", "section", "article", "header", "footer", "main", "aside", "nav", "figure", "figcaption",
          "address", "center", "form", "fieldset", "dl", "dt", "dd", "body", "html", "caption", "details", "summary"}
VOID = {"br", "hr", "img", "meta", "link", "input", "col", "area", "base", "wbr", "source", "embed", "param", "track"}
IMAGE_TYPES = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "gif": ".gif", "webp": ".webp"}
LARGEST = 20 * 1024 * 1024  # an image file beside a page, read only up to this size


class Images:
    """The images a document keeps, each once, by the name the Markdown gives it."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.lines: list[str] = []
        self.numbers: dict[str, int] = {}

    def add(self, data: bytes, suffix: str, alt: str) -> str:
        key = hashlib.sha256(data).hexdigest()
        if key not in self.numbers:
            n = self.numbers[key] = len(self.numbers) + 1
            name = f"image-{n}{suffix}"
            self.files[name] = data
            self.lines.append(f"- Image {n}: `{name}`" + (f": {alt}" if alt else ""))
        return f"[Image {self.numbers[key]}" + (f": {alt}" if alt else "") + "]"


def read_html(path: Path, options: Options) -> Document:
    data = path.read_bytes()
    text, warnings = decode(data, path.name)
    images = Images()
    base = path.parent.resolve()

    def image(src: str, alt: str) -> str | None:
        if found := data_url(src):
            return images.add(*found, alt)
        if src and not re.match(r"[a-z][a-z0-9+.-]*:|//", src, re.IGNORECASE):  # a file beside the page
            file = (base / unquote(src.split("#")[0].split("?")[0])).resolve()
            suffix = file.suffix.lower().replace(".jpeg", ".jpg")
            if (file.is_relative_to(base) and file.is_file() and suffix in IMAGE_TYPES.values()
                    and file.stat().st_size <= LARGEST):
                return images.add(file.read_bytes(), suffix, alt)
        return f"[Image: {alt}]" if alt else None

    body, title, found = to_markdown(text, options, image)
    title = title or next((line.lstrip("#").strip() for line in body.splitlines() if line.startswith("#")), "") \
        or path.stem
    lines = [f"# {title}", "", f"`{path.name}`: an HTML page" + (f", with {len(images.files)} image(s)"
                                                                 if images.files else "") + ".", "", body]
    if images.lines:
        lines += ["", "## Images", ""] + images.lines
    if images.files:
        found.append(f"{path.name} has {len(images.files)} image(s), which bridge-kit can't read: each is marked "
                     "[Image N]; bridge-kit inputs add keeps them, for an agent to describe any that matters")
    return Document("html", title, "\n".join(lines).rstrip() + "\n", warnings + found, images.files)


def decode(data: bytes, name: str) -> tuple[str, list[str]]:
    """The page's text, by the charset it declares, else UTF-8, else Windows-1252 with a warning."""
    declared = re.search(rb"""charset\s*=\s*["']?([\w.:-]+)""", data[:4096], re.IGNORECASE)
    for charset in ([declared.group(1).decode("ascii", "replace")] if declared else []) + ["utf-8"]:
        try:
            return data.decode(charset).lstrip("﻿"), []
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("cp1252", errors="replace"), [f"{name} isn't UTF-8: read as Windows-1252, so check its "
                                                     "accented letters"]


def data_url(src: str) -> tuple[bytes, str] | None:
    """A data URL's image, and its file's suffix."""
    found = re.match(r"data:image/([a-z]+);base64,(.*)", src, re.IGNORECASE | re.DOTALL)
    if not found or found.group(1).lower() not in IMAGE_TYPES:
        return None
    try:
        return base64.b64decode(found.group(2), validate=False), IMAGE_TYPES[found.group(1).lower()]
    except ValueError:
        return None


def to_markdown(html: str, options: Options,
                image: Callable[[str, str], str | None] | None = None) -> tuple[str, str, list[str]]:
    """The HTML's Markdown, its title, and its warnings: personal data in its text, and per column of its tables."""
    writer = _Writer(options, image or (lambda src, alt: f"[Image: {alt}]" if alt else None))
    writer.feed(html)
    writer.close()
    writer.end()
    blocks = writer.outs[0].blocks
    texts = [block for block in blocks if not block.startswith("Table ")]  # tables are checked by column
    if warning := personal.warning("Its text", texts):
        writer.warnings.insert(0, warning)
    return join_blocks(blocks), " ".join(writer.title.split()), writer.warnings


class _Out:
    """What a part of the page has written: its blocks, and the line being written."""

    def __init__(self, spans: tuple[int, int] = (1, 1)):
        self.blocks: list[str] = []
        self.line: list[str] = []
        self.spans = spans  # a table cell's columns and rows


class _Writer(HTMLParser):
    def __init__(self, options: Options, image: Callable[[str, str], str | None]):
        super().__init__(convert_charrefs=True)
        self.options, self.image = options, image
        self.outs = [_Out()]
        self.skipping: list | None = None  # [tag, depth] while inside one left out
        self.title, self.in_title = "", False
        self.heading = 0
        self.lists: list[list] = []  # [kind, count]
        self.item: str | None = None  # the open list item's prefix
        self.quote = 0
        self.pre: list[str] | None = None
        self.marks: list[list] = []  # [tag, where in the line, href]
        self.tables: list[dict] = []
        self.count = 0
        self.warnings: list[str] = []

    @property
    def out(self) -> _Out:
        return self.outs[-1]

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs = {k: v or "" for k, v in attrs}
        if self.skipping:
            self.skipping[1] += tag == self.skipping[0]
            return
        if tag == "title":
            self.in_title = True
        elif tag in SKIP or "hidden" in attrs or re.search(r"display\s*:\s*none|mso-hide\s*:\s*all",
                                                          attrs.get("style", ""), re.IGNORECASE):
            if tag not in VOID:
                self.skipping = [tag, 1]
        elif re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.heading = int(tag[1])
        elif tag in BLOCKS:
            self.flush()
        elif tag == "br":
            self.out.line.append("\n")
        elif tag == "hr":
            self.flush()
            self.out.blocks.append(self.quoted("---"))
        elif tag in ("ul", "ol"):
            self.flush()
            start = attrs.get("start", "1")
            self.lists.append([tag, int(start) - 1 if start.isdigit() else 0])
        elif tag == "li":
            self.flush()
            if self.lists:
                self.lists[-1][1] += 1
                kind, n = self.lists[-1]
                self.item = "  " * (len(self.lists) - 1) + "- " + (f"{n}. " if kind == "ol" else "")
            else:
                self.item = "- "
        elif tag == "blockquote":
            self.flush()
            self.quote += 1
        elif tag == "pre":
            self.flush()
            self.pre = []
        elif tag == "a":
            self.marks.append(["a", len(self.out.line), attrs.get("href", "")])
        elif tag in ("s", "strike", "del"):
            self.marks.append(["s", len(self.out.line), ""])
        elif tag == "img":
            if marker := self.image(attrs.get("src", ""), " ".join(attrs.get("alt", "").split())):
                self.out.line.append(f" {marker} ")
        elif tag == "table":
            self.flush()
            if self.tables:
                self.tables[-1]["nested"] = True
            self.tables.append({"rows": [], "nested": False, "cell": False, "depth": len(self.outs)})
        elif tag == "tr" and self.tables:
            self.close_cell()
            self.tables[-1]["rows"].append([])
        elif tag in ("td", "th") and self.tables:
            self.close_cell()
            table = self.tables[-1]
            if not table["rows"]:
                table["rows"].append([])
            self.flush()
            self.outs.append(_Out((_span(attrs.get("colspan")), _span(attrs.get("rowspan")))))
            table["cell"] = True

    def handle_endtag(self, tag: str) -> None:
        if self.skipping:
            self.skipping[1] -= tag == self.skipping[0]
            if not self.skipping[1]:
                self.skipping = None
            return
        if tag == "title":
            self.in_title = False
        elif re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.heading = 0
        elif tag in BLOCKS or tag == "li":
            self.flush()
        elif tag in ("ul", "ol"):
            self.flush()
            if self.lists:
                self.lists.pop()
        elif tag == "blockquote":
            self.flush()
            self.quote = max(0, self.quote - 1)
        elif tag == "pre" and self.pre is not None:
            text = "".join(self.pre).strip("\n")
            self.pre = None
            if text.strip():
                self.out.blocks.append(self.quoted(f"```\n{text}\n```"))
        elif tag in ("a", "s", "strike", "del"):
            kind = "a" if tag == "a" else "s"
            mark = next((m for m in reversed(self.marks) if m[0] == kind), None)
            if mark is None:
                return
            self.marks.remove(mark)
            start, href = min(mark[1], len(self.out.line)), mark[2]
            text = " ".join("".join(self.out.line[start:]).split())
            if not text:
                return
            if kind == "s":
                self.out.line[start:] = [f"~~{text}~~"]
            elif re.match(r"(https?|mailto):", href, re.IGNORECASE) and text != href.removeprefix("mailto:"):
                self.out.line[start:] = [f"[{text}]({href})"]
        elif tag in ("td", "th"):
            self.close_cell()
        elif tag == "table" and self.tables:
            self.close_cell()
            self.flush()
            self.write_table(self.tables.pop())

    def handle_data(self, data: str) -> None:
        if self.skipping:
            return
        if self.in_title:
            self.title += data
        elif self.pre is not None:
            self.pre.append(data)
        else:
            self.out.line.append(re.sub(r"\s+", " ", data))

    def end(self) -> None:
        while self.tables:
            self.close_cell()
            self.write_table(self.tables.pop())
        self.flush()

    def close_cell(self) -> None:
        if self.tables and self.tables[-1]["cell"] and len(self.outs) > self.tables[-1]["depth"]:
            self.flush()
            self.tables[-1]["rows"][-1].append(self.outs.pop())
            self.tables[-1]["cell"] = False

    def flush(self) -> None:
        out = self.out
        lines = [" ".join(line.split()) for line in "".join(out.line).replace("~~~~", "").split("\n")]
        lines = [line for line in lines if line]
        out.line = []
        for mark in self.marks:
            mark[1] = 0
        if not lines:
            return
        if self.heading:
            block = "#" * min(self.heading + 1, 6) + " " + " ".join(lines)
        elif self.item is not None:
            indent = " " * len(self.item)
            block = self.item + f"\n{indent}".join(lines)
            self.item = None
        else:
            block = "\n".join(lines)
        out.blocks.append(self.quoted(block))

    def quoted(self, block: str) -> str:
        return "\n".join("> " * self.quote + line for line in block.split("\n")) if self.quote else block

    def write_table(self, table: dict) -> None:
        rows = table["rows"]
        grid = _grid(rows)
        width = max((len(row) for row in grid), default=0)
        cells = [cell for row in grid for cell in row]
        data = (not table["nested"] and width >= 2 and all(len(cell) <= 1 for cell in cells)
                and not any(re.match(r"(#|- |\||> |```|---$)", cell[0]) for cell in cells if cell))
        if not data:  # a table for layout: what its cells hold, in order
            for row in rows:
                for out in row:
                    self.out.blocks += out.blocks
            return
        values = [[cell[0] if cell else "" for cell in row] for row in grid]
        values = [row + [""] * (width - len(row)) for row in values if any(value.strip() for value in row)]
        if not values:
            return
        self.count += 1
        n = self.count
        heads = [tables.cell(value) or f"(column {i + 1})" for i, value in enumerate(values[0])]
        shown, note = tables.limit(list(enumerate(values[1:], 2)), self.options)
        for i, head in enumerate(heads):
            if warning := personal.warning(f"Table {n}, column {head}", [row[i] for _, row in shown]):
                self.warnings.append(warning)
        self.out.blocks.append(self.quoted(f"Table {n}:\n\n" + tables.table(heads, shown).rstrip("\n")
                                           + note.rstrip("\n")))


def _span(value: str | None) -> int:
    return min(int(value), 50) if value and value.isdigit() and int(value) > 0 else 1


def _grid(rows: list[list[_Out]]) -> list[list[list[str]]]:
    """Each row's cells' blocks, a cell spanning columns or rows repeated in each place it covers."""
    grid, below = [], {}  # below: a column's cell spanning down, and the rows it has left
    for row in rows:
        line, cells = [], list(row)
        while cells or len(line) in below:
            column = len(line)
            if column in below:
                blocks, left = below[column]
                line.append(blocks)
                if left > 1:
                    below[column] = (blocks, left - 1)
                else:
                    del below[column]
                continue
            out = cells.pop(0)
            columns, down = out.spans
            for _ in range(columns):
                if down > 1:
                    below[len(line)] = (out.blocks, down - 1)
                line.append(out.blocks)
        grid.append(line)
    return grid
