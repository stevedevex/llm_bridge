"""bridge-kit gitlab, against a stand-in GitLab: stories and wiki pages read from declared projects and groups only,
named by key, by project or by link, paged to the end; the token sent as a header and in no output; and GitLab's
errors as one line each."""

import json
import os

import pytest
import yaml
from conftest import LANDSCAPE
from fixtures.fake_gitlab import Error, FakeGitLab, Page

from bridge_kit.auth import TokenError, read_token
from bridge_kit.cli import main
from bridge_kit.config import check_config

TOKEN = "glpat-test-only-0123456789"
STORY = {"iid": 142, "title": "Show each legal entity's EU VAT registration", "state": "opened",
         "description": "As a credit analyst, I want to see each legal entity's VAT registrations.",
         "labels": ["requirement", "vat"], "milestone": {"title": "R12"},
         "assignees": [{"username": "ba.user"}], "author": {"username": "po.user"},
         "created_at": "2026-10-20T09:00:00Z", "updated_at": "2026-10-27T15:30:00Z",
         "web_url": "{url}/ba-team/ba-repo/-/issues/142", "references": {"full": "ba-team/ba-repo#142"}}
NOTES = [{"body": "Which countries count as EU?", "author": {"username": "dev.user"},
          "created_at": "2026-10-21T10:00:00Z", "system": False},
         {"body": "added ~vat label", "author": {"username": "ba.user"}, "created_at": "2026-10-21T10:05:00Z",
          "system": True}]
LINKS = [{"iid": 7, "title": "Add the VAT slot to the model", "state": "opened", "link_type": "blocks",
          "references": {"full": "ba-team/ba-repo#7"}}]
PAGE = {"title": "Checklist", "slug": "onboarding/checklist", "format": "markdown",
        "content": "# Onboarding checklist\n\n1. Get the upstream's spec jar\n2. Ask about its time zone\n"}


def routes(url: str) -> dict:
    story = {**STORY, "web_url": STORY["web_url"].format(url=url)}
    return {
        "/api/v4/user": {"username": "ba.user", "name": "A Business Analyst"},
        "/api/v4/projects/101": {"path_with_namespace": "ba-team/ba-repo"},
        "/api/v4/projects/202": {"path_with_namespace": "dev/service-a-java"},
        "/api/v4/groups/7": {"full_path": "ba-team"},
        "/api/v4/projects/101/issues/142": story,
        "/api/v4/projects/101/issues/142/notes": NOTES,
        "/api/v4/projects/101/issues/142/links": LINKS,
        "/api/v4/projects/101/issues": [Page([{**story, "iid": n, "title": f"Story {n}"} for n in (150, 149)]),
                                        Page([{**story, "iid": 148, "title": "Story 148", "labels": []}])],
        "/api/v4/groups/7/epics/3": {"iid": 3, "title": "VAT", "state": "opened", "labels": ["vat"],
                                     "web_url": f"{url}/groups/ba-team/-/epics/3", "description": "All of VAT"},
        "/api/v4/groups/7/epics/3/issues": [story],
        "/api/v4/projects/101/wikis": [{"title": "Home", "slug": "home"},
                                       {"title": "Checklist", "slug": "onboarding/checklist"}],
        "/api/v4/projects/101/wikis/onboarding%2Fchecklist": PAGE,  # a nested slug, URL-encoded
        "/api/v4/projects/101/search": [{"path": "onboarding/checklist.md", "data": "2. Ask about its time zone\n"}],
        "/api/v4/groups/7/wikis": [{**PAGE, "slug": "pod/ways-of-working", "title": "Ways of working",
                                    "content": "We review mappings on Tuesdays.\nTime zone: London."}],
    }


