"""Word documents (`.docx`), on Python's own zip and XML modules.

- Headings from the paragraph styles (`heading 1` is `##`, the document's title being `#`), with their numbers when
  the styles number them (`## 3.2 Scope`); the Title style in bold.
- Lists at their levels, each item with its label as Word shows it (`1.`, `a)`, `3.2.1`); bullets as `-`.
- Tables, each as `Table N:` with its row numbers, merged cells spread across and down.
- Links as Markdown links; footnotes and endnotes as `[^N]`, listed at the end.
- Comments: `[comment N]` where they are, listed at the end with the text they're on and their author.
- Tracked changes shown as their result (insertions kept, deletions dropped), and listed at the end: who did what.
- Struck-through text as `~~text~~`; hidden text left out, as Word shows it.
- Images as `[Image N: <alt text>]` where they are, kept apart (`Document.images`) for `inputs add`; text boxes'
  text in place; charts and SmartArt named, not read.
"""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from bridge_kit.documents import Document, DocumentError, Options, join_blocks, personal, tables
from bridge_kit.documents.ooxml import Package, alt_text, attr, local, tag

LISTED = 50  # at most this many tracked changes listed
OFF = ("0", "false", "off", "none")


def read_word(path: Path, options: Options) -> Document:
    package = Package(path, "a Word document")
    document = package.xml("word/document.xml")
    body = None if document is None else document.find(tag("w:body"))
    if body is None:
        raise DocumentError(f"{path.name} has no word/document.xml: it isn't a Word document inside")
    reader = _Reader(package, options)
    blocks = reader.blocks(body)
    return reader.document(path, blocks)


