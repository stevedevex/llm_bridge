"""`bridge-kit validate impact <id>`: a requirement's impact analysis, `work/<id>/impact.md`, against
`templates/impact.md` and the component catalog. The Impact Analyzer's final check, and the BA's on one written by hand.

- The front matter names the work item and the requirement; the sections are there.
- Each `###` under Affected components is a component of the catalog, once, with its Why, Contracts and Confidence.
- Every component of the catalog is under Affected components or Not affected, never both.
- A Contracts line changes only contracts the component owns, each additive or breaking; a component that never
  defines a schema (`defines_schemas: false`) changes no schema contract.
- A component that owns a contract outside clients use has its External impact.
- Confidence is high, medium or low, and a low one is an open question too.
- Each package file it cites is there, or a warning: `impact.md` comes before the model change and the mapping specs
  it names, and the package check requires them. Its open questions are reported, as information: the package
  check stops on them.
"""

from __future__ import annotations

import re
from pathlib import Path

from bridge_kit.markdown import FormatError, code_spans, read_markdown
from bridge_kit.stories import CatalogError, load_catalog
from bridge_kit.validators import Finding
from bridge_kit.validators.package import CONTRACT_CHANGE, NOTHING, PACKAGE_PATH, unanswered, work_folder

SECTIONS = ("Data elements", "Affected components", "Not affected", "Open questions")
FIELDS = ("Why", "Contracts", "Confidence")
CONFIDENCE = ("high", "medium", "low")


def validate_impact(work_item: str, ba_repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    folder = work_folder(ba_repo, work_item)
    file = (folder or ba_repo / "work" / work_item) / "impact.md"
    shown = file.relative_to(ba_repo).as_posix() if file.is_relative_to(ba_repo) else str(file)

    def add(severity: str, check: str, message: str, line: int | None = None) -> None:
        findings.append(Finding(severity, check, message, shown, line))

    if not file.is_file():
        add("error", "impact", f"No impact analysis: write {shown} from templates/impact.md, or run /impact {work_item}")
        return findings
    try:
        catalog = load_catalog(ba_repo)
    except CatalogError as e:
        add("error", "catalog", str(e))
        return findings
    text = file.read_text(encoding="utf-8")
    try:
        front = read_markdown(text).front_matter
    except FormatError as e:
        add("error", "format", str(e), e.line)
        return findings

    if str(front.get("work_item") or "") != work_item:
        add("error", "front-matter", f"work_item should be {work_item}", 1)
    if not str(front.get("requirement") or "").strip():
        add("error", "front-matter", "The front matter has no requirement: its title", 1)

    sections, affected, not_affected = _read(text)
    for name in SECTIONS:
        if name not in sections:
            add("error" if name != "Data elements" else "warning", "sections", f"The section {name} is missing")
    if "Data elements" in sections and not any(line.lstrip().startswith("|") for _, line in sections["Data elements"]):
        add("warning", "data", "Data elements has no table: a row per data element, where each component has it",
            sections["Data elements"][0][0] if sections["Data elements"] else None)

    for name, (line, fields) in affected.items():
        if name not in catalog.components:
            add("error", "components", f"{name} isn't a component of architecture/components.yaml", line)
            continue
        for field in FIELDS:
            if field not in fields:
                add("error", "components", f"{name} has no **{field}:** line", line)
        owns = set(catalog.owns(name))
        changes = dict(CONTRACT_CHANGE.findall(fields.get("Contracts", (line, ""))[1]))
        for contract, change in changes.items():
            where = fields["Contracts"][0]
            if (catalog.components.get(name) or {}).get("defines_schemas") is False and catalog.is_schema(contract):
                add("error", "contracts", f"{name} never defines a schema: {contract} changes in the model's "
                                          "component, and this one consumes it", where)
            elif contract not in owns:
                owner = catalog.owner(contract)
                add("error", "contracts", f"{name} changes {contract}, which it doesn't own"
                                          + (f": {owner} does, and its own entry says so" if owner else ""), where)
        external = [c for c in owns if (catalog.contracts.get(c) or {}).get("external")]
        if (external or (catalog.components.get(name) or {}).get("external")) and "External impact" not in fields:
            add("error", "external", f"{name} owns {', '.join(external) or 'what outside clients use'}: say its "
                                     "External impact (breaking or not, the API version, what clients and the "
                                     "gateway must do), or none", line)
        confidence = fields.get("Confidence", (line, ""))[1].strip().split(" ")[0].strip(".,;:").lower()
        if "Confidence" in fields and confidence not in CONFIDENCE:
            add("error", "confidence", f"{name}'s confidence is high, medium or low, not {confidence or 'blank'}",
                fields["Confidence"][0])
        if confidence == "low" and not _section_text(sections.get("Open questions", [])):
            add("error", "confidence", f"{name}'s confidence is low: ask what would settle it under Open questions",
                fields["Confidence"][0])

    for name, line in not_affected.items():
        if name not in catalog.components:
            add("error", "components", f"Not affected names {name}, which isn't a component of the catalog", line)
        elif name in affected:
            add("error", "components", f"{name} is under both Affected components and Not affected", line)
    for name in catalog.components:
        if name not in affected and name not in not_affected:
            add("error", "coverage", f"{name} isn't under Affected components or Not affected: say whether the "
                                     "requirement touches it, and why")

    for number, line in enumerate(text.splitlines(), start=1):
        for span in code_spans(line):
            path = span.strip().split("@", 1)[0]
            if PACKAGE_PATH.match(path) and not (ba_repo / path).is_file():
                add("warning", "files", f"It cites {path}, which isn't there yet: the package needs it", number)
    questions = unanswered(_section_text(sections.get("Open questions", [])))
    if questions:
        add("info", "open", f"{len(questions)} open question(s): the package isn't ready while one is open",
            sections["Open questions"][0][0] if sections.get("Open questions") else None)
    return findings


def _read(text: str) -> tuple[dict, dict, dict]:
    """The sections' lines; each affected component's line and its fields (field -> (line, text)); and each component
    Not affected names, with its line."""
    sections: dict[str, list[tuple[int, str]]] = {}
    affected: dict[str, tuple[int, dict]] = {}
    not_affected: dict[str, int] = {}
    section, component = None, None
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            section, component = line[3:].strip(), None
            sections[section] = []
            continue
        if section is None:
            continue
        sections[section].append((number, line))
        if section == "Affected components" and line.startswith("### "):
            component = line[4:].strip().strip("`")
            affected.setdefault(component, (number, {}))
        elif section == "Affected components" and component and (m := re.match(r"\s*- \*\*([^*:]+):\*\*(.*)", line)):
            affected[component][1][m.group(1).strip()] = (number, m.group(2))
        elif section == "Affected components" and component and line.startswith("  ") and affected[component][1]:
            key = list(affected[component][1])[-1]  # a field's line wrapped onto the next
            field_line, value = affected[component][1][key]
            affected[component][1][key] = (field_line, f"{value} {line.strip()}")
        elif section == "Not affected" and (m := re.match(r"\s*- `?([\w-]+)`?\s*[:,—-]", line)):
            not_affected[m.group(1)] = number
    return sections, affected, not_affected


def _section_text(lines: list[tuple[int, str]]) -> str:
    text = "\n".join(line for _, line in lines).strip()
    return "" if text.lower().rstrip(".") in NOTHING else text
