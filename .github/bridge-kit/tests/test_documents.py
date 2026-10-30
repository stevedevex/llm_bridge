"""Documents as Markdown, and kept as a work item's inputs: each kind recognised by its extension and first bytes, the
old formats and locked files refused with what to do; text and CSV read; long tables cut; values that look like personal
data counted, never shown; an image kept with what an agent says it shows. Every file is made here, with made-up
content."""

import io
import json

import pytest

from bridge_kit.cli import main
from bridge_kit.documents import COMPOUND, ZIP, DocumentError, Options, kind_of, read_document
from bridge_kit.documents.personal import count
from bridge_kit.documents.tables import column_letter
from bridge_kit.markdown import read_markdown

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
ROUGH = ("Source field;Target attribute;Rule;\n"
         "legalEntityId;legalEntity.id;copy;\n"
         "vatNo;vatRegistrations[].number;\"copy | trim\nthen upper\";\n"
         ";;;\n"
         "ctry;vatRegistrations[].country;;lookup\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A BA repo, and a folder of files outside it, as a BA's downloads."""
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    files = tmp_path / "downloads"
    files.mkdir()
    return {"repo": repo, "files": files}


def write(folder, name: str, content: str | bytes):
    path = folder / name
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


# --- kinds, and what's refused --------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, content, message", [
    ("spec.doc", b"x", "spec.doc is the old Word format: open it in Word and save it as .docx"),
    ("rough.xls", b"x", "rough.xls is the old Excel format: open it in Excel and save it as .xlsx"),
    ("deck.ppt", b"x", "deck.ppt is the old PowerPoint format: open it in PowerPoint and save it as .pptx"),
    ("reply.msg", b"x", "reply.msg isn't an Outlook message inside"),
    ("scan.tiff", b"x", "scan.tiff is an image format Copilot doesn't take: save it as PNG"),
    ("spec.docx", COMPOUND + b"\x00" * 100, "spec.docx is locked, by a password or a sensitivity label"),
    ("rough.xlsx", b"Source field,Target\n", "rough.xlsx isn't an Excel workbook inside"),
    ("spec.pdf", b"<html>", "spec.pdf isn't a PDF inside"),
    ("board.png", b"<svg/>", "board.png isn't an image inside"),
    ("bundle.zip", ZIP, "bridge-kit doesn't read .zip files: it reads .csv, .docx, .eml"),
])
def test_the_old_formats_locked_files_and_unknown_kinds_are_refused_with_what_to_do(repo, name, content, message):
    with pytest.raises(DocumentError) as refused:
        read_document(write(repo["files"], name, content))

    assert str(refused.value).startswith(message)


@pytest.mark.parametrize("name, content, kind", [
    ("notes.txt", "Hello", "text"), ("NOTES.MD", "# Notes", "text"), ("rough.tsv", "a\tb", "csv"),
    ("spec.docx", ZIP, "docx"), ("rough.xlsm", ZIP, "xlsx"), ("spec.pdf", b"%PDF-1.7\n", "pdf"),
    ("board.jpg", b"\xff\xd8\xff\xe0", "image"), ("board.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image"),
])
def test_each_kind_by_its_extension_and_first_bytes(repo, name, content, kind):
    assert kind_of(write(repo["files"], name, content)) == kind


def test_an_image_is_for_the_agent_to_read(repo):
    with pytest.raises(DocumentError, match="board.png is an image, which bridge-kit can't read: read it yourself"):
        read_document(write(repo["files"], "board.png", PNG))


# --- text and CSV ---------------------------------------------------------------------------------------------------

def test_text_comes_as_it_is_titled_by_its_first_heading_or_line(repo):
    markdown = read_document(write(repo["files"], "notes.md", "Intro line\n# VAT registration\r\n\nBody\n"))
    plain = read_document(write(repo["files"], "call.txt", "\n  Call with the upstream team, 27 Oct\nWe agreed\n"))

    assert (markdown.title, markdown.markdown) == ("VAT registration", "Intro line\n# VAT registration\n\nBody\n")
    assert (plain.kind, plain.title, plain.warnings) == ("text", "Call with the upstream team, 27 Oct", [])


