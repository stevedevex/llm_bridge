"""`bridge-kit export`: the kit exported into an empty folder holds what ships and nothing else, runs on its own; a
second export updates the kit's files and keeps the BA repo's own, and stops at a kit file changed there since."""

import hashlib
import os
import stat
import subprocess
import sys
import tomllib

import pytest
import yaml
from conftest import KIT

from bridge_kit.cli import main
from bridge_kit.export import RECORD, ExportError, export, shipped

BA_REPO = KIT.parents[1]


@pytest.fixture
def target(tmp_path):
    folder = tmp_path / "another-ba-repo"
    folder.mkdir()
    return folder


def test_what_ships_and_what_doesn_t():
    files = shipped(BA_REPO)

    for expected in (".github/agents/mapping-drafter.agent.md", ".github/prompts/profile-component.prompt.md",
                     ".github/skills/document-reading/SKILL.md", ".github/skills/spec-resolver/pom.xml",
                     ".github/bridge-kit/bin/bridge-kit", ".github/bridge-kit/bin/bridge-kit-mcp",
                     ".github/bridge-kit/schema/bridge-kit.schema.json", ".github/bridge-kit/src/bridge_kit/cli.py",
                     ".github/bridge-kit/src/bridge_kit/documents/excel.py", ".github/bridge-kit/pyproject.toml",
                     ".github/bridge-kit/uv.lock", ".github/bridge-kit/README.md", ".github/bridge-kit/GUIDE.md",
                     ".github/bridge-kit/guides/README.md", ".github/bridge-kit/guides/story-writer.md",
                     ".github/bridge-kit/bridge-kit.example.yaml",
                     ".github/bridge-kit/agents/story-writer/manifest.yaml",
                     "templates/story.md", "templates/impact.md", "mappings/FORMAT.md", "mappings/REQUEST.md"):
        assert expected in files, expected
    for left_out in ("/tests/", "__pycache__", ".pyc"):
        assert not any(left_out in f for f in files), left_out
    assert ".github/bridge-kit/bridge-kit.yaml" not in files
    assert not any(f.startswith(("architecture/", "work/", "assembly/", "lookups/", ".work/")) for f in files)
    agents = {f.split("/")[3] for f in files if f.startswith(".github/bridge-kit/agents/")}
    assert agents == {p.name.removesuffix(".agent.md") for p in (BA_REPO / ".github" / "agents").glob("*.agent.md")}


def test_an_export_into_an_empty_folder(target, capsys):
    assert main(["export", "--to", str(target), "--dry-run"]) == 0
    assert "Would export" in capsys.readouterr().out and list(target.iterdir()) == []

    assert main(["export", "--to", str(target)]) == 0

    files = shipped(BA_REPO)
    assert all((target / f).is_file() for f in files)
    assert os.stat(target / ".github/bridge-kit/bin/bridge-kit").st_mode & stat.S_IXUSR
    assert (target / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        "# Caches, scratch files and run output (bridge-kit's working folder)", ".work/", "",
        "# One person's overrides of bridge-kit.yaml: a repo's mode and path, the environment's name",
        ".github/bridge-kit/bridge-kit.local.yaml"]
    record = yaml.safe_load((target / RECORD).read_text(encoding="utf-8"))
    assert record["files"] == files and record["source_commit"]


