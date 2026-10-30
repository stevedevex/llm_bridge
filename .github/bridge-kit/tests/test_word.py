"""Word documents as Markdown: one made with python-docx on Word's own template (its heading and list styles, its
numbering), and others written as their XML for what python-docx can't make: numbered headings, tracked changes,
footnotes and endnotes, links, hidden text, images, text boxes, charts, merged cells. Made-up content only."""

import json
import zipfile

import docx
import pytest

from bridge_kit.cli import main
from bridge_kit.documents import DocumentError, read_document
from bridge_kit.documents.word import _format
from bridge_kit.markdown import read_markdown
from fixtures.office import docx as write_docx
from fixtures.office import image, p, r, style

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_a_document_on_word_s_own_template_reads_as_written(tmp_path):
    document = docx.Document()
    document.core_properties.title = "VAT registration: upstream spec notes"
    document.add_heading("Scope", level=1)
    paragraph = document.add_paragraph("Each legal entity reports its VAT numbers. ")
    paragraph.add_run("Old rule: copy as is.").font.strike = True
    document.add_heading("Fields", level=2)
    document.add_paragraph("vatNo, the number", style="List Number")
    document.add_paragraph("ctry, the country", style="List Number")
    document.add_paragraph("A note", style="List Bullet")
    table = document.add_table(rows=3, cols=3)
    for row, values in enumerate([["Field", "Target", "Rule"], ["vatNo", "vatRegistrations[].number", "trim | upper"],
                                  ["ctry", "vatRegistrations[].country", "lookup"]]):
        for col, value in enumerate(values):
            table.cell(row, col).text = value
    paragraph = document.add_paragraph("Ask the upstream team about ")
    document.add_comment([paragraph.add_run("time zones")], text="Which time zone do their dates use?",
                         author="Anna Example", initials="AE")
    document.save(tmp_path / "spec-notes.docx")

    read = read_document(tmp_path / "spec-notes.docx")

    assert (read.kind, read.title) == ("docx", "VAT registration: upstream spec notes")
    assert read.markdown == (
        "# VAT registration: upstream spec notes\n\n"
        "`spec-notes.docx`: a Word document, with 1 table(s), 1 comment(s).\n\n"
        "## Scope\n\n"
        "Each legal entity reports its VAT numbers. ~~Old rule: copy as is.~~\n\n"
        "### Fields\n\n"
        "- 1. vatNo, the number\n"
        "- 2. ctry, the country\n"
        "- A note\n\n"
        "Table 1:\n\n"
        "| Row | Field | Target | Rule |\n"
        "|---|---|---|---|\n"
        "| 2 | vatNo | vatRegistrations[].number | trim \\| upper |\n"
        "| 3 | ctry | vatRegistrations[].country | lookup |\n\n"
        "Ask the upstream team about time zones [comment 1]\n\n"
        "## Comments\n\n"
        "- Comment 1, by Anna Example on “time zones”: Which time zone do their dates use?\n")
    assert read.warnings == [
        "spec-notes.docx has 1 comment(s), listed at the end with the text they're on: open questions, perhaps",
        "spec-notes.docx has struck-through text, shown as ~~text~~: often something dropped"]


NUMBERING = (
    '<w:abstractNum w:abstractNumId="1">'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1"/></w:lvl>'
    '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2"/></w:lvl>'
    '</w:abstractNum>'
    '<w:abstractNum w:abstractNumId="2">'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1)"/></w:lvl>'
    '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerRoman"/><w:lvlText w:val="%2."/></w:lvl>'
    '</w:abstractNum>'
    '<w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>'
    '<w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>'
    '<w:num w:numId="3"><w:abstractNumId w:val="2"/>'
    '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>')
STYLES = (
    style("Heading1", "heading 1", '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>')
    + style("Heading2", "heading 2", '<w:basedOn w:val="Heading1"/>'
                                     '<w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>')
    + style("Requirement", "Requirement", '<w:basedOn w:val="Heading2"/>')
    + style("Title", "Title"))


