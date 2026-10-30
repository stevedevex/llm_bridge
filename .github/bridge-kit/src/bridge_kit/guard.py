"""What an agent may ask GitLab for: only what `bridge-kit.yaml` declares. A personal token reaches every project its
owner can, so the kit itself refuses anything else, before any request is made. A story is named by its work item id
(`REQ-101`, the project's key and the issue's number), by the project's declared name (`ba-requirements#142`), or by its
GitLab URL, which must be a declared project's."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from bridge_kit.config import GitLabConfig, GitLabGroup, GitLabProject


class GuardError(Exception):
    """What was asked for isn't declared in bridge-kit.yaml."""


@dataclass
class IssueRef:
    project: GitLabProject
    iid: int

    @property
    def label(self) -> str:
        """The story as the BA names it: by key where the project has one."""
        return f"{self.project.key}-{self.iid}" if self.project.key else f"{self.project.name}#{self.iid}"


@dataclass
class WikiRef:
    owner: GitLabProject | GitLabGroup

    @property
    def is_group(self) -> bool:
        return isinstance(self.owner, GitLabGroup)


def issue_ref(gitlab: GitLabConfig, ref: str, project: str | None = None) -> IssueRef:
    ref = ref.strip()
    keyed = re.fullmatch(r"([A-Z][A-Z0-9]{1,9})-(\d+)", ref)
    if keyed:
        found = next((p for p in gitlab.projects.values() if p.key == keyed.group(1)), None)
        if found is None:
            raise GuardError(f"No declared project has the key {keyed.group(1)}")
        return IssueRef(found, int(keyed.group(2)))
    named = re.fullmatch(r"([a-z0-9]+(?:-[a-z0-9]+)*)#(\d+)", ref)
    if named:
        return IssueRef(declared_project(gitlab, named.group(1)), int(named.group(2)))
    if ref.startswith(("http://", "https://")):
        url, base = urlparse(ref), urlparse(gitlab.url)
        prefix = base.path.rstrip("/")  # a GitLab served under a path of its own
        if (url.scheme, url.netloc) != (base.scheme, base.netloc) or not url.path.startswith(prefix + "/"):
            raise GuardError(f"{ref} isn't on the declared GitLab, {gitlab.url}")
        match = re.fullmatch(r"/(.+?)/-/(?:issues|work_items)/(\d+)/?", url.path[len(prefix):])
        if not match:
            raise GuardError(f"{ref} isn't a link to an issue")
        found = next((p for p in gitlab.projects.values() if p.path == match.group(1)), None)
        if found is None:
            raise GuardError(f"{match.group(1)} isn't a declared project")
        return IssueRef(found, int(match.group(2)))
    if ref.isdigit():
        name = project or gitlab.default_project
        if not name:
            raise GuardError(f"Which project is #{ref} in? Name it with --project, or write it as <project>#{ref}")
        return IssueRef(declared_project(gitlab, name), int(ref))
    raise GuardError(f"{ref} isn't a story's id (REQ-101), <project>#<number>, or its GitLab link")


def declared_project(gitlab: GitLabConfig, name: str) -> GitLabProject:
    if name not in gitlab.projects:
        raise GuardError(f"{name} isn't a declared project: {', '.join(gitlab.projects) or 'there are none'}")
    return gitlab.projects[name]


def writable_project(gitlab: GitLabConfig, name: str) -> GitLabProject:
    """A declared project the kit may write in: `access: read-write`."""
    project = declared_project(gitlab, name)
    if project.access != "read-write":
        raise GuardError(f"{name} is read-only in bridge-kit.yaml: declare it access: read-write for the kit to write "
                         "its issues")
    return project


def writable_issue(gitlab: GitLabConfig, ref: str, project: str | None = None) -> IssueRef:
    found = issue_ref(gitlab, ref, project)
    writable_project(gitlab, found.project.name)
    return found


def declared_group(gitlab: GitLabConfig, name: str) -> GitLabGroup:
    if name not in gitlab.groups:
        raise GuardError(f"{name} isn't a declared group: {', '.join(gitlab.groups) or 'there are none'}")
    return gitlab.groups[name]


def wiki_ref(gitlab: GitLabConfig, name: str | None = None) -> WikiRef:
    """The wiki to read: a declared project's or group's with `wiki: true`; without a name, the only one there is."""
    wikis: dict[str, GitLabProject | GitLabGroup] = {
        **{n: p for n, p in gitlab.projects.items() if p.wiki}, **{n: g for n, g in gitlab.groups.items() if g.wiki}}
    if name is None:
        if len(wikis) == 1:
            return WikiRef(next(iter(wikis.values())))
        raise GuardError("Which wiki? Name it with --wiki: " + (", ".join(wikis) or "none is declared (wiki: true)"))
    if name not in wikis:
        raise GuardError(f"{name} isn't a declared wiki: {', '.join(wikis) or 'none is declared (wiki: true)'}")
    return WikiRef(wikis[name])