def test_text_that_isn_t_utf_8_is_read_as_windows_1252_with_a_warning(repo):
    document = read_document(write(repo["files"], "notes.txt", "Café règles".encode("cp1252")))

    assert document.markdown == "Café règles"
    assert document.warnings == ["notes.txt isn't UTF-8: read as Windows-1252, so check its accented letters"]


def test_a_csv_is_a_table_with_its_row_numbers_and_column_letters(repo):
    document = read_document(write(repo["files"], "rough-mapping.csv", ROUGH))

    assert document.kind == "csv" and document.title == "rough-mapping"
    assert document.markdown == (
        "# rough-mapping\n\n"
        "`rough-mapping.csv`: a CSV file, 4 column(s), 3 row(s) below its heading row (row 1).\n\n"
        "| Row | Source field (A) | Target attribute (B) | Rule (C) | (D) |\n"
        "|---|---|---|---|---|\n"
        "| 2 | legalEntityId | legalEntity.id | copy |  |\n"
        "| 3 | vatNo | vatRegistrations[].number | copy \\| trim<br>then upper |  |\n"
        "| 5 | ctry | vatRegistrations[].country |  | lookup |\n")  # a record per row, as a spreadsheet has


def test_a_tsv_and_an_empty_csv(repo):
    tsv = read_document(write(repo["files"], "codes.tsv", "Code\tMeaning\nDE\tGermany\n"))
    empty = read_document(write(repo["files"], "empty.csv", "\n,,\n"))

    assert "a TSV file, 2 column(s), 1 row(s)" in tsv.markdown and "| 2 | DE | Germany |" in tsv.markdown
    assert empty.markdown == "# empty\n\n`empty.csv`: a CSV file with nothing in it.\n"


@pytest.mark.parametrize("options, shown, note", [
    (Options(), 200, "The first 200 of 501 rows shown: --rows all shows every one."),
    (Options(rows=10), 10, "The first 10 of 501 rows shown"),
    (Options(rows="all"), 501, None),
    (Options(headers_only=True), 0, "The heading row only (--headers-only): 501 row(s) not shown."),
])
def test_a_long_table_shows_its_first_rows_unless_asked(repo, options, shown, note):
    path = write(repo["files"], "records.csv", "Id,Amount\n" + "".join(f"{n},{n * 10}\n" for n in range(1, 502)))

    markdown = read_document(path, options).markdown

    assert markdown.count("\n| ") - 1 == shown
    assert (note in markdown) if note else "rows shown" not in markdown


def test_short_tables_aren_t_cut():
    from bridge_kit.documents.tables import limit

    assert limit(list(range(500)), Options()) == (list(range(500)), "")


# --- personal data --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, found", [
    ("Ask anna.example@example.com or ops@example.co.uk", {"email": 2}),
    ("IBAN GB82 WEST 1234 5698 7654 32 AND ALSO DE89370400440532013000", {"iban": 2}),
    ("GB82 WEST 1234 5698 7654 33", {}),  # its check digits don't fit
    ("Card 4111 1111 1111 1111, and 4111-1111-1111-1112", {"card": 1}),
    ("On 2026-10-28 12:00, call +44 20 7946 0958; order 123456789012", {}),
])
def test_what_looks_like_personal_data_is_counted_by_its_checks(text, found):
    assert {k: v for k, v in count(text).items() if v} == found


def test_a_warning_names_the_column_and_never_the_value(repo):
    path = write(repo["files"], "owners.csv", "Field,Owner\nvatNo,anna.example@example.com\nctry,bo@example.com\n")

    document = read_document(path)

    assert document.warnings == ["Column Owner (B) has values that look like personal data (2 email addresses): "
                                 "check before committing it"]
    assert "example.com" not in " ".join(document.warnings)
    assert read_document(path, Options(headers_only=True)).warnings == []  # only what the Markdown shows


