"""The Spec Validator's checks for mapping specs, as defined in mappings/FORMAT.md.

Checks the header, the tables and every row against the internal model, the lookups and the assembly spec, and,
when the spec jar can be found, every source path against the upstream's own spec.
"""

from __future__ import annotations

import re
from pathlib import Path

from bridge_kit.internal_model import Field, InternalModel, ModelError
from bridge_kit.mappings import (
    CATEGORIES, HEADER_KEYS, MODEL_CHANGES_SECTION, QUESTIONS_SECTION, REQUIRED_COLUMNS, REVERSE_ENGINEERED_COLUMNS,
    RULES, STATUSES, MappingSpec, Row, Table, clean, load_assembly, load_lookup, load_mapping, normalize_path,
    repo_root,
)
from bridge_kit.markdown import FormatError
from bridge_kit.spec_resolver import ResolveError
from bridge_kit.spec_resolver import resolve as resolve_spec
from bridge_kit.specs import SourceError, resolver_for
from bridge_kit.validators import Finding

NEEDS_DETAILS = ("constant", "lookup", "format", "combine", "condition", "derive")
CONFIDENCE_LEVELS = ("high", "medium", "low")


class MappingValidator:
    def __init__(self, model: InternalModel, maven_repositories: list[Path] | None = None):
        self.model = model
        self.repositories = maven_repositories or []

    def validate(self, path: Path) -> list[Finding]:
        return _Run(self, path).findings


