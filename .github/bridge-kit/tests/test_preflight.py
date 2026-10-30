"""bridge-kit preflight: the landscape passes, and git checkouts made in a test, cloned from a bare remote, each fail
the way they're broken: a missing path, another remote, another branch, changes in a read-only checkout, commits
behind the upstream (as of the last fetch, never fetched), a folder inside another checkout; tools and files the
environment lacks; and a declared GitLab, on the stand-in: an id naming another project stops, anything else warns."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from fixtures.fake_gitlab import Error, FakeGitLab
from test_gitlab import TOKEN, config, routes

from bridge_kit.cli import main
from bridge_kit.preflight import format_preflight, in_range, preflight

GIT_ENV = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com", "GIT_COMMITTER_NAME": "test",
           "GIT_COMMITTER_EMAIL": "test@example.com", "GIT_CONFIG_GLOBAL": "/dev/null"}


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True,
                            env={**os.environ, **GIT_ENV})
    return result.stdout.strip()


def commit(path: Path, name: str) -> None:
    (path / name).write_text(name, encoding="utf-8")
    git(path, "add", name)
    git(path, "commit", "-q", "-m", name)


@pytest.fixture
def layout(tmp_path):
    """/projects with a BA repo and two checkouts on develop, each cloned from a bare remote; returns the paths and
    the bridge-kit.yaml content, which a test changes before calling write()."""
    projects, remotes = tmp_path / "projects", tmp_path / "remotes"
    paths = {"ba_repo": projects / "ba-repo", "tmp": tmp_path}
    (paths["ba_repo"] / ".github" / "bridge-kit").mkdir(parents=True)
    repos = {}
    for name, access in (("shared-model", "read-write"), ("service-a-java", "read-only")):
        seed = tmp_path / "seed" / name
        seed.mkdir(parents=True)
        git(seed, "init", "-q", "-b", "develop")
        commit(seed, "README.md")
        subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(remotes / f"{name}.git")], check=True,
                       env={**os.environ, **GIT_ENV})
        subprocess.run(["git", "clone", "-q", str(remotes / f"{name}.git"), str(projects / name)], check=True,
                       env={**os.environ, **GIT_ENV})
        repos[name] = {"mode": "local", "path": f"../{name}", "remote": str(remotes / f"{name}.git"),
                       "branch": "develop", "access": access}
        paths[name] = projects / name
    repos["shared-model"]["writers"] = ["model-designer"]
    paths["config"] = {"bridge-kit": {"version": "0.1.0"}, "environment": {"manager": "none", "tools": {"git": "*"}},
                       "workspace": {"repos": repos}, "model": {"repo": "shared-model"},
                       "rules": {"workspace": {"dirty_read_only": "warn"}, "writes": {"work_branch_prefix": "feature/"}}}
    return paths


def write(layout, local: dict | None = None) -> Path:
    kit = layout["ba_repo"] / ".github" / "bridge-kit"
    (kit / "bridge-kit.yaml").write_text(yaml.safe_dump(layout["config"], sort_keys=False), encoding="utf-8")
    if local is not None:
        (kit / "bridge-kit.local.yaml").write_text(yaml.safe_dump(local), encoding="utf-8")
    return layout["ba_repo"]


def row(report, repo: str):
    return next(r for r in report.repos if r.repo == repo)


def test_clean_checkouts_on_their_branches_pass(layout):
    report = preflight(write(layout))

    assert report.ok and report.warnings == [], format_preflight(report)
    model = row(report, "shared-model")
    assert (model.branch, model.severity) == ("develop", "ok")
    assert model.commit == git(layout["shared-model"], "rev-parse", "--short", "HEAD")
    assert model.status == "OK; up to date with origin/develop as of the last fetch"


def test_a_missing_checkout_stops(layout):
    shutil.rmtree(layout["service-a-java"])

    report = preflight(write(layout))

    assert report.stops == ["service-a-java: not at ../service-a-java: check it out there, or "
                            "correct the path"]


def test_a_clone_mode_repo_that_isn_t_there_stops_until_the_kit_can_clone(layout):
    layout["config"]["workspace"]["repos"]["service-a-java"]["mode"] = "clone"
    shutil.rmtree(layout["service-a-java"])

    assert "the kit can't clone yet" in preflight(write(layout)).stops[0]


def test_another_repo_at_the_declared_path_stops(layout):
    git(layout["service-a-java"], "remote", "set-url", "origin", str(layout["tmp"] / "elsewhere.git"))

    report = preflight(write(layout))

    assert len(report.stops) == 1 and "it's another repo at the declared path" in report.stops[0]


def test_a_read_only_checkout_must_be_on_its_branch(layout):
    git(layout["service-a-java"], "checkout", "-q", "-b", "feature/REQ-1")

    report = preflight(write(layout))

    assert report.stops == ["service-a-java: on feature/REQ-1, and bridge-kit.yaml says develop"]


def test_a_read_write_checkout_may_be_on_a_work_branch(layout):
    git(layout["shared-model"], "checkout", "-q", "-b", "feature/REQ-341")
    assert preflight(write(layout)).ok

    git(layout["shared-model"], "checkout", "-q", "-b", "hotfix")
    report = preflight(write(layout))

    assert report.stops == ["shared-model: on hotfix, and bridge-kit.yaml says develop or a feature/ branch"]


def test_changes_in_a_read_only_checkout_warn_or_stop_as_the_rules_say(layout):
    (layout["service-a-java"] / "notes.txt").write_text("mine", encoding="utf-8")
    (layout["shared-model"] / "draft.json").write_text("{}", encoding="utf-8")

    report = preflight(write(layout))

    assert report.ok
    assert report.warnings == ["service-a-java: read-only, but 1 file(s) changed in it; up to date with "
                               "origin/develop as of the last fetch"]
    assert row(report, "shared-model").status.startswith("OK, 1 changed file(s)")

    layout["config"]["rules"]["workspace"]["dirty_read_only"] = "stop"
    assert not preflight(write(layout)).ok


def test_commits_behind_count_from_the_last_fetch_and_nothing_is_fetched(layout):
    other = layout["tmp"] / "other"
    subprocess.run(["git", "clone", "-q", layout["config"]["workspace"]["repos"]["shared-model"]["remote"],
                    str(other)], check=True, env={**os.environ, **GIT_ENV})
    commit(other, "CHANGELOG.md")
    git(other, "push", "-q", "origin", "develop")

    assert preflight(write(layout)).warnings == []  # it doesn't know yet: the preflight never fetches

    git(layout["shared-model"], "fetch", "-q")
    report = preflight(write(layout))

    assert report.ok
    assert report.warnings == ["shared-model: OK; 1 commit(s) behind origin/develop as of the last fetch: pull "
                               "only with the BA's OK"]


def test_a_folder_inside_another_checkout_isn_t_a_checkout_of_its_own(layout):
    (layout["shared-model"] / "schemas").mkdir()
    layout["config"]["workspace"]["repos"]["shared-model"]["path"] = "../shared-model/schemas"

    report = preflight(write(layout))

    assert report.stops == ["shared-model: ../shared-model/schemas isn't a git checkout of its own"]


def test_tools_and_files_the_environment_lacks_stop(layout):
    layout["config"]["environment"] = {"manager": "none", "tools": {"git": ">=99", "no-such-tool": "*"},
                                       "files": [str(layout["tmp"] / "settings.xml")]}

    report = preflight(write(layout))

    assert report.stops[0].startswith("git: 2.") and report.stops[0].endswith(", and bridge-kit.yaml needs >=99")
    assert report.stops[1] == "no-such-tool: doesn't run in the environment (FileNotFoundError)"
    assert report.stops[2] == f"{layout['tmp'] / 'settings.xml'} doesn't exist: the environment needs it"


def test_a_broken_config_stops_before_anything_else_is_checked(layout):
    layout["config"]["environment"]["manager"] = "conda"

    report = preflight(write(layout))

    assert (report.repos, report.tools) == ([], [])
    assert "environment.manager must be one of micromamba, none" in report.stops[0]
    assert format_preflight(report).endswith("Preflight: STOP: agents stop here")


def test_an_overridden_repo_is_marked(layout):
    moved = layout["tmp"] / "elsewhere" / "service-a-java"
    moved.parent.mkdir()
    shutil.move(layout["service-a-java"], moved)

    report = preflight(write(layout, {"workspace": {"repos": {"service-a-java": {"path": str(moved)}}}}))

    assert report.ok
    assert row(report, "service-a-java").overridden
    assert report.config.endswith("bridge-kit.yaml, with bridge-kit.local.yaml")
    assert f"| service-a-java | local (overridden) | {moved} | develop |" in format_preflight(report)


@pytest.fixture
def gitlab(layout, monkeypatch):
    """The layout's bridge-kit.yaml declaring the stand-in GitLab: two projects, a group, two wikis."""
    with FakeGitLab({}) as fake:
        fake.routes.update(routes(fake.url))
        layout["config"]["integrations"] = config(fake.url)["integrations"]
        monkeypatch.setenv("BRIDGE_KIT_TEST_GITLAB_TOKEN", TOKEN)
        yield fake


