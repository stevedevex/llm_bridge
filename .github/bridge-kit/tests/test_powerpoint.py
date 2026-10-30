"""PowerPoint decks as Markdown: made with python-pptx on PowerPoint's own template (its layouts, whose placeholders
give the slides' shapes their positions), with a SmartArt diagram written into one as its XML. Made-up content only.
Slides in order, shapes in reading order, bullets, tables, groups, pictures once each, charts named, notes, hidden
slides."""

import io
import re
import zipfile

import pytest
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.oxml.ns import qn
from pptx.util import Inches

from bridge_kit.cli import main
from bridge_kit.documents import DocumentError, read_document
from bridge_kit.markdown import read_markdown


def png(colour: str = "blue") -> io.BytesIO:
    data = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(data, "PNG")
    data.seek(0)
    return data


def onboarding(path):
    """A title slide, a slide of bullets with a picture, a text box and notes, one with a table and a chart, and a
    hidden one."""
    deck = Presentation()
    deck.core_properties.title = "VAT onboarding"
    first = deck.slides.add_slide(deck.slide_layouts[0])
    first.shapes.title.text = "VAT registration"
    first.placeholders[1].text = "Onboarding the upstream"
    flow = deck.slides.add_slide(deck.slide_layouts[1])
    flow.shapes.title.text = "Data flow"
    body = flow.placeholders[1].text_frame
    body.text = "The upstream sends a file nightly"
    deeper = body.add_paragraph()
    deeper.text, deeper.level = "Validated on arrival", 1
    flow.shapes.add_textbox(Inches(6), Inches(6), Inches(3), Inches(1)).text_frame.text = "Owner: data team"
    flow.shapes.add_picture(png(), Inches(1), Inches(5))._element.nvPicPr.cNvPr.set("descr", "The flow, drawn")
    flow.notes_slide.notes_text_frame.text = "Mention the time zone."
    fields = deck.slides.add_slide(deck.slide_layouts[5])
    fields.shapes.title.text = "Fields"
    table = fields.shapes.add_table(3, 2, Inches(1), Inches(2), Inches(6), Inches(2)).table
    for row, values in enumerate([["Field", "Rule"], ["vatNo", "trim | upper"], ["ctry", "lookup"]]):
        for col, value in enumerate(values):
            table.cell(row, col).text = value
    data = CategoryChartData()
    data.categories = ["Oct"]
    data.add_series("Volume", (10,))
    fields.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(4.5), Inches(4), Inches(2), data)
    old = deck.slides.add_slide(deck.slide_layouts[5])
    old.shapes.title.text = "Old plan"
    old._element.set("show", "0")
    deck.save(path)
    return path


def test_a_deck_reads_slide_by_slide_in_reading_order(tmp_path):
    document = read_document(onboarding(tmp_path / "onboarding.pptx"))

    assert (document.kind, document.title) == ("pptx", "VAT onboarding")
    assert document.markdown == (
        "# VAT onboarding\n\n"
        "`onboarding.pptx`: a PowerPoint deck, 4 slide(s), 1 of them hidden.\n\n"
        "## Slide 1: VAT registration\n\n"
        "Onboarding the upstream\n\n"
        "## Slide 2: Data flow\n\n"
        "- The upstream sends a file nightly\n"
        "  - Validated on arrival\n\n"
        "[Image 1: The flow, drawn]\n\n"
        "Owner: data team\n\n"
        "Speaker notes:\n\n"
        "Mention the time zone.\n\n"
        "## Slide 3: Fields\n\n"
        "Table 1:\n\n"
        "| Row | Field | Rule |\n"
        "|---|---|---|\n"
        "| 2 | vatNo | trim \\| upper |\n"
        "| 3 | ctry | lookup |\n\n"
        "[A chart, not read]\n\n"
        "## Slide 4: Old plan (hidden)\n\n"
        "_No text on this slide._\n\n"
        "## Images\n\n"
        "- Image 1: `image-1.png`: The flow, drawn\n")
    assert list(document.images) == ["image-1.png"] and document.images["image-1.png"].startswith(b"\x89PNG")
    assert [w.split(":")[0] for w in document.warnings] == [
        "onboarding.pptx has 1 hidden slide(s) (4)", "onboarding.pptx has 1 image(s), which bridge-kit can't read",
        "onboarding.pptx has 1 chart(s) and 0 video(s) or embedded object(s), not read"]


