import pytest

from bridge_kit.markdown import FormatError, code_spans, read_markdown, split_cells


def test_splits_cells_and_keeps_escaped_pipes():
    assert split_cells("| 1 | a \\| b |  |") == ["1", "a | b", ""]


def test_reads_front_matter_sections_paragraphs_and_tables():
    doc = read_markdown("---\nname: x\n---\n\n## One\n\nFirst line\ncontinued.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")

    section = doc.section("One")
    assert doc.front_matter == {"name": "x"}
    assert section.paragraphs == [(7, "First line continued.")]
    assert section.tables[0].columns == ["a", "b"]
    assert section.tables[0].rows == [(12, ["1", "2"])]


def test_rejects_a_row_with_the_wrong_number_of_cells():
    with pytest.raises(FormatError) as error:
        read_markdown("## T\n\n| a | b |\n|---|---|\n| 1 |\n")

    assert error.value.line == 5


def test_rejects_unclosed_front_matter():
    with pytest.raises(FormatError):
        read_markdown("---\nname: x\n")


def test_finds_code_spans():
    assert code_spans("The entry of `Data.Balance[]` with `Type` OPBD") == ["Data.Balance[]", "Type"]
