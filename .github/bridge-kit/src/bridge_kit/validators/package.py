"""`bridge-kit validate package <id>`: the Spec Validator's package checks. Whether a requirement package gives each
component's developers what they need to build from without coming back to ask.

The package, in local mode, is the work folder (`work/<id>/`, with or without its slug): `impact.md`,
`model-change.md`, `decisions.md`, the stories in `stories/`, the mapping requests and spec digests in `inputs/`; and
the files the stories implement (the mapping specs and the assembly spec). The model change is in the model's checkout.

First every file's own checks, then what only the files together can say:

1. Every file's own validator: the mapping specs, the requests, the digests, the model change, `impact.md`, the stories
   as a set.
2. Everything approved and nothing open; every file committed, so the package can be locked at one commit.
3. One story per component `impact.md` names, and none for a component it doesn't.
4. Every file `impact.md` cites, and the model change, implemented by a story; every file a story implements there.
5. One model version, and contract changes that agree across `model-change.md`, `impact.md` and the stories.
6. Every path the model change adds has an owner: a mapping row or the assembly on the input side, a story on the
   output side.
7. Every mapping spec has its assembly row, naming it, with when it's called, with what, and what a failure does.
8. The requests and the digests agree with the specs drafted from them, and each cell of the BA's rough mapping a
   spec's Notes cite ("From the BA's rough mapping, `Mapping!D12`") is in the rough mapping its request names.

Errors block approval; warnings are for the BA to judge. Inputs never change once added, so their open questions are
answered elsewhere (the specs, `decisions.md`), not checked here.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from bridge_kit.config import Config
from bridge_kit.internal_model import InternalModel, open_model
from bridge_kit.mappings import NOT_MAPPED_SECTION, MappingSpec, clean, load_assembly, load_mapping, normalize_path
from bridge_kit.markdown import FormatError, code_spans, read_markdown
from bridge_kit.rough_mapping import RoughMappingError, check, cited, tables
from bridge_kit.spec_digest import ANSWER_COLUMNS, path_key
from bridge_kit.stories import Story, load_story
from bridge_kit.validators import Finding
from bridge_kit.validators.digest import answer_path, is_not_available, validate_digest
from bridge_kit.validators.mapping import MappingValidator
from bridge_kit.validators.model import MR_FILE, validate_model
from bridge_kit.validators.request import validate_request
from bridge_kit.validators.story import validate_stories

APPROVED = {"mapping": ("approved", "implemented"), "assembly": ("approved", "implemented"),
            "story": ("approved", "created")}
KINDS = {"mapping": "The mapping spec", "assembly": "The assembly spec", "story": "The story"}
PACKAGE_PATH = re.compile(r"^(mappings|assembly|work)/[\w./-]+\.md$")
CONTRACT_CHANGE = re.compile(r"`([\w-]+)`\s+(additive|breaking)\b")
NOTHING = {"", "none", "n/a", "-", "—"}


@dataclass
class Impact:
    file: Path
    components: dict[str, int] = field(default_factory=dict)  # component -> its heading's line
    contracts: dict[str, dict[str, str]] = field(default_factory=dict)  # component -> contract -> change
    cited: set[str] = field(default_factory=set)  # package files it names, by path in the BA repo
    questions: tuple[int, str] | None = None  # the Open questions section's line and text


def work_folder(ba_repo: Path, work_item: str) -> Path | None:
    """The work item's folder, with or without its slug."""
    found = sorted(p for p in (ba_repo / "work").glob(f"{work_item}*")
                   if p.is_dir() and (p.name == work_item or p.name.startswith(f"{work_item}-")))
    return found[0] if found else None


def load_impact(path: Path) -> Impact:
    """`impact.md`'s affected components (each `### <component>` under Affected components), their contract
    changes (`- **Contracts:**`), the package files it cites and its open questions."""
    impact = Impact(path)
    section, component, questions = None, None, []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for span in code_spans(line):
            if PACKAGE_PATH.match(span.strip()):
                impact.cited.add(span.strip().split("@", 1)[0])
        if line.startswith("## "):
            section, component = line[3:].strip(), None
            if section == "Open questions":
                impact.questions = (number, "")
        elif section == "Affected components" and line.startswith("### "):
            component = line[4:].strip().strip("`")
            impact.components[component] = number
            impact.contracts[component] = {}
        elif component and "**Contracts:**" in line:
            impact.contracts[component].update(CONTRACT_CHANGE.findall(line))
        elif section == "Open questions":
            questions.append(line)
    if impact.questions:
        impact.questions = (impact.questions[0], "\n".join(questions).strip())
    return impact


