"""PDFs as Markdown: written here by hand (fixtures/pdfs.py), with pypdf adding a title, bookmarks, page labels and
passwords; made-up content only. Each page's text, laid out or not, a page with no text named, JPEGs kept once each, a
locked PDF refused, and a scan's pages described by an agent kept as an input."""

import pytest
from pypdf import PdfReader, PdfWriter

from bridge_kit.cli import main
from bridge_kit.documents import DocumentError, Options, ranges, read_document
from bridge_kit.markdown import read_markdown
from fixtures.pdfs import JPEG, pdf

TABLE = [(72, 700, "Field"), (200, 700, "Rule"), (72, 684, "vatNo"), (200, 684, "trim, then upper")]


def finish(path, title=None, bookmarks=(), labels=(), password=None):
    """The PDF with what pypdf's writer adds: a title, bookmarks as (title, page, parent's index), page labels as
    (from, to, style, start), a password."""
    writer = PdfWriter(clone_from=PdfReader(path))
    if title:
        writer.add_metadata({"/Title": title})
    added = []
    for name, page, parent in bookmarks:
        added.append(writer.add_outline_item(name, page, parent=None if parent is None else added[parent]))
    for first, last, style, start in labels:
        writer.set_page_label(first, last, style=style, start=start)
    if password is not None:
        writer.encrypt(user_password=password, owner_password="owner", algorithm="RC4-128")
    writer.write(path)
    return path


@pytest.fixture
def spec(tmp_path):
    path = pdf(tmp_path / "vat-spec.pdf", [["VAT registration spec", "Each entity reports its VAT numbers."], [], TABLE],
               images={1: [JPEG]})
    return finish(path, title="Microsoft Word - vat-spec.docx", bookmarks=[("Scope", 0, None), ("Fields", 2, 0)],
                  labels=[(0, 0, "/r", 1), (1, 2, "/D", 1)])


def test_a_spec_reads_page_by_page_with_its_title_bookmarks_and_labels(spec):
    document = read_document(spec)

    assert (document.kind, document.title) == ("pdf", "vat-spec")
    assert document.markdown == (
        "# vat-spec\n\n"
        "`vat-spec.pdf`: a PDF, 3 page(s), 1 of them without text.\n\n"
        "Contents, from its bookmarks:\n\n"
        "- Scope (page 1)\n"
        "  - Fields (page 3)\n\n"
        "## Page 1 (labelled i)\n\n"
        "VAT registration spec\n"
        "Each entity reports its VAT numbers.\n\n"
        "## Page 2 (labelled 1)\n\n"
        "_No text on this page: a scan or a picture._\n\n"
        "Images on this page: Image 1 (`image-1.jpg`).\n\n"
        "## Page 3 (labelled 2)\n\n"
        "Field Rule\n"
        "vatNo trim, then upper\n")
    assert document.images == {"image-1.jpg": JPEG}
    assert document.warnings == [
        "vat-spec.pdf has 1 page(s) with no text (2): a scan, or pictures. Copilot reads a PDF's pages itself: "
        "describe what they show, and keep it with bridge-kit inputs add --description",
        "vat-spec.pdf has 1 image(s), which bridge-kit can't read: bridge-kit inputs add keeps their JPEGs; Copilot "
        "can read them on the PDF's pages"]


def test_layout_keeps_a_table_s_columns_apart(spec):
    text = read_document(spec, Options(layout=True)).markdown

    assert ("## Page 3 (labelled 2)\n\n```text\n"
            "Field                       Rule\n"
            "vatNo                       trim, then upper\n```\n") in text


def test_a_logo_on_every_page_is_one_image_and_other_images_are_counted(tmp_path):
    path = pdf(tmp_path / "deck.pdf", [["One"], ["Two"]], logo=JPEG,
               images={1: [(b"x" * 40, "/FlateDecode", 100), (JPEG, "/DCTDecode", 16)]})

    document = read_document(path)

    assert "## Page 1\n\nOne\n\nImages on this page: Image 1 (`image-1.jpg`).\n\n" in document.markdown
    assert "## Page 2\n\nTwo\n\nImages on this page: Image 2 (not kept: not a JPEG).\n" in document.markdown
    assert document.images == {"image-1.jpg": JPEG}  # the 16-pixel icon is left out


def test_a_title_from_the_first_line_or_the_file_s_name(tmp_path):
    assert read_document(pdf(tmp_path / "notes.pdf", [[], ["Call notes, 27 October", "More"]])).title == (
        "Call notes, 27 October")
    assert read_document(pdf(tmp_path / "scan.pdf", [[]])).title == "scan"


def test_a_pdf_locked_by_a_password_is_refused_and_one_with_an_owner_s_only_is_read(tmp_path):
    locked = finish(pdf(tmp_path / "locked.pdf", [["Secret"]]), password="secret")
    owner = finish(pdf(tmp_path / "owner.pdf", [["Open to read"]]), password="")

    with pytest.raises(DocumentError, match="locked.pdf is locked by a password: open it, print it to a new PDF"):
        read_document(locked)
    assert "Open to read" in read_document(owner).markdown


def test_a_broken_pdf_is_refused(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nnot really\n")

    with pytest.raises(DocumentError, match="broken.pdf can't be read as a PDF .*: open it and print it to a new PDF"):
        read_document(path)


def test_personal_data_is_named_by_its_pages(tmp_path):
    path = pdf(tmp_path / "contacts.pdf", [["Ask anna.example@example.com"], ["Nothing here"], ["Or bo@example.com"]])

    assert read_document(path).warnings == [
        "contacts.pdf (page(s) 1, 3) has values that look like personal data (2 email addresses): check before "
        "committing it"]


@pytest.mark.parametrize("numbers, shown", [([1], "1"), ([1, 2, 3, 7], "1–3, 7"), ([2, 4, 5], "2, 4–5")])
def test_page_ranges(numbers, shown):
    assert ranges(numbers) == shown


def test_a_scan_s_pages_described_by_an_agent_are_kept_with_its_text_and_images(spec, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    description = tmp_path / "page-2.md"
    description.write_text("Page 2 is a diagram: upstream -> collector -> model.\n", encoding="utf-8")

    assert main(["inputs", "add", str(spec), "--work-item", "REQ-341", "--description", str(description),
                 "--by", "spec-explorer"]) == 0

    text = (repo / "work/REQ-341/inputs/01-vat-spec.md").read_text(encoding="utf-8")
    header = read_markdown(text).front_matter
    assert (header["kind"], header["described_by"], header["images"]) == (
        "pdf", "spec-explorer", ".work/sources/REQ-341/01-vat-spec-images")
    assert text.endswith("## Read from its pages' images, by spec-explorer\n\n"
                         "Page 2 is a diagram: upstream -> collector -> model.\n")
    assert (repo / header["images"] / "image-1.jpg").read_bytes() == JPEG
    assert capsys.readouterr().err.startswith("Warning: vat-spec.pdf has 1 page(s) with no text (2)")
