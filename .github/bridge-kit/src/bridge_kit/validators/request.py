"""The checks on a mapping request, the BA's input to the Mapping Drafter (`mappings/REQUEST.md`).

The front matter must say which upstream operation fills which target, and give the spec; the target must be in the
internal model and the spec must resolve; the Purpose must be written. Every other section is optional: a blank one is
a question for the drafter to ask, never a gap to guess.

A request may name the BA's rough mapping (`rough_mapping`, and `rough_mapping_table` when it has several tables):
it must be one of the work item's inputs, beside the request, and hold the table, with two columns or more and a row.
Its warnings (colours, struck text, comments, hidden rows) are passed on to the drafter.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from bridge_kit.internal_model import InternalModel, ModelError
from bridge_kit.markdown import FormatError, read_markdown
from bridge_kit.rough_mapping import RoughMappingError, find, tables
from bridge_kit.spec_resolver import ResolveError, resolve
from bridge_kit.validators import Finding
from bridge_kit.validators.digest import repo_of

REQUIRED_KEYS = ("upstream", "operation", "target", "spec")
OPTIONAL_SECTIONS = ("Known rules", "Codes", "Calling", "Who to ask", "Samples")
PLACEHOLDER = "_To be written._"


def validate_request(path: Path, model: InternalModel, repository_url: str | None = None,
                     cache: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []

    def add(severity: str, check: str, message: str, line: int | None = None) -> None:
        findings.append(Finding(severity, check, message, str(path), line))

    try:
        doc = read_markdown(path.read_text(encoding="utf-8"))
    except FormatError as e:
        add("error", "format", str(e), e.line)
        return findings
    front = doc.front_matter
    for key in REQUIRED_KEYS:
        if not str(front.get(key) or "").strip():
            add("error", "front-matter", f"The front matter has no {key}", 1)

    target = str(front.get("target") or "").strip()
    if target:
        try:
            model.resolve(target)
        except ModelError as e:
            add("error", "target", f"The target {target} isn't in the internal model: {e}", 1)

    repo = repo_of(path)
    spec = str(front.get("spec") or "").strip()
    if spec:
        _check_spec(spec, repo, repository_url, cache, add)
    digest = str(front.get("digest") or "").strip()
    if digest and repo is not None and not (repo / digest).is_file():
        add("warning", "digest", f"The digest {digest} isn't there", 1)
    rough, table = (str(front.get(key) or "").strip() for key in ("rough_mapping", "rough_mapping_table"))
    rough, table = ("" if value.startswith("<") else value for value in (rough, table))  # the template's placeholders
    if rough:
        _check_rough_mapping(path, repo, rough, table, add)
    elif table:
        add("error", "rough-mapping", "rough_mapping_table names a table, but rough_mapping names no input", 1)

    purpose = doc.section("Purpose")
    if purpose is None:
        add("error", "purpose", "The section Purpose is missing: say what the data is for")
    elif not purpose.paragraphs or purpose.paragraphs[0][1].startswith(PLACEHOLDER):
        add("error", "purpose", "Purpose isn't written yet: say what the data is for, item by item", purpose.line)
    blank = [name for name in OPTIONAL_SECTIONS if _blank(doc, name)]
    if blank:
        add("info", "blank", f"Left for the drafter to ask about: {', '.join(blank)}")
    return findings


def _check_rough_mapping(path: Path, repo: Path | None, rough: str, name: str, add) -> None:
    keep = "keep your file with bridge-kit inputs add <file> --work-item <id>, and name the input it makes"
    file = (repo or path.parent) / rough
    if not file.is_file():
        add("error", "rough-mapping", f"The rough mapping {rough} isn't there: {keep}", 1)
        return
    if file.resolve().parent != path.resolve().parent:
        add("error", "rough-mapping", f"The rough mapping {rough} isn't one of this work item's inputs, beside the "
                                      f"request: {keep}", 1)
        return
    try:
        doc = read_markdown(file.read_text(encoding="utf-8"))
        table = find(tables(file.read_text(encoding="utf-8")), name)
    except (FormatError, RoughMappingError) as e:
        add("error", "rough-mapping", f"The rough mapping {rough} {e}" if isinstance(e, RoughMappingError)
            else f"The rough mapping {rough} can't be read: {e}", 1)
        return
    if len(table.letters) < 2 or not table.rows:
        add("error", "rough-mapping", f"The rough mapping's {table.label} has {len(table.letters)} column(s) and "
                                      f"{len(table.rows)} row(s): it needs at least a source and a target column, and "
                                      "a row", 1)
    for warning in doc.front_matter.get("warnings") or []:
        add("info", "rough-mapping", f"For the drafter, from the rough mapping: {warning}", 1)


def _check_spec(spec: str, repo: Path | None, repository_url: str | None, cache: Path | None, add) -> None:
    """The spec resolves: a file in the repo, or whatever the spec resolver takes (coordinates, a URL)."""
    if repo is not None and ":" not in spec and (repo / spec).exists():
        return
    if re.fullmatch(r"[\w.-]+:[\w.-]+:[\w.-]+", spec) and not (repository_url
                                                               or os.environ.get("BRIDGE_KIT_NEXUS_URL")):
        add("warning", "spec", "The spec isn't checked: no Nexus URL to get it from", 1)
        return
    try:
        resolution = resolve(spec, repository_url=repository_url, cache=cache)
    except ResolveError as e:
        add("error", "spec", f"The spec doesn't resolve: {e}", 1)
        return
    if resolution.status != "resolved":
        add("error", "spec", f"The spec doesn't resolve: {resolution.message}", 1)


def _blank(doc, name: str) -> bool:
    """A section that's missing, or holds only the template's guidance (the paragraph after its heading)."""
    section = doc.section(name)
    if section is None or not section.paragraphs:
        return True
    return all(_is_guidance(name, text) for _, text in section.paragraphs)


TEMPLATE_STARTS = {"Known rules": "Fallbacks, defaults, filters", "Codes": "What the upstream's codes mean",
                   "Calling": "Which identifier the call takes", "Who to ask": "Who answers each kind of question",
                   "Samples": "Request ids of real payloads"}


def _is_guidance(name: str, text: str) -> bool:
    return text.startswith(TEMPLATE_STARTS.get(name, "\0")) or text.strip().lower() in ("", "none.", "none")
