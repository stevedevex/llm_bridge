"""bridge-kit workspace scan, on a stand-in /projects: each folder's remote (its token taken out), the remote's default
branch or the current one flagged, a wiki, the model's repo, the environment's tools as ranges; what differs from
bridge-kit.yaml; and --write adding only what's missing, its comments kept."""

import json
import shutil
import subprocess

import pytest
import yaml
from conftest import KIT, LANDSCAPE

from bridge_kit import workspace_scan
from bridge_kit.cli import main
from bridge_kit.config import check_config

SECRET = "glpat-not-a-real-token"


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)


@pytest.fixture
def projects(tmp_path, monkeypatch):
    """A workspace with the BA repo (the landscape's bridge-kit.yaml) and the checkouts beside it."""
    root = tmp_path / "projects"
    kit = root / "ba-repo" / ".github" / "bridge-kit"
    kit.mkdir(parents=True)
    shutil.copy(LANDSCAPE / "bridge-kit.yaml", kit / "bridge-kit.yaml")
    model = root / "shared-model" / "schemas"
    model.mkdir(parents=True)
    for name in ("credit-file", "amount"):
        (model / f"{name}.json").write_text(json.dumps({"$schema": "http://json-schema.org/draft-07/schema#"}))
    collection = root / "service-a-java"
    collection.mkdir()
    git(collection, "init", "-q", "-b", "develop")
    git(collection, "remote", "add", "origin",
        f"https://ba.user:{SECRET}@gitlab.example/lending/service-a-java.git")
    git(collection, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
    business = root / "service-c-java"
    business.mkdir()
    git(business, "init", "-q", "-b", "feature/REQ-142-vat")
    git(business, "remote", "add", "origin", "git@gitlab.example:lending/service-c-java.git")
    wiki = root / "pod-wiki"
    wiki.mkdir()
    git(wiki, "init", "-q", "-b", "main")
    git(wiki, "remote", "add", "origin", "https://gitlab.example/lending/pod.wiki.git")
    git(wiki, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    (root / ".cache").mkdir()
    (root / "notes.txt").write_text("not a repo")
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(root / "ba-repo"))
    monkeypatch.setattr(workspace_scan, "_tools", lambda: {"java": "21.0.4", "mvn": "3.9.12", "python": "3.13.7"})
    return root


def run(capsys, *args):
    code = main(["workspace", "scan", *args])
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err  # a token in a remote's URL is never shown
    return code, out.out, out.err


def test_the_scan_drafts_each_repo_from_its_checkout(projects, capsys):
    code, out, _ = run(capsys)

    assert code == 0
    block = yaml.safe_load(out.split("\n\n", 1)[1].split("\n\nCompared", 1)[0])
    assert block["workspace"]["repos"] == {
        "service-c-java": {"mode": "local", "path": "../service-c-java", "access": "read-only",
                             "remote": "git@gitlab.example:lending/service-c-java.git",
                             "branch": "feature/REQ-142-vat"},
        "service-a-java": {"mode": "local", "path": "../service-a-java", "access": "read-only",
                                    "remote": "https://gitlab.example/lending/service-a-java.git",
                                    "branch": "develop"},
        "shared-model": {"mode": "local", "path": "../shared-model", "access": "read-only",
                                "git": False},
        "pod-wiki": {"mode": "local", "path": "../pod-wiki", "access": "read-only", "kind": "wiki",
                     "remote": "https://gitlab.example/lending/pod.wiki.git", "branch": "main"}}
    assert block["environment"]["tools"] == {"java": ">=21", "mvn": ">=3.9", "python": ">=3.13"}


def test_the_scan_says_what_differs_from_bridge_kit_yaml(projects, capsys):
    _, out, _ = run(capsys)

    compared = out.split("Compared with bridge-kit.yaml:\n", 1)[1]
    assert "- not declared: service-c-java (--write adds it, read-only)" in compared
    assert "- not declared: pod-wiki (--write adds it, read-only)" in compared
    assert ("- differs: service-a-java: a git checkout here, git: false in bridge-kit.yaml") in compared
    assert ("Note: service-c-java: git doesn't know the remote's default branch, so its current branch, "
            "feature/REQ-142-vat, is proposed: check it") in compared
    assert ("Note: shared-model looks like the internal model's repo: set it read-write with writers "
            "[model-designer] and its build, and name it as model.repo") in compared


def test_a_declared_repo_that_isn_t_there_is_named(projects, capsys):
    shutil.rmtree(projects / "service-a-java")

    _, out, _ = run(capsys)

    assert "- declared, not found: service-a-java" in out


def test_write_adds_only_the_missing_repos_and_keeps_the_comments(projects, capsys):
    file = projects / "ba-repo" / ".github" / "bridge-kit" / "bridge-kit.yaml"
    before = file.read_text(encoding="utf-8")

    code, out, _ = run(capsys, "--write")

    after = file.read_text(encoding="utf-8")
    data = yaml.safe_load(after)
    assert code == 0 and out.endswith("Added to bridge-kit.yaml: pod-wiki, service-c-java\n")
    assert check_config(data) == []
    assert list(data["workspace"]["repos"]) == ["shared-model", "service-a-java", "pod-wiki",
                                                "service-c-java"]
    assert data["workspace"]["repos"]["service-a-java"] == yaml.safe_load(before)["workspace"]["repos"][
        "service-a-java"]  # an entry that's there is never changed
    assert "# validate model runs it" in after and after.startswith(before.split("    service-a-java:")[0])

    code, out, _ = run(capsys, "--write")
    assert out.endswith("Nothing to add: bridge-kit.yaml declares every repo found\n")


def test_the_json_and_another_folder(projects, capsys):
    other = projects / "elsewhere"
    other.mkdir()
    (other / "ui-react").mkdir()

    code, out, _ = run(capsys, str(other), "--json")

    data = json.loads(out)
    assert code == 0
    assert data["repos"] == {"ui-react": {"mode": "local", "path": "../elsewhere/ui-react",
                                              "access": "read-only", "git": False}}
    assert run(capsys, str(projects / "nowhere"))[0] == 2


def test_write_adds_to_a_file_still_like_the_example(projects, capsys):
    file = projects / "ba-repo" / ".github" / "bridge-kit" / "bridge-kit.yaml"
    shutil.copy(KIT / "bridge-kit.example.yaml", file)

    code, out, err = run(capsys, "--write")

    text = file.read_text(encoding="utf-8")
    repos = yaml.safe_load(text)["workspace"]["repos"]
    assert code == 0, err
    assert repos["service-c-java"] == {"mode": "local", "path": "../service-c-java", "access": "read-only",
                                         "remote": "git@gitlab.example:lending/service-c-java.git",
                                         "branch": "feature/REQ-142-vat"}
    assert repos["pod-wiki"]["kind"] == "wiki"
    assert "# every repo an agent may read or write" in text  # the example's comments stay
    assert "<https URL of the GitLab>" in text  # its placeholders are the BA's to fill, and the preflight's to check