def test_a_declared_gitlab_that_answers_at_its_paths_passes(layout, gitlab):
    report = preflight(write(layout))

    assert report.ok and report.warnings == [], format_preflight(report)
    assert report.gitlab == f"@ba.user on {gitlab.url}: 2 project(s), 1 group(s), 2 wiki(s): OK"
    assert f"GitLab:      @ba.user on {gitlab.url}" in format_preflight(report)
    assert {path for path, _, _ in gitlab.requests} == {"/api/v4/user", "/api/v4/projects/101", "/api/v4/projects/202",
                                                        "/api/v4/projects/101/wikis", "/api/v4/groups/7",
                                                        "/api/v4/groups/7/wikis",
                                                        "/api/v4/personal_access_tokens/self"}  # a read-write project
    output = format_preflight(report) + json.dumps(report.to_dict())
    assert TOKEN not in output and {token for _, _, token in gitlab.requests} == {TOKEN}


def test_without_a_gitlab_there_s_no_gitlab_line(layout):
    report = preflight(write(layout))

    assert report.gitlab == "" and "GitLab" not in format_preflight(report)


def test_a_project_id_naming_another_project_stops(layout, gitlab):
    gitlab.routes["/api/v4/projects/202"] = {"path_with_namespace": "dev/something-else"}

    report = preflight(write(layout))

    assert not report.ok
    assert report.stops == ["GitLab: service-a: id 202 is dev/something-else, and bridge-kit.yaml says "
                            "dev/service-a-java"]
    assert report.gitlab.endswith(": 1 problem(s)")


