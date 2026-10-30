"""Documents a BA brings, as Markdown: `bridge-kit doc read` prints one, and `bridge-kit inputs add <file>` keeps one as
a work item's input. One reader per kind, each giving the Markdown, a title and its warnings. The kind comes from the
file's extension, checked against its first bytes.

Read: plain text and Markdown, CSV and TSV, Excel workbooks, Word documents, PDFs, PowerPoint decks, HTML pages,
and emails (`.eml`, and Outlook's `.msg`). bridge-kit can't read an image: the agent reads it and describes it
(`bridge-kit inputs add --description`).

Refused, each with what to do: the old formats (save it as .docx, .xlsx or .pptx), an Office file locked by a
password or a sensitivity label, and any kind not listed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

KINDS = {".txt": "text", ".md": "text", ".markdown": "text", ".csv": "csv", ".tsv": "csv",
         ".xlsx": "xlsx", ".xlsm": "xlsx", ".docx": "docx", ".pptx": "pptx", ".pdf": "pdf",
         ".html": "html", ".htm": "html", ".eml": "email", ".msg": "msg",
         ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".webp": "image"}
NAMES = {"text": "a text file", "csv": "a CSV file", "xlsx": "an Excel workbook", "docx": "a Word document",
         "pptx": "a PowerPoint deck", "pdf": "a PDF", "html": "an HTML page", "email": "an email",
         "msg": "an Outlook message", "image": "an image"}
RESAVE = {
    ".doc": "the old Word format: open it in Word and save it as .docx",
    ".rtf": "rich text: open it in Word and save it as .docx",
    ".odt": "an OpenDocument text: save it as .docx",
    ".xls": "the old Excel format: open it in Excel and save it as .xlsx",
    ".xlsb": "Excel's binary format: open it in Excel and save it as .xlsx",
    ".ods": "an OpenDocument spreadsheet: save it as .xlsx",
    ".ppt": "the old PowerPoint format: open it in PowerPoint and save it as .pptx",
    ".odp": "an OpenDocument presentation: save it as .pptx",
    ".bmp": "an image format Copilot doesn't take: save it as PNG",
    ".tif": "an image format Copilot doesn't take: save it as PNG",
    ".tiff": "an image format Copilot doesn't take: save it as PNG",
    ".heic": "an image format Copilot doesn't take: save it as PNG or JPEG",
}
ZIP, COMPOUND = b"PK\x03\x04", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # an Office file; an encrypted one
IMAGES = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")

IMAGE_HELP = ("{name} is an image, which bridge-kit can't read: read it yourself and write down what it shows, then "
              "keep it with bridge-kit inputs add {name} --work-item <id> --description <file> --by <your name> "
              "(the document-reading skill says how)")


class DocumentError(Exception):
    """The file can't be read: not there, a kind bridge-kit doesn't read, or locked. One line, saying what to do."""


@dataclass(frozen=True)
class Options:
    sheets: tuple[str, ...] = ()  # only these sheets of a workbook
    rows: int | str | None = None  # at most this many rows a table, or "all"; None: a table over 500 rows shows 200
    headers_only: bool = False  # a table's heading row only, for a sheet of real records
    layout: bool = False  # a PDF's pages as laid out

    def to_header(self) -> dict | None:
        """The options that aren't the default, for an input's header; None when there are none."""
        chosen = {"sheet": list(self.sheets) or None, "rows": self.rows, "headers_only": self.headers_only or None,
                  "layout": self.layout or None}
        return {k: v for k, v in chosen.items() if v is not None} or None


@dataclass
class Document:
    kind: str
    title: str
    markdown: str
    warnings: list[str] = field(default_factory=list)
    images: dict[str, bytes] = field(default_factory=dict, repr=False)  # by the name the Markdown gives each
    attachments: dict[str, bytes] = field(default_factory=dict, repr=False)  # an email's, by their file names

    def to_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title, "markdown": self.markdown, "warnings": self.warnings,
                "images": list(self.images), "attachments": list(self.attachments)}


def kind_of(path: Path) -> str:
    """The file's kind, from its extension, checked against its first bytes."""
    if not path.is_file():
        raise DocumentError(f"No such file: {path}")
    suffix = path.suffix.lower()
    if suffix in RESAVE:
        raise DocumentError(f"{path.name} is {RESAVE[suffix]}")
    kind = KINDS.get(suffix)
    if kind is None:
        raise DocumentError(f"bridge-kit doesn't read {suffix or 'extensionless'} files: it reads "
                            + ", ".join(sorted(KINDS)))
    with path.open("rb") as f:
        head = f.read(1024)
    if kind == "msg":
        ok = head.startswith(COMPOUND)
    elif kind in ("xlsx", "docx", "pptx"):
        if head.startswith(COMPOUND):
            raise DocumentError(f"{path.name} is locked, by a password or a sensitivity label: save a copy without "
                                "it, or ask its owner for one")
        ok = head.startswith(ZIP)
    elif kind == "pdf":
        ok = b"%PDF-" in head
    elif kind == "image":
        ok = head.startswith(IMAGES) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    else:
        ok = True
    if not ok:
        raise DocumentError(f"{path.name} isn't {NAMES[kind]} inside: it doesn't start as one does")
    return kind


def read_document(path: Path, options: Options = Options()) -> Document:
    kind = kind_of(path)
    if kind == "image":
        raise DocumentError(IMAGE_HELP.format(name=path.name))
    reader = _readers().get(kind)
    if reader is None:
        raise DocumentError(f"bridge-kit can't read {path.name}: it has no reader for {NAMES[kind]}")
    return reader(path, options)


def join_blocks(blocks: list[str]) -> str:
    """Markdown blocks apart by a blank line, but a list's items on adjacent lines."""
    text, listing = "", False
    for block in blocks:
        item = re.match(r" *- ", block) is not None
        text += ("\n" if item and listing else "\n\n" if text else "") + block
        listing = item
    return text


def ranges(numbers: list[int]) -> str:
    """1, 2, 3, 7 as 1–3, 7."""
    found, start = [], None
    for n, following in zip(numbers, numbers[1:] + [None]):
        start = n if start is None else start
        if following != n + 1:
            found.append(str(n) if start == n else f"{start}–{n}")
            start = None
    return ", ".join(found)


def _readers() -> dict[str, Callable[[Path, Options], Document]]:
    from bridge_kit.documents import excel, html, mail, outlook, pdf, powerpoint, text, word

    return {"text": text.read_text, "csv": text.read_csv, "xlsx": excel.read_excel, "docx": word.read_word,
            "pdf": pdf.read_pdf, "pptx": powerpoint.read_powerpoint, "html": html.read_html, "email": mail.read_email,
            "msg": outlook.read_msg}
