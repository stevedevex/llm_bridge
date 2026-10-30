"""`bridge-kit work status <id>`: where a work item stands, worked out from its files, and the next step. The
Requirements Analyst starts from it; a BA can too.

The steps, in the order the work goes, each done, to do, with problems, or not needed:

1. **Requirement:** an input to start from (`requirement.md`, a GitLab story, a document).
2. **Breakdown** (`breakdown.md`) and 3. **evaluation** (`evaluation-NN.md`, its blocking questions answered): the
   Requirements Analyst's. Not needed once the impact analysis is there: the work has moved on.
4. **Impact** (`impact.md`), by `validate impact`, its open questions answered.
5. **Model change** (`model-change.md`), when `impact.md` names the model's component; its open questions answered.
6. **Mapping specs:** a spec drafted for each mapping request, and approved.
7. **Stories:** written, passing `validate story`, approved.
8. **Validation:** the latest `validation-NN.md`, its verdict.
9. **Published:** every story with its GitLab id.
10. **Tests:** the test cases written (`/write-tests`), passing `validate test-case`, every criterion covered
   (`tests coverage`), and approved by the tester and the BA.

Nothing is run but the file checks (`validate impact`, `validate story`, `validate test-case`, `tests coverage`): the
model's build and the package check are the Spec Validator's.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from bridge_kit.markdown import FormatError, read_markdown

DONE, TO_DO, PROBLEMS, NOT_NEEDED = "done", "to do", "problems", "not needed"


@dataclass
class Step:
    name: str
    state: str
    detail: str
    next: str = ""  # what to do, when it's to do or has problems


@dataclass
class WorkStatus:
    work_item: str
    folder: str | None
    steps: list[Step] = field(default_factory=list)

    @property
    def next(self) -> str:
        step = next((s for s in self.steps if s.state in (TO_DO, PROBLEMS)), None)
        return step.next if step else "Nothing: the stories are published and the test cases approved."

    def to_dict(self) -> dict:
        return {"work_item": self.work_item, "folder": self.folder, "steps": [asdict(s) for s in self.steps],
                "next": self.next}


def work_status(work_item: str, ba_repo: Path, model_repo: str | None = None) -> WorkStatus:
    from bridge_kit.case_coverage import coverage
    from bridge_kit.stories import CatalogError, load_catalog, load_story
    from bridge_kit.test_cases import load_test_case
    from bridge_kit.validators.impact import validate_impact
    from bridge_kit.validators.package import load_impact, unanswered, work_folder
    from bridge_kit.validators.story import validate_stories
    from bridge_kit.validators.test_case import validate_test_cases

    folder = work_folder(ba_repo, work_item)
    status = WorkStatus(work_item, folder.relative_to(ba_repo).as_posix() if folder else None)
    add = lambda *args: status.steps.append(Step(*args))  # noqa: E731
    if folder is None:
        add("Requirement", TO_DO, "no work folder", f"Start the work item: /read-story <its story> {work_item}, or "
                                                    f"/requirement {work_item}")
        return status
    inputs = folder / "inputs"

    # 1. The requirement
    kept = [_front(p) for p in sorted(inputs.glob("*.md"))] if inputs.is_dir() else []
    kinds = [str(f.get("kind") or "") for f in kept]
    given = (["requirement.md"] if (inputs / "requirement.md").is_file() else []) + \
        [f"{kinds.count(k)} {name}" for k, name in (("gitlab-issue", "GitLab story(ies)"),
                                                    ("gitlab-wiki-page", "wiki page(s)")) if k in kinds]
    documents = sum(k not in ("", "gitlab-issue", "gitlab-wiki-page") for k in kinds)
    given += [f"{documents} document(s)"] if documents else []
    add("Requirement", DONE if given else TO_DO, ", ".join(given) or "nothing yet",
        f"Add the requirement: /read-story <its story> {work_item}, or write {status.folder}/inputs/requirement.md")

    # 2 and 3. The breakdown and the evaluation, unless the work has moved on
    impact_file = folder / "impact.md"
    moved_on = impact_file.is_file()
    if (folder / "breakdown.md").is_file():
        add("Breakdown", DONE, "breakdown.md")
    else:
        add("Breakdown", NOT_NEEDED if moved_on else TO_DO, "the impact analysis is there" if moved_on else "",
            f"Break the requirement down: /requirement {work_item}")
    evaluations = sorted(folder.glob("evaluation-*.md"))
    if evaluations:
        blocking = unanswered(_section(evaluations[-1], "Blocking questions"))
        add("Evaluation", PROBLEMS if blocking else DONE,
            f"{evaluations[-1].name}" + (f": {len(blocking)} blocking question(s)" if blocking else ""),
            f"Answer the blocking questions in {evaluations[-1].name}, then /requirement {work_item} works them in")
    else:
        add("Evaluation", NOT_NEEDED if moved_on else TO_DO, "the impact analysis is there" if moved_on else "",
            f"Evaluate the requirement for gaps: /requirement {work_item}")

    # 4. The impact analysis
    affected: list[str] = []
    if not impact_file.is_file():
        add("Impact", TO_DO, "", f"Analyse its impact: /impact {work_item}")
    else:
        findings = validate_impact(work_item, ba_repo)
        errors = [f for f in findings if f.severity == "error"]
        open_ = [f for f in findings if f.check == "open"]
        affected = list(load_impact(impact_file).components)
        detail = "affects " + (", ".join(affected) or "nothing")
        if errors:
            add("Impact", PROBLEMS, f"{len(errors)} error(s)", f"Fix impact.md: bridge-kit validate impact {work_item}")
        elif open_:
            add("Impact", PROBLEMS, f"{detail}; {open_[0].message.split(':')[0]}",
                f"Answer the open questions in {status.folder}/impact.md")
        else:
            add("Impact", DONE, detail)

    # 5. The model change, when the model's component is affected
    try:
        catalog = load_catalog(ba_repo)
    except CatalogError:
        catalog = None
    model = next((name for name, entry in (catalog.components if catalog else {}).items()
                  if model_repo and (entry or {}).get("repo") == model_repo), None) or \
        next((c.get("source") for c in (catalog.contracts if catalog else {}).values()
              if (c or {}).get("kind") == "json-schema"), None)
    change = folder / "model-change.md"
    if change.is_file():
        front = _front(change)
        questions = unanswered(_section(change, "Open questions"))
        add("Model change", PROBLEMS if questions else DONE,
            f"{front.get('change')}, {front.get('base_version')} → {front.get('version')}"
            + (f"; {len(questions)} open question(s)" if questions else ""),
            f"Answer the open questions in {status.folder}/model-change.md")
    elif model and model in affected:
        add("Model change", TO_DO, f"{model} is affected", f"Design the model change: /model-change {work_item}")
    else:
        add("Model change", NOT_NEEDED, f"{model or 'the model'} isn't affected" if impact_file.is_file() else
            "until the impact analysis says")

    # 6. The mapping specs drafted from the requests
    requests = sorted(inputs.glob("mapping-request*.md")) if inputs.is_dir() else []
    if not requests:
        add("Mapping specs", NOT_NEEDED, "no mapping request")
    else:
        specs = {(str(f.get("upstream")), str(f.get("operation"))): (p, f) for p in sorted(
            (ba_repo / "mappings").glob("*/*.md")) if (f := _front(p)).get("upstream")}
        missing, drafts = [], []
        for request in requests:
            front = _front(request)
            found = specs.get((str(front.get("upstream")), str(front.get("operation"))))
            if found is None:
                missing.append(f"{front.get('upstream')} {front.get('operation')}")
            elif found[1].get("status") not in ("approved", "implemented"):
                drafts.append(found[0].relative_to(ba_repo).as_posix())
        if missing:
            add("Mapping specs", TO_DO, f"no spec yet for {', '.join(missing)}",
                f"Draft the mapping: /draft-mapping {work_item}")
        elif drafts:
            add("Mapping specs", PROBLEMS, f"{', '.join(drafts)} not approved",
                "The BA reviews and approves the mapping specs (their open questions answered first)")
        else:
            add("Mapping specs", DONE, f"{len(requests)} approved")

    # 7 to 9. The stories, the validation, publishing
    files = sorted((folder / "stories").glob("*.md"))
    stories = [load_story(f) for f in files]
    if not stories:
        add("Stories", TO_DO, "", f"Write the stories: /write-stories {work_item}")
    else:
        errors = [f for f in validate_stories(files, ba_repo) if f.severity == "error"]
        drafts = [s.ref or s.file.name for s in stories if s.header.get("status") == "draft"]
        if errors:
            add("Stories", PROBLEMS, f"{len(errors)} error(s)", f"Fix the stories: bridge-kit validate story "
                                                              f"{status.folder}/stories")
        elif drafts:
            add("Stories", PROBLEMS, f"{len(stories)}, {len(drafts)} draft ({', '.join(drafts)})",
                "The BA reviews and approves the stories")
        else:
            add("Stories", DONE, f"{len(stories)}, approved")
    reports = sorted(folder.glob("validation-*.md"))
    if not reports:
        add("Validation", TO_DO, "", f"Validate the package: /validate {work_item}")
    else:
        verdict = str(_front(reports[-1]).get("verdict") or "")
        add("Validation", DONE if verdict == "ready" else PROBLEMS, f"{reports[-1].name}: {verdict or 'no verdict'}",
            f"Work the findings of {reports[-1].name} in, then /validate {work_item} again")
    created = [str(s.header["id"]) for s in stories if s.header.get("id")]
    if stories and len(created) == len(stories):
        add("Published", DONE, ", ".join(created))
    else:
        add("Published", TO_DO, f"{len(created)} of {len(stories)}" if stories else "",
            f"Publish the stories to GitLab: /publish-stories {work_item}")

    # 10. The test cases
    cases = sorted((folder / "tests").glob("*.md"))
    if not cases:
        add("Tests", TO_DO, "", f"Write the test cases: /write-tests {work_item}")
    else:
        errors = [f for f in validate_test_cases(cases, ba_repo) if f.severity == "error"]
        gaps = [f for f in coverage(work_item, ba_repo).findings if f.severity == "error"]
        drafts = [c.label for c in map(load_test_case, cases) if c.status == "draft"]
        if errors or gaps:
            found = [f"{len(errors)} error(s)"] * bool(errors) + [f"{len(gaps)} criteria with no case"] * bool(gaps)
            add("Tests", PROBLEMS, ", ".join(found), "Fix the cases: bridge-kit validate test-case "
                                                     f"{status.folder}/tests, then bridge-kit tests coverage "
                                                     f"{work_item}")
        elif drafts:
            add("Tests", PROBLEMS, f"{len(cases)}, {len(drafts)} draft ({', '.join(drafts)})",
                "The tester and the BA review and approve the test cases")
        else:
            add("Tests", DONE, f"{len(cases)}, approved, every criterion covered")
    return status


def format_status(status: WorkStatus) -> str:
    width = max(len(s.name) for s in status.steps)
    lines = [f"{status.work_item}" + (f" ({status.folder})" if status.folder else ""), ""]
    lines += [f"  {s.name:<{width}}  {s.state:<10}  {s.detail}".rstrip() for s in status.steps]
    return "\n".join(lines + ["", f"Next: {status.next}"]) + "\n"


def _front(path: Path) -> dict:
    try:
        return read_markdown(path.read_text(encoding="utf-8")).front_matter
    except (FormatError, OSError):
        return {}


def _section(path: Path, heading: str) -> str:
    """A level-2 section's text, as written."""
    lines, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == heading
        elif inside:
            lines.append(line)
    return "\n".join(lines).strip()