def test_shapes_level_with_each_other_read_left_to_right_and_a_group_in_its_own_order(tmp_path):
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])  # blank
    for left, top, text in ((5, 1.05, "Right, a little lower"), (1, 1, "Left"), (1, 4, "Below")):
        slide.shapes.add_textbox(Inches(left), Inches(top), Inches(3), Inches(1)).text_frame.text = text
    group = slide.shapes.add_group_shape()
    for left, text in ((4, "Group, second"), (1, "Group, first")):
        group.shapes.add_textbox(Inches(left), Inches(6), Inches(2), Inches(1)).text_frame.text = text
    deck.save(tmp_path / "order.pptx")

    text = read_document(tmp_path / "order.pptx").markdown

    assert ("## Slide 1\n\nLeft\n\nRight, a little lower\n\nBelow\n\nGroup, first\n\nGroup, second\n") in text


def test_bullets_numbers_links_and_struck_text(tmp_path):
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Rules"
    body = slide.placeholders[1].text_frame
    body.text = "A bullet"
    plain = body.add_paragraph()
    plain.text = "Not a bullet"
    etree.SubElement(plain._p.get_or_add_pPr(), qn("a:buNone"))
    box = slide.shapes.add_textbox(Inches(1), Inches(5), Inches(6), Inches(2)).text_frame
    box.text = "Trim it"
    second = box.add_paragraph()
    second.text = "Upper-case it"
    for paragraph in box.paragraphs:
        etree.SubElement(paragraph._p.get_or_add_pPr(), qn("a:buAutoNum"), type="arabicPeriod")
    link = box.add_paragraph().add_run()
    link.text = "the upstream's spec"
    link.hyperlink.address = "https://example.com/spec"
    old = box.add_paragraph().add_run()
    old.text = "Copy it as is"
    old.font._rPr.set("strike", "sngStrike")
    deck.save(tmp_path / "rules.pptx")

    document = read_document(tmp_path / "rules.pptx")

    assert ("## Slide 1: Rules\n\n- A bullet\nNot a bullet\n\n- 1. Trim it\n- 2. Upper-case it\n"
            "[the upstream's spec](https://example.com/spec)\n~~Copy it as is~~\n") in document.markdown
    assert document.warnings == ["rules.pptx has struck-through text, shown as ~~text~~: often something dropped"]


def test_merged_table_cells_are_spread(tmp_path):  # python-pptx moves a merged-away cell's text into the merged one
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    table = slide.shapes.add_table(3, 3, Inches(1), Inches(1), Inches(6), Inches(2)).table
    for row, values in enumerate([["Field", "Rule", "Notes"], ["vatNo", "copy", ""], ["ctry", "lookup", "ISO"]]):
        for col, value in enumerate(values):
            table.cell(row, col).text = value
    table.cell(1, 1).merge(table.cell(1, 2))
    table.cell(1, 0).merge(table.cell(2, 0))
    deck.save(tmp_path / "merged.pptx")

    text = read_document(tmp_path / "merged.pptx").markdown

    assert "| 2 | vatNo<br>ctry | copy | copy |\n| 3 | vatNo<br>ctry | lookup | ISO |\n" in text


