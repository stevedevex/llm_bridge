"""PDFs, on pypdf.

- The title from the PDF's properties (without Word's "Microsoft Word - " prefix), else its first line.
- Its bookmarks as contents, each with its page.
- Each page's text under `## Page N`, with the page's own label when it has another (`labelled iv`); `--layout`
  keeps the page laid out, in a code block, so a table's columns stay apart. It isn't the default: it also puts
  two columns of text side by side.
- A page with no text is named, since it's a scan or a picture: Copilot reads a PDF's pages itself, and what it
  reads is kept with `bridge-kit inputs add --description`.
- Images: JPEGs kept apart (`Document.images`), once each however many pages show them; others counted, since
  turning them into files would need Pillow. Icons under 32 pixels are left out.
- A PDF locked by a password is refused; one with an owner's password only (no printing, say) is read.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

from bridge_kit.documents import Document, DocumentError, Options, personal, ranges

PREFIXES = ("Microsoft Word - ", "Microsoft PowerPoint - ", "Microsoft Excel - ")
SMALLEST = 32  # an image narrower or lower than this, in pixels, is an icon or a rule


def read_pdf(path: Path, options: Options) -> Document:
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # it logs every oddity it recovers from
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted and not _unlocked(reader):
            raise DocumentError(f"{path.name} is locked by a password: open it, print it to a new PDF, and add that")
        pages = list(reader.pages)
    except DocumentError:
        raise
    except Exception as e:  # pypdf raises many kinds on a broken file
        raise DocumentError(f"{path.name} can't be read as a PDF ({type(e).__name__}): open it and print it to a new "
                            "PDF") from None
    labels = _labels(reader, len(pages))
    seen: dict[int, str] = {}  # an image's object, by the name it's given
    images: dict[str, bytes] = {}
    sections, blank, unreadable, texts = [], [], [], {}
    count = 0
    for number, page in enumerate(pages, 1):
        try:
            text = _clean(page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False)
                          if options.layout else page.extract_text(), options.layout)
        except Exception as e:
            text = ""
            unreadable.append(f"{number} ({type(e).__name__})")
        label = labels[number - 1]
        lines = [f"## Page {number}" + (f" (labelled {label})" if label != str(number) else ""), ""]
        if text:
            texts[number] = text
            lines.append(f"```text\n{text}\n```" if options.layout else text)
        else:
            blank.append(number)
            lines.append("_No text on this page: a scan or a picture._")
        shown = []
        for ref, data in _images(page):
            if ref in seen:
                continue
            count += 1
            if data is None:
                seen[ref] = ""
                shown.append(f"Image {count} (not kept: not a JPEG)")
                continue
            seen[ref] = name = f"image-{count}.jpg"
            images[name] = data
            shown.append(f"Image {count} (`{name}`)")
        if shown:
            lines += ["", "Images on this page: " + ", ".join(shown) + "."]
        sections.append("\n".join(lines))

    first = next(iter(texts.values()), "").strip().splitlines()
    title = _title(reader) or (first[0].strip()[:80] if first else "") or path.stem
    head = [f"# {title}", "", f"`{path.name}`: a PDF, {len(pages)} page(s)" + (
        f", {len(blank)} of them without text" if blank else "") + "."]
    if contents := _outline(reader, reader.outline if _has_outline(reader) else []):
        head += ["", "Contents, from its bookmarks:", ""] + contents[:200]
    warnings = []
    if blank:
        warnings.append(f"{path.name} has {len(blank)} page(s) with no text ({ranges(blank)}): a scan, or "
                        "pictures. Copilot reads a PDF's pages itself: describe what they show, and keep it with "
                        "bridge-kit inputs add --description")
    if count:
        warnings.append(f"{path.name} has {count} image(s), which bridge-kit can't read: bridge-kit inputs add keeps "
                        "their JPEGs; Copilot can read them on the PDF's pages")
    if unreadable:
        warnings.append(f"{path.name}: page(s) {', '.join(unreadable)} couldn't be read")
    if with_data := [n for n, text in texts.items() if any(personal.count(text).values())]:
        if warning := personal.warning(f"{path.name} (page(s) {ranges(with_data)})", [texts[n] for n in with_data]):
            warnings.append(warning)
    return Document("pdf", title, "\n".join(head) + "\n\n" + "\n\n".join(sections) + "\n", warnings, images)


def _unlocked(reader) -> bool:
    """Whether an empty password opens it, as it does a PDF with an owner's password only."""
    try:
        return bool(reader.decrypt(""))
    except Exception:  # AES needs the cryptography package, which the kit doesn't bring
        return False


def _clean(text: str, layout: bool) -> str:
    lines = [line.rstrip() for line in (text or "").replace("\r\n", "\n").split("\n")]
    found = "\n".join(lines).strip("\n")
    while "\n\n\n" in found:
        found = found.replace("\n\n\n", "\n\n")
    return textwrap.dedent(found) if layout else found.strip()


def _title(reader) -> str:
    try:
        title = str(reader.metadata.title or "").strip() if reader.metadata else ""
    except Exception:
        return ""
    for prefix in PREFIXES:
        title = title.removeprefix(prefix)
    for suffix in (".docx", ".doc", ".pptx", ".xlsx"):
        title = title.removesuffix(suffix)
    return title.strip()


def _labels(reader, count: int) -> list[str]:
    try:
        labels = list(reader.page_labels)
    except Exception:
        labels = []
    return labels if len(labels) == count else [str(n) for n in range(1, count + 1)]


def _has_outline(reader) -> bool:
    try:
        return bool(reader.outline)
    except Exception:
        return False


def _outline(reader, items, depth: int = 0) -> list[str]:
    lines = []
    for item in items:
        if isinstance(item, list):
            lines += _outline(reader, item, depth + 1)
            continue
        try:
            page = reader.get_destination_page_number(item) + 1
        except Exception:
            page = None
        lines.append("  " * depth + f"- {' '.join(str(item.title).split())}" + (f" (page {page})" if page else ""))
    return lines


def _images(page) -> list[tuple[int, bytes | None]]:
    """The page's images, in its own resources and its forms', each with its object's number and its JPEG's bytes
    (None when it isn't one)."""
    found = []

    def walk(resources, depth: int) -> None:
        if resources is None or depth > 5:
            return
        xobjects = resources.get_object().get("/XObject")
        for ref in ([] if xobjects is None else xobjects.get_object().values()):
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Form":
                walk(obj.get("/Resources"), depth + 1)
            elif obj.get("/Subtype") == "/Image":
                if min(int(obj.get("/Width", 0)), int(obj.get("/Height", 0))) < SMALLEST:
                    continue
                filters = obj.get("/Filter")
                filters = list(filters) if isinstance(filters, list) else [filters]
                found.append((getattr(ref, "idnum", id(obj)), obj.get_data() if filters == ["/DCTDecode"] else None))

    try:
        walk(page.get("/Resources"), 0)
    except Exception:
        pass  # an image bridge-kit can't get at is one Copilot reads on the page
    return found