class _Run:
    """One validation of one mapping file."""

    def __init__(self, validator: MappingValidator, path: Path):
        self.model = validator.model
        self.repositories = validator.repositories
        self.path = path
        self.findings: list[Finding] = []
        self.root = repo_root(path)
        self.relative = str(path.resolve().relative_to(self.root / "mappings")) if self.root else path.name
        try:
            self.spec = load_mapping(path)
        except FormatError as e:
            self.add("error", "format", str(e), e.line)
            return
        self.fields: dict[str, dict[str, Field]] = {}
        self.check_header()
        self.check_tables()
        self.check_status()
        self.check_sources()

    def add(self, severity: str, check: str, message: str, line: int | None = None, row: str | None = None) -> None:
        self.findings.append(Finding(severity, check, message, str(self.path), line, row))

    # Header

    def check_header(self) -> None:
        header = self.spec.header
        for key in HEADER_KEYS:
            if not str(header.get(key, "")).strip():
                self.add("error", "header", f"The header has no {key}", 1)
        if header.get("category") and header["category"] not in CATEGORIES:
            self.add("error", "header", f"category must be one of {', '.join(CATEGORIES)}", 1)
        if header.get("status") and header["status"] not in STATUSES:
            self.add("error", "header", f"status must be one of {', '.join(STATUSES)}", 1)
        if header.get("origin") not in (None, "reverse-engineered"):
            self.add("error", "header", "origin, when present, must be reverse-engineered", 1)
        version = str(header.get("target_schema_version", ""))
        if self.model.version and version and version != self.model.version:
            self.add("warning", "header", f"Written against internal model {version}, which is now "
                     f"{self.model.version}: check for new, renamed or removed fields", 1)
        upstream = str(header.get("upstream", ""))
        if upstream and self.path.parent.name != upstream:
            self.add("warning", "header", f"The file is in {self.path.parent.name}/, but its upstream is {upstream}", 1)
        if not self.spec.tables:
            self.add("error", "tables", "The file has no mapping tables")
        elif header.get("target") and normalize_path(self.spec.tables[0].path) != normalize_path(str(header["target"])):
            self.add("error", "tables", f"The first table is {self.spec.tables[0].path}, but the target is "
                     f"{header['target']}", self.spec.tables[0].line)
        for section in (MODEL_CHANGES_SECTION, QUESTIONS_SECTION):
            if section not in self.spec.sections:
                self.add("error", "sections", f"The section '{section}' is missing")

    # Tables and rows

    def check_tables(self) -> None:
        roots = self.model.payload_roots
        for index, table in enumerate(self.spec.tables):
            if table.path.split(".")[0] not in roots:
                self.add("error", "target", f"Write {table.path} from the payload root: "
                         f"{self.model.canonical(table.path)}", table.line)
            try:
                self.fields[table.path] = self.model.fields(self.model.resolve(table.path))
            except ModelError as e:
                self.add("error", "target", f"Table {table.path}: {e}", table.line)
                continue
            self.check_columns(table)
            if index > 0:
                self.check_parent(table)
            self.check_numbering(table, index)
            for row in table.rows:
                self.check_row(table, row)
            self.check_coverage(table)

    def check_columns(self, table: Table) -> None:
        if not table.columns:
            self.add("error", "columns", f"Table {table.path} has no table", table.line)
            return
        missing = [c for c in REQUIRED_COLUMNS if c not in table.columns]
        if missing:
            self.add("error", "columns", f"Table {table.path} lacks the columns {', '.join(missing)}", table.line)
        if self.spec.reverse_engineered:
            missing = [c for c in REVERSE_ENGINEERED_COLUMNS if c not in table.columns]
            if missing:
                self.add("error", "columns", f"A reverse-engineered spec needs the columns {', '.join(missing)}",
                         table.line)

    def check_parent(self, table: Table) -> None:
        if self.spec.parent_row(table) is None:
            self.add("error", "tables", f"Table {table.path} has no parent row naming its field", table.line)

    def check_numbering(self, table: Table, index: int) -> None:
        prefix = ""
        if index > 0:
            parent = self.spec.parent_row(table)
            if parent is None:
                return
            prefix = parent[1].number + "."
        for position, row in enumerate(table.rows, start=1):
            expected = f"{prefix}{position}"
            if row.number != expected:
                self.add("error", "numbering", f"Row {row.number or '(blank)'} should be {expected}", row.line, row.number)

    def check_row(self, table: Table, row: Row) -> None:
        field = self.fields[table.path].get(row.field)
        if field is None:
            self.add("error", "field", f"{row.field or '(blank)'} isn't a field of {table.path}", row.line, row.number)
            return
        if row.rule not in RULES:
            self.add("error", "rule", f"Unknown rule '{row.rule}'", row.line, row.number)
            return
        if row.rule == "not mapped":
            if row.source:
                self.add("error", "not-mapped", "A not mapped row has no source", row.line, row.number)
            if not row.notes:
                self.add("error", "not-mapped", "A not mapped row needs its reason in Notes", row.line, row.number)
            if field.required:
                self.add("error", "not-mapped", f"{row.field} is required by the internal model", row.line, row.number)
            return
        if row.rule == "tbd":
            if not (row.details or row.notes):
                self.add("error", "tbd", "A TBD row needs its open question in Details or Notes", row.line, row.number)
            return
        if not row.sources:
            self.add("error", "source", "The row has no source", row.line, row.number)
        elif "," in row.source:
            self.add("error", "source", "Sources aren't separated by commas: keep the main one in Source and name the "
                     "others in Details (only a combine row joins several with +)", row.line, row.number)
        elif len(row.sources) > 1 and row.rule != "combine":
            self.add("error", "source", "Only a combine row lists several sources: keep the main one in Source and "
                     "name the others in Details", row.line, row.number)
        if row.rule in NEEDS_DETAILS and not row.details:
            self.add("error", "details", f"A {row.rule} row needs Details", row.line, row.number)
        elif row.rule == "format" and not re.search(r"→|->|\bcase\b", row.details, re.IGNORECASE):
            self.add("warning", "rule", "A format gives its pattern as from → to (`yyyyMMdd → yyyy-MM-dd`) or a "
                     "case change; one that only converts the type, keeping all of the value, is copy", row.line,
                     row.number)
        if row.rule == "list" and not field.is_list:
            self.add("error", "rule", f"{row.field} isn't a list, so the rule can't be list", row.line, row.number)
        self.check_if_missing(table, row, field)
        if row.rule == "lookup":
            self.check_lookup(table, row, field)
        if self.spec.reverse_engineered:
            self.check_reverse_engineered(row)

    def check_if_missing(self, table: Table, row: Row, field: Field) -> None:
        value = row.if_missing.strip()
        keyword = value.lower()
        if not value:
            self.add("error", "if-missing", "If missing is required", row.line, row.number)
        elif keyword == "skip":
            if not normalize_path(table.path).endswith("[]"):
                self.add("error", "if-missing", "skip leaves out a list item, but this table isn't a list item",
                         row.line, row.number)
        elif keyword == "empty list":
            if not field.is_list:
                self.add("error", "if-missing", f"{row.field} isn't a list, so it can't be an empty list",
                         row.line, row.number)
        elif keyword == "omit":
            if field.required and not row.notes:
                self.add("warning", "if-missing", f"{row.field} is required by the internal model, so omit leaves "
                         "out the whole object: say so in Notes", row.line, row.number)
        elif keyword != "error":
            if not (value.startswith("`") and value.endswith("`")):
                self.add("error", "if-missing", f"Unknown If missing value '{value}': use error, omit, skip, "
                         "empty list or a `default`", row.line, row.number)
            elif "`" in clean(value):
                self.add("error", "if-missing", f"Write the default in one pair of backticks: "
                         f"`{clean(value).strip('`').strip()}`", row.line, row.number)
            else:
                problem = _default_problem(clean(value), field)
                if problem:
                    self.add("error", "if-missing", problem, row.line, row.number)

    def check_lookup(self, table: Table, row: Row, field: Field) -> None:
        name = row.lookup_name
        if not name:
            self.add("error", "lookup", "A lookup row names its table in Details, e.g. `account-type`", row.line,
                     row.number)
            return
        if self.root is None or not (self.root / "lookups" / f"{name}.md").exists():
            self.add("error", "lookup", f"lookups/{name}.md doesn't exist", row.line, row.number)
            return
        try:
            lookup = load_lookup(self.root / "lookups" / f"{name}.md")
        except FormatError as e:
            self.add("error", "lookup", f"lookups/{name}.md: {e}", row.line, row.number)
            return
        target = f"{normalize_path(table.path)}.{row.field}"
        if normalize_path(lookup.target) != target:
            self.add("error", "lookup", f"lookups/{name}.md produces {lookup.target or '(no target)'}, not {target}",
                     row.line, row.number)
        allowed = field.enum
        if allowed:
            wrong = sorted({v for v in lookup.entries.values() if v not in allowed})
            if wrong:
                self.add("error", "lookup", f"lookups/{name}.md maps to values {target} doesn't allow: "
                         f"{', '.join(wrong)}", row.line, row.number)
        if lookup.otherwise is None:
            self.add("error", "lookup", f"lookups/{name}.md has no Otherwise line", row.line, row.number)
        elif lookup.otherwise not in ("omit", "skip", "error") and allowed and lookup.otherwise not in allowed:
            self.add("error", "lookup", f"lookups/{name}.md: Otherwise {lookup.otherwise} isn't allowed for {target}",
                     row.line, row.number)
        elif lookup.otherwise == "skip" and not normalize_path(table.path).endswith("[]"):
            self.add("error", "lookup", f"lookups/{name}.md: Otherwise skip needs a list item table", row.line,
                     row.number)

    def check_reverse_engineered(self, row: Row) -> None:
        if not (row.code or "").strip():
            self.add("error", "code", "A reverse-engineered row needs a code reference", row.line, row.number)
        if row.confidence not in CONFIDENCE_LEVELS:
            self.add("error", "confidence", f"Confidence must be one of {', '.join(CONFIDENCE_LEVELS)}", row.line,
                     row.number)
        elif row.confidence == "low" and not row.notes:
            self.add("error", "confidence", "A low-confidence row needs the reason in Notes", row.line, row.number)

    def check_coverage(self, table: Table) -> None:
        fields = self.fields[table.path]
        listed = {row.field for row in table.rows}
        filled_elsewhere = self.assembly_filled(table)
        for name, field in fields.items():
            if name not in listed and name not in filled_elsewhere:
                self.add("error", "coverage", f"{table.path} has no row for {name}", table.line)
        for row in table.rows:
            field = fields.get(row.field)
            if field is None or not field.is_object or row.rule in ("not mapped", "tbd"):
                continue
            child = f"{normalize_path(table.path)}.{row.field}{'[]' if field.is_list else ''}"
            if self.spec.table(child) is None:
                self.add("error", "coverage", f"{row.field} is an object: it needs its own table ({child})",
                         row.line, row.number)

    def assembly_filled(self, table: Table) -> set[str]:
        """Fields of the table that the assembly spec fills from other mapping files."""
        if self.root is None or not (self.root / "assembly").is_dir():
            return set()
        filled = set()
        prefix = normalize_path(table.path) + "."
        for file in sorted((self.root / "assembly").glob("*.md")):
            try:
                branches = load_assembly(file).branches
            except FormatError:
                continue
            for branch in branches:
                if branch.path.startswith(prefix) and branch.mapping != self.relative:
                    rest = branch.path[len(prefix):]
                    if "." not in rest.removesuffix("[]"):
                        filled.add(rest.removesuffix("[]"))
        return filled

    # Status gates

    def check_status(self) -> None:
        if self.spec.header.get("status") != "approved":
            return
        for table in self.spec.tables:
            for row in table.rows:
                if row.rule == "tbd":
                    self.add("error", "status", "An approved spec can't have TBD rows", row.line, row.number)
                if row.proposed:
                    self.add("error", "status", "An approved spec can't have proposed rows", row.line, row.number)
        line, text = self.spec.sections.get(QUESTIONS_SECTION, (None, ""))
        if text.strip().rstrip(".").lower() not in ("", "none"):
            self.add("error", "status", "An approved spec can't have open questions", line)

    # Sources against the upstream's spec

    def check_sources(self) -> None:
        if not self.spec.tables:
            return
        category = self.spec.header.get("category")
        if category == "JDBC":
            self.add("info", "source", "JDBC sources aren't checked: the columns come from the service's own query")
            return
        location = self.spec_file()
        if location is None and not self.repositories:
            # Found as `bridge-kit spec resolve` finds it: the Nexus URL, else Maven's own settings and local repository
            try:
                resolution = resolve_spec(str(self.spec.header.get("spec", "")))
            except ResolveError as e:
                self.add("warning", "source", f"Sources aren't checked: {e}", 1)
                return
            if resolution.status != "resolved" or not resolution.location:
                self.add("warning", "source", f"Sources aren't checked: {resolution.message}", 1)
                return
            location = Path(resolution.location)
        try:
            resolver = resolver_for(self.spec.header, self.repositories, location)
        except SourceError as e:
            self.add("warning", "source", f"Sources aren't checked: {e}", 1)
            return
        if resolver is None:
            return
        nodes = {}
        for index, table in enumerate(self.spec.tables):
            node = None
            try:
                if index == 0:
                    # For REST, a root without a path in `code` ("the response body") is the body itself
                    if table.source_root_path is None and category == "REST":
                        node, _ = resolver.root("")
                    elif table.source_root_path is None:
                        self.add("warning", "source", "The Source root names no path in `code`, so sources aren't "
                                 "checked", table.source_root_line or table.line)
                    else:
                        node, warnings = resolver.root(table.source_root_path)
                        for warning in warnings:
                            self.add("warning", "source", f"Source root: {warning}", table.source_root_line)
                else:
                    parent = self.spec.parent_row(table)
                    parent_node = nodes.get(parent[0].path) if parent else None
                    if parent_node is not None and len(parent[1].sources) == 1:
                        node, _ = resolver.child(parent_node, parent[1].sources[0])
            except SourceError as e:
                self.add("error", "source", f"Source root: {e}", table.source_root_line or table.line)
            nodes[table.path] = node
            if node is not None:
                for row in table.rows:
                    self.check_row_sources(resolver, node, row)

    def spec_file(self) -> Path | None:
        """The spec, when the header names a file in the repo rather than a jar: a spec not published to Nexus yet."""
        spec = str(self.spec.header.get("spec", "")).strip()
        if self.root is None or not spec or ":" in spec:
            return None
        file = (self.root / spec).resolve()
        return file if file.is_file() else None

    def check_row_sources(self, resolver, node, row: Row) -> None:
        for source in row.sources:
            if source.startswith("request:"):
                continue
            try:
                found, warnings = resolver.child(node, source)
            except SourceError as e:
                self.add("error", "source", f"{source} doesn't exist in the spec: {e}", row.line, row.number)
                continue
            for warning in warnings:
                self.add("warning", "source", warning, row.line, row.number)
            if row.rule == "lookup" and found.enum and len(row.sources) == 1:
                self.check_lookup_codes(row, found.enum)

    def check_lookup_codes(self, row: Row, codes: list[str]) -> None:
        if self.root is None or not row.lookup_name:
            return
        file = self.root / "lookups" / f"{row.lookup_name}.md"
        if not file.exists():
            return
        lookup = load_lookup(file)
        unknown = sorted(set(lookup.entries) - set(codes))
        if unknown:
            self.add("warning", "lookup", f"lookups/{row.lookup_name}.md has codes the spec doesn't define: "
                     f"{', '.join(unknown)}", row.line, row.number)
        uncovered = [c for c in codes if c not in lookup.entries]
        if uncovered and lookup.otherwise == "error":
            self.add("error", "lookup", f"lookups/{row.lookup_name}.md doesn't cover the spec's codes "
                     f"{', '.join(uncovered)}, and Otherwise is error", row.line, row.number)


def _default_problem(value: str, field: Field) -> str | None:
    if field.enum and value not in field.enum:
        return f"Default {value} isn't one of {field.name}'s values"
    if field.kind == "boolean" and value not in ("true", "false"):
        return f"Default {value} isn't a boolean"
    if field.kind in ("number", "integer"):
        try:
            float(value)
        except ValueError:
            return f"Default {value} isn't a number"
    if field.is_list:
        return f"{field.name} is a list: use empty list rather than a default"
    return None