class _Reader:
    def __init__(self, package: Package, options: Options):
        self.package, self.options = package, options
        self.rels = package.rels("word/document.xml")
        self.styles = _Styles(package.xml("word/styles.xml"))
        self.numbering = _Numbering(package.xml("word/numbering.xml"))
        self.comments = _comments(package.xml("word/comments.xml"))
        self.numbers = {cid: n for n, cid in enumerate(self.comments, 1)}
        self.notes = {"footnote": package.xml("word/footnotes.xml"), "endnote": package.xml("word/endnotes.xml")}
        self.used_notes: list[tuple[str, str]] = []
        self.anchors: dict[str, str] = {}
        self.open: set[str] = set()
        self.changes: list[str] = []
        self.images: dict[str, bytes] = {}
        self.image_lines: list[str] = []
        self.unread = {"chart": 0, "diagram": 0}
        self.tables = 0
        self.struck = False
        self.title = ""
        self.texts: list[str] = []
        self.warnings: list[str] = []

    # --- blocks: paragraphs and tables ---------------------------------------------------------------------------

    def blocks(self, parent: ET.Element, in_cell: bool = False) -> list[str]:
        found = []
        for child in parent:
            name = local(child)
            if name == "p":
                if line := self.paragraph(child, in_cell):
                    found.append(line)
            elif name == "tbl":
                found.append(self.flat_table(child) if in_cell else self.table(child))
            elif name in ("sdt", "customXml", "AlternateContent"):
                found += self.blocks(_content(child), in_cell)
        return found

    def paragraph(self, p: ET.Element, in_cell: bool = False) -> str:
        ppr = p.find(tag("w:pPr"))
        style = attr(ppr.find(tag("w:pStyle")) if ppr is not None else None, "w:val")
        text = self.inline(p).replace("~~~~", "").strip()
        if not text:
            return ""
        num = ppr.find(tag("w:numPr")) if ppr is not None else None
        num_id = attr(num.find(tag("w:numId")) if num is not None else None, "w:val")
        level = attr(num.find(tag("w:ilvl")) if num is not None else None, "w:val")
        if num_id is None:
            num_id, level = self.styles.numbering(style)
        label = self.numbering.label(num_id, int(level or 0)) if num_id else None
        outline = attr(ppr.find(tag("w:outlineLvl")) if ppr is not None else None, "w:val")
        heading = self.styles.heading(style, outline)
        if self.styles.is_title(style):
            self.title = self.title or text
            return f"**{text}**"
        if heading:
            self.title = self.title or ("" if heading > 1 else text)
            return "#" * min(heading + 1, 6) + " " + (f"{label} " if label else "") + " ".join(text.split())
        if not in_cell:  # a table's text is checked column by column
            self.texts.append(text)
        if label is not None:
            return "  " * int(level or 0) + "- " + (f"{label} " if label else "") + text
        return text

    def table(self, tbl: ET.Element) -> str:
        self.tables += 1
        n = self.tables
        rows = self.grid(tbl)
        rows = [row for row in rows if any(row)]
        if not rows:
            return f"Table {n}: empty."
        width = max(len(row) for row in rows)
        heads = [tables.cell(text) or f"(column {i + 1})" for i, text in
                 enumerate(rows[0] + [""] * (width - len(rows[0])))]
        body = list(enumerate(rows[1:], 2))
        shown, note = tables.limit(body, self.options)
        for i, head in enumerate(heads):
            if warning := personal.warning(f"Table {n}, column {head}", [row[i] for _, row in shown if i < len(row)]):
                self.warnings.append(warning)
        return f"Table {n}:\n\n" + tables.table(heads, shown).rstrip("\n") + note.rstrip("\n")

    def grid(self, tbl: ET.Element) -> list[list[str]]:
        """The table's rows as cells, a cell merged across repeated in each column it spans, one merged down
        repeated from the cell above."""
        rows = []
        for tr in _children(tbl, "tr"):
            row = []
            for tc in _children(tr, "tc"):
                tcpr = tc.find(tag("w:tcPr"))
                span = int(attr(tcpr.find(tag("w:gridSpan")) if tcpr is not None else None, "w:val") or 1)
                merge = tcpr.find(tag("w:vMerge")) if tcpr is not None else None
                text = "\n".join(self.blocks(tc, in_cell=True))
                if merge is not None and attr(merge, "w:val") != "restart" and rows:
                    above = rows[-1]
                    text = above[len(row)] if len(row) < len(above) else text
                row += [text] * span
            rows.append(row)
        return rows

    def flat_table(self, tbl: ET.Element) -> str:
        """A table inside a table's cell, as its cells' text."""
        return " / ".join(" | ".join(cell for cell in row if cell) for row in self.grid(tbl) if any(row))

    # --- inline: runs, links, changes, comments, drawings --------------------------------------------------------

    def inline(self, parent: ET.Element) -> str:
        found = []
        for child in parent:
            name = local(child)
            if name == "r":
                found.append(self.run(child))
            elif name == "hyperlink":
                text = self.inline(child)
                target, external = self.rels.get(attr(child, "r:id") or "", ("", False))
                found.append(f"[{text}]({target})" if external and target and text.strip() else text)
            elif name in ("ins", "moveTo"):
                text = self.inline(child)
                self.change("Inserted" if name == "ins" else "Moved here", child, text)
                found.append(text)
            elif name in ("del", "moveFrom"):
                deleted = "".join(t.text or "" for t in child.iter() if local(t) in ("delText", "t"))
                self.change("Deleted" if name == "del" else "Moved away", child, deleted)
            elif name in ("smartTag", "fldSimple", "customXml", "sdt", "sdtContent", "AlternateContent"):
                found.append(self.inline(_content(child)))
            elif name == "commentRangeStart":
                self.open.add(attr(child, "w:id") or "")
            elif name == "commentRangeEnd":
                self.open.discard(attr(child, "w:id") or "")
        return "".join(found)

    def run(self, r: ET.Element) -> str:
        rpr = r.find(tag("w:rPr"))
        if _on(rpr, "w:vanish"):
            return ""
        found, plain = [], []
        for child in r:
            name = local(child)
            if name == "t":
                found.append(child.text or "")
                plain.append(child.text or "")
            elif name in ("tab", "ptab"):
                found.append(" ")
                plain.append(" ")
            elif name in ("br", "cr") and attr(child, "w:type") not in ("page", "column"):
                found.append("\n")
            elif name == "noBreakHyphen":
                found.append("-")
            elif name in ("footnoteReference", "endnoteReference"):
                kind = name.removesuffix("Reference")
                note = attr(child, "w:id") or ""
                self.used_notes.append((kind, note))
                found.append(f"[^{'' if kind == 'footnote' else 'e'}{note}]")
            elif name == "commentReference":
                number = self.numbers.get(attr(child, "w:id") or "")
                found.append(f" [comment {number}]" if number else "")
            elif name in ("drawing", "pict", "object", "AlternateContent"):
                found.append(self.drawing(_content(child)))
        for comment in self.open:
            self.anchors[comment] = self.anchors.get(comment, "") + "".join(plain)
        text = "".join(found)
        if (_on(rpr, "w:strike") or _on(rpr, "w:dstrike")) and text.strip():
            self.struck = True
            core = text.strip()
            text = text[:len(text) - len(text.lstrip())] + f"~~{core}~~" + text[len(text.rstrip()):]
        return text

    def drawing(self, element: ET.Element) -> str:
        found = []
        names = {local(e) for e in element.iter()}
        if "chart" in names:
            self.unread["chart"] += 1
            found.append("[A chart, not read]")
        if "relIds" in names:
            self.unread["diagram"] += 1
            found.append("[A diagram (SmartArt), not read]")
        alt = next((text for d in element.iter(tag("wp:docPr")) if (text := alt_text(d.get("descr"), d.get("title")))),
                   "")
        ids = [attr(b, "r:embed") or attr(b, "r:link") for b in element.iter(tag("a:blip"))]
        ids += [attr(i, "r:id") for i in element.iter(tag("v:imagedata"))]
        for rid in dict.fromkeys(i for i in ids if i):
            target, external = self.rels.get(rid, ("", True))
            data = None if external else self.package.data(target)
            if data is None:
                continue
            n = len(self.images) + 1
            name = f"image-{n}{posixpath.splitext(target)[1].lower()}"
            self.images[name] = data
            self.image_lines.append(f"- Image {n}: `{name}`" + (f": {alt}" if alt else ""))
            found.append(f"[Image {n}" + (f": {alt}" if alt else "") + "]")
        boxes = [" ".join(self.inline(p).split()) for box in element.iter(tag("w:txbxContent"))
                 for p in box.iter(tag("w:p"))]
        if boxes := [b for b in boxes if b]:
            found.append("[Text box: " + " / ".join(boxes) + "]")
        return " ".join(found)

    def change(self, kind: str, element: ET.Element, text: str) -> None:
        if not text.strip():
            return
        when = (attr(element, "w:date") or "")[:10]
        self.changes.append(f"- {kind} by {attr(element, 'w:author') or 'someone'}" + (f" on {when}" if when else "")
                            + f": “{' '.join(text.split())}”")

    # --- the document --------------------------------------------------------------------------------------------

    def document(self, path: Path, blocks: list[str]) -> Document:
        notes = []
        for kind, note in dict.fromkeys(self.used_notes):
            root = self.notes[kind]
            found = None if root is None else next((n for n in root.iter(tag(f"w:{kind}"))
                                                    if attr(n, "w:id") == note), None)
            if found is not None:
                text = " ".join(" ".join(self.blocks(found)).split())
                notes.append(f"[^{'' if kind == 'footnote' else 'e'}{note}]: {text}")
        title = self.package.title() or self.title or path.stem
        counts = [f"{n} {what}" for n, what in ((self.tables, "table(s)"), (len(self.comments), "comment(s)"),
                                                (len(self.changes), "tracked change(s)"),
                                                (len(self.images), "image(s)")) if n]
        lines = [f"# {title}", "", f"`{path.name}`: a Word document" + (", with " + ", ".join(counts) if counts
                                                                          else "") + ".", ""]
        lines.append(join_blocks(blocks))
        comments = [f"- Comment {n}, by {author}" + (f" on “{_short(self.anchors[cid])}”"
                                                     if self.anchors.get(cid, "").strip() else "") + f": {text}"
                    for n, (cid, (author, text)) in enumerate(self.comments.items(), 1)]
        for heading, listed in (("Footnotes and endnotes", notes), ("Comments", comments),
                                ("Tracked changes", self.changes), ("Images", self.image_lines)):
            if listed:
                lines += ["", f"## {heading}", ""] + listed[:LISTED]
                if len(listed) > LISTED:
                    lines.append(f"- and {len(listed) - LISTED} more")
        warnings = []
        if self.changes:
            warnings.append(f"{path.name} has {len(self.changes)} tracked change(s), not yet accepted: shown as if "
                            "accepted, and listed at the end; ask the BA whether they stand")
        if self.comments:
            warnings.append(f"{path.name} has {len(self.comments)} comment(s), listed at the end with the text "
                            "they're on: open questions, perhaps")
        if self.images:
            warnings.append(f"{path.name} has {len(self.images)} image(s), which bridge-kit can't read: each is marked "
                            "[Image N]; bridge-kit inputs add keeps them, for an agent to describe any that matters")
        if any(self.unread.values()):
            warnings.append(f"{path.name} has {self.unread['chart']} chart(s) and {self.unread['diagram']} "
                            "SmartArt diagram(s), not read: ask the BA what they show if it matters")
        if self.struck:
            warnings.append(f"{path.name} has struck-through text, shown as ~~text~~: often something dropped")
        if warning := personal.warning(f"{path.name}'s text", self.texts):
            warnings.append(warning)
        return Document("docx", title, "\n".join(lines).rstrip() + "\n", warnings + self.warnings, self.images)


