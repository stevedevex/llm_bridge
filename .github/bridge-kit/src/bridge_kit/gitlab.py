"""The GitLab client: the calls `bridge-kit gitlab` and `bridge-kit-mcp` share, on Python's own HTTP library. Every call
goes to a project or group `guard.py` has let through, and a write only to a project declared `read-write`; the token
comes from `auth.py` and goes only into the request's header. GitLab's errors become one line each.

The writes: an issue created or updated, a note added, two issues linked ("relates to"). Each is the BA's to
approve: the commands write only with `--yes`, and the MCP tools aren't marked read-only, so the IDE asks.

The `render_*` functions turn what GitLab returns into the Markdown the commands print: what a person or an agent
reads, without GitLab's own bookkeeping (system notes, ids)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from bridge_kit.auth import read_token
from bridge_kit.config import GitLabConfig, GitLabGroup, GitLabProject
from bridge_kit.guard import IssueRef, WikiRef

PER_PAGE = 100
LINK_KINDS = {"relates_to": "relates to", "blocks": "blocks", "is_blocked_by": "is blocked by"}


class GitLabError(Exception):
    """A call failed: one line saying why, never the token."""


@dataclass
class Response:
    data: object
    next_page: str | None


class GitLab:
    def __init__(self, config: GitLabConfig, token: str | None = None):
        self.config = config
        self._token = token if token is not None else read_token(config.token)
        self._context = ssl.create_default_context(cafile=config.ca_file) if config.ca_file else None

    # --- requests -----------------------------------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None, what: str = "") -> Response:
        return self._request("GET", path, params, None, what)

    def _send(self, method: str, path: str, body: dict, what: str) -> object:
        return self._request(method, path, None, body, what).data

    def _request(self, method: str, path: str, params: dict | None, body: dict | None, what: str) -> Response:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")}, doseq=True)
        url = f"{self.config.url}/api/v4{path}" + (f"?{query}" if query else "")
        headers = {"PRIVATE-TOKEN": self._token, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps({k: v for k, v in body.items() if v is not None}).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30, context=self._context) as response:
                text = response.read().decode("utf-8")
                return Response(json.loads(text) if text else None, response.headers.get("X-Next-Page") or None)
        except urllib.error.HTTPError as e:
            raise GitLabError(_http_error(e.code, what or path, write=method != "GET")) from None
        except urllib.error.URLError as e:
            raise GitLabError(f"Can't reach GitLab at {self.config.url}: {e.reason}") from None
        except (TimeoutError, json.JSONDecodeError) as e:
            raise GitLabError(f"GitLab at {self.config.url} didn't answer as its API does: {type(e).__name__}") from None

    def _get_all(self, path: str, params: dict | None = None, limit: int | None = None, what: str = "") -> list:
        items: list = []
        page: str | None = "1"
        while page and (limit is None or len(items) < limit):
            response = self._get(path, {**(params or {}), "per_page": PER_PAGE, "page": page}, what)
            items += response.data or []
            page = response.next_page
        return items[:limit] if limit is not None else items

    # --- calls --------------------------------------------------------------------------------------------------

    def user(self) -> dict:
        return self._get("/user", what="the token's user").data

    def project(self, project: GitLabProject) -> dict:
        return self._get(f"/projects/{project.id}", what=f"project {project.name}").data

    def group(self, group: GitLabGroup) -> dict:
        return self._get(f"/groups/{group.id}", what=f"group {group.name}").data

    def issue(self, ref: IssueRef) -> dict:
        return self._get(f"/projects/{ref.project.id}/issues/{ref.iid}", what=ref.label).data

    def notes(self, ref: IssueRef) -> list[dict]:
        notes = self._get_all(f"/projects/{ref.project.id}/issues/{ref.iid}/notes",
                              {"sort": "asc", "order_by": "created_at"}, what=f"{ref.label}'s comments")
        return [n for n in notes if not n.get("system")]

    def links(self, ref: IssueRef) -> list[dict]:
        return self._get_all(f"/projects/{ref.project.id}/issues/{ref.iid}/links", what=f"{ref.label}'s links")

    def issues(self, project: GitLabProject, labels: str | None = None, milestone: str | None = None,
               state: str | None = None, search: str | None = None, author: str | None = None,
               limit: int | None = 50) -> list[dict]:
        params = {"labels": labels, "milestone": milestone, "state": state, "search": search,
                  "author_username": author, "order_by": "updated_at"}
        return self._get_all(f"/projects/{project.id}/issues", params, limit, what=f"{project.name}'s issues")

    def epic(self, group: GitLabGroup, iid: int) -> tuple[dict, list[dict]]:
        what = f"epic &{iid} in {group.name} (epics need a paid GitLab tier)"
        epic = self._get(f"/groups/{group.id}/epics/{iid}", what=what).data
        return epic, self._get_all(f"/groups/{group.id}/epics/{iid}/issues", what=what)

    def token_scopes(self) -> list[str] | None:
        """The token's scopes, or None when this GitLab doesn't say (before 16.0)."""
        try:
            return list(self._get("/personal_access_tokens/self", what="the token's scopes").data.get("scopes") or [])
        except (GitLabError, AttributeError):
            return None

    # --- writes: each one the BA approved -----------------------------------------------------------------------

    def create_issue(self, project: GitLabProject, title: str, description: str, labels: list[str]) -> dict:
        return self._send("POST", f"/projects/{project.id}/issues",
                          {"title": title, "description": description, "labels": ",".join(labels) or None},
                          what=f"create an issue in {project.name}")

    def update_issue(self, ref: IssueRef, title: str | None = None, description: str | None = None,
                     labels: list[str] | None = None, state_event: str | None = None) -> dict:
        return self._send("PUT", f"/projects/{ref.project.id}/issues/{ref.iid}",
                          {"title": title, "description": description,
                           "labels": None if labels is None else ",".join(labels), "state_event": state_event},
                          what=f"update {ref.label}")

    def add_note(self, ref: IssueRef, body: str) -> dict:
        return self._send("POST", f"/projects/{ref.project.id}/issues/{ref.iid}/notes", {"body": body},
                          what=f"comment on {ref.label}")

    def link(self, ref: IssueRef, target: IssueRef) -> dict:
        """A "relates to" link between two issues: the one kind every GitLab tier has."""
        return self._send("POST", f"/projects/{ref.project.id}/issues/{ref.iid}/links",
                          {"target_project_id": target.project.id, "target_issue_iid": target.iid,
                           "link_type": "relates_to"}, what=f"link {ref.label} to {target.label}")

    def wiki_pages(self, wiki: WikiRef) -> list[dict]:
        return self._get_all(f"{_wiki_root(wiki)}/wikis", what=_wiki_what(wiki))

    def wiki_page(self, wiki: WikiRef, slug: str) -> dict:
        return self._get(f"{_wiki_root(wiki)}/wikis/{urllib.parse.quote(slug, safe='')}",
                         what=f"page {slug} of {_wiki_what(wiki)}").data

    def wiki_search(self, wiki: WikiRef, text: str, limit: int | None = 20) -> list[dict]:
        if wiki.is_group:  # a group's wiki has no search of its own: its pages are searched by title and content
            pages = self._get_all(f"{_wiki_root(wiki)}/wikis", {"with_content": 1}, what=_wiki_what(wiki))
            hits = [{"title": p["title"], "slug": p["slug"],
                     "lines": [line for line in (p.get("content") or "").splitlines() if text.lower() in line.lower()]}
                    for p in pages if text.lower() in (p.get("title", "") + "\n" + (p.get("content") or "")).lower()]
            return hits[:limit] if limit else hits
        blobs = self._get_all(f"/projects/{wiki.owner.id}/search", {"scope": "wiki_blobs", "search": text}, limit,
                              what=f"a search of {_wiki_what(wiki)}")
        hits: dict[str, dict] = {}
        for blob in blobs:
            slug = str(blob.get("path") or blob.get("filename") or "").rsplit(".", 1)[0]
            hit = hits.setdefault(slug, {"title": slug.rsplit("/", 1)[-1].replace("-", " "), "slug": slug, "lines": []})
            hit["lines"] += [line for line in str(blob.get("data") or "").splitlines() if line.strip()]
        return list(hits.values())


def _wiki_root(wiki: WikiRef) -> str:
    return f"/groups/{wiki.owner.id}" if wiki.is_group else f"/projects/{wiki.owner.id}"


def _wiki_what(wiki: WikiRef) -> str:
    return (f"group {wiki.owner.name}'s wiki (group wikis need a paid GitLab tier)" if wiki.is_group
            else f"project {wiki.owner.name}'s wiki")


def _http_error(code: int, what: str, write: bool = False) -> str:
    if code == 401:
        return "GitLab refused the token: check where bridge-kit.yaml says it is, and that it hasn't expired"
    if code == 403 and write:
        return f"GitLab won't let the token {what}: writing needs the api scope, and Reporter access or more"
    if code == 403:
        return f"The token can't read {what}: it needs the read_api scope and access to it"
    if write and code in (400, 422):
        return f"GitLab refused to {what} ({code}): what was sent isn't what it takes"
    if code == 404:
        return f"GitLab has no {what}, or the token can't see it"
    if code == 429:
        return "GitLab is limiting requests: wait a minute and try again"
    return f"GitLab answered {code} for {what}"


# --- rendering ----------------------------------------------------------------------------------------------------

def _people(people: list[dict] | None) -> str:
    return ", ".join(f"@{p.get('username')}" for p in people or []) or "-"


def _day(stamp: str | None) -> str:
    return (stamp or "")[:10] or "-"


def render_issue(ref: IssueRef, issue: dict, notes: list[dict] | None = None, links: list[dict] | None = None) -> str:
    milestone = (issue.get("milestone") or {}).get("title") or "-"
    rows = [("Project", f"{ref.project.name} ({ref.project.path}#{ref.iid})"), ("State", issue.get("state") or "-"),
            ("Labels", ", ".join(issue.get("labels") or []) or "-"), ("Milestone", milestone),
            ("Assignees", _people(issue.get("assignees"))), ("Author", _people([issue.get("author") or {}])),
            ("Created", _day(issue.get("created_at"))), ("Updated", _day(issue.get("updated_at"))),
            ("Link", issue.get("web_url") or "-")]
    lines = [f"# {ref.label}: {issue.get('title', '')}", "", "| | |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    lines += ["", "## Description", "", (issue.get("description") or "").strip() or "None."]
    if links is not None:
        lines += ["", "## Linked stories", ""]
        lines += [f"- {LINK_KINDS.get(l.get('link_type'), l.get('link_type'))} "
                  f"{(l.get('references') or {}).get('full') or l.get('web_url')}: {l.get('title')} ({l.get('state')})"
                  for l in links] or ["None."]
    if notes is not None:
        lines += ["", "## Comments", ""]
        for note in notes:
            lines += [f"### @{(note.get('author') or {}).get('username')}, {_day(note.get('created_at'))}", "",
                      (note.get("body") or "").strip(), ""]
        if not notes:
            lines.append("None.")
    return "\n".join(lines).rstrip() + "\n"


def render_issue_list(project: GitLabProject, issues: list[dict]) -> str:
    def label(issue: dict) -> str:
        return f"{project.key}-{issue['iid']}" if project.key else f"{project.name}#{issue['iid']}"

    lines = [f"- {label(i)} ({i.get('state')}): {i.get('title')}"
             + (f" [{', '.join(i.get('labels') or [])}]" if i.get("labels") else "") for i in issues]
    return "\n".join(lines or ["No story matches."]) + "\n"


def render_links(ref: IssueRef, links: list[dict]) -> str:
    lines = [f"- {ref.label} {LINK_KINDS.get(l.get('link_type'), l.get('link_type'))} "
             f"{(l.get('references') or {}).get('full') or l.get('web_url')}: {l.get('title')} ({l.get('state')})"
             for l in links]
    return "\n".join(lines or [f"{ref.label} has no linked stories."]) + "\n"


def render_epic(group: GitLabGroup, epic: dict, issues: list[dict]) -> str:
    lines = [f"# {group.name}&{epic.get('iid')}: {epic.get('title', '')}", "",
             f"State {epic.get('state')}; labels {', '.join(epic.get('labels') or []) or '-'}; {epic.get('web_url')}",
             "", "## Description", "", (epic.get("description") or "").strip() or "None.", "", "## Stories", ""]
    lines += [f"- {(i.get('references') or {}).get('full') or i.get('web_url')} ({i.get('state')}): {i.get('title')}"
              for i in issues] or ["None."]
    return "\n".join(lines) + "\n"


def render_wiki_list(wiki: WikiRef, pages: list[dict]) -> str:
    lines = [f"- {p.get('title')} (`{p.get('slug')}`)" for p in pages]
    return "\n".join(lines or [f"{wiki.owner.name}'s wiki has no pages."]) + "\n"


def render_wiki_page(wiki: WikiRef, page: dict) -> str:
    head = [f"# {page.get('title', '')}", "",
            f"From {wiki.owner.name}'s wiki: `{page.get('slug')}`, {page.get('format', 'markdown')}", ""]
    return "\n".join(head) + (page.get("content") or "").strip() + "\n"


def render_wiki_hits(hits: list[dict]) -> str:
    lines = []
    for hit in hits:
        lines += [f"- {hit['title']} (`{hit['slug']}`)"] + [f"  > {line.strip()}" for line in hit["lines"][:3]]
    return "\n".join(lines or ["No page matches."]) + "\n"


def status(client: GitLab) -> tuple[list[str], list[str], list[str]]:
    """Who the token is, and whether each declared project, group and wiki answers at its declared path: the lines
    to print, the problems among them, and which of those are an id naming another project or group than declared,
    where a read would go to the wrong place."""
    lines, problems, mismatched = [], [], []
    user = client.user()
    lines.append(f"Token: @{user.get('username')} ({user.get('name')}) on {client.config.url}")
    writable = [p.name for p in client.config.projects.values() if p.access == "read-write"]
    scopes = client.token_scopes() if writable else None
    if scopes is not None:
        lines.append(f"Token scopes: {', '.join(scopes) or 'none'}")
        if "api" not in scopes:
            problems.append(f"The token can't write (its scopes: {', '.join(scopes) or 'none'}), and bridge-kit.yaml "
                            f"declares {', '.join(writable)} read-write: writing their issues needs the api scope")
    for project in client.config.projects.values():
        try:
            data = client.project(project)
        except GitLabError as e:
            problems.append(f"{project.name}: {e}")
            continue
        actual = data.get("path_with_namespace")
        if actual != project.path:
            problems.append(f"{project.name}: id {project.id} is {actual}, and bridge-kit.yaml says {project.path}")
            mismatched.append(problems[-1])
            continue
        note = f"{project.name}: {actual}, {project.access}" + (f", key {project.key}" if project.key else "")
        if project.wiki:
            try:
                pages = client._get(f"/projects/{project.id}/wikis", what=f"project {project.name}'s wiki").data
                note += f", its wiki ({len(pages or [])} page(s))"
            except GitLabError as e:
                problems.append(f"{project.name}'s wiki: {e}")
        lines.append(note)
    for group in client.config.groups.values():
        try:
            data = client.group(group)
        except GitLabError as e:
            problems.append(f"{group.name}: {e}")
            continue
        if data.get("full_path") != group.path:
            problems.append(f"{group.name}: id {group.id} is {data.get('full_path')}, and bridge-kit.yaml says {group.path}")
            mismatched.append(problems[-1])
            continue
        lines.append(f"{group.name}: the group {group.path}")
        if group.wiki:
            try:
                client.wiki_pages(WikiRef(group))
            except GitLabError as e:
                problems.append(f"{group.name}'s wiki: {e}")
    return lines, problems, mismatched


# --- the reads both front ends share: each returns the Markdown to show and the data behind it -------------------

def read_status(client: GitLab) -> tuple[str, dict]:
    lines, problems, _ = status(client)
    text = "\n".join(lines + [f"PROBLEM {p}" for p in problems]) + "\n" + \
        ("GitLab: OK\n" if not problems else f"GitLab: {len(problems)} problem(s)\n")
    return text, {"lines": lines, "problems": problems, "ok": not problems}


def read_issue(client: GitLab, story: str, project: str | None = None, notes: bool = False,
               links: bool = False) -> tuple[str, dict]:
    from bridge_kit.guard import issue_ref

    ref = issue_ref(client.config, story, project)
    issue = client.issue(ref)
    comments = client.notes(ref) if notes else None
    linked = client.links(ref) if links else None
    return render_issue(ref, issue, comments, linked), {"ref": ref.label, "issue": issue, "notes": comments,
                                                        "links": linked}


def read_issue_list(client: GitLab, project: str | None = None, label: str | None = None,
                    milestone: str | None = None, state: str | None = None, search: str | None = None,
                    author: str | None = None, limit: int | None = 50) -> tuple[str, list]:
    from bridge_kit.guard import GuardError, declared_project

    name = project or client.config.default_project
    if not name:
        raise GuardError("Which project? Name it, or set integrations.gitlab.default_project")
    found = declared_project(client.config, name)
    issues = client.issues(found, label, milestone, None if state == "all" else state, search, author, limit)
    return render_issue_list(found, issues), issues


def read_links(client: GitLab, story: str, project: str | None = None) -> tuple[str, dict]:
    from bridge_kit.guard import issue_ref

    ref = issue_ref(client.config, story, project)
    linked = client.links(ref)
    return render_links(ref, linked), {"ref": ref.label, "links": linked}


def read_epic(client: GitLab, group: str, iid: int) -> tuple[str, dict]:
    from bridge_kit.guard import declared_group

    found = declared_group(client.config, group)
    epic, issues = client.epic(found, iid)
    return render_epic(found, epic, issues), {"epic": epic, "issues": issues}


def read_wiki_list(client: GitLab, wiki: str | None = None) -> tuple[str, list]:
    from bridge_kit.guard import wiki_ref

    found = wiki_ref(client.config, wiki)
    pages = client.wiki_pages(found)
    return render_wiki_list(found, pages), pages


def read_wiki_page(client: GitLab, slug: str, wiki: str | None = None) -> tuple[str, dict]:
    from bridge_kit.guard import wiki_ref

    found = wiki_ref(client.config, wiki)
    page = client.wiki_page(found, slug)
    return render_wiki_page(found, page), page


def read_wiki_search(client: GitLab, text: str, wiki: str | None = None) -> tuple[str, list]:
    from bridge_kit.guard import wiki_ref

    found = wiki_ref(client.config, wiki)
    hits = client.wiki_search(found, text)
    return render_wiki_hits(hits), hits


# --- the writes both front ends share: each returns what it did, as a line, and GitLab's answer; or, as a dry run,
# what it would do, without a request ---------------------------------------------------------------------------

def _labels(labels: list[str] | None) -> str:
    return f" [{', '.join(labels)}]" if labels else ""


def write_create_issue(client: GitLab, project: str, title: str, description: str = "",
                       labels: list[str] | None = None, dry_run: bool = False) -> tuple[str, dict]:
    from bridge_kit.guard import writable_project

    found = writable_project(client.config, project)
    if not title.strip():
        raise GitLabError("An issue needs a title")
    if dry_run:
        return f"Would create in {project}: {title}{_labels(labels)}\n", {"dry_run": True, "project": project}
    issue = client.create_issue(found, title, description, labels or [])
    ref = IssueRef(found, int(issue["iid"]))
    return (f"Created {ref.label} in {project}: {title}\n{issue.get('web_url') or ''}".rstrip() + "\n",
            {"ref": ref.label, "issue": issue})


def write_update_issue(client: GitLab, story: str, project: str | None = None, title: str | None = None,
                       description: str | None = None, labels: list[str] | None = None, state: str | None = None,
                       dry_run: bool = False) -> tuple[str, dict]:
    from bridge_kit.guard import writable_issue

    ref = writable_issue(client.config, story, project)
    if state not in (None, "close", "reopen"):
        raise GitLabError(f"{state} isn't close or reopen")
    changed = [name for name, value in (("title", title), ("description", description), ("labels", labels),
                                        ("state", state)) if value is not None]
    if not changed:
        raise GitLabError(f"Nothing to change on {ref.label}: give a title, a description, labels or a state")
    if dry_run:
        return f"Would update {ref.label}: {', '.join(changed)}\n", {"dry_run": True, "ref": ref.label}
    issue = client.update_issue(ref, title, description, labels, state)
    return f"Updated {ref.label}: {', '.join(changed)}\n", {"ref": ref.label, "issue": issue}


def write_add_note(client: GitLab, story: str, body: str, project: str | None = None,
                   dry_run: bool = False) -> tuple[str, dict]:
    from bridge_kit.guard import writable_issue

    ref = writable_issue(client.config, story, project)
    if not body.strip():
        raise GitLabError("The comment is empty")
    if dry_run:
        return f"Would comment on {ref.label}\n", {"dry_run": True, "ref": ref.label}
    note = client.add_note(ref, body)
    return f"Commented on {ref.label}\n", {"ref": ref.label, "note": note}


def write_link_issues(client: GitLab, story: str, target: str, project: str | None = None,
                      dry_run: bool = False) -> tuple[str, dict]:
    from bridge_kit.guard import issue_ref, writable_issue

    ref, other = writable_issue(client.config, story, project), issue_ref(client.config, target, project)
    if dry_run:
        return f"Would link {ref.label} to {other.label}: relates to\n", {"dry_run": True, "ref": ref.label}
    client.link(ref, other)
    return f"Linked {ref.label} to {other.label}: relates to\n", {"ref": ref.label, "target": other.label}
