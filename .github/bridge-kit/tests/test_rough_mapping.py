"""The BA's rough mapping: its tables as the document readers write them, from an Excel workbook, a Word document, a CSV
and a table the BA wrote in Markdown; the one a request names; and the cells a spec's Notes cite. Made-up content
only."""

import docx
import openpyxl
import pytest

from bridge_kit.documents import read_document
from bridge_kit.rough_mapping import RoughMappingError, check, cited, find, tables


@pytest.fixture
def workbook(tmp_path) -> str:
    """A rough mapping in Excel: a title above the table, a hidden row; and a sheet of codes."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Mapping"
    sheet["A1"] = "VAT registration, rough"
    sheet.append([])
    sheet.append(["Upstream attribute", "Model field", "Transformation"])
    sheet.append(["VatNumber", "vatNumber", "as is"])
    sheet.append(["Jurisdiction", "countryCode", "EL is GR"])
    sheet.append(["Status", "active", "Accepted is true"])
    sheet.row_dimensions[6].hidden = True
    codes = book.create_sheet("Codes")
    codes.append(["Code", "Meaning"])
    codes.append(["EL", "Greece"])
    book.save(tmp_path / "rough.xlsx")
    return read_document(tmp_path / "rough.xlsx").markdown


def test_an_excel_rough_mapping_s_tables_are_its_sheets(workbook):
    found = tables(workbook)

    assert [(t.name, t.letters, list(t.rows)) for t in found] == [
        ("Mapping", ["A", "B", "C"], ["4", "5", "6"]), ("Codes", ["A", "B"], ["2"])]
    assert found[0].rows["5"] == ["Jurisdiction", "countryCode", "EL is GR"]


def test_a_word_document_s_tables_by_their_number(tmp_path):
    document = docx.Document()
    document.add_heading("Rough mapping", level=1)
    for rows in ([["Field", "Rule"], ["vatNo", "copy"]], [["Code", "Meaning"], ["EL", "Greece"], ["XI", "GB"]]):
        table = document.add_table(rows=len(rows), cols=2)
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                table.cell(r, c).text = value
    document.save(tmp_path / "rough.docx")

    found = tables(read_document(tmp_path / "rough.docx").markdown)

    assert [(t.name, t.letters, list(t.rows)) for t in found] == [("Table 1", ["A", "B"], ["2"]),
                                                                  ("Table 2", ["A", "B"], ["2", "3"])]


def test_a_csv_and_a_markdown_table_are_a_file_s_only_table(tmp_path):
    (tmp_path / "rough.csv").write_text("Field,Target,Rule\nvatNo,vatNumber,copy\n", encoding="utf-8")
    written = "# Rough mapping\n\n| Field | Target |\n|---|---|\n| vatNo | vatNumber |\n| ctry | countryCode |\n"

    csv = tables(read_document(tmp_path / "rough.csv").markdown)
    markdown = tables(written)

    assert [(t.name, t.letters, list(t.rows)) for t in csv] == [("", ["A", "B", "C"], ["2"])]
    assert [(t.name, t.letters, list(t.rows)) for t in markdown] == [("", ["A", "B"], ["2", "3"])]  # as Excel numbers


def test_the_table_a_request_names(workbook):
    found = tables(workbook)

    assert find(found, "codes").name == "Codes"
    with pytest.raises(RoughMappingError, match=r"has 2 tables \(Mapping, Codes\): name the one to draft from in "
                                                "rough_mapping_table"):
        find(found, None)
    with pytest.raises(RoughMappingError, match="has no table Rules: its tables are Mapping, Codes"):
        find(found, "Rules")
    with pytest.raises(RoughMappingError, match="holds no table"):
        find([], None)


@pytest.mark.parametrize("notes, refs", [
    ("From the BA's rough mapping, `Mapping!C5`", ["Mapping!C5"]),
    ("EL is GR. From the BA's rough mapping, `Mapping!C5` and `Codes!B2`", ["Mapping!C5", "Codes!B2"]),
    ("From the BA's rough mapping, `C5`, `C6`. Decided by the BA", ["C5", "C6"]),
    ("`proposed`: the rough mapping's row is struck", []),
])
def test_the_cells_a_row_s_notes_cite(notes, refs):
    assert cited(notes) == refs


@pytest.mark.parametrize("ref, named, why", [
    ("Mapping!C5", None, None),
    ("C5", "Mapping", None),
    ("Mapping!6", None, None),  # a hidden row is there, if not to be taken
    ("Mapping!C9", None, "Mapping has no row 9"),
    ("Mapping!F5", None, "Mapping has no column F"),
    ("Rules!C5", None, "the rough mapping has no table Rules: its tables are Mapping, Codes"),
    ("C5", None, "the rough mapping has 2 tables (Mapping, Codes): name the one to draft from in rough_mapping_table"),
    ("Mapping!row 5", None, "Mapping!row 5 isn't a cell"),
])
def test_whether_a_cited_cell_is_there(workbook, ref, named, why):
    found = check(tables(workbook), ref, named)

    assert found == why if why is None else found.startswith(why)
