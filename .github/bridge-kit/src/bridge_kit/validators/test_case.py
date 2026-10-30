"""`bridge-kit validate test-case`: test cases against templates/test-case.md. Errors stop a case being approved: the
header, the sections, the data it names, its steps, the data path where it's needed, the stories and criteria it
verifies, the approval rules, and, across a work item's cases, each number once and each file named for it. Warnings are
for the tester and the BA to judge: vague words in a result, more than ten steps, data defined and never used, no Never
list, an Objective that doesn't name its criteria."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bridge_kit.schema import problems
from bridge_kit.stories import load_story
from bridge_kit.test_cases import (
    DATA_NAME, FILE_NAME, HEADER_SCHEMA, OPTIONAL_SECTIONS, SECTIONS, TestCase, cell_name, load_test_case,
)
from bridge_kit.validators import Finding

DATA_COLUMNS = ["Name", "Value", "Why", "Source"]
STEP_COLUMNS = ["#", "Action", "Expected result"]
PATH_COLUMNS = ["Hop", "Where to look", "Expected"]
VAGUE = re.compile(r"\b(works?|working|correct(ly)?|as expected|appropriate(ly)?|properly|relevant|valid)\b", re.I)
MOST_STEPS = 10


def validate_test_cases(files: list[Path], repo: Path) -> list[Finding]:
    """Checks the cases one by one, then as one set: a work item's cases."""
    schema_file = repo / HEADER_SCHEMA
    schema = json.loads(schema_file.read_text(encoding="utf-8")) if schema_file.exists() else None
    cases = [load_test_case(f) for f in files]
    findings: list[Finding] = []
    if schema is None:
        findings.append(Finding("warning", "header", f"No header schema at {HEADER_SCHEMA}: headers aren't checked",
                                str(repo)))
    for case in cases:
        findings += CaseValidator(case, schema, repo).validate()
    return findings + _check_set(cases)


