"""The Spec Validator's story checks (templates/story.md): each story's header and body, and the set's order and
dependencies, against the component catalog."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bridge_kit.stories import (
    HEADER_SCHEMA, OPTIONAL_SECTIONS, SECTIONS, Catalog, CatalogError, Story, check_header, load_catalog, load_story,
)
from bridge_kit.validators import Finding


def validate_stories(files: list[Path], repo: Path) -> list[Finding]:
    """Checks the stories as one set: the work item's stories, all written for the same requirement."""
    try:
        catalog = load_catalog(repo)
    except CatalogError as e:
        return [Finding("error", "catalog", str(e), str(repo))]
    schema_file = repo / HEADER_SCHEMA
    schema = json.loads(schema_file.read_text(encoding="utf-8")) if schema_file.exists() else None
    stories = [load_story(f) for f in files]
    findings: list[Finding] = []
    if schema is None:
        findings.append(Finding("warning", "header", f"No header schema at {HEADER_SCHEMA}: headers aren't checked",
                                str(repo)))
    for story in stories:
        findings += StoryValidator(story, catalog, schema, repo).validate()
    return findings + _check_set([s for s in stories if s.error is None], catalog)


class StoryValidator:
    def __init__(self, story: Story, catalog: Catalog, schema: dict | None, repo: Path):
        self.story, self.catalog, self.schema, self.repo = story, catalog, schema, repo
        self.findings: list[Finding] = []

    def add(self, severity: str, check: str, message: str, line: int | None = None) -> None:
        self.findings.append(Finding(severity, check, message, str(self.story.file), line))

    def validate(self) -> list[Finding]:
        if self.story.error:
            self.add("error", "header", self.story.error, 1)
            return self.findings
        self.check_header()
        self.check_sections()
        self.check_criteria()
        self.check_contracts()
        self.check_status()
        return self.findings

    def check_header(self) -> None:
        story, catalog = self.story, self.catalog
        for problem in check_header(story.header, self.schema) if self.schema else []:
            self.add("error", "header", problem, 1)
        if story.component not in catalog.components:
            self.add("error", "catalog", f"{story.component or '(none)'} isn't a component in the catalog", 1)
            return
        if story.order is not None and story.order != catalog.order(story.component):
            self.add("error", "order", f"{story.component} is number {catalog.order(story.component)} in the "
                     f"catalog's order, not {story.order}", 1)
        labels = story.header.get("labels") or []
        if sorted(labels) != sorted(catalog.labels(story.component)):
            expected = ", ".join(catalog.labels(story.component))
            self.add("warning", "labels", f"The labels should be the catalog's: {expected}", 1)
        for path in story.implements:
            if not (self.repo / path).exists():
                self.add("warning", "implements", f"{path} isn't in the BA repo", 1)

    def check_sections(self) -> None:
        story = self.story
        names = [s.name for s in story.sections]
        for name in SECTIONS:
            if name not in names and name not in OPTIONAL_SECTIONS:
                self.add("error", "sections", f"The {name} section is missing")
        known = [n for n in names if n in SECTIONS]
        if known != sorted(known, key=SECTIONS.index):
            self.add("error", "sections", f"The sections are out of order: {', '.join(SECTIONS)}")
        for section in story.sections:
            if section.name not in SECTIONS:
                self.add("warning", "sections", f"{section.heading} isn't a section of the template", section.line)
        details = story.section("Component details")
        if details and details.heading != f"Component details: {story.component}":
            self.add("error", "sections", f"The component section must be headed "
                     f"\"Component details: {story.component}\"", details.line)
        sentence = story.section("Story")
        if sentence and not all(re.search(p, sentence.text, re.IGNORECASE) for p in (r"\bas an? ", r"\bI want\b",
                                                                                      r"\bso that\b")):
            self.add("error", "sections", "The Story section must read \"As a role, I want capability, so that "
                     "benefit\"", sentence.line)
        scope = story.section("Scope")
        if scope and not (re.search(r"in scope", scope.text, re.I) and re.search(r"out of scope", scope.text, re.I)):
            self.add("error", "sections", "Scope needs both In scope and Out of scope", scope.line)
        dependencies = story.section("Dependencies")
        if dependencies and not (re.search(r"blocked by", dependencies.text, re.I)
                                 and re.search(r"\bblocks\b", dependencies.text, re.I)):
            self.add("warning", "dependencies", "Dependencies should give Blocked by and Blocks", dependencies.line)

    def check_criteria(self) -> None:
        criteria = self.story.criteria
        section = self.story.section("Acceptance criteria")
        if section is None:
            return
        if not criteria:
            self.add("error", "criteria", "No acceptance criterion: each is an `### AC-<n>:` heading over a gherkin "
                     "block", section.line)
            return
        numbers = [c.number for c in criteria]
        if numbers != list(range(1, len(criteria) + 1)):
            self.add("error", "criteria", f"The criteria must be numbered from AC-1 without gaps, not "
                     f"{', '.join(f'AC-{n}' for n in numbers)}", section.line)
        for criterion in criteria:
            words = {step.split(" ", 1)[0].lower() for step in criterion.steps if step}
            missing = [w for w in ("given", "when", "then") if w not in words]
            if missing:
                self.add("error", "criteria", f"AC-{criterion.number} lacks {', '.join(m.title() for m in missing)} "
                         f"in its gherkin block", criterion.line)

    def check_contracts(self) -> None:
        story, catalog = self.story, self.catalog
        if story.component not in catalog.components:
            return
        table = _contracts_table(story)
        for contract in set(story.contracts) | set(table):
            if contract not in catalog.contracts:
                self.add("error", "catalog", f"{contract} isn't a contract in the catalog", 1)
        for contract in story.contracts:
            if contract in catalog.contracts and contract not in catalog.owns(story.component):
                self.add("error", "contracts", f"{story.component} doesn't own {contract}: its change belongs in "
                         f"{catalog.owner(contract)}'s story", 1)
        for contract in set(story.contracts) ^ set(table):
            self.add("warning", "contracts", f"{contract} is in the "
                     f"{'header' if contract in story.contracts else 'Contracts and data table'} but not the "
                     f"{'Contracts and data table' if contract in story.contracts else 'header'}")
        if (catalog.components[story.component] or {}).get("defines_schemas") is False:
            schemas = sorted(c for c in set(story.contracts) | set(table) if catalog.is_schema(c))
            if schemas:
                self.add("error", "schemas", f"A {story.component} story never changes a schema: "
                         f"{', '.join(schemas)} belongs in "
                         f"{' or '.join(sorted({catalog.owner(c) for c in schemas}))}'s story", 1)

    def check_status(self) -> None:
        story = self.story
        status = story.header.get("status")
        if status in ("approved", "created") and story.open_questions:
            section = story.section("Open questions")
            self.add("error", "status", f"A story can't be {status} with open questions", section.line if section
                     else None)
        if status == "created" and not story.header.get("id"):
            self.add("error", "status", "A created story has its GitLab id", 1)