def config(url: str) -> dict:
    data = yaml.safe_load((LANDSCAPE / "bridge-kit.yaml").read_text(encoding="utf-8"))
    data["integrations"] = {"gitlab": {
        "url": url,
        "projects": {"ba-requirements": {"id": 101, "path": "ba-team/ba-repo", "key": "REQ", "access": "read-write",
                                         "wiki": True},
                     "service-a": {"id": 202, "path": "dev/service-a-java", "access": "read-only"}},
        "groups": {"pod": {"id": 7, "path": "ba-team", "wiki": True, "epics": True}},
        "default_project": "ba-requirements",
        "auth": {"token": {"from": "env", "env": "BRIDGE_KIT_TEST_GITLAB_TOKEN"}}}}
    return data


@pytest.fixture
def gitlab(tmp_path, monkeypatch):
    """A BA repo whose bridge-kit.yaml declares the stand-in GitLab; returns it and the stand-in."""
    with FakeGitLab({}) as fake:
        fake.routes.update(routes(fake.url))
        repo = tmp_path / "ba-repo"
        (repo / ".github" / "bridge-kit").mkdir(parents=True)
        (repo / ".github" / "bridge-kit" / "bridge-kit.yaml").write_text(yaml.safe_dump(config(fake.url)),
                                                                         encoding="utf-8")
        monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
        monkeypatch.setenv("BRIDGE_KIT_TEST_GITLAB_TOKEN", TOKEN)
        yield {"fake": fake, "repo": repo}


def run(capsys, *args) -> tuple[int, str, str]:
    code = main(["gitlab", *args])
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err  # the token is in no output, ever
    return code, out.out, out.err


def test_status_says_who_the_token_is_and_that_everything_declared_answers(gitlab, capsys):
    code, out, _ = run(capsys, "status")

    assert code == 0, out
    assert out.splitlines() == [
        f"Token: @ba.user (A Business Analyst) on {gitlab['fake'].url}",
        "ba-requirements: ba-team/ba-repo, read-write, key REQ, its wiki (2 page(s))",
        "service-a: dev/service-a-java, read-only",
        "pod: the group ba-team",
        "GitLab: OK"]
    assert {token for _, _, token in gitlab["fake"].requests} == {TOKEN}


def test_status_finds_a_project_id_that_names_another_project(gitlab, capsys):
    gitlab["fake"].routes["/api/v4/projects/202"] = {"path_with_namespace": "dev/something-else"}

    code, out, _ = run(capsys, "status")

    assert code == 1
    assert ("PROBLEM service-a: id 202 is dev/something-else, and bridge-kit.yaml says "
            "dev/service-a-java") in out


@pytest.mark.parametrize("ref", ["REQ-142", "ba-requirements#142", "{url}/ba-team/ba-repo/-/issues/142", "142"])
def test_a_story_is_named_by_key_by_project_by_link_or_by_number(gitlab, capsys, ref):
    code, out, _ = run(capsys, "issue", "get", ref.format(url=gitlab["fake"].url))

    assert code == 0
    assert out.startswith("# REQ-142: Show each legal entity's EU VAT registration\n")
    assert "| Labels | requirement, vat |" in out and "| Milestone | R12 |" in out
    assert "As a credit analyst" in out


def test_a_story_s_comments_leave_gitlab_s_own_notes_out_and_its_links_say_how(gitlab, capsys):
    _, out, _ = run(capsys, "issue", "get", "REQ-142", "--notes", "--links")

    assert "### @dev.user, 2026-10-21\n\nWhich countries count as EU?" in out
    assert "added ~vat label" not in out
    assert "- blocks ba-team/ba-repo#7: Add the VAT slot to the model (opened)" in out
    _, out, _ = run(capsys, "issue", "links", "REQ-142")
    assert out == "- REQ-142 blocks ba-team/ba-repo#7: Add the VAT slot to the model (opened)\n"