def validate_package(work_item: str, ba_repo: Path, config: Config, maven_repositories: list[Path] | None = None,
                     repository_url: str | None = None, build: bool = True) -> list[Finding]:
    ba_repo = ba_repo.resolve()
    findings: list[Finding] = []

    def add(severity: str, check: str, message: str, file: Path | str, line: int | None = None,
            row: str | None = None) -> None:
        findings.append(Finding(severity, check, message, _relative(file, ba_repo), line, row))

    folder = work_folder(ba_repo, work_item)
    if folder is None:
        add("error", "package", f"No work folder for {work_item}: work/{work_item}/", f"work/{work_item}")
        return findings
    impact_file = folder / "impact.md"
    if not impact_file.exists():
        add("error", "package", "No impact.md: it names the components the package is for", impact_file)
        return findings
    impact = load_impact(impact_file)
    stories = [load_story(p) for p in sorted((folder / "stories").glob("*.md"))]
    if not stories:
        add("error", "package", "No stories: one per affected component, in stories/", folder / "stories")
    model_change = folder / MR_FILE
    implemented = {path for story in stories for path in story.implements}
    specs, assemblies = [], []
    for path in sorted(implemented):
        file = ba_repo / path
        if not file.exists():
            continue
        if path.startswith("mappings/") and "/lookups/" not in path:
            specs.append(_load(load_mapping, file, add))
        elif path.startswith("assembly/"):
            assemblies.append(file)
    specs = [s for s in specs if s is not None]
    model = open_model(config.model.path, config.model_layout)
    requests = sorted((folder / "inputs").glob("mapping-request*.md"))
    digests = sorted((folder / "inputs").glob("spec-digest-*.md"))

    # 1. Every file's own checks
    validator = MappingValidator(model, maven_repositories)
    for spec in specs:
        findings += [_rebased(f, ba_repo) for f in validator.validate(spec.file)]
    for request in requests:  # its blank sections were the drafter's to ask about, and the spec is drafted now
        findings += [_rebased(f, ba_repo) for f in validate_request(request, model, repository_url)
                     if f.check != "blank"]
    for digest in digests:
        findings += [_rebased(f, ba_repo) for f in validate_digest(digest, repository_url)]
    from bridge_kit.validators.impact import validate_impact  # it reads impact.md as this module does

    findings += [f for f in validate_impact(work_item, ba_repo) if f.check not in ("impact", "open")]
    if model_change.exists():
        _check_model_branch(model_change, config, add)
        findings += [_rebased(f, ba_repo) for f in validate_model(work_item, config, ba_repo / ".work", ba_repo,
                                                                  build=build)]
    if stories:  # an implemented file that isn't there is an error here (check 4), not the story check's warning
        findings += [_rebased(f, ba_repo) for f in validate_stories([s.file for s in stories], ba_repo)
                     if f.check != "implements"]

    # 2. Approved, nothing open, committed
    for spec in specs:
        _check_status("mapping", spec.header.get("status"), spec.file, add)
    for assembly in assemblies:
        _check_status("assembly", _front(assembly).get("status"), assembly, add)
    for story in stories:
        _check_status("story", story.header.get("status"), story.file, add)
    if impact.questions and unanswered(impact.questions[1]):
        add("error", "open", "impact.md has open questions: answer them before the package", impact_file,
            impact.questions[0])
    if model_change.exists():
        _check_model_questions(model_change, add)
    _check_committed(ba_repo, [folder, *(ba_repo / p for p in sorted(implemented))], add)

    # 3. One story per affected component
    by_component: dict[str, list[Story]] = {}
    for story in stories:
        by_component.setdefault(story.component, []).append(story)
    for component, line in impact.components.items():
        if component not in by_component:
            add("error", "components", f"impact.md names {component}, but it has no story", impact_file, line)
    for component, written in by_component.items():
        if component and component not in impact.components:
            for story in written:
                add("error", "components", f"A story for {component}, which impact.md doesn't name", story.file, 1)

    # 4. Every package file implemented, and there
    for story in stories:
        for path in story.implements:
            if not (ba_repo / path).exists():
                add("error", "implements", f"Implements {path}, which isn't in the BA repo", story.file, 1)
    wanted = set(impact.cited) | ({_relative(model_change, ba_repo)} if model_change.exists() else set())
    for path in sorted(wanted - implemented):
        add("error", "implements", f"{path} is part of the package, but no story implements it", impact_file)

    # 5. One model version, agreed contract changes
    for story in stories:
        if story.component in impact.contracts and story.contracts != impact.contracts[story.component]:
            add("error", "contracts", f"The story changes {_contracts(story.contracts)}; impact.md says "
                                      f"{_contracts(impact.contracts[story.component])}", story.file, 1)
    change = _front(model_change) if model_change.exists() else {}
    if change:
        _check_versions(change, model_change, specs, assemblies, stories, config, add)

    # 6. Every added path has an owner
    if model_change.exists():
        _check_added_paths(model_change, specs, assemblies, stories, config, add)

    # 7. Every mapping spec has its assembly row
    branches = [b for file in sorted((ba_repo / "assembly").glob("*.md")) for b in load_assembly(file).branches]
    for spec in specs:
        _check_assembly_row(spec, branches, ba_repo, add)

    # 8. The requests and the digests against the specs
    for request in requests:
        _check_request(request, specs, add)
    for spec in specs:
        _check_rough_citations(spec, requests, ba_repo, add)
    for digest in digests:
        _check_digest(digest, specs, add)
    return sorted(findings, key=lambda f: ("error", "warning", "info").index(f.severity))