def _contracts_table(story: Story) -> dict[str, str]:
    """The Contracts and data table's rows: contract to change."""
    section = story.section("Contracts and data")
    rows = {}
    for _, line in section.lines if section else []:
        cells = [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and line.strip().startswith("|") and not set(cells[0]) <= set("-: ") \
                and cells[0].lower() != "contract":
            rows[cells[0]] = cells[1].lower()
    return rows


def _check_set(stories: list[Story], catalog: Catalog) -> list[Finding]:
    findings = []
    by_ref = {s.ref: s for s in stories if s.ref}
    by_id = {str(s.header["id"]): s for s in stories if s.header.get("id")}  # created ones, by their GitLab id
    seen: dict[str, Story] = {}
    for story in stories:
        if story.component in seen:
            findings.append(Finding("error", "dependencies", f"Two stories for {story.component}: "
                                    f"{seen[story.component].file.name} and {story.file.name}", str(story.file), 1))
        seen[story.component] = story
    changed = {c for s in stories for c in s.contracts}
    for story in stories:
        for ref in story.blocked_by:
            if not re.fullmatch(r"S\d+", ref):
                continue  # a GitLab id: created already, outside this set
            blocker = by_ref.get(ref)
            if blocker is None:
                findings.append(Finding("error", "dependencies", f"Blocked by {ref}, which isn't in the set",
                                        str(story.file), 1))
            elif story.order is not None and blocker.order is not None and blocker.order >= story.order:
                findings.append(Finding("error", "dependencies", f"Blocked by {ref} ({blocker.component}), which "
                                        f"comes after it", str(story.file), 1))
        waits_for = {(by_ref.get(r) or by_id[r]).component for r in story.blocked_by if r in by_ref or r in by_id}
        for owner in sorted(catalog.blocked_by(story.component, changed) - waits_for):
            if owner in seen:
                findings.append(Finding("warning", "dependencies", f"It consumes a contract {owner}'s story changes, "
                                        f"so it's blocked by {seen[owner].ref}", str(story.file), 1))
    return findings