@pytest.mark.parametrize("ref, message", [
    ("ABC-1", "No declared project has the key ABC"),
    ("other-project#5", "other-project isn't a declared project"),
    ("{url}/someone/else/-/issues/5", "someone/else isn't a declared project"),
    ("https://gitlab.elsewhere/ba-team/ba-repo/-/issues/142", "isn't on the declared GitLab"),
])
def test_anything_undeclared_is_refused_before_a_request(gitlab, capsys, ref, message):
    code, _, err = run(capsys, "issue", "get", ref.format(url=gitlab["fake"].url))

    assert code == 2 and message in err
    assert gitlab["fake"].requests == []


def test_stories_are_listed_page_by_page_to_the_limit(gitlab, capsys):
    _, out, _ = run(capsys, "issue", "list", "--label", "vat", "--state", "opened")

    assert out == ("- REQ-150 (opened): Story 150 [requirement, vat]\n- REQ-149 (opened): Story 149 [requirement, vat]\n"
                   "- REQ-148 (opened): Story 148\n")
    queries = [query for path, query, _ in gitlab["fake"].requests if path.endswith("/issues")]
    assert [q["page"] for q in queries] == ["1", "2"]
    assert queries[0]["labels"] == "vat" and queries[0]["state"] == "opened"
    _, out, _ = run(capsys, "issue", "list", "--limit", "1", "--json")
    assert [i["iid"] for i in json.loads(out)] == [150]


def test_an_epic_and_its_stories(gitlab, capsys):
    _, out, _ = run(capsys, "epic", "get", "pod", "3")

    assert out.startswith("# pod&3: VAT\n") and "- ba-team/ba-repo#142 (opened): Show each" in out


@pytest.mark.parametrize("route, code, message", [
    ("/api/v4/projects/101/issues/142", 401, "GitLab refused the token: check where bridge-kit.yaml says it is"),
    ("/api/v4/projects/101/issues/142", 403, "The token can't read REQ-142: it needs the read_api scope"),
    ("/api/v4/projects/101/issues/142", 404, "GitLab has no REQ-142, or the token can't see it"),
])
def test_gitlab_s_errors_are_one_line_each(gitlab, capsys, route, code, message):
    gitlab["fake"].routes[route] = Error(code)

    status, _, err = run(capsys, "issue", "get", "REQ-142")

    assert status == 1 and err.strip().startswith(message) and err.count("\n") == 1


def test_a_tier_without_epics_says_so(gitlab, capsys):
    gitlab["fake"].routes["/api/v4/groups/7/epics/3"] = Error(404)

    _, _, err = run(capsys, "epic", "get", "pod", "3")

    assert "epics need a paid GitLab tier" in err


def test_a_project_s_wiki_pages_are_listed_read_and_searched(gitlab, capsys):
    _, out, _ = run(capsys, "wiki", "list", "--wiki", "ba-requirements")
    assert out == "- Home (`home`)\n- Checklist (`onboarding/checklist`)\n"

    _, out, _ = run(capsys, "wiki", "get", "onboarding/checklist", "--wiki", "ba-requirements")
    assert out.startswith("# Checklist\n\nFrom ba-requirements's wiki: `onboarding/checklist`, markdown\n")
    assert "2. Ask about its time zone" in out

    _, out, _ = run(capsys, "wiki", "search", "time zone", "--wiki", "ba-requirements")
    assert out == "- checklist (`onboarding/checklist`)\n  > 2. Ask about its time zone\n"
    search = next(q for p, q, _ in gitlab["fake"].requests if p.endswith("/search"))
    assert search["scope"] == "wiki_blobs" and search["search"] == "time zone"


def test_a_group_s_wiki_is_searched_by_its_pages(gitlab, capsys):
    _, out, _ = run(capsys, "wiki", "search", "time zone", "--wiki", "pod")

    assert out == "- Ways of working (`pod/ways-of-working`)\n  > Time zone: London.\n"


def test_two_wikis_need_one_named(gitlab, capsys):
    code, _, err = run(capsys, "wiki", "list")

    assert code == 2 and err.startswith("Which wiki? Name it with --wiki: ba-requirements, pod")