class _Styles:
    """Each paragraph style's name, the style it's based on, its outline level and its numbering."""

    def __init__(self, root: ET.Element | None):
        self.styles = {}
        for style in [] if root is None else root.iter(tag("w:style")):
            ppr = style.find(tag("w:pPr"))
            num = ppr.find(tag("w:numPr")) if ppr is not None else None
            self.styles[attr(style, "w:styleId")] = {
                "name": (attr(style.find(tag("w:name")), "w:val") or "").lower(),
                "based": attr(style.find(tag("w:basedOn")), "w:val"),
                "outline": attr(ppr.find(tag("w:outlineLvl")) if ppr is not None else None, "w:val"),
                "num": None if num is None else (attr(num.find(tag("w:numId")), "w:val"),
                                                 attr(num.find(tag("w:ilvl")), "w:val"))}

    def chain(self, style: str | None):
        for _ in range(10):  # a style's bases, nearest first; a loop in them is cut short
            if style not in self.styles:
                return
            yield self.styles[style]
            style = self.styles[style]["based"]

    def heading(self, style: str | None, outline: str | None) -> int | None:
        if outline is not None:
            return int(outline) + 1 if outline.isdigit() and int(outline) < 9 else None
        for found in self.chain(style):
            if m := re.fullmatch(r"heading (\d)", found["name"]):
                return int(m.group(1))
            if found["outline"] is not None and found["outline"].isdigit() and int(found["outline"]) < 9:
                return int(found["outline"]) + 1
        return None

    def is_title(self, style: str | None) -> bool:
        return any(found["name"] in ("title", "subtitle") for found in self.chain(style))

    def numbering(self, style: str | None) -> tuple[str | None, str | None]:
        for found in self.chain(style):
            if found["num"] is not None:
                return found["num"]
        return None, None


