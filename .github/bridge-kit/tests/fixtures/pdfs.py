"""PDFs written by hand, the few objects a page of text needs: each page's lines in Helvetica at the positions given,
and a JPEG image where asked. pypdf's own writer adds what a test needs on top: a title, bookmarks, page labels,
a password.

    pdf(path, [["Line one", "Line two"], [], [(72, 700, "Field"), (200, 700, "Rule")]], images={0: [JPEG]},
        logo=JPEG)
"""

from __future__ import annotations

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64 + b"\xff\xd9"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(path, pages: list[list], images: dict[int, list] | None = None, logo: bytes | None = None):
    """Each page a list of lines, from the top down, or of (x, y, text) placed where they say; an empty list is a
    page with no text. `images` puts images on the pages given, by their index: a JPEG's bytes for a 100 x 100 one,
    or (data, filter, size) for another. `logo` is a JPEG on every page, from one object."""
    images = images or {}
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"")  # the page tree, once its pages are known
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    def image(data: bytes, filter_name: str = "/DCTDecode", size: int = 100) -> int:
        return add(f"<< /Type /XObject /Subtype /Image /Width {size} /Height {size} /ColorSpace /DeviceRGB "
                   f"/BitsPerComponent 8 /Filter {filter_name} /Length {len(data)} >>\nstream\n".encode() + data
                   + b"\nendstream")

    shared = image(logo) if logo else None
    kids = []
    for index, lines in enumerate(pages):
        placed = [line if isinstance(line, tuple) else (72, 740 - 16 * n, line) for n, line in enumerate(lines)]
        content = "".join(f"BT /F1 12 Tf 1 0 0 1 {x} {y} Tm ({_escape(text)}) Tj ET\n" for x, y, text in placed)
        drawn = ([shared] if shared else []) + [image(*(spec if isinstance(spec, tuple) else (spec,)))
                                                 for spec in images.get(index, [])]
        xobjects = (" /XObject << " + " ".join(f"/Im{n} {obj} 0 R" for n, obj in enumerate(drawn, 1)) + " >>"
                    if drawn else "")
        content += "".join(f"q 100 0 0 100 300 300 cm /Im{n} Do Q\n" for n in range(1, len(drawn) + 1))
        stream = content.encode("latin-1")
        contents = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
        kids.append(add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R"
                        f" >>{xobjects} >> /Contents {contents} 0 R >>".encode()))
    objects[1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>").encode()
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path