def test_no_gitlab_declared(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    (repo / ".github" / "bridge-kit" / "bridge-kit.yaml").write_text((LANDSCAPE / "bridge-kit.yaml").read_text(),
                                                                     encoding="utf-8")
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))

    assert main(["gitlab", "status"]) == 2
    assert "declares no GitLab" in capsys.readouterr().err


def test_a_token_comes_only_from_its_declared_source(tmp_path, monkeypatch):
    monkeypatch.delenv("BRIDGE_KIT_TEST_GITLAB_TOKEN", raising=False)
    with pytest.raises(TokenError, match="BRIDGE_KIT_TEST_GITLAB_TOKEN isn't set"):
        read_token({"from": "env", "env": "BRIDGE_KIT_TEST_GITLAB_TOKEN"})

    file = tmp_path / "token"
    file.write_text(TOKEN + "\n", encoding="utf-8")
    os.chmod(file, 0o644)
    with pytest.raises(TokenError, match="can be read by others: chmod 600 it"):
        read_token({"from": "file", "file": str(file)})
    os.chmod(file, 0o600)
    assert read_token({"from": "file", "file": str(file)}) == TOKEN

    assert read_token({"from": "command", "command": f"echo {TOKEN}"}) == TOKEN
    with pytest.raises(TokenError, match="exited with 1 and printed no token") as error:
        read_token({"from": "command", "command": "false"})
    assert TOKEN not in str(error.value)


@pytest.mark.parametrize("change, problem", [
    (lambda g: g["projects"]["service-a"].update(key="REQ"),
     "integrations.gitlab.projects: the key REQ names more than one project"),
    (lambda g: g.update(default_project="nowhere"), "integrations.gitlab.default_project: nowhere isn't a declared"),
    (lambda g: g["auth"]["token"].pop("env"), "integrations.gitlab.auth.token: from env needs its env"),
    (lambda g: g["projects"]["ba-requirements"].update(key="tao"), "key doesn't match"),
])
def test_the_gitlab_section_is_checked(change, problem):
    data = config("https://gitlab.example")
    change(data["integrations"]["gitlab"])

    assert any(problem in p for p in check_config(data)), check_config(data)


# bridge-kit inputs add: a story or a wiki page as a work item's next input

from bridge_kit.markdown import read_markdown  # noqa: E402


def add(capsys, *args) -> tuple[int, str, str]:
    code = main(["inputs", "add", *args])
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err
    return code, out.out, out.err


def test_a_story_becomes_a_work_item_s_input_with_its_source_and_version(gitlab, capsys):
    code, out, _ = add(capsys, "gitlab:REQ-142", "--work-item", "REQ-341")

    assert (code, out) == (0, "Added work/REQ-341/inputs/01-story-req-142.md: Show each legal entity's EU VAT "
                              "registration\n")
    text = (gitlab["repo"] / "work/REQ-341/inputs/01-story-req-142.md").read_text(encoding="utf-8")
    header = read_markdown(text).front_matter
    assert {k: header[k] for k in ("kind", "source", "version", "summary", "raw")} == {
        "kind": "gitlab-issue", "source": "REQ-142", "version": "2026-10-27T15:30:00Z",
        "summary": "Show each legal entity's EU VAT registration",
        "raw": ".work/sources/REQ-341/01-story-req-142.json"}
    assert header["url"] == f"{gitlab['fake'].url}/ba-team/ba-repo/-/issues/142"
    assert "## Comments" in text and "Which countries count as EU?" in text and "## Linked stories" in text
    raw = json.loads((gitlab["repo"] / header["raw"]).read_text(encoding="utf-8"))
    assert raw["issue"]["iid"] == 142 and TOKEN not in text