def test_a_smartart_diagram_s_text_is_a_list(tmp_path):
    deck = Presentation()
    deck.slides.add_slide(deck.slide_layouts[6])
    deck.save(tmp_path / "diagram.pptx")
    with zipfile.ZipFile(tmp_path / "diagram.pptx") as z:
        parts = {name: z.read(name) for name in z.namelist()}
    frame = ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="9" name="Diagram 1"/><p:cNvGraphicFramePr/><p:nvPr/>'
             '</p:nvGraphicFramePr><p:xfrm><a:off x="0" y="0"/><a:ext cx="1" cy="1"/></p:xfrm><a:graphic>'
             '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/diagram"><dgm:relIds '
             'xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" r:dm="rId90" r:lo="rId91" '
             'r:qs="rId92" r:cs="rId93"/></a:graphicData></a:graphic></p:graphicFrame>')
    parts["ppt/slides/slide1.xml"] = parts["ppt/slides/slide1.xml"].replace(b"</p:spTree>", frame.encode()
                                                                            + b"</p:spTree>")
    parts["ppt/slides/_rels/slide1.xml.rels"] = parts["ppt/slides/_rels/slide1.xml.rels"].replace(
        b"</Relationships>", b'<Relationship Id="rId90" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                             b'relationships/diagramData" Target="../diagrams/data1.xml"/></Relationships>')
    points = "".join(f'<dgm:pt modelId="{n}"><dgm:t><a:p><a:r><a:t>{text}</a:t></a:r></a:p></dgm:t></dgm:pt>'
                     for n, text in enumerate(("Upstream", "Collector", "Model"), 1))
    parts["ppt/diagrams/data1.xml"] = (
        '<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><dgm:ptLst><dgm:pt modelId="0" type="doc"/>'
        f'{points}<dgm:pt modelId="9" type="parTrans"><dgm:t><a:p><a:r><a:t>link</a:t></a:r></a:p></dgm:t></dgm:pt>'
        "</dgm:ptLst></dgm:dataModel>").encode()
    with zipfile.ZipFile(tmp_path / "diagram.pptx", "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)

    text = read_document(tmp_path / "diagram.pptx").markdown

    assert "## Slide 1\n\nDiagram (SmartArt):\n\n- Upstream\n- Collector\n- Model\n" in text


def test_a_picture_on_two_slides_is_one_image(tmp_path):
    deck = Presentation()
    for _ in range(2):
        deck.slides.add_slide(deck.slide_layouts[6]).shapes.add_picture(png("red"), Inches(1), Inches(1))
    deck.save(tmp_path / "logo.pptx")

    document = read_document(tmp_path / "logo.pptx")

    assert len(document.images) == 1 and document.markdown.count("[Image 1]") == 2  # its file's name isn't alt text


def test_personal_data_by_slide_and_by_table_column(tmp_path):
    deck = Presentation()
    first = deck.slides.add_slide(deck.slide_layouts[6])
    first.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame.text = "Ask anna.example@example.com"
    second = deck.slides.add_slide(deck.slide_layouts[6])
    table = second.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(1)).table
    for (row, col), value in {(0, 0): "Field", (0, 1): "Contact", (1, 0): "vatNo", (1, 1): "bo@example.com"}.items():
        table.cell(row, col).text = value
    deck.save(tmp_path / "contacts.pptx")

    assert read_document(tmp_path / "contacts.pptx").warnings == [
        "contacts.pptx (slide(s) 1) has values that look like personal data (1 email address): check before "
        "committing it",
        "Table 1, column Contact has values that look like personal data (1 email address): check before committing "
        "it"]


def test_a_deck_that_isn_t_powerpoint_inside_is_refused(tmp_path):
    with zipfile.ZipFile(tmp_path / "broken.pptx", "w") as z:
        z.writestr("ppt/other.xml", "<x/>")

    with pytest.raises(DocumentError, match="has no ppt/presentation.xml: it isn't a PowerPoint deck inside"):
        read_document(tmp_path / "broken.pptx")


def test_a_deck_s_images_are_kept_beside_its_input(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))

    assert main(["inputs", "add", str(onboarding(tmp_path / "onboarding.pptx")), "--work-item", "REQ-341"]) == 0

    assert capsys.readouterr().out == "Added work/REQ-341/inputs/01-onboarding.md: VAT onboarding\n"
    header = read_markdown((repo / "work/REQ-341/inputs/01-onboarding.md").read_text(encoding="utf-8")).front_matter
    assert header["kind"] == "pptx" and re.fullmatch(r"\.work/sources/REQ-341/01-onboarding-images", header["images"])
    assert (repo / header["images"] / "image-1.png").read_bytes().startswith(b"\x89PNG")
