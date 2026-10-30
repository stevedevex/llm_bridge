from pathlib import Path

import pytest
from conftest import edit
from test_spec_digest import LOANS_WSDL

from bridge_kit.cli import main
from bridge_kit.spec_digest import PLACEHOLDER
from bridge_kit.validators.digest import validate_digest

ANSWERS = """\
| # | Asked for | Operation | Path | Type | Notes |
|---|---|---|---|---|---|
| 1 | the loan's id | GetLoans | `GetLoansResponse/Loan[]/Id` | string | |
| 2 | whether it's running | GetLoans | `GetLoansResponse/Loan[]/State` | StateCode | OPEN means running |
| 3 | the interest rate | — | — | | Not in the spec |
"""


def fill(path: Path, answers: str = ANSWERS) -> None:
    text = path.read_text(encoding="utf-8")
    table = "| # | Asked for | Operation | Path | Type | Notes |\n|---|---|---|---|---|---|\n"
    text = text.replace(table, answers, 1)
    for section in ("Summary", "Not available", "Open questions"):
        text = text.replace(f"## {section}\n\n{PLACEHOLDER}", f"## {section}\n\nWritten.", 1)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def digest(tmp_path: Path) -> Path:
    """A digest of an attached WSDL, generated in a BA repo and filled in."""
    repo = tmp_path / "ba-repo"
    (repo / ".github").mkdir(parents=True)
    inputs = repo / "work" / "REQ-1" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "LoanService.wsdl").write_text(LOANS_WSDL, encoding="utf-8")
    out = inputs / "spec-digest-loans.md"
    assert main(["spec", "digest", str(inputs / "LoanService.wsdl"), "--upstream", "loans", "--out", str(out)]) == 0
    fill(out)
    return out


def checks(findings, severity="error"):
    return [(f.check, f.row) for f in findings if f.severity == severity]


def test_a_filled_digest_passes(digest):
    assert validate_digest(digest) == []
    assert "file: work/REQ-1/inputs/LoanService.wsdl" in digest.read_text(encoding="utf-8")


def test_an_operation_the_spec_doesnt_have_is_an_error(digest):
    edit(digest, "| 1 | the loan's id | GetLoans |", "| 1 | the loan's id | GetLoan |")

    assert checks(validate_digest(digest)) == [("operation", "1")]


def test_a_path_the_operation_doesnt_return_is_an_error(digest):
    edit(digest, "GetLoans | `GetLoansResponse/Loan[]/State`", "GetLoans | `GetLoansResponse/Loan[]/Status`")

    assert checks(validate_digest(digest)) == [("path", "2")]


def test_a_missing_list_marker_is_a_warning(digest):
    edit(digest, "GetLoans | `GetLoansResponse/Loan[]/State`", "GetLoans | `GetLoansResponse/Loan/State`")

    findings = validate_digest(digest)
    assert checks(findings) == []
    assert checks(findings, "warning") == [("path", "2")]


def test_data_that_isnt_there_has_no_path(digest):
    edit(digest, "| 3 | the interest rate | — | — |", "| 3 | the interest rate | — | `GetLoansResponse/Loan[]/Id` |")

    assert checks(validate_digest(digest)) == [("not-available", "3")]


def test_unwritten_sections_and_wrong_numbering_are_errors(digest):
    edit(digest, "## Open questions\n\nWritten.", f"## Open questions\n\n{PLACEHOLDER}")
    edit(digest, "| 3 | the interest rate |", "| 4 | the interest rate |")

    assert checks(validate_digest(digest)) == [("sections", None), ("numbering", "4")]


def test_the_command_reports_errors_with_exit_code_1(digest, capsys):
    edit(digest, "| 1 | the loan's id | GetLoans |", "| 1 | the loan's id | GetLoan |")

    assert main(["validate", "digest", str(digest)]) == 1
    assert "GetLoan isn't an operation of the spec" in capsys.readouterr().out
