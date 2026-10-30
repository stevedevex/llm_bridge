"""Office Open XML packages (`.docx`, `.pptx`), on Python's own zip and XML modules: a part as XML, its
relationships, the package's title. A part over 100 MB, or one declaring a DTD, is refused rather than parsed."""

from __future__ import annotations

import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from bridge_kit.documents import DocumentError

MAX_PART = 100 * 1024 * 1024
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
    "v": "urn:schemas-microsoft-com:vml",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "dc": "http://purl.org/dc/elements/1.1/",
}


FILE_NAME = re.compile(r"[\w\-. ()]+\.(png|jpe?g|gif|bmp|emf|wmf|tiff?|svg|webp)", re.IGNORECASE)


def alt_text(*values: str | None) -> str:
    """An image's alt text, from its description or its title. A file's name says nothing, and is what tools that
    make documents put there, so it's none."""
    for value in values:
        text = " ".join((value or "").split())
        if text and not FILE_NAME.fullmatch(text):
            return text
    return ""


def tag(name: str) -> str:
    """`w:p` as ElementTree names it: `{http://...}p`."""
    prefix, local_name = name.split(":")
    return f"{{{NS[prefix]}}}{local_name}"


def local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def attr(element: ET.Element | None, name: str) -> str | None:
    return None if element is None else element.get(tag(name))


class Package:
    def __init__(self, path: Path, what: str):
        self.path, self.what = path, what
        try:
            self.zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as e:
            raise DocumentError(f"{path.name} can't be read as {what} ({type(e).__name__}): open it and save it "
                                "again") from None

    def data(self, name: str) -> bytes | None:
        try:
            info = self.zip.getinfo(name)
        except KeyError:
            return None
        if info.file_size > MAX_PART:
            raise DocumentError(f"{self.path.name} holds a part of {info.file_size // 2 ** 20} MB ({name}): too big "
                                "to read")
        return self.zip.read(info)

    def xml(self, name: str) -> ET.Element | None:
        data = self.data(name)
        if data is None:
            return None
        if b"<!DOCTYPE" in data[:4096]:
            raise DocumentError(f"{self.path.name} declares a DTD in {name}, which Office never writes: not read")
        try:
            return ET.fromstring(data)
        except ET.ParseError as e:
            raise DocumentError(f"{self.path.name} can't be read as {self.what}: {name} isn't well-formed ({e})") \
                from None

    def rels(self, part: str) -> dict[str, tuple[str, bool]]:
        """A part's relationships: each id's target, a part's name or a URL, and whether it's external."""
        folder, name = posixpath.split(part)
        root = self.xml(posixpath.join(folder, "_rels", f"{name}.rels"))
        found = {}
        for rel in [] if root is None else root.iter(tag("rel:Relationship")):
            target, external = rel.get("Target", ""), rel.get("TargetMode") == "External"
            if not external:
                target = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
                    posixpath.join(folder, target))
            found[rel.get("Id", "")] = (target, external)
        return found

    def title(self) -> str:
        core = self.xml("docProps/core.xml")
        found = None if core is None else core.find(tag("dc:title"))
        return (found.text or "").strip() if found is not None else ""
