"""PowerPoint decks (`.pptx`), on Python's own zip and XML modules.

- Each slide under `## Slide N: <title>`, in the deck's order, hidden ones marked.
- Its shapes in reading order: top to bottom, then left to right, shapes level with each other (within a
  twentieth of the slide's height) taken as one row. A placeholder without a position of its own takes its
  layout's, or its master's.
- Text: a body placeholder's paragraphs as list items at their levels, a text box's as lines unless they have
  bullets; numbered bullets numbered; links as Markdown links; struck-through text as `~~text~~`.
- Tables, each as `Table N:` with its row numbers, merged cells spread; grouped shapes in their own order;
  SmartArt's text as a list.
- Images as `[Image N: <alt text>]`, each picture once however many slides show it, kept apart for `inputs add`;
  charts, videos and embedded objects named, not read.
- The slide's speaker notes under it.
"""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
from pathlib import Path

from bridge_kit.documents import Document, DocumentError, Options, personal, ranges, tables
from bridge_kit.documents.ooxml import Package, alt_text, attr, local, tag

TITLES = ("title", "ctrTitle")
BULLETED = ("body", "obj")  # the placeholders whose paragraphs are bullets unless they say otherwise
BAND = 20  # shapes whose tops are within 1/BAND of the slide's height of each other are read as one row
OFF = ("0", "false")


def read_powerpoint(path: Path, options: Options) -> Document:
    package = Package(path, "a PowerPoint deck")
    presentation = package.xml("ppt/presentation.xml")
    if presentation is None:
        raise DocumentError(f"{path.name} has no ppt/presentation.xml: it isn't a PowerPoint deck inside")
    rels = package.rels("ppt/presentation.xml")
    size = presentation.find(tag("p:sldSz"))
    height = int(size.get("cy", 6858000)) if size is not None else 6858000
    parts = [rels[rid][0] for s in presentation.iter(tag("p:sldId")) if (rid := attr(s, "r:id")) in rels]
    deck = _Deck(package, options, height)
    sections = [deck.slide(number, part) for number, part in enumerate(parts, 1)]
    return deck.document(path, sections)