class CaseValidator:
    def __init__(self, case: TestCase, schema: dict | None, repo: Path):
        self.case, self.schema, self.repo = case, schema, repo
        self.findings: list[Finding] = []

    def add(self, severity: str, check: str, message: str, line: int | None = None) -> None:
        self.findings.append(Finding(severity, check, message, str(self.case.file), line))

    def validate(self) -> list[Finding]:
        if self.case.error:
            self.add("error", "header", self.case.error, 1)
            return self.findings
        for problem in problems(self.case.header, self.schema, unknown="isn't a header field") if self.schema else []:
            self.add("error", "header", problem, 1)
        self.check_sections()
        self.check_data()
        self.check_steps()
        components = self.check_verifies()
        self.check_data_path(components)
        self.check_status()
        self.check_wording()
        return self.findings

    def check_sections(self) -> None:
        headings = [s.heading for s in self.case.sections]
        for name in SECTIONS:
            if name not in headings and name not in OPTIONAL_SECTIONS:
                self.add("error", "sections", f"The {name} section is missing")
        known = [h for h in headings if h in SECTIONS]
        if known != sorted(known, key=SECTIONS.index):
            self.add("error", "sections", f"The sections are out of order: {', '.join(SECTIONS)}")
        for section in self.case.sections:
            if section.heading not in SECTIONS:
                self.add("warning", "sections", f"{section.heading} isn't a section of the template", section.line)

    def _columns(self, heading: str, columns: list[str]):
        """The section's table, when it has the template's columns; an error otherwise."""
        section, table = self.case.section(heading), self.case.table(heading)
        if section is None:
            return None
        if table is None or table.columns != columns:
            self.add("error", "sections", f"{heading} needs a table with the columns {', '.join(columns)}",
                     section.line)
            return None
        return table

    def check_data(self) -> None:
        table = self._columns("Test data", DATA_COLUMNS)
        if table is None:
            return
        defined: dict[str, int] = {}
        for line, cells in table.rows:
            name = cell_name(cells[0])
            if name is None:
                self.add("error", "data", f"{cells[0]} isn't a data name: write it in braces, `{{entity}}`", line)
            elif name in defined:
                self.add("error", "data", f"{{{name}}} is defined twice", line)
            else:
                defined[name] = line
        used = DATA_NAME.findall(self.case.body)
        for name in sorted(set(used) - set(defined)):
            self.add("error", "data", f"{{{name}}} is used but isn't in Test data")
        for name, line in defined.items():
            if used.count(name) < 2:  # its own row only
                self.add("warning", "data", f"{{{name}}} is defined and never used", line)

    def check_steps(self) -> None:
        table = self._columns("Steps", STEP_COLUMNS)
        if table is None:
            return
        numbers = [cells[0] for _, cells in table.rows]
        if numbers != [str(n) for n in range(1, len(numbers) + 1)]:
            self.add("error", "steps", f"The steps must be numbered from 1 without gaps, not {', '.join(numbers)}",
                     table.line)
        for line, cells in table.rows:
            if not cells[1].strip() or not cells[2].strip() or cells[2].strip() in ("-", "—"):
                self.add("error", "steps", f"Step {cells[0]} needs an action and a result someone can observe", line)
        if len(table.rows) > MOST_STEPS:
            self.add("warning", "steps", f"{len(table.rows)} steps: more than {MOST_STEPS} usually means two cases",
                     table.line)

    def check_verifies(self) -> set[str]:
        """The stories and criteria it verifies, each there; returns the components their stories are for."""
        components: set[str] = set()
        for verified in self.case.verifies:
            path = self.repo / verified.story
            if not path.is_file():
                self.add("error", "verifies", f"{verified.story} isn't in the BA repo", 1)
                continue
            story = load_story(path)
            components.add(story.component)
            have = {f"AC-{c.number}" for c in story.criteria}
            for criterion in verified.criteria:
                if criterion not in have:
                    self.add("error", "verifies", f"{verified.story} has no {criterion}", 1)
            if story.header.get("status") not in ("approved", "created"):
                self.add("error", "verifies", f"{verified.story} isn't approved: write cases from approved stories", 1)
        return components

    def check_data_path(self, components: set[str]) -> None:
        heading = "Checks along the data path"
        if self.case.section(heading) is not None:
            self._columns(heading, PATH_COLUMNS)
        elif self.case.header.get("level") in ("system", "end-to-end") and len(components) > 1:
            self.add("error", "data-path", f"A {self.case.header['level']} case across {len(components)} components "
                     f"needs {heading}: a row per hop, so a failure says where it broke")

    def check_status(self) -> None:
        header, status = self.case.header, self.case.status
        if status in ("approved", "created") and self.case.open_questions:
            self.add("error", "status", f"A case is {status} only with Open questions empty", 1)
        if status == "created" and not header.get("id"):
            self.add("error", "status", "A created case has its id in the test tool", 1)
        if header.get("automation") == "automated" and not header.get("automated_by"):
            self.add("error", "status", "An automated case names its test in automated_by", 1)

    def check_wording(self) -> None:
        for heading, column in (("Steps", 2), ("Checks along the data path", 2)):
            table = self.case.table(heading)
            for line, cells in table.rows if table else []:
                found = VAGUE.search(cells[column]) if len(cells) > column else None
                if found:
                    self.add("warning", "wording", f"\"{found.group(0)}\" in a result: say what's seen instead", line)
        passes = self.case.section("Pass criteria")
        if passes and "**Never:**" not in passes.text:
            self.add("warning", "pass", "Pass criteria has no **Never:** list: what must not happen", passes.line)
        objective = self.case.section("Objective")
        named = set(re.findall(r"\bAC-\d+\b", objective.text)) if objective else set()
        missing = sorted({c for v in self.case.verifies for c in v.criteria} - named)
        if objective and missing:
            self.add("warning", "objective", f"The Objective doesn't name {', '.join(missing)}", objective.line)


def _check_set(cases: list[TestCase]) -> list[Finding]:
    findings = []
    seen: dict[int, TestCase] = {}
    for case in cases:
        if case.error or case.number is None:
            continue
        if case.number in seen:
            findings.append(Finding("error", "set", f"{case.label} is also {seen[case.number].file.name}",
                                    str(case.file), 1))
        seen.setdefault(case.number, case)
        named = FILE_NAME.fullmatch(case.file.name)
        if not named or int(named.group(1)) != case.number:
            findings.append(Finding("error", "set", f"The file of {case.label} is named "
                                    f"tc-{case.number:02d}-<slug>.md", str(case.file), 1))
    return findings