def test_numbered_headings_and_lists_carry_their_labels_as_word_shows_them(tmp_path):
    body = (p("Spec notes", style="Title") + p("Scope", style="Heading1") + p("Sources", style="Heading2")
            + p("The upstream's REST API", num=(2, 0)) + p("Its v2 endpoint", num=(2, 1))
            + p("Its v3 endpoint", num=(2, 1)) + p("The nightly file", num=(2, 0))
            + p("Rules", style="Heading1") + p("REQ: VAT numbers are trimmed", style="Requirement")
            + p("A list restarted", num=(3, 0)))
    path = write_docx(tmp_path / "notes.docx", body, styles=STYLES, numbering=NUMBERING)

    read = read_document(path)

    assert read.title == "Spec notes"
    assert read.markdown.split("\n\n", 2)[2] == (
        "**Spec notes**\n\n"
        "## 1 Scope\n\n"
        "### 1.1 Sources\n\n"
        "- a) The upstream's REST API\n"
        "  - i. Its v2 endpoint\n"
        "  - ii. Its v3 endpoint\n"
        "- b) The nightly file\n\n"
        "## 2 Rules\n\n"
        "### 2.1 REQ: VAT numbers are trimmed\n\n"
        "- a) A list restarted\n")


def test_changes_notes_links_comments_images_text_boxes_and_charts(tmp_path):
    text_box = ('<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wp:anchor>'
                '<wp:docPr id="2" name="Text Box 1"/><a:graphic><a:graphicData><wps:wsp><wps:txbx><w:txbxContent>'
                + p("Owner: data team") + '</w:txbxContent></wps:txbx></wps:wsp></a:graphicData></a:graphic>'
                '</wp:anchor></w:drawing></mc:Choice><mc:Fallback><w:pict><v:textbox><w:txbxContent>'
                + p("Owner: data team") + '</w:txbxContent></v:textbox></w:pict></mc:Fallback>'
                '</mc:AlternateContent></w:r>')
    chart = ('<w:r><w:drawing><wp:inline><wp:docPr id="3" name="Chart 1"/><a:graphic><a:graphicData>'
             '<c:chart r:id="rId3"/></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    body = (p("The upstream sends ",
              '<w:ins w:id="1" w:author="Anna Example" w:date="2026-10-20T10:00:00Z">' + r("monthly ") + "</w:ins>",
              '<w:del w:id="2" w:author="Bo Example" w:date="2026-10-21T09:00:00Z"><w:r><w:delText>weekly '
              "</w:delText></w:r></w:del>", "files.", '<w:r><w:footnoteReference w:id="2"/></w:r>')
            + p('<w:hyperlink r:id="rId2">' + r("the upstream's spec") + "</w:hyperlink>", " and ",
                r("an internal note ", "<w:vanish/>"), "its codes.")
            + p("Flow: ", image("rId1", "Upstream to collector to model"))
            + p(text_box)
            + p("Volumes: ", chart)
            + p('<w:commentRangeStart w:id="0"/>', "Dates are in UTC", '<w:commentRangeEnd w:id="0"/>',
                '<w:r><w:commentReference w:id="0"/></w:r>', '<w:r><w:endnoteReference w:id="1"/></w:r>'))
    path = write_docx(
        tmp_path / "notes.docx", body,
        footnotes=('<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                   '<w:footnote w:id="2"><w:p><w:r><w:footnoteRef/></w:r>' + r(" From the call of 27 October.")
                   + "</w:p></w:footnote>"),
        endnotes='<w:endnote w:id="1">' + p("See the onboarding checklist.") + "</w:endnote>",
        comments='<w:comment w:id="0" w:author="Anna Example">' + p("Confirm with the upstream team") + "</w:comment>",
        rels=(("rId1", "media/image1.png", False), ("rId2", "https://example.com/spec", True),
              ("rId3", "charts/chart1.xml", False)),
        media={"image1.png": PNG})

    read = read_document(path)

    assert read.markdown == (
        "# notes\n\n"
        "`notes.docx`: a Word document, with 1 comment(s), 2 tracked change(s), 1 image(s).\n\n"
        "The upstream sends monthly files.[^2]\n\n"
        "[the upstream's spec](https://example.com/spec) and its codes.\n\n"
        "Flow: [Image 1: Upstream to collector to model]\n\n"
        "[Text box: Owner: data team]\n\n"
        "Volumes: [A chart, not read]\n\n"
        "Dates are in UTC [comment 1][^e1]\n\n"
        "## Footnotes and endnotes\n\n"
        "[^2]: From the call of 27 October.\n"
        "[^e1]: See the onboarding checklist.\n\n"
        "## Comments\n\n"
        "- Comment 1, by Anna Example on “Dates are in UTC”: Confirm with the upstream team\n\n"
        "## Tracked changes\n\n"
        "- Inserted by Anna Example on 2026-10-20: “monthly”\n"
        "- Deleted by Bo Example on 2026-10-21: “weekly”\n\n"
        "## Images\n\n"
        "- Image 1: `image-1.png`: Upstream to collector to model\n")
    assert read.images == {"image-1.png": PNG}
    assert [w.split(":")[0] for w in read.warnings] == [
        "notes.docx has 2 tracked change(s), not yet accepted", "notes.docx has 1 comment(s), listed at the end with "
        "the text they're on", "notes.docx has 1 image(s), which bridge-kit can't read", 
        "notes.docx has 1 chart(s) and 0 SmartArt diagram(s), not read"]