class _Deck:
    def __init__(self, package: Package, options: Options, height: int):
        self.package, self.options, self.band = package, options, max(height // BAND, 1)
        self.places: dict[str, dict] = {}  # each layout's placeholders' positions
        self.images: dict[str, bytes] = {}
        self.seen: dict[str, int] = {}  # a picture's part, by its image number
        self.image_lines: list[str] = []
        self.tables = self.charts = self.objects = 0
        self.hidden: list[int] = []
        self.texts: dict[int, list[str]] = {}
        self.warnings: list[str] = []
        self.struck = False
        self.first_title = ""

    # --- a slide -------------------------------------------------------------------------------------------------

    def slide(self, number: int, part: str) -> str:
        root = self.package.xml(part)
        if root is None:
            return f"## Slide {number}\n\n_Missing from the file._"
        rels = self.package.rels(part)
        self.number, self.title, self.texts[number] = number, "", []
        tree = root.find(f"{tag('p:cSld')}/{tag('p:spTree')}")
        places = self.layout_places(rels)
        found = [] if tree is None else self.items(tree, rels, places)
        blocks = [block for *_, block in sorted(found, key=lambda item: (item[0] // self.band, item[1])) if block]
        hidden = root.get("show") in OFF
        if hidden:
            self.hidden.append(number)
        self.first_title = self.first_title or self.title
        lines = [f"## Slide {number}" + (f": {self.title}" if self.title else "") + (" (hidden)" if hidden else "")]
        lines += [""] + ["\n\n".join(blocks) if blocks else "_No text on this slide._"]
        notes = self.notes(rels)
        if notes:
            lines += ["", "Speaker notes:", "", notes]
        return "\n".join(lines)

    def items(self, container: ET.Element, rels: dict, places: dict) -> list[tuple[int, int, str]]:
        """Each shape's top, left and Markdown."""
        found = []
        for child in container:
            name = local(child)
            if name == "AlternateContent":
                choice = child.find(tag("mc:Choice"))
                found += [] if choice is None else self.items(choice, rels, places)
            elif name == "sp":
                ph = child.find(f"{tag('p:nvSpPr')}/{tag('p:nvPr')}/{tag('p:ph')}")
                kind = None if ph is None else ph.get("type", "obj")
                text = self.text_body(child.find(tag("p:txBody")), rels, kind in BULLETED)
                if kind in TITLES:
                    self.title = self.title or " ".join(text.split())
                    continue
                found.append((*self.position(child, places), text))
            elif name == "grpSp":
                inner = self.items(child, rels, places)
                block = "\n\n".join(b for *_, b in sorted(inner, key=lambda i: (i[0] // self.band, i[1])) if b)
                found.append((*self.position(child, places), block))
            elif name == "graphicFrame":
                found.append((*self.position(child, places), self.frame(child, rels)))
            elif name == "pic":
                found.append((*self.position(child, places), self.picture(child, rels)))
        return found

    def position(self, shape: ET.Element, places: dict) -> tuple[int, int]:
        """The shape's top and left, its own or, for a placeholder, its layout's; a shape with neither goes last."""
        for path in (f"{tag('p:spPr')}/{tag('a:xfrm')}", tag("p:xfrm"), f"{tag('p:grpSpPr')}/{tag('a:xfrm')}"):
            off = shape.find(f"{path}/{tag('a:off')}")
            if off is not None:
                return int(off.get("y", 0)), int(off.get("x", 0))
        ph = shape.find(f".//{tag('p:nvPr')}/{tag('p:ph')}")
        if ph is not None:
            for key in (("idx", ph.get("idx")), ("type", ph.get("type", "obj"))):
                if key in places:
                    return places[key]
        return 10 ** 12, 0

    def layout_places(self, rels: dict) -> dict:
        """The slide layout's placeholders' positions, by index and by type, with its master's for those it lacks."""
        layout = next((target for target, _ in rels.values() if "/slideLayouts/" in f"/{target}"), None)
        if layout is None:
            return {}
        if layout not in self.places:
            places = {}
            master = next((t for t, _ in self.package.rels(layout).values() if "/slideMasters/" in f"/{t}"), None)
            for part in (master, layout):  # the layout's own win
                root = None if part is None else self.package.xml(part)
                for shape in [] if root is None else root.iter(tag("p:sp")):
                    ph = shape.find(f".//{tag('p:nvPr')}/{tag('p:ph')}")
                    off = shape.find(f"{tag('p:spPr')}/{tag('a:xfrm')}/{tag('a:off')}")
                    if ph is not None and off is not None:
                        where = (int(off.get("y", 0)), int(off.get("x", 0)))
                        if ph.get("idx") is not None:
                            places[("idx", ph.get("idx"))] = where
                        places[("type", ph.get("type", "obj"))] = where
            self.places[layout] = places
        return self.places[layout]

    # --- text, tables, pictures ----------------------------------------------------------------------------------

    def text_body(self, body: ET.Element | None, rels: dict, bulleted: bool) -> str:
        if body is None:
            return ""
        lines, counts = [], {}
        for paragraph in body.findall(tag("a:p")):
            text = self.runs(paragraph, rels).replace("~~~~", "").strip()
            if not text:
                continue
            self.texts[self.number].append(text)
            ppr = paragraph.find(tag("a:pPr"))
            level = int(ppr.get("lvl", 0)) if ppr is not None else 0
            marks = {local(e) for e in ([] if ppr is None else ppr)}
            numbered = "buAutoNum" in marks
            bullet = "buNone" not in marks and (bulleted or numbered or "buChar" in marks)
            if numbered:
                counts[level] = counts.get(level, 0) + 1
                for deeper in [k for k in counts if k > level]:
                    del counts[deeper]
            lines.append("  " * level + "- " + (f"{counts[level]}. " if numbered else "") + text if bullet else text)
        return "\n".join(lines)

    def runs(self, paragraph: ET.Element, rels: dict) -> str:
        found = []
        for child in paragraph:
            name = local(child)
            if name in ("r", "fld"):
                text = "".join(t.text or "" for t in child.iter(tag("a:t")))
                rpr = child.find(tag("a:rPr"))
                link = None if rpr is None else rpr.find(tag("a:hlinkClick"))
                target, external = rels.get(attr(link, "r:id") or "", ("", False))
                if external and target and text.strip():
                    text = f"[{text}]({target})"
                if rpr is not None and rpr.get("strike", "noStrike") != "noStrike" and text.strip():
                    self.struck = True
                    core = text.strip()
                    text = text[:len(text) - len(text.lstrip())] + f"~~{core}~~" + text[len(text.rstrip()):]
                found.append(text)
            elif name == "br":
                found.append("\n")
        return "".join(found)

    def frame(self, frame: ET.Element, rels: dict) -> str:
        data = frame.find(f"{tag('a:graphic')}/{tag('a:graphicData')}")
        if data is None:
            return ""
        table = data.find(tag("a:tbl"))
        if table is not None:
            return self.table(table, rels)
        names = {local(e) for e in data.iter()}
        if "chart" in names:
            self.charts += 1
            return "[A chart, not read]"
        if "relIds" in names:
            ids = next(e for e in data.iter() if local(e) == "relIds")
            target, _ = rels.get(attr(ids, "r:dm") or "", ("", True))
            root = self.package.xml(target) if target else None
            texts = [" ".join("".join(t.text or "" for t in pt.iter(tag("a:t"))).split())
                     for pt in ([] if root is None else root.iter(tag("dgm:pt"))) if pt.get("type", "node") == "node"]
            texts = [t for t in texts if t]
            self.texts[self.number] += texts
            return "Diagram (SmartArt):\n\n" + "\n".join(f"- {t}" for t in texts) if texts else ""
        self.objects += 1
        return "[An embedded object, not read]"

    def table(self, tbl: ET.Element, rels: dict) -> str:
        self.tables += 1
        n = self.tables
        rows = []
        for tr in tbl.findall(tag("a:tr")):
            row = []
            for tc in tr.findall(tag("a:tc")):
                text = "\n".join(t for p in tc.iter(tag("a:p")) if (t := self.runs(p, rels).strip()))
                if tc.get("hMerge") in ("1", "true") and row:
                    text = row[-1]
                elif tc.get("vMerge") in ("1", "true") and rows and len(row) < len(rows[-1]):
                    text = rows[-1][len(row)]
                row.append(text)
            rows.append(row)
        rows = [row for row in rows if any(row)]
        if not rows:
            return f"Table {n}: empty."
        width = max(len(row) for row in rows)
        heads = [tables.cell(text) or f"(column {i + 1})" for i, text in
                 enumerate(rows[0] + [""] * (width - len(rows[0])))]
        shown, note = tables.limit(list(enumerate(rows[1:], 2)), self.options)
        for i, head in enumerate(heads):
            if warning := personal.warning(f"Table {n}, column {head}", [row[i] for _, row in shown if i < len(row)]):
                self.warnings.append(warning)
        return f"Table {n}:\n\n" + tables.table(heads, shown).rstrip("\n") + note.rstrip("\n")

    def picture(self, pic: ET.Element, rels: dict) -> str:
        if {local(e) for e in pic.iter()} & {"videoFile", "audioFile"}:
            self.objects += 1
            return "[A video or a sound, not read]"
        props = pic.find(f"{tag('p:nvPicPr')}/{tag('p:cNvPr')}")
        alt = alt_text(props.get("descr"), props.get("title")) if props is not None else ""
        blip = pic.find(f".//{tag('a:blip')}")
        target, external = rels.get(attr(blip, "r:embed") or "", ("", True))
        if target in self.seen:
            n = self.seen[target]
        else:
            data = None if external or not target else self.package.data(target)
            if data is None:
                return ""
            n = self.seen[target] = len(self.seen) + 1
            name = f"image-{n}{posixpath.splitext(target)[1].lower()}"
            self.images[name] = data
            self.image_lines.append(f"- Image {n}: `{name}`" + (f": {alt}" if alt else ""))
        return f"[Image {n}" + (f": {alt}" if alt else "") + "]"

    def notes(self, rels: dict) -> str:
        part = next((target for target, _ in rels.values() if "/notesSlides/" in f"/{target}"), None)
        root = None if part is None else self.package.xml(part)
        if root is None:
            return ""
        found = []
        for shape in root.iter(tag("p:sp")):
            ph = shape.find(f".//{tag('p:nvPr')}/{tag('p:ph')}")
            if ph is not None and ph.get("type") == "body":
                found.append(self.text_body(shape.find(tag("p:txBody")), self.package.rels(part), False))
        return "\n".join(f for f in found if f)

    # --- the deck -----------------------------------------------------------------------------------------------

    def document(self, path: Path, sections: list[str]) -> Document:
        title = self.package.title() or self.first_title or path.stem
        count = len(sections)
        lines = [f"# {title}", "", f"`{path.name}`: a PowerPoint deck, {count} slide(s)"
                 + (f", {len(self.hidden)} of them hidden" if self.hidden else "") + ".", "", "\n\n".join(sections)]
        if self.image_lines:
            lines += ["", "## Images", ""] + self.image_lines
        warnings = []
        if self.hidden:
            warnings.append(f"{path.name} has {len(self.hidden)} hidden slide(s) ({ranges(self.hidden)}): read too, "
                            "and marked")
        if self.images:
            warnings.append(f"{path.name} has {len(self.images)} image(s), which bridge-kit can't read: each is marked "
                            "[Image N]; bridge-kit inputs add keeps them, for an agent to describe any that matters")
        if self.charts or self.objects:
            warnings.append(f"{path.name} has {self.charts} chart(s) and {self.objects} video(s) or embedded "
                            "object(s), not read: ask the BA what they show if it matters")
        if self.struck:
            warnings.append(f"{path.name} has struck-through text, shown as ~~text~~: often something dropped")
        with_data = [n for n, texts in self.texts.items() if any(any(personal.count(t).values()) for t in texts)]
        if with_data and (warning := personal.warning(f"{path.name} (slide(s) {ranges(with_data)})",
                                                      [t for n in with_data for t in self.texts[n]])):
            warnings.append(warning)
        return Document("pptx", title, "\n".join(lines).rstrip() + "\n", warnings + self.warnings, self.images)
