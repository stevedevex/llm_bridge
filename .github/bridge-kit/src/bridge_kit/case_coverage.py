"""`bridge-kit tests coverage <id>`: whether a work item's test cases cover its stories' acceptance criteria. A table of
each story's criteria and the cases that verify them, with their status, then the gaps:

- an error for a criterion no case verifies;
- warnings, read from a criterion's own words and so sometimes wrong: one whose Given or When names alternatives or
  failures ("no customer id, an empty result, or a fault") with no alternate or error case, and one about accessibility,
  performance or security with no case of that type.

A story for a component that owns only schemas (the internal model's) is checked when its change is, by
`validate model` and the model's build, so its criteria aren't counted as gaps. It's separate from the package check:
cases are written while developers build, after the package is approved.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bridge_kit.stories import Catalog, CatalogError, Story, load_catalog, load_story
from bridge_kit.test_cases import TestCase, load_test_case
from bridge_kit.validators import Finding

ALTERNATIVES = re.compile(r"\b(no|none|empty|without|missing|absent|faults?|fails?|failure|errors?|invalid|unknown|"
                          r"rejected|unavailable|time[sd]? out|timeout)\b|, or\b|\beither\b", re.I)
NON_FUNCTIONAL = {
    "accessibility": re.compile(r"accessib|assistive|screen reader|keyboard|\bwcag\b|contrast", re.I),
    "performance": re.compile(r"\bwithin \d|\b\d+ ?(ms|milliseconds?|seconds?)\b|response time|latency|throughput|"
                              r"under load", re.I),
    "security": re.compile(r"permission|authori[sz]|authenticat|\bencrypt|\bmask|personal data|access control", re.I),
}
SCHEMA_CHECKED = "checked by `validate model`"


@dataclass
class Row:
    story: str  # its file's name
    ref: str  # S<order> component
    criterion: str  # AC-<n>
    title: str
    cases: list[str] = field(default_factory=list)  # "TC-1 (draft)"; or SCHEMA_CHECKED


@dataclass
class Coverage:
    work_item: str
    rows: list[Row] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    cases: int = 0

    @property
    def errors(self) -> int:
        return sum(f.severity == "error" for f in self.findings)

    def to_dict(self) -> dict:
        return {"work_item": self.work_item, "cases": self.cases, "errors": self.errors,
                "rows": [asdict(r) for r in self.rows], "findings": [asdict(f) for f in self.findings]}


def coverage(work_item: str, ba_repo: Path) -> Coverage:
    from bridge_kit.validators.package import work_folder

    result = Coverage(work_item)
    folder = work_folder(ba_repo, work_item)
    if folder is None:
        result.findings.append(Finding("error", "coverage", f"No work folder for {work_item}", "work"))
        return result
    stories = sorted((load_story(p) for p in sorted((folder / "stories").glob("*.md"))),
                     key=lambda s: (s.order or 99, s.file.name))
    cases = [c for c in (load_test_case(p) for p in sorted((folder / "tests").glob("*.md"))) if not c.error]
    result.cases = len(cases)
    try:
        catalog = load_catalog(ba_repo)
    except CatalogError:
        catalog = Catalog({}, {})
    verifying: dict[tuple[str, str], list[TestCase]] = {}
    for case in cases:
        for verified in case.verifies:
            for criterion in verified.criteria:
                verifying.setdefault((verified.story, criterion), []).append(case)
    if not cases:
        result.findings.append(Finding("error", "coverage", f"No test cases yet: write them with /write-tests "
                                       f"{work_item}", (folder / "tests").relative_to(ba_repo).as_posix()))
    for story in stories:
        path = story.file.relative_to(ba_repo).as_posix()
        schema_only = _schema_only(story, catalog)
        for criterion in story.criteria:
            ac = f"AC-{criterion.number}"
            row = Row(story.file.name, f"{story.ref} {story.component}".strip(), ac, criterion.title)
            result.rows.append(row)
            if schema_only:
                row.cases = [SCHEMA_CHECKED]
                continue
            found = verifying.get((path, ac), [])
            row.cases = [f"{c.label} ({c.status or 'no status'})" for c in found]
            where = (path, criterion.line)
            if not found:
                if cases:
                    result.findings.append(Finding("error", "coverage", f"{row.ref} {ac}: no case verifies it", *where))
                continue
            conditions = " ".join(_conditions(criterion.steps))
            if ALTERNATIVES.search(conditions) and not any(c.header.get("path") in ("alternate", "error")
                                                           for c in found):
                result.findings.append(Finding("warning", "coverage", f"{row.ref} {ac} names alternatives or "
                                               "failures, and no alternate or error case verifies it", *where))
            words = f"{criterion.title} {' '.join(criterion.steps)}"
            for kind, pattern in NON_FUNCTIONAL.items():
                if pattern.search(words) and not any(c.header.get("type") == kind for c in found):
                    result.findings.append(Finding("warning", "coverage", f"{row.ref} {ac} reads as {kind}, and no "
                                                   f"{kind} case verifies it", *where))
    return result


def _schema_only(story: Story, catalog: Catalog) -> bool:
    owns = catalog.owns(story.component)
    return bool(owns) and all(catalog.is_schema(c) for c in owns)


def _conditions(steps: list[str]) -> list[str]:
    """A criterion's Given and When lines, with their Ands: what it's about, not what it expects."""
    found = []
    for step in steps:
        if step.split(" ", 1)[0].lower() == "then":
            break
        found.append(step)
    return found


def format_coverage(result: Coverage) -> str:
    covered = sum(bool(r.cases) for r in result.rows)
    lines = [f"{result.work_item}: {len(result.rows)} criteria, {result.cases} case(s)", "",
             "| Story | Criterion | Cases |", "|---|---|---|"]
    lines += [f"| {r.ref} | {r.criterion}: {r.title} | {', '.join(r.cases) or 'none'} |" for r in result.rows]
    lines += [""] + [str(f) for f in result.findings]
    warnings = sum(f.severity == "warning" for f in result.findings)
    lines.append(f"Coverage: {covered} of {len(result.rows)} criteria covered, {result.errors} error(s), "
                 f"{warnings} warning(s)")
    return "\n".join(lines) + "\n"