def _relative(file: Path | str, ba_repo: Path) -> str:
    path = Path(file)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(ba_repo).as_posix()
        except ValueError:
            return str(path)
    return path.as_posix()


def _rebased(finding: Finding, ba_repo: Path) -> Finding:
    finding.file = _relative(finding.file, ba_repo)
    return finding


def _load(loader, file: Path, add):
    try:
        return loader(file)
    except FormatError as e:
        add("error", "format", str(e), file, e.line)
        return None


def _front(file: Path) -> dict:
    try:
        return read_markdown(file.read_text(encoding="utf-8")).front_matter
    except FormatError:
        return {}


def _contracts(contracts: dict[str, str]) -> str:
    return ", ".join(f"{c} {change}" for c, change in sorted(contracts.items())) or "no contract"


def _check_status(kind: str, status, file: Path, add) -> None:
    if status not in APPROVED[kind]:
        add("error", "approved", f"{KINDS[kind]} is {status or 'without a status'}: it must be "
                                 f"{' or '.join(APPROVED[kind])} for the package", file, 1)


def unanswered(text: str) -> list[str]:
    """An Open questions section's questions with no answer: each bullet without an `Answer (…): …` line below it,
    or text that isn't a bullet and isn't "None"."""
    questions: list[list[str]] = []
    loose = []
    for line in text.splitlines():
        if line.startswith("- "):
            questions.append([line[2:].strip()])
        elif line.startswith(" ") and questions and line.strip():
            questions[-1].append(line.strip())
        elif line.strip():
            loose.append(line.strip())
    open_ = [" ".join(q) for q in questions if not any(part.lower().startswith("answer") for part in q[1:])]
    text_left = " ".join(loose).rstrip(".").strip().lower()
    return open_ + ([" ".join(loose)] if text_left and text_left not in NOTHING else [])


def _check_model_questions(model_change: Path, add) -> None:
    lines = model_change.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "## Open questions"), None)
    if start is None:
        return  # validate model reports a missing section
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    if unanswered("\n".join(lines[start + 1:end])):
        add("error", "open", "The model change has open questions: answer them before the package", model_change,
            start + 1)