class _Numbering:
    """List labels as Word shows them. Lists sharing an abstract definition count on together, as Word does, and a
    list instance with a start override starts again the first time it's used."""

    def __init__(self, root: ET.Element | None):
        self.abstract, self.instances, self.counts, self.started = {}, {}, {}, set()
        for abstract in [] if root is None else root.iter(tag("w:abstractNum")):
            levels = {}
            for lvl in abstract.iter(tag("w:lvl")):
                levels[int(attr(lvl, "w:ilvl") or 0)] = (attr(lvl.find(tag("w:numFmt")), "w:val") or "decimal",
                                                         attr(lvl.find(tag("w:lvlText")), "w:val") or "",
                                                         int(attr(lvl.find(tag("w:start")), "w:val") or 1))
            self.abstract[attr(abstract, "w:abstractNumId")] = levels
        for num in [] if root is None else root.iter(tag("w:num")):
            overrides = {int(attr(o, "w:ilvl") or 0): int(attr(o.find(tag("w:startOverride")), "w:val"))
                         for o in num.iter(tag("w:lvlOverride")) if o.find(tag("w:startOverride")) is not None}
            self.instances[attr(num, "w:numId")] = (attr(num.find(tag("w:abstractNumId")), "w:val"), overrides)

    def label(self, num_id: str, level: int) -> str | None:
        """The item's label, "" for a bullet, or None when it isn't in a list."""
        if num_id not in self.instances or num_id == "0":
            return None
        abstract, overrides = self.instances[num_id]
        levels = self.abstract.get(abstract, {})
        counts = self.counts.setdefault(abstract, {})
        if num_id not in self.started:
            self.started.add(num_id)
            for lvl, start in overrides.items():
                counts[lvl] = start - 1
                for deeper in [k for k in counts if k > lvl]:
                    del counts[deeper]
        fmt, text, start = levels.get(level, ("decimal", f"%{level + 1}.", 1))
        counts[level] = counts.get(level, start - 1) + 1
        for deeper in [k for k in counts if k > level]:
            del counts[deeper]
        if fmt in ("bullet", "none"):
            return ""

        def number(lvl: int) -> str:
            lfmt, _, lstart = levels.get(lvl, ("decimal", "", 1))
            return _format(counts.get(lvl, lstart), lfmt)

        return re.sub(r"%(\d)", lambda m: number(int(m.group(1)) - 1), text)