def test_a_second_export_updates_the_kit_s_files_and_keeps_the_ba_repo_s(target):
    export(BA_REPO, target)
    for name, text in ((".github/bridge-kit/bridge-kit.yaml", "model:\n  repo: our-model\n"),
                       ("architecture/components.yaml", "components: {}\n"), ("work/ABC-1/inputs/notes.md", "Notes\n"),
                       (".github/skills/our-own/SKILL.md", "Ours\n")):
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(text, encoding="utf-8")
    (target / "mappings/FORMAT.md").write_text("An earlier kit's FORMAT\n", encoding="utf-8")
    (target / ".github/skills/old-skill").mkdir()
    (target / ".github/skills/old-skill/SKILL.md").write_text("From an earlier kit\n", encoding="utf-8")
    record = yaml.safe_load((target / RECORD).read_text(encoding="utf-8"))
    record["sha256"]["mappings/FORMAT.md"] = hashlib.sha256(b"An earlier kit's FORMAT\n").hexdigest()
    record["files"].append(".github/skills/old-skill/SKILL.md")  # as an earlier export would have written them
    (target / RECORD).write_text(yaml.safe_dump(record), encoding="utf-8")
    (target / ".gitignore").write_text("node_modules/\n.work/\n", encoding="utf-8")

    result = export(BA_REPO, target)

    assert result.files["mappings/FORMAT.md"] == "updated"
    assert (target / "mappings/FORMAT.md").read_bytes() == (BA_REPO / "mappings/FORMAT.md").read_bytes()
    assert result.files[".github/skills/old-skill/SKILL.md"] == "removed"
    assert not (target / ".github/skills/old-skill/SKILL.md").exists()
    assert result.count("unchanged") == len(shipped(BA_REPO)) - 1
    for kept in (".github/bridge-kit/bridge-kit.yaml", "architecture/components.yaml", "work/ABC-1/inputs/notes.md",
                 ".github/skills/our-own/SKILL.md"):
        assert (target / kept).exists(), kept
    assert result.gitignore == "added"
    assert (target / ".gitignore").read_text(encoding="utf-8").startswith("node_modules/\n.work/\n\n# One person's")


def test_a_kit_file_changed_there_since_stops_it_before_anything_is_written(target, capsys):
    export(BA_REPO, target)
    (target / "mappings/FORMAT.md").write_text("Edited in that BA repo\n", encoding="utf-8")
    (target / "templates/story.md").unlink()
    record = yaml.safe_load((target / RECORD).read_text(encoding="utf-8"))
    del record["sha256"]["templates/impact.md"]  # an older record: the file at its commit is what it wrote
    (target / RECORD).write_text(yaml.safe_dump(record), encoding="utf-8")
    (target / "templates/impact.md").write_text("Edited too\n", encoding="utf-8")

    assert main(["export", "--to", str(target)]) == 1

    out = capsys.readouterr()
    assert "changed there mappings/FORMAT.md" in out.out and "changed there templates/impact.md" in out.out
    assert "Stopped, nothing written: 2 of the kit's file(s) changed" in out.err
    assert not (target / "templates/story.md").exists()  # nothing written, not even what's new
    assert (target / "mappings/FORMAT.md").read_text(encoding="utf-8") == "Edited in that BA repo\n"

    result = export(BA_REPO, target, force=True)

    assert (result.stopped, result.files["mappings/FORMAT.md"], result.files["templates/story.md"]) == (
        False, "overwritten", "new")
    assert (target / "mappings/FORMAT.md").read_bytes() == (BA_REPO / "mappings/FORMAT.md").read_bytes()


def test_it_won_t_export_into_the_kit_s_own_repo_or_nowhere(tmp_path):
    with pytest.raises(ExportError, match="isn't a folder"):
        export(BA_REPO, tmp_path / "missing")
    with pytest.raises(ExportError, match="is the kit's own repo"):
        export(BA_REPO, BA_REPO / "templates")


def test_the_exported_kit_runs_on_its_own(target, tmp_path):
    export(BA_REPO, target)
    (tmp_path / "rough.csv").write_text("Field,Rule\nprefChannel,trim\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(target / ".github/bridge-kit/src"), "BRIDGE_KIT_REPO_ROOT": str(target)}

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "bridge_kit", *args], capture_output=True, text=True, env=env,
                              cwd=tmp_path)

    where = subprocess.run([sys.executable, "-c", "import bridge_kit; print(bridge_kit.__file__)"], capture_output=True,
                           text=True, env=env).stdout
    assert where.startswith(str(target))
    commands = run("--help").stdout
    assert all(name in commands for name in ("export", "doc", "gitlab", "components", "preflight", "validate"))
    assert run("doc", "read", "rough.csv").stdout.startswith("# rough\n")
    preflight = run("preflight")
    assert preflight.returncode == 1 and "Traceback" not in preflight.stdout + preflight.stderr
    assert run("components", "build").returncode == 0


def test_the_exported_kit_needs_only_its_five_packages_to_run():
    project = tomllib.loads((BA_REPO / ".github/bridge-kit/pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert sorted(d.split(">")[0].split("=")[0] for d in project["dependencies"]) == [
        "olefile", "openpyxl", "pymongo", "pypdf", "pyyaml"]
    assert "--no-dev" in (BA_REPO / ".github/bridge-kit/bin/bridge-kit").read_text(encoding="utf-8")