def _check_model_branch(model_change: Path, config: Config, add) -> None:
    """In git mode the model's checkout must be on the change's branch, or the specs are checked against another
    model."""
    branch = str(_front(model_change).get("branch") or "")
    if not config.model.git or not branch:
        return
    result = subprocess.run(["git", "-C", str(config.model.path), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True, check=False)
    current = result.stdout.strip()
    if result.returncode == 0 and current != branch:
        add("error", "version", f"The model's checkout is on {current}, the change on {branch}: check out {branch}",
            model_change, 1)


def _check_committed(ba_repo: Path, paths: list[Path], add) -> None:
    inside = subprocess.run(["git", "-C", str(ba_repo), "rev-parse", "--is-inside-work-tree"], capture_output=True,
                            text=True, check=False)
    if inside.returncode != 0:
        return
    existing = [str(p) for p in paths if p.exists()]
    result = subprocess.run(["git", "-C", str(ba_repo), "status", "--porcelain", "--untracked-files=all", "--",
                             *existing], capture_output=True, text=True, check=False)
    top = subprocess.run(["git", "-C", str(ba_repo), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                         check=False).stdout.strip()
    for line in result.stdout.splitlines():
        file = Path(top) / line[3:].strip().strip('"')
        add("warning", "committed", "Not committed: the package is locked at one commit, so commit it first", file)


def _check_versions(change: dict, model_change: Path, specs: list[MappingSpec], assemblies: list[Path],
                    stories: list[Story], config: Config, add) -> None:
    version = str(change.get("version") or "")
    for spec in specs:
        if version and str(spec.header.get("target_schema_version")) != version:
            add("error", "version", f"Targets the model at {spec.header.get('target_schema_version')}; the change "
                                    f"makes it {version}", spec.file, 1)
    for assembly in assemblies:
        target = _front(assembly).get("target_schema_version")
        if version and target is not None and str(target) != version:
            add("error", "version", f"Targets the model at {target}; the change makes it {version}", assembly, 1)
    kind = str(change.get("change") or "")
    for story in stories:
        if story.component != config.model_repo:
            continue
        breaking = "breaking" in story.contracts.values()
        if kind == "breaking" and not breaking:
            add("error", "contracts", "The model change is breaking, but the story changes no contract as breaking",
                story.file, 1)
        elif kind == "additive" and breaking:
            add("error", "contracts", "The model change is additive, but the story says a contract breaks",
                story.file, 1)


def _added_paths(model_change: Path) -> list[tuple[int, str]]:
    """The paths the Changes table adds."""
    try:
        doc = read_markdown(model_change.read_text(encoding="utf-8"))
    except FormatError:
        return []
    section = doc.section("Changes")
    added = []
    for table in section.tables if section else []:
        columns = [c.lower() for c in table.columns]
        if "path" not in columns or "change" not in columns:
            continue
        for line, cells in table.rows:
            spans = code_spans(cells[columns.index("path")])
            if spans and cells[columns.index("change")].strip().lower().startswith("added"):
                added.append((line, normalize_path(spans[0])))
    return added


def _check_added_paths(model_change: Path, specs: list[MappingSpec], assemblies: list[Path],
                       stories: list[Story], config: Config, add) -> None:
    roots = {str(_front(a).get("root") or "") for a in assemblies} | {
        normalize_path(str(s.header.get("target") or "")).split(".", 1)[0] for s in specs}
    roots.discard("")
    filled = set()
    for spec in specs:
        for table in spec.tables:
            filled.add(normalize_path(table.path))
            filled.update(normalize_path(f"{table.path}.{row.field}") for row in table.rows)
    for assembly in assemblies:
        filled.update(b.path for b in load_assembly(assembly).branches)
    others = " ".join(s.body for s in stories if s.component != config.model_repo)
    for line, path in _added_paths(model_change):
        if path.split(".", 1)[0] in roots:
            if path not in filled:
                add("error", "added-paths", f"{path} is added, but no mapping or assembly row fills it",
                    model_change, line)
        else:
            name = path.rsplit(".", 1)[-1].removesuffix("[]")
            if not re.search(rf"\b{re.escape(name)}\b", others):
                add("warning", "added-paths", f"{path} is added, but no story outside the model's names {name}",
                    model_change, line)


def _check_assembly_row(spec: MappingSpec, branches: list, ba_repo: Path, add) -> None:
    mappings = ba_repo / "mappings"
    name = spec.file.resolve().relative_to(mappings).as_posix() if spec.file.resolve().is_relative_to(mappings) \
        else spec.file.name
    rows = [b for b in branches if b.mapping == name or b.mapping.endswith(f"/{name}")]
    if not rows:
        add("error", "assembly", f"No assembly row names {name}: when it's called, with what, and what a failure "
                                 f"does", spec.file, 1)
        return
    target = normalize_path(str(spec.header.get("target") or ""))
    for branch in rows:
        where = f"assembly row {branch.number}"
        if target and branch.path != target:
            add("error", "assembly", f"The {where} attaches it at {branch.path}; the spec targets {target}",
                spec.file, 1)
        for label, value in (("Called", branch.called), ("Called with", branch.called_with),
                             ("If the call fails", branch.if_fails)):
            if clean(value).lower() in NOTHING:
                add("error", "assembly", f"The {where} has no {label}", spec.file, 1)
        if clean(branch.attaches).lower() in NOTHING:
            add("warning", "assembly", f"The {where} doesn't say what it attaches", spec.file, 1)


def _check_request(request: Path, specs: list[MappingSpec], add) -> None:
    front = _front(request)
    upstream, operation = str(front.get("upstream") or ""), str(front.get("operation") or "")
    spec = next((s for s in specs if str(s.header.get("upstream")) == upstream
                 and str(s.header.get("operation")) == operation), None)
    if spec is None:
        add("error", "request", f"The request for {upstream} {operation} has no mapping spec a story implements",
            request, 1)
        return
    for key in ("target", "spec"):
        asked, drafted = str(front.get(key) or ""), str(spec.header.get(key) or "")
        if key == "target":
            asked, drafted = normalize_path(asked), normalize_path(drafted)
        if asked and asked != drafted:
            add("error", "request", f"The request's {key} is {asked}; {spec.file.name} has {drafted}", request, 1)


def _check_rough_citations(spec: MappingSpec, requests: list[Path], ba_repo: Path, add) -> None:
    """Each cell of the BA's rough mapping the spec's rows cite is in the rough mapping its request names: a row's
    decision has nothing behind it otherwise."""
    citing = [(row, ref) for table in spec.tables for row in table.rows for ref in cited(row.notes)]
    if not citing:
        return
    front = next((f for f in map(_front, requests) if str(f.get("upstream")) == str(spec.header.get("upstream"))
                  and str(f.get("operation")) == str(spec.header.get("operation"))), {})
    rough = str(front.get("rough_mapping") or "").strip()
    if not rough or rough.startswith("<"):
        for row, ref in citing:
            add("error", "rough-mapping", f"Row {row.number} cites the BA's rough mapping ({ref}), but its request "
                                          "names none", spec.file, row.line, row.number)
        return
    try:
        found = tables((ba_repo / rough).read_text(encoding="utf-8"))
    except (OSError, FormatError, RoughMappingError):
        return  # validate request reports it
    for row, ref in citing:
        if why := check(found, ref, str(front.get("rough_mapping_table") or "").strip() or None):
            add("error", "rough-mapping", f"Row {row.number} cites {ref} from the BA's rough mapping, but {why}",
                spec.file, row.line, row.number)


def _check_digest(digest: Path, specs: list[MappingSpec], add) -> None:
    try:
        doc = read_markdown(digest.read_text(encoding="utf-8"))
    except FormatError:
        return  # validate digest reports it
    upstream = str(doc.front_matter.get("upstream") or "")
    drafted = [s for s in specs if str(s.header.get("upstream")) == upstream]
    if not drafted:
        return
    for spec in drafted:
        explored, used = str(doc.front_matter.get("spec") or ""), str(spec.header.get("spec") or "")
        if explored and used and explored != used:
            add("warning", "digest", f"The digest explored {explored}; {spec.file.name} is drafted against {used}",
                digest, 1)
    section = doc.section("Where the data is")
    table = section.tables[0] if section and section.tables else None
    if table is None or table.columns[:len(ANSWER_COLUMNS)] != ANSWER_COLUMNS:
        return  # validate digest reports it
    for line, cells in table.rows:
        number, asked, operation, path = cells[0], cells[1], clean(cells[2]), answer_path(cells[3])
        if is_not_available(cells[2]) or not path or is_not_available(path):
            continue
        spec = next((s for s in drafted if str(s.header.get("operation")) == operation), None)
        if spec is not None and not _reads(spec, path):
            add("warning", "digest", f"{asked} ({path}): no row of {spec.file.name} reads it; map it, or record why "
                                     f"in decisions.md", digest, line, number)


def _reads(spec: MappingSpec, path: str) -> bool:
    """Whether a row reads the path, or the spec lists it among the fields it doesn't map."""
    wanted = path_key(path)
    for table in spec.tables:
        for row in table.rows:
            if any(path_key(spec.full_path(table, source)) == wanted for source in row.sources):
                return True
    not_mapped = spec.sections.get(NOT_MAPPED_SECTION, (None, ""))[1]
    return any(wanted == key or re.search(rf"[/.]{re.escape(key)}$", wanted)
               for key in (path_key(span) for span in code_spans(not_mapped)) if key)