def test_an_input_is_numbered_after_the_ones_already_there(gitlab, capsys):
    inputs = gitlab["repo"] / "work" / "REQ-341-vat-registration" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "requirement.md").write_text("# The requirement\n", encoding="utf-8")
    (inputs / "01-email-2026-10-20.md").write_text("---\nkind: email\n---\n\nHello\n", encoding="utf-8")

    _, out, _ = add(capsys, "gitlab:REQ-142", "--work-item", "REQ-341")

    assert out.startswith("Added work/REQ-341-vat-registration/inputs/02-story-req-142.md")


def test_a_source_added_again_is_already_there_until_it_changes(gitlab, capsys):
    add(capsys, "gitlab:REQ-142", "--work-item", "REQ-341")

    _, out, _ = add(capsys, "gitlab:ba-requirements#142", "--work-item", "REQ-341")
    assert out == "Already there, unchanged: work/REQ-341/inputs/01-story-req-142.md\n"

    gitlab["fake"].routes["/api/v4/projects/101/issues/142"]["updated_at"] = "2026-10-28T08:00:00Z"
    _, out, _ = add(capsys, "gitlab:REQ-142", "--work-item", "REQ-341")
    assert out == ("Changed since work/REQ-341/inputs/01-story-req-142.md: added "
                   "work/REQ-341/inputs/02-story-req-142.md\n")
    assert sorted(p.name for p in (gitlab["repo"] / "work/REQ-341/inputs").iterdir()) == [
        "01-story-req-142.md", "02-story-req-142.md"]


def test_a_wiki_page_becomes_an_input_its_version_its_content(gitlab, capsys):
    code, out, _ = add(capsys, "wiki:onboarding/checklist", "--wiki", "ba-requirements", "--work-item", "REQ-341")

    assert (code, out) == (0, "Added work/REQ-341/inputs/01-wiki-onboarding-checklist.md: Checklist\n")
    file = gitlab["repo"] / "work/REQ-341/inputs/01-wiki-onboarding-checklist.md"
    header = read_markdown(file.read_text(encoding="utf-8")).front_matter
    assert header["kind"] == "gitlab-wiki-page" and header["source"] == "ba-requirements:onboarding/checklist"
    assert header["version"].startswith("sha256:")
    assert header["url"] == f"{gitlab['fake'].url}/ba-team/ba-repo/-/wikis/onboarding/checklist"

    gitlab["fake"].routes["/api/v4/projects/101/wikis/onboarding%2Fchecklist"] = {
        **PAGE, "content": PAGE["content"] + "3. Check its codes\n"}
    _, out, _ = add(capsys, "wiki:onboarding/checklist", "--wiki", "ba-requirements", "--work-item", "REQ-341")
    assert out.startswith("Changed since work/REQ-341/inputs/01-wiki-onboarding-checklist.md: added ")


@pytest.mark.parametrize("args, message", [
    (["gitlab:REQ-142", "--work-item", "vat-work"], "vat-work isn't a work item's id"),
    (["gitlab:ABC-1", "--work-item", "REQ-341"], "No declared project has the key ABC"),
    (["pdf:notes.pdf", "--work-item", "REQ-341"], "isn't a source bridge-kit reads"),
])
def test_a_wrong_work_item_or_source_is_refused_before_a_request(gitlab, capsys, args, message):
    code, _, err = add(capsys, *args)

    assert code == 2 and message in err
    assert gitlab["fake"].requests == []
    assert not (gitlab["repo"] / "work").exists()


# Writes: each one a dry run without --yes, and only to a read-write project

