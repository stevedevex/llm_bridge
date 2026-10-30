"""Excel workbooks as Markdown: a BA's rough mapping, made here with openpyxl and made-up content, read with its heading
row found below a title, row numbers and column letters, hidden rows, columns and sheets marked, merged cells spread,
struck text, comments, formulas and colours; values as Excel saved them; and kept as a work item's input."""

import re
import zipfile
from datetime import date, datetime

import openpyxl
import pytest
from openpyxl.chart import BarChart, Reference
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.styles.colors import Color

from bridge_kit.cli import main
from bridge_kit.documents import DocumentError, Options, read_document
from bridge_kit.documents.excel import _shape
from bridge_kit.markdown import read_markdown


def rough_mapping(path):
    """A BA's working mapping: a title, a heading row, a comment, a yellow row, a struck row, a merged rule, red
    text, a hidden row and column, a formula down a column; and a hidden sheet of lookups."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Mapping"
    sheet["A1"] = "VAT registration mapping, v2"
    sheet.append([])
    sheet.append(["Source field", "Target attribute", "Rule", "Owner", "Key"])
    sheet.append(["legalEntityId", "legalEntity.id", "copy", "data team", '=A4&"-"&B4'])
    sheet.append(["vatNo", "vatRegistrations[].number", "trim | upper", None, '=A5&"-"&B5'])
    sheet.append(["oldCode", "legalEntity.code", "copy", None, '=A6&"-"&B6'])
    sheet.append(["ctry", "vatRegistrations[].country", "lookup"])
    sheet.append(["ctrySub", "vatRegistrations[].region"])
    sheet.merge_cells("C7:C8")
    sheet["C4"].comment = Comment("Is copy right for every entity?", "Anna Example")
    for cell in ("A5", "B5", "C5"):
        sheet[cell].fill = PatternFill("solid", fgColor="FFFF00")
    for cell in ("A6", "B6", "C6"):
        sheet[cell].font = Font(strike=True)
    sheet["B7"].font = Font(color="FF0000")
    sheet.row_dimensions[8].hidden = True
    sheet.column_dimensions["D"].hidden = True
    lookups = book.create_sheet("Lookups")
    lookups.append(["Code", "Country"])
    lookups.append(["DE", "Germany"])
    lookups.sheet_state = "hidden"
    book.save(path)
    return path


def saved_by_excel(path, values: dict[str, str]):
    """The workbook as Excel would save it: each formula's result kept beside it, which openpyxl doesn't write."""
    with zipfile.ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    xml = parts["xl/worksheets/sheet1.xml"].decode("utf-8")
    for cell, value in values.items():
        kind = "" if re.fullmatch(r"-?\d+(\.\d+)?", value) else ' t="str"'  # a text result is marked as one
        # openpyxl writes the empty result as <v /> or <v></v>, as it has lxml or not
        xml, n = re.subn(rf'<c r="{cell}"([^>]*)>(<f>[^<]*</f>)(?:<v ?/>|<v></v>)',
                         rf'<c r="{cell}"\1{kind}>\2<v>{value}</v>', xml)
        assert n == 1, cell
    parts["xl/worksheets/sheet1.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


@pytest.fixture
def book(tmp_path):
    return rough_mapping(tmp_path / "rough-mapping.xlsx")


def test_a_rough_mapping_reads_as_the_ba_wrote_it(book):
    document = read_document(book)

    assert document.kind == "xlsx" and document.title == "rough-mapping"
    text = document.markdown
    assert text.startswith("# rough-mapping\n\n`rough-mapping.xlsx`: an Excel workbook, 2 sheet(s): Mapping, "
                           "Lookups (hidden).\n\n## Sheet: Mapping\n\nA1:E8: 5 row(s) below its heading row (row 3).\n")
    assert "Above the table:\n\n- Row 1: VAT registration mapping, v2\n" in text
    assert ("| Row | Source field (A) | Target attribute (B) | Rule (C) | Owner (D, hidden) | Key (E) |\n"
            "|---|---|---|---|---|---|\n"
            "| 4 | legalEntityId | legalEntity.id | copy | data team | =A4&\"-\"&B4 |\n"
            "| 5 | vatNo | vatRegistrations[].number | trim \\| upper |  | =A5&\"-\"&B5 |\n"
            "| 6 | ~~oldCode~~ | ~~legalEntity.code~~ | ~~copy~~ |  | =A6&\"-\"&B6 |\n"
            "| 7 | ctry | vatRegistrations[].country | lookup |  |  |\n"
            "| 8 (hidden) | ctrySub | vatRegistrations[].region | lookup |  |  |\n") in text
    assert "### Comments\n\n- C4 (Anna Example): Is copy right for every entity?\n" in text
    assert "### Formulas\n\n- E4:E6: =A4&\"-\"&B4, and alike down to row 6\n" in text
    assert "### Coloured cells\n\n- A5:C5: yellow (#FFFF00)\n" in text
    assert "### Coloured text\n\n- B7: red (#FF0000)\n" in text
    assert "## Sheet: Lookups (hidden)\n\nA1:B2: 1 row(s) below its heading row (row 1).\n" in text
    assert document.warnings == [
        "Sheet Mapping has 1 hidden row(s) and 1 hidden column(s): read too, and marked (hidden)",
        "Sheet Mapping has coloured cells or text, listed under its table: ask the BA what the colours mean, unless "
        "the sheet has a legend",
        "Sheet Mapping has struck-through text, shown as ~~text~~: often a row or a rule that was dropped",
        "Sheet Mapping: 3 formula(s) have no value saved, as when the file wasn't last saved by Excel: their formulas "
        "are shown in their cells",
        "Sheet Lookups is hidden: read too, and marked"]


def test_a_formula_shows_the_value_excel_saved_and_is_listed_too(book):
    document = read_document(saved_by_excel(book, {"E4": "legalEntityId-legalEntity.id", "E5": "x", "E6": "y"}))

    assert "| 4 | legalEntityId | legalEntity.id | copy | data team | legalEntityId-legalEntity.id |" in document.markdown
    assert "- E4:E6: =A4&\"-\"&B4, and alike down to row 6" in document.markdown
    assert not any("no value saved" in w for w in document.warnings)


def test_values_dates_percentages_and_numbers_as_excel_shows_them(tmp_path):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Kind", "Value"])
    rows = [("date", date(2026, 10, 28)), ("time", datetime(2026, 10, 28, 14, 30)), ("float", 0.1 + 0.2),
            ("whole", 12.0), ("share", 0.125), ("flag", True), ("text", "  padded  ")]
    for kind, value in rows:
        sheet.append([kind, value])
    sheet["B6"].number_format = "0.0%"
    book.save(tmp_path / "values.xlsx")

    text = read_document(tmp_path / "values.xlsx").markdown

    for row, shown in ((2, "2026-10-28"), (3, "2026-10-28 14:30"), (4, "0.3"), (5, "12"), (6, "12.5%"),
                       (7, "TRUE"), (8, "padded")):
        assert f"| {row} | {rows[row - 2][0]} | {shown} |" in text


def test_only_the_sheets_asked_for_by_name_in_any_case(book):
    text = read_document(book, Options(sheets=("lookups",))).markdown

    assert "Read here: Lookups." in text and "## Sheet: Mapping" not in text and "## Sheet: Lookups" in text
    with pytest.raises(DocumentError, match="rough-mapping.xlsx has no sheet Codes: its sheets are Mapping, Lookups"):
        read_document(book, Options(sheets=("Codes",)))


def test_a_long_sheet_shows_its_first_rows_and_lists_only_what_they_hold(tmp_path):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Records"
    sheet.append(["Id", "Contact"])
    for n in range(1, 502):
        sheet.append([n, f"person{n}@example.com"])
    sheet["B400"].fill = PatternFill("solid", fgColor="FFFF00")
    book.save(tmp_path / "records.xlsx")

    document = read_document(tmp_path / "records.xlsx")

    assert "The first 200 of 501 rows shown: --rows all shows every one." in document.markdown
    assert "Coloured cells" not in document.markdown  # row 400 isn't shown
    assert document.warnings == ["Sheet Records, column Contact (B) has values that look like personal data (200 "
                                 "email addresses): check before committing it"]
    assert read_document(tmp_path / "records.xlsx", Options(headers_only=True)).warnings == []


def test_threaded_comments_theme_colours_and_what_isn_t_a_colour(tmp_path):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Field", "Rule"])
    sheet.append(["vatNo", "copy"])
    sheet.append(["ctry", "lookup"])
    sheet["B2"].comment = Comment("[Threaded comment]\n\nYour version of Excel allows you to read this threaded "
                                  "comment.\n\nComment:\n    Which lookup?\nReply:\n    The country one", "tc={0A1B}")
    sheet["A2"].fill = PatternFill("solid", fgColor=Color(theme=4, tint=0.6))
    sheet["A3"].fill = PatternFill("solid", fgColor="FFFFFF")  # white: no colour
    sheet["B3"].font = Font(color="000000")  # black text: no colour
    book.save(tmp_path / "notes.xlsx")

    text = read_document(tmp_path / "notes.xlsx").markdown

    assert "- B2 (a threaded comment): Which lookup? Reply: The country one" in text
    assert "### Coloured cells\n\n- A2: theme colour 4, tinted\n" in text and "Coloured text" not in text


def test_a_title_from_the_workbook_an_empty_sheet_and_a_chart_sheet(tmp_path):
    book = openpyxl.Workbook()
    book.properties.title = "Upstream onboarding"
    book.active.title = "Notes"
    data = book.create_sheet("Data")
    data.append(["Month", "Volume"])
    data.append(["Oct", 10])
    chart = BarChart()
    chart.add_data(Reference(data, min_col=2, min_row=1, max_row=2), titles_from_data=True)
    book.create_chartsheet("Volumes").add_chart(chart)
    book.save(tmp_path / "onboarding.xlsx")

    document = read_document(tmp_path / "onboarding.xlsx")

    assert document.title == "Upstream onboarding"
    assert "3 sheet(s): Notes, Data, Volumes (a chart, not read)." in document.markdown
    assert "## Sheet: Notes\n\nEmpty.\n" in document.markdown and "A chart sheet, not read." in document.markdown


def test_a_broken_workbook_is_refused(tmp_path):
    path = tmp_path / "broken.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("hello.txt", "not a workbook")

    with pytest.raises(DocumentError, match="broken.xlsx can't be read as a workbook .*: open it in Excel and save it"):
        read_document(path)


@pytest.mark.parametrize("formula, row, shape", [
    ("=A4&B4", 4, "=A[0]&B[0]"),
    ("=$A$1+B5", 5, "=$A$1+B[0]"),
    ("=A$1+B4", 5, "=A$1+B[-1]"),
    ("=LOG10(C7)", 7, "=LOG10(C[0])"),
    ("=VLOOKUP(B9,Lookups!A:B,2,FALSE)", 9, "=VLOOKUP(B[0],Lookups!A:B,2,FALSE)"),
])
def test_a_formula_s_shape_is_its_rows_as_offsets(formula, row, shape):
    assert _shape(formula, row) == shape


def test_different_formulas_down_a_column_are_listed_apart(tmp_path):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["A", "B", "Sum"])
    for row in range(2, 5):
        sheet.append([1, 2, f"=A{row}+B{row}"])
    sheet["C5"] = "=SUM(C2:C4)"
    book.save(tmp_path / "sums.xlsx")

    text = read_document(tmp_path / "sums.xlsx").markdown

    assert "- C2:C4: =A2+B2, and alike down to row 4\n- C5: =SUM(C2:C4)\n" in text


def test_a_workbook_kept_as_an_input_with_its_options(book, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))

    assert main(["inputs", "add", str(book), "--work-item", "REQ-341", "--sheet", "Mapping"]) == 0

    assert capsys.readouterr().out == "Added work/REQ-341/inputs/01-rough-mapping.md: rough-mapping\n"
    header = read_markdown((repo / "work/REQ-341/inputs/01-rough-mapping.md").read_text(encoding="utf-8")).front_matter
    assert (header["kind"], header["options"], header["raw"]) == (
        "xlsx", {"sheet": ["Mapping"]}, ".work/sources/REQ-341/01-rough-mapping.xlsx")
    assert len(header["warnings"]) == 4  # the hidden sheet isn't read
