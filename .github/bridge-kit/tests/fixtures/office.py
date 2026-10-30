"""Word documents written as their XML, for what python-docx can't make: tracked changes, footnotes, numbered
headings, images, text boxes, charts. Only the parts the reader needs, as Word writes them.

    docx(path, body=p("Hello"), styles=..., numbering=..., rels=[("rId1", "media/image1.png", False)], ...)
"""

from __future__ import annotations

import zipfile
from xml.sax.saxutils import escape

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:v="urn:schemas-microsoft-com:vml"')
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def r(text: str, props: str = "") -> str:
    """A run of text; `props` is its run properties' XML, e.g. <w:strike/>."""
    return f'<w:r>{f"<w:rPr>{props}</w:rPr>" if props else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def p(*content: str, style: str | None = None, num: tuple[int, int] | None = None) -> str:
    """A paragraph of runs (plain strings become runs), with a style and a list's (numId, level)."""
    props = (f'<w:pStyle w:val="{style}"/>' if style else "") + (
        f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>' if num else "")
    runs = "".join(c if c.startswith("<") else r(c) for c in content)
    return f'<w:p>{f"<w:pPr>{props}</w:pPr>" if props else ""}{runs}</w:p>'


def style(style_id: str, name: str, extra: str = "") -> str:
    return f'<w:style w:type="paragraph" w:styleId="{style_id}"><w:name w:val="{name}"/>{extra}</w:style>'


def image(rid: str, alt: str, name: str = "Picture 1") -> str:
    return ('<w:r><w:drawing><wp:inline><wp:extent cx="1" cy="1"/>'
            f'<wp:docPr id="1" name="{name}" descr="{escape(alt)}"/><a:graphic><a:graphicData>'
            f'<pic:pic><pic:blipFill><a:blip r:embed="{rid}"/></pic:blipFill></pic:pic>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')


def docx(path, body: str, *, styles: str = "", numbering: str = "", footnotes: str = "", endnotes: str = "",
         comments: str = "", rels: tuple = (), media: dict | None = None, title: str = ""):
    relationships = "".join(f'<Relationship Id="{rid}" Type="t" Target="{escape(target)}"'
                            + (' TargetMode="External"' if external else "") + "/>"
                            for rid, target, external in rels)
    parts = {
        "[Content_Types].xml": XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "word/document.xml": f"{XML}<w:document {NS}><w:body>{body}</w:body></w:document>",
        "word/_rels/document.xml.rels": XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                                              f'relationships">{relationships}</Relationships>',
    }
    for name, content, root in (("styles", styles, "styles"), ("numbering", numbering, "numbering"),
                                ("footnotes", footnotes, "footnotes"), ("endnotes", endnotes, "endnotes"),
                                ("comments", comments, "comments")):
        if content:
            parts[f"word/{name}.xml"] = f"{XML}<w:{root} {NS}>{content}</w:{root}>"
    if title:
        parts["docProps/core.xml"] = (XML + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/'
                                      '2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                      f"<dc:title>{escape(title)}</dc:title></cp:coreProperties>")
    for name, data in (media or {}).items():
        parts[f"word/media/{name}"] = data
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path