def test_a_write_is_a_dry_run_until_yes_and_then_it_s_made(gitlab, capsys, tmp_path):
    fake = gitlab["fake"]
    fake.routes["POST /api/v4/projects/101/issues"] = lambda body: {"iid": 151, "web_url": f"{fake.url}/151", **body}
    (tmp_path / "story.md").write_text("As a credit analyst, I want ...\n", encoding="utf-8")
    args = ["issue", "create", "--project", "ba-requirements", "--title", "Show VAT", "--description-file",
            str(tmp_path / "story.md"), "--label", "vat", "--label", "component::model"]

    code, out, _ = run(capsys, *args)
    assert (code, out) == (0, "Would create in ba-requirements: Show VAT [vat, component::model]\n"
                              "Run it again with --yes once the BA has said so.\n")
    assert fake.writes == []

    code, out, _ = run(capsys, *args, "--yes")
    assert (code, out) == (0, f"Created REQ-151 in ba-requirements: Show VAT\n{fake.url}/151\n")
    assert fake.writes == [("POST", "/api/v4/projects/101/issues", {
        "title": "Show VAT", "description": "As a credit analyst, I want ...\n", "labels": "vat,component::model"},
        TOKEN)]


def test_update_comment_and_link(gitlab, capsys, tmp_path):
    fake = gitlab["fake"]
    fake.routes.update({"PUT /api/v4/projects/101/issues/142": {"iid": 142},
                        "POST /api/v4/projects/101/issues/142/notes": {"id": 1},
                        "POST /api/v4/projects/101/issues/142/links": {}})
    (tmp_path / "note.md").write_text("Stories written.\n", encoding="utf-8")

    assert run(capsys, "issue", "update", "REQ-142", "--state", "close", "--label", "done", "--yes")[1] == (
        "Updated REQ-142: labels, state\n")
    assert run(capsys, "issue", "comment", "REQ-142", "--body-file", str(tmp_path / "note.md"), "--yes")[1] == (
        "Commented on REQ-142\n")
    assert run(capsys, "issue", "link", "REQ-142", "service-a#5", "--yes")[1] == (
        "Linked REQ-142 to service-a#5: relates to\n")
    assert [(m, p, b) for m, p, b, _ in fake.writes] == [
        ("PUT", "/api/v4/projects/101/issues/142", {"labels": "done", "state_event": "close"}),
        ("POST", "/api/v4/projects/101/issues/142/notes", {"body": "Stories written.\n"}),
        ("POST", "/api/v4/projects/101/issues/142/links",
         {"target_project_id": 202, "target_issue_iid": 5, "link_type": "relates_to"})]


@pytest.mark.parametrize("args, message", [
    (["issue", "create", "--project", "service-a", "--title", "X", "--yes"],
     "service-a is read-only in bridge-kit.yaml: declare it access: read-write"),
    (["issue", "comment", "service-a#5", "--body-file", "{note}", "--yes"],
     "service-a is read-only in bridge-kit.yaml"),
    (["issue", "update", "REQ-142", "--yes"], "Nothing to change on REQ-142"),
])
def test_a_write_to_a_read_only_project_or_of_nothing_is_refused_before_a_request(gitlab, capsys, tmp_path, args,
                                                                                    message):
    (tmp_path / "note.md").write_text("Hello\n", encoding="utf-8")
    code, _, err = run(capsys, *[a.format(note=tmp_path / "note.md") for a in args])

    assert code in (1, 2) and message in err
    assert gitlab["fake"].writes == []


def test_gitlab_s_refusal_of_a_write_is_one_line(gitlab, capsys):
    gitlab["fake"].routes["POST /api/v4/projects/101/issues"] = Error(403)

    code, _, err = run(capsys, "issue", "create", "--project", "ba-requirements", "--title", "X", "--yes")

    assert (code, err) == (1, "GitLab won't let the token create an issue in ba-requirements: writing needs the api "
                              "scope, and Reporter access or more\n")


def test_status_says_when_the_token_can_t_write_a_read_write_project(gitlab, capsys):
    gitlab["fake"].routes["/api/v4/personal_access_tokens/self"] = {"scopes": ["read_api"]}

    code, out, _ = run(capsys, "status")

    assert code == 1 and "Token scopes: read_api\n" in out
    assert ("PROBLEM The token can't write (its scopes: read_api), and bridge-kit.yaml declares ba-requirements "
            "read-write: writing their issues needs the api scope") in out