def test_a_missing_token_warns_and_nothing_is_asked(layout, gitlab, monkeypatch):
    monkeypatch.delenv("BRIDGE_KIT_TEST_GITLAB_TOKEN")

    report = preflight(write(layout))

    assert report.ok and gitlab.requests == []
    assert report.gitlab == (f"{gitlab.url}: not checked: No GitLab token: the environment variable "
                             "BRIDGE_KIT_TEST_GITLAB_TOKEN isn't set")
    assert report.warnings == ["GitLab: No GitLab token: the environment variable BRIDGE_KIT_TEST_GITLAB_TOKEN isn't "
                               "set; the gitlab commands and tools won't work until it's fixed"]


@pytest.mark.parametrize("route, warning", [
    ("/api/v4/user", "GitLab: GitLab refused the token: check where bridge-kit.yaml says it is, and that it hasn't "
                     "expired; the gitlab commands and tools won't work until it's fixed"),
    ("/api/v4/groups/7/wikis", "GitLab: pod's wiki: GitLab has no "),
])
def test_a_refused_token_or_a_wiki_that_doesn_t_answer_warns(layout, gitlab, route, warning):
    gitlab.routes[route] = Error(401 if route == "/api/v4/user" else 404)

    report = preflight(write(layout))

    assert report.ok and len(report.warnings) == 1 and report.warnings[0].startswith(warning)


@pytest.mark.parametrize("version, wanted, ok", [
    ("24.0.2", ">=21", True), ("17.0.9", ">=21", False), ("3.9.12", ">=3.9", True), ("3.8", ">=3.9", False),
    ("25", ">=21, <26", True), ("26.0.1", ">=21, <26", False), ("0.9.1", "*", True), ("2.50.1", "==2.50.1", True),
    ("3.13.7", "3.13", False), ("1.2", "about 1", False),
])
def test_version_ranges(version, wanted, ok):
    assert in_range(version, wanted) is ok


def test_the_command_exits_1_on_a_stop(layout, monkeypatch, capsys):
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(write(layout)))
    assert main(["preflight"]) == 0
    assert capsys.readouterr().out.strip().endswith("Preflight: OK, 0 warning(s)")

    shutil.rmtree(layout["service-a-java"])
    assert main(["preflight", "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False and len(result["stops"]) == 1