def _format(n: int, fmt: str) -> str:
    if fmt == "decimalZero":
        return f"{n:02d}"
    if fmt in ("lowerLetter", "upperLetter"):
        letters = tables.column_letter(n - 1)
        return letters.lower() if fmt == "lowerLetter" else letters
    if fmt in ("lowerRoman", "upperRoman"):
        roman = ""
        for value, numeral in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                               (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
            while n >= value:
                roman, n = roman + numeral, n - value
        return roman.lower() if fmt == "lowerRoman" else roman
    return str(n)


def _comments(root: ET.Element | None) -> dict[str, tuple[str, str]]:
    found = {}
    for comment in [] if root is None else root.iter(tag("w:comment")):
        text = " ".join("".join(t.text or "" for t in p.iter(tag("w:t"))) for p in comment.iter(tag("w:p")))
        found[attr(comment, "w:id") or ""] = (attr(comment, "w:author") or "no author", " ".join(text.split()))
    return found


def _content(element: ET.Element) -> ET.Element:
    """What a wrapper holds: a content control's content, a markup-compatibility block's first choice."""
    inner = {"sdt": "w:sdtContent", "AlternateContent": "mc:Choice"}.get(local(element))
    if inner is None:
        return element
    found = element.find(tag(inner))
    return ET.Element("empty") if found is None else found


def _children(parent: ET.Element, name: str):
    """A table's rows, or a row's cells, through any content controls around them."""
    for child in parent:
        if local(child) == name:
            yield child
        elif local(child) in ("sdt", "customXml"):
            yield from _children(_content(child), name)


def _on(rpr: ET.Element | None, name: str) -> bool:
    found = None if rpr is None else rpr.find(tag(name))
    return found is not None and (attr(found, "w:val") or "true").lower() not in OFF


def _short(text: str, most: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"
