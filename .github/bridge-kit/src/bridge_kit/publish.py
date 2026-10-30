"""`bridge-kit stories publish <id> [--yes]`: a work item's approved stories, created as GitLab issues.

- **Which stories:** the work item's `approved` ones, once `validate story` and the package check pass on the set. A
  story with a GitLab id is created already, and never again.
- **Where:** each in its component's GitLab project, the catalog's `stories.project`, which `bridge-kit.yaml` must
  declare `read-write` and with a key, so the story's id reads like the template's (`DASH-311`).
- **What:** its title, its labels, and its Markdown as the description, ending with the requirement it's part of and
  the stories it waits for. Each is linked to the requirement's issue and to the stories it waits for, "relates to"
  (the user, 2026-10-29: every tier has it; GitLab won't show it as blocked).
- **After:** each story's file records its id (`id: DASH-311`, `status: created`, its `blocked_by` as ids), and the
  requirement's issue gets a comment listing them, when its project is `read-write` too.

Without `--yes` it's a dry run: what it would create, and nothing is sent. With it, a failure stops the run at that
story; those created already have their ids, so running it again goes on from there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from bridge_kit.config import Config
from bridge_kit.gitlab import GitLab
from bridge_kit.guard import GuardError, IssueRef, issue_ref, writable_project
from bridge_kit.stories import Story, load_catalog, load_story


class PublishError(Exception):
    """The stories can't be published: not ready, or not declared."""


@dataclass
class Planned:
    story: Story
    project: str
    status: str = "to create"  # to create, created already, created now
    id: str | None = None


@dataclass
class Published:
    work_item: str
    planned: list[Planned] = field(default_factory=list)
    dry_run: bool = True
    comment: str = ""  # the requirement's issue's comment: made, or why not

    def to_dict(self) -> dict:
        return {"work_item": self.work_item, "dry_run": self.dry_run, "comment": self.comment,
                "stories": [{"file": p.story.file.name, "ref": p.story.ref, "component": p.story.component,
                             "project": p.project, "status": p.status, "id": p.id} for p in self.planned]}


def plan(work_item: str, ba_repo: Path, config: Config, package_findings: list | None = None) -> Published:
    """What publishing would do, or why it can't: every reason at once."""
    from bridge_kit.validators.package import work_folder
    from bridge_kit.validators.story import validate_stories

    folder = work_folder(ba_repo, work_item)
    files = sorted((folder / "stories").glob("*.md")) if folder else []
    if not files:
        raise PublishError(f"No stories for {work_item}: write them first (/write-stories {work_item})")
    if config.gitlab is None:
        raise PublishError("bridge-kit.yaml declares no GitLab: add integrations.gitlab (see bridge-kit.example.yaml)")
    problems = [f"{f.file}: {f.message}" for f in validate_stories(files, ba_repo) if f.severity == "error"]
    problems += [f"The package check: {f.file}: {f.message}" for f in package_findings or [] if f.severity == "error"]
    catalog = load_catalog(ba_repo)
    result = Published(work_item)
    stories = sorted((load_story(f) for f in files), key=lambda s: (s.order or 0, s.file.name))
    for story in stories:
        name = str(((catalog.components.get(story.component) or {}).get("stories") or {}).get("project") or "")
        if story.header.get("id"):
            result.planned.append(Planned(story, name, "created already", str(story.header["id"])))
            continue
        if story.header.get("status") != "approved":
            problems.append(f"{story.ref} ({story.component}) is {story.header.get('status')}: the BA approves it "
                            "first")
        try:
            project = writable_project(config.gitlab, name) if name else None
        except GuardError as e:
            problems.append(f"{story.ref} ({story.component}): {e}")
            project = None
        if not name:
            problems.append(f"{story.ref} ({story.component}): the catalog gives no stories.project for it")
        elif project is not None and not project.key:
            problems.append(f"{story.ref} ({story.component}): {name} has no key in bridge-kit.yaml, so its stories "
                            "would have no id like DASH-311: give it one")
        result.planned.append(Planned(story, name))
    parent = {str(s.header.get("parent") or "") for s in stories}
    try:
        for ref in parent:
            issue_ref(config.gitlab, ref)
    except GuardError as e:
        problems.append(f"The requirement's issue: {e}")
    if problems:
        raise PublishError("Not published:\n" + "\n".join(f"  - {p}" for p in problems))
    return result


def publish(work_item: str, ba_repo: Path, config: Config, client: GitLab | None, dry_run: bool = True,
            package_findings: list | None = None) -> Published:
    result = plan(work_item, ba_repo, config, package_findings)
    result.dry_run = dry_run
    if dry_run:
        return result
    ids = {p.story.ref: p.id for p in result.planned if p.id}
    created = []
    for planned in result.planned:
        if planned.status != "to create":
            continue
        story = planned.story
        project = config.gitlab.projects[planned.project]
        waits = [ids.get(ref, ref) for ref in story.blocked_by]
        parent = str(story.header["parent"])
        description = (story.body.rstrip() + f"\n\n---\n\nPart of {parent}. Waits for: "
                       + (", ".join(waits) if waits else "nothing") + f".\n\nWritten with bridge-kit from "
                       f"`{story.file.relative_to(ba_repo).as_posix()}`.\n")
        issue = client.create_issue(project, str(story.header.get("title") or ""), description,
                                    [str(label) for label in story.header.get("labels") or []])
        ref = IssueRef(project, int(issue["iid"]))
        planned.id, planned.status = ref.label, "created now"
        ids[story.ref] = ref.label
        _record(story.file, ref.label, waits)  # before the links, so a failure there can't create it twice
        created.append(planned)
        for other in [parent, *waits]:
            client.link(ref, issue_ref(config.gitlab, other))
    if created:
        parent = issue_ref(config.gitlab, str(created[0].story.header["parent"]))
        if parent.project.access == "read-write":
            client.add_note(parent, "Stories for this requirement, written with bridge-kit:\n\n"
                            + "\n".join(f"- {p.id}: {p.story.header.get('title')} ({p.story.component})"
                                        for p in result.planned if p.id) + "\n")
            result.comment = f"Commented on {parent.label} with the list."
        else:
            result.comment = f"{parent.project.name} is read-only in bridge-kit.yaml: no comment on {parent.label}."
    return result


def _record(file: Path, story_id: str, blocked_by: list[str]) -> None:
    """The story's id, its status and its dependencies by id, in its front matter, the rest of the file as it is."""
    text = file.read_text(encoding="utf-8")
    head, sep, rest = text.partition("\n---\n")
    head = re.sub(r"^id: .*$", f"id: {story_id}", head, count=1, flags=re.MULTILINE)
    head = re.sub(r"^status: .*$", "status: created", head, count=1, flags=re.MULTILINE)
    head = re.sub(r"^blocked_by: .*$", f"blocked_by: [{', '.join(blocked_by)}]", head, count=1, flags=re.MULTILINE)
    file.write_text(head + sep + rest, encoding="utf-8")