def test_merged_cells_are_spread_and_a_table_in_a_cell_is_flattened(tmp_path):
    inner = "<w:tbl><w:tr><w:tc>" + p("DE") + "</w:tc><w:tc>" + p("Germany") + "</w:tc></w:tr></w:tbl>"
    body = ("<w:tbl>"
            "<w:tr><w:tc>" + p("Field") + "</w:tc><w:tc>" + p("Rule") + "</w:tc><w:tc>" + p("Notes") + "</w:tc></w:tr>"
            "<w:tr><w:tc>" + p("vatNo") + '</w:tc><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>' + p("copy")
            + "</w:tc></w:tr>"
            '<w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr>' + p("ctry") + "</w:tc><w:tc>" + p("lookup")
            + "</w:tc><w:tc>" + inner + "</w:tc></w:tr>"
            "<w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr>" + p("") + "</w:tc><w:tc>" + p("upper") + "</w:tc><w:tc>"
            + p("a | b") + p("second line") + "</w:tc></w:tr>"
            "</w:tbl>")

    read = read_document(write_docx(tmp_path / "table.docx", body))

    assert ("Table 1:\n\n| Row | Field | Rule | Notes |\n|---|---|---|---|\n"
            "| 2 | vatNo | copy | copy |\n"
            "| 3 | ctry | lookup | DE \\| Germany |\n"
            "| 4 | ctry | upper | a \\| b<br>second line |\n") in read.markdown


def test_personal_data_in_the_text_and_in_a_table_s_column(tmp_path):
    body = (p("Write to anna.example@example.com") + "<w:tbl><w:tr><w:tc>" + p("Field") + "</w:tc><w:tc>"
            + p("Contact") + "</w:tc></w:tr><w:tr><w:tc>" + p("vatNo") + "</w:tc><w:tc>" + p("bo@example.com")
            + "</w:tc></w:tr></w:tbl>")

    read = read_document(write_docx(tmp_path / "contacts.docx", body))

    assert read.warnings == [
        "contacts.docx's text has values that look like personal data (1 email address): check before committing it",
        "Table 1, column Contact has values that look like personal data (1 email address): check before committing "
        "it"]


@pytest.mark.parametrize("parts, message", [
    ({"word/other.xml": "<x/>"}, "has no word/document.xml: it isn't a Word document inside"),
    ({"word/document.xml": '<!DOCTYPE x [<!ENTITY a "a">]><x/>'}, "declares a DTD in word/document.xml"),
    ({"word/document.xml": "<w:document"}, "word/document.xml isn't well-formed"),
])
def test_a_document_that_isn_t_word_inside_is_refused(tmp_path, parts, message):
    path = tmp_path / "broken.docx"
    with zipfile.ZipFile(path, "w") as z:
        for name, content in parts.items():
            z.writestr(name, content)

    with pytest.raises(DocumentError, match=message):
        read_document(path)


@pytest.mark.parametrize("n, fmt, shown", [(4, "lowerRoman", "iv"), (9, "upperRoman", "IX"), (27, "lowerLetter", "aa"),
                                            (2, "upperLetter", "B"), (3, "decimalZero", "03"), (12, "ordinal", "12")])
def test_list_numbers_in_each_format(n, fmt, shown):
    assert _format(n, fmt) == shown


def test_a_document_s_images_are_kept_beside_its_input(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    path = write_docx(tmp_path / "flow.docx", p("Flow: ", image("rId1", "The flow")),
                      rels=(("rId1", "media/image1.png", False),), media={"image1.png": PNG})

    assert main(["doc", "read", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["images"] == ["image-1.png"]

    assert main(["inputs", "add", str(path), "--work-item", "REQ-341"]) == 0
    header = read_markdown((repo / "work/REQ-341/inputs/01-flow.md").read_text(encoding="utf-8")).front_matter
    assert header["images"] == ".work/sources/REQ-341/01-flow-images"
    assert (repo / header["images"] / "image-1.png").read_bytes() == PNG
    assert (repo / header["raw"]).read_bytes() == path.read_bytes()