@pytest.mark.parametrize("index, letters", [(0, "A"), (25, "Z"), (26, "AA"), (701, "ZZ"), (702, "AAA")])
def test_column_letters(index, letters):
    assert column_letter(index) == letters


# --- bridge-kit doc read ----------------------------------------------------------------------------------------------

def test_doc_read_prints_the_markdown_and_its_warnings_apart(repo, capsys):
    path = write(repo["files"], "owners.csv", "Field,Owner\nvatNo,anna.example@example.com\n")

    assert main(["doc", "read", str(path)]) == 0
    out = capsys.readouterr()
    assert out.out.startswith("# owners\n") and out.out.endswith("|\n")
    assert out.err == ("Warning: Column Owner (B) has values that look like personal data (1 email address): check "
                       "before committing it\n")

    assert main(["doc", "read", str(path), "--headers-only", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert (result["kind"], result["title"], result["warnings"]) == ("csv", "owners", [])


def test_doc_read_exits_1_on_a_refusal_and_2_on_a_wrong_option(repo, capsys):
    assert main(["doc", "read", str(write(repo["files"], "spec.doc", b"x"))]) == 1
    assert "save it as .docx" in capsys.readouterr().err

    assert main(["doc", "read", "x.csv", "--rows", "some"]) == 2
    assert "some isn't a number of rows, or all" in capsys.readouterr().err


# --- bridge-kit inputs add <file> -------------------------------------------------------------------------------------

def add(capsys, *args) -> tuple[int, str, str]:
    code = main(["inputs", "add", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def header(repo, file: str) -> dict:
    return read_markdown((repo["repo"] / file).read_text(encoding="utf-8")).front_matter


def test_a_file_becomes_an_input_its_version_its_hash_its_original_kept(repo, capsys):
    path = write(repo["files"], "Rough mapping v2.csv", ROUGH)

    code, out, err = add(capsys, str(path), "--work-item", "REQ-341")

    assert (code, out, err) == (0, "Added work/REQ-341/inputs/01-rough-mapping-v2.md: Rough mapping v2\n", "")
    found = header(repo, "work/REQ-341/inputs/01-rough-mapping-v2.md")
    assert {k: found[k] for k in ("kind", "source", "summary", "raw")} == {
        "kind": "csv", "source": "file:Rough mapping v2.csv", "summary": "Rough mapping v2",
        "raw": ".work/sources/REQ-341/01-rough-mapping-v2.csv"}
    assert found["version"].startswith("sha256:") and "options" not in found and "warnings" not in found
    assert (repo["repo"] / found["raw"]).read_bytes() == path.read_bytes()
    text = (repo["repo"] / "work/REQ-341/inputs/01-rough-mapping-v2.md").read_text(encoding="utf-8")
    assert "| 5 | ctry | vatRegistrations[].country |  | lookup |" in text


def test_a_file_added_again_is_there_until_it_or_its_options_change(repo, capsys):
    path = write(repo["files"], "rough.csv", ROUGH)
    add(capsys, str(path), "--work-item", "REQ-341")

    assert add(capsys, str(path), "--work-item", "REQ-341")[1] == (
        "Already there, unchanged: work/REQ-341/inputs/01-rough.md\n")

    _, out, _ = add(capsys, str(path), "--work-item", "REQ-341", "--rows", "all")
    assert out == "Changed since work/REQ-341/inputs/01-rough.md: added work/REQ-341/inputs/02-rough.md\n"
    assert header(repo, "work/REQ-341/inputs/02-rough.md")["options"] == {"rows": "all"}

    path.write_text(ROUGH + "status;status.code;copy;\n", encoding="utf-8")
    _, out, _ = add(capsys, str(path), "--work-item", "REQ-341")
    assert out == "Changed since work/REQ-341/inputs/02-rough.md: added work/REQ-341/inputs/03-rough.md\n"


def test_an_input_s_warnings_are_in_its_header_and_on_standard_error(repo, capsys):
    path = write(repo["files"], "owners.csv", "Field,Owner\nvatNo,anna.example@example.com\n")

    code, _, err = add(capsys, str(path), "--work-item", "REQ-341", "--json")

    assert code == 0 and err == ""  # with --json, the warnings are in the JSON
    assert header(repo, "work/REQ-341/inputs/01-owners.md")["warnings"] == [
        "Column Owner (B) has values that look like personal data (1 email address): check before committing it"]


def test_an_image_is_kept_with_what_the_agent_says_it_shows(repo, capsys, monkeypatch):
    image = write(repo["files"], "whiteboard.png", PNG)
    description = write(repo["files"], "description.md", "## Text\n\n- \"VAT no. per country\"\n- [unreadable]\n")

    code, out, _ = add(capsys, str(image), "--work-item", "REQ-341", "--description", str(description),
                       "--by", "spec-explorer")

    assert (code, out) == (0, "Added work/REQ-341/inputs/01-whiteboard.md: whiteboard\n")
    found = header(repo, "work/REQ-341/inputs/01-whiteboard.md")
    assert (found["kind"], found["described_by"]) == ("image", "spec-explorer")
    assert (repo["repo"] / found["raw"]).read_bytes() == PNG and found["raw"].endswith(".png")
    text = (repo["repo"] / "work/REQ-341/inputs/01-whiteboard.md").read_text(encoding="utf-8")
    assert "`whiteboard.png`, an image, as spec-explorer described it." in text and "[unreadable]" in text

    monkeypatch.setattr("sys.stdin", io.StringIO("A flow: upstream -> collector -> model\n"))
    other = write(repo["files"], "flow.jpg", b"\xff\xd8\xff\xe0")
    assert add(capsys, str(other), "--work-item", "REQ-341", "--description", "-", "--by", "ba")[0] == 0
    assert "upstream -> collector" in (repo["repo"] / "work/REQ-341/inputs/02-flow.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("args, code, message", [
    (["--description", "{d}"], 2, "--description needs --by"),
    ([], 1, "whiteboard.png is an image, which bridge-kit can't read: read it yourself"),
    (["--description", "{empty}", "--by", "ba"], 2, "The description is empty"),
    (["--description", "{files}/nowhere.md", "--by", "ba"], 2, "Can't read the description"),
])
def test_an_image_needs_a_description_and_who_wrote_it(repo, capsys, args, code, message):
    image = write(repo["files"], "whiteboard.png", PNG)
    names = {"d": write(repo["files"], "d.md", "Boxes"), "empty": write(repo["files"], "e.md", " \n"),
             "files": repo["files"]}

    result, _, err = add(capsys, str(image), "--work-item", "REQ-341", *[a.format(**names) for a in args])

    assert result == code and message in err
    assert not (repo["repo"] / "work" / "REQ-341" / "inputs").exists() or not any(
        (repo["repo"] / "work" / "REQ-341" / "inputs").iterdir())


@pytest.mark.parametrize("args, code, message", [
    (["{csv}", "--work-item", "vat-work"], 2, "vat-work isn't a work item's id"),
    (["{csv}", "--work-item", "REQ-341", "--description", "{csv}", "--by", "ba"], 2,
     "rough.csv doesn't take --description: only an image or a PDF does"),
    (["{files}/missing.csv", "--work-item", "REQ-341"], 2, "isn't a source bridge-kit reads: gitlab:<story>, wiki:"),
    (["{files}/spec.doc", "--work-item", "REQ-341"], 1, "spec.doc is the old Word format"),
])
def test_a_wrong_work_item_file_or_description_is_refused(repo, capsys, args, code, message):
    write(repo["files"], "spec.doc", b"x")
    names = {"csv": write(repo["files"], "rough.csv", ROUGH), "files": repo["files"]}

    result, _, err = add(capsys, *[a.format(**names) for a in args])

    assert result == code and message in err
    assert not (repo["repo"] / ".work" / "sources").exists()
