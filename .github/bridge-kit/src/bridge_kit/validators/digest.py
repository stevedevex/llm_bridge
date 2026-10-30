"""The Spec Validator's checks for spec digests.

The Spec Explorer's sections must be written, and every operation and path it names in "Where the data is" must
exist in the spec: the operation in the spec, the path in that operation's response.
"""

from __future__ import annotations

from pathlib import Path

from bridge_kit.markdown import FormatError, MdDocument, code_spans, read_markdown
from bridge_kit.spec_digest import (
    ANSWER_COLUMNS, JUDGEMENT_SECTIONS, PLACEHOLDER, Digest, DigestError, digest_spec, path_key, pick_spec,
)
from bridge_kit.spec_resolver import ResolveError, classify, resolve
from bridge_kit.validators import Finding

FRONT_MATTER_KEYS = ("upstream", "category", "spec", "spec_file", "generated_by")
NOT_AVAILABLE = {"", "-", "—", "n/a", "none", "not available"}


def is_not_available(cell: str) -> bool:
    return cell.replace("`", "").strip().lower() in NOT_AVAILABLE


def answer_path(cell: str) -> str:
    """The path a cell names: its first code span, else its text."""
    spans = code_spans(cell)
    return (spans[0] if spans else cell).strip()


def repo_of(path: Path) -> Path | None:
    """The repo a digest belongs to: the nearest folder above it with a `.github` folder."""
    return next((p for p in path.resolve().parents if (p / ".github").is_dir()), None)


def load_spec_digest(front: dict, digest_file: Path, repository_url: str | None = None,
                     cache: Path | None = None) -> Digest:
    """Digests the spec a digest file was generated from, as its front matter records it."""
    try:
        if front.get("spec"):
            resolution = resolve(str(front["spec"]), repository_url=repository_url, cache=cache)
        elif front.get("url"):
            resolution = resolve(str(front["url"]), cache=cache)
        elif front.get("file"):
            file = Path(str(front["file"]))
            repo = repo_of(digest_file)
            resolution = resolve(str(file if file.is_absolute() or repo is None else repo / file), cache=cache)
        else:
            raise DigestError("The front matter names no spec, url or file to check against")
    except ResolveError as e:
        raise DigestError(str(e)) from e
    if not resolution.location:
        raise DigestError(resolution.message or "The spec can't be resolved")
    return digest_spec(pick_spec(classify(Path(resolution.location)), front.get("spec_file")))


def validate_digest(path: Path, repository_url: str | None = None, cache: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []

    def add(severity: str, check: str, message: str, line: int | None = None, row: str | None = None) -> None:
        findings.append(Finding(severity, check, message, str(path), line, row))

    try:
        doc = read_markdown(path.read_text(encoding="utf-8"))
    except FormatError as e:
        add("error", "format", str(e), e.line)
        return findings
    for key in FRONT_MATTER_KEYS:
        if key not in doc.front_matter:
            add("error", "front-matter", f"The front matter has no {key}: generate the file with "
                                         "`bridge-kit spec digest`", 1)
    _check_sections(doc, add)
    rows = _answer_rows(doc, add)
    if not rows:
        return findings
    try:
        digest = load_spec_digest(doc.front_matter, path, repository_url, cache)
    except DigestError as e:
        add("warning", "source", f"Operations and paths aren't checked: {e}", 1)
        return findings
    for line, cells in rows:
        number, operation, named = cells[0], cells[2], answer_path(cells[3])
        if is_not_available(operation):
            if named and not is_not_available(named):
                add("error", "not-available", "A row with no operation can't name a path", line, number)
            continue
        op = digest.operation(operation)
        if op is None:
            add("error", "operation", f"{operation} isn't an operation of the spec", line, number)
            continue
        if not named or is_not_available(named):
            add("error", "path", f"The row names {op.name} but no path", line, number)
            continue
        field = next((f for f in op.outputs if path_key(f.path) == path_key(named)), None)
        if field is None:
            add("error", "path", f"{named} isn't in what {op.name} returns", line, number)
        elif field.path != named.replace("`", "").strip():
            add("warning", "path", f"The spec writes this path as {field.path}", line, number)
    return findings


def _check_sections(doc: MdDocument, add) -> None:
    for heading in (*JUDGEMENT_SECTIONS, "Operations"):
        section = doc.section(heading)
        if section is None:
            add("error", "sections", f"The section {heading} is missing")
        elif any(text.strip() == PLACEHOLDER for _, text in section.paragraphs):
            add("error", "sections", f"The section {heading} isn't written yet", section.line)


def _answer_rows(doc: MdDocument, add) -> list[tuple[int, list[str]]]:
    section = doc.section("Where the data is")
    if section is None:
        return []
    if not section.tables or section.tables[0].columns[:len(ANSWER_COLUMNS)] != ANSWER_COLUMNS:
        add("error", "answers", "Where the data is needs a table with the columns " + ", ".join(ANSWER_COLUMNS),
            section.line)
        return []
    rows = section.tables[0].rows
    if not rows:
        add("error", "answers", "Where the data is has no rows: one per item the BA asked about", section.line)
    for expected, (line, cells) in enumerate(rows, start=1):
        if cells[0] != str(expected):
            add("error", "numbering", f"Row {cells[0] or '(blank)'} should be {expected}, in the order the BA asked",
                line, cells[0])
    return rows
