"""`bridge-kit export --to <a BA repo>`: writes BRIDGE into another BA repo, and nothing of that repo's own.

- **The kit's, written on every export:** the agents, prompts and skills in `.github`; the kit in
  `.github/bridge-kit` (its launchers, schemas, source, `pyproject.toml`, `uv.lock`, the
  README, `bridge-kit.example.yaml`, and the manifest of each agent with a file in `.github/agents`); `templates/`; and
  `mappings/FORMAT.md` and `REQUEST.md`. A BA repo changes the kit through `bridge-kit.yaml`, not by editing these.
- **The BA repo's own, never written:** `bridge-kit.yaml` and `bridge-kit.local.yaml`, `architecture/` (the catalog
  and the profiles), the assembly and mapping specs, lookups, work items, `.work/`.
- **Never shipped:** the kit's tests, its own `bridge-kit.yaml`, caches.
- `.gitignore` gains the kit's two lines if it lacks them; nothing else in it changes.
- A file an earlier export wrote that the kit no longer has is removed: `.github/bridge-kit/EXPORTED` records each
  export's files, with the commit and date it came from and each file's SHA-256.
- **A kit file changed in that BA repo since the last export is never overwritten unawares:** the export stops before
  writing anything and lists them, the changes to bring back to BRIDGE's repo. `force` overwrites them. A file is
  changed there when it's neither what the last export wrote (by its SHA-256, or for an older record, the file at the
  recorded commit) nor what this export would write.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

KIT = ".github/bridge-kit"
SHIPPED_FOLDERS = (".github/agents", ".github/prompts", ".github/skills", f"{KIT}/bin", f"{KIT}/schema",
                   f"{KIT}/src/bridge_kit", f"{KIT}/guides", "templates")
SHIPPED_FILES = (f"{KIT}/pyproject.toml", f"{KIT}/uv.lock", f"{KIT}/README.md", f"{KIT}/GUIDE.md",
                 f"{KIT}/bridge-kit.example.yaml",
                 "mappings/FORMAT.md", "mappings/REQUEST.md")
LEFT_OUT = re.compile(r"(^|/)(__pycache__|\.venv|\.pytest_cache)(/|$)|\.pyc$|\.DS_Store$")
RECORD = f"{KIT}/EXPORTED"
GITIGNORE = {".work/": "# Caches, scratch files and run output (bridge-kit's working folder)",
             f"{KIT}/bridge-kit.local.yaml": "# One person's overrides of bridge-kit.yaml: a repo's mode and path, the "
                                          "environment's name"}


class ExportError(Exception):
    """The export can't be written: no target, or the target is the kit's own repo."""


@dataclass
class Exported:
    target: Path
    files: dict[str, str] = field(default_factory=dict)  # by path: new, updated, unchanged or removed
    gitignore: str = "unchanged"  # created, added or unchanged
    commit: str | None = None
    dirty: bool = False  # the shipped files had changes not committed
    stopped: bool = False  # kit files changed in the target since the last export: nothing written

    def count(self, status: str) -> int:
        return sum(s == status for s in self.files.values())

    def to_dict(self) -> dict:
        return {"target": str(self.target), "commit": self.commit, "dirty": self.dirty, "stopped": self.stopped,
                "gitignore": self.gitignore, "files": self.files}


def shipped(source: Path) -> list[str]:
    """Every file that ships, by its path in the BA repo."""
    found = {p.relative_to(source).as_posix() for folder in SHIPPED_FOLDERS for p in (source / folder).rglob("*")
             if p.is_file()}
    found |= {f for f in SHIPPED_FILES if (source / f).is_file()}
    for agent in (source / ".github" / "agents").glob("*.agent.md"):  # the BA agents' manifests, not the developers'
        manifest = f"{KIT}/agents/{agent.name.removesuffix('.agent.md')}/manifest.yaml"
        if (source / manifest).is_file():
            found.add(manifest)
    return sorted(f for f in found if not LEFT_OUT.search(f))


def export(source: Path, target: Path, dry_run: bool = False, force: bool = False) -> Exported:
    source, target = source.resolve(), target.resolve()
    if not target.is_dir():
        raise ExportError(f"{target} isn't a folder: give a BA repo, checked out")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ExportError(f"{target} is the kit's own repo, or holds it: export to another BA repo")
    files = shipped(source)
    commit, dirty = _commit(source, files)
    result = Exported(target, commit=commit, dirty=dirty)
    record = _record(target)
    changed = "overwritten" if force else "changed there"
    for name in files:
        here, there = source / name, target / name
        if not there.exists():
            status = "new"
        elif there.read_bytes() == here.read_bytes():
            status = "unchanged"
        else:
            status = changed if _changed_there(source, target, name, record) else "updated"
        result.files[name] = status
    for name in sorted(_previous(record) - set(files)):
        if (target / name).is_file():
            result.files[name] = changed if _changed_there(source, target, name, record) and not force else "removed"
    result.stopped = "changed there" in result.files.values()
    if result.stopped:
        return result
    result.gitignore = _gitignore(target, dry_run)
    if dry_run:
        return result
    for name, status in result.files.items():
        if status in ("new", "updated", "overwritten"):
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target / name)  # the launchers keep their executable bit
        elif status == "removed":
            (target / name).unlink()
    (target / RECORD).write_text(yaml.safe_dump({
        "source_commit": commit, "uncommitted_changes": dirty,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files,
        "sha256": {name: _sha256(source / name) for name in files}}, sort_keys=False), encoding="utf-8")
    return result


def _record(target: Path) -> dict:
    """What the last export recorded, or nothing."""
    try:
        record = yaml.safe_load((target / RECORD).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return record if isinstance(record, dict) else {}


def _previous(record: dict) -> set[str]:
    """The files the last export wrote."""
    names = record.get("files")
    return {str(n) for n in names or [] if not str(n).startswith(("/", "..")) and ".." not in Path(str(n)).parts}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _changed_there(source: Path, target: Path, name: str, record: dict) -> bool:
    """Whether the target's file was changed since the last export wrote it; False when that can't be told."""
    if name not in _previous(record):
        return False  # the last export didn't write it: a file of the target's own, by the kit's name
    digests = record.get("sha256")
    if isinstance(digests, dict) and name in digests:
        return _sha256(target / name) != digests[name]
    commit = record.get("source_commit")
    if not commit:
        return False
    try:
        written = subprocess.run(["git", "-C", str(source), "show", f"{commit}:./{name}"], capture_output=True,
                                 timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return written.returncode == 0 and written.stdout != (target / name).read_bytes()


def _gitignore(target: Path, dry_run: bool) -> str:
    file = target / ".gitignore"
    existed = file.exists()
    lines = file.read_text(encoding="utf-8").splitlines() if existed else []
    missing = [line for line in GITIGNORE if line not in lines]
    if not missing:
        return "unchanged"
    if not dry_run:
        text = "\n".join(lines).rstrip("\n")
        added = "\n".join(f"{GITIGNORE[line]}\n{line}\n" for line in missing)
        file.write_text(f"{text}\n\n{added}" if text else added, encoding="utf-8")
    return "added" if existed else "created"


def _commit(source: Path, files: list[str]) -> tuple[str | None, bool]:
    """The kit repo's commit, and whether the shipped files have changes not committed; (None, False) outside git."""
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    commit = git("rev-parse", "--short", "HEAD")
    if commit is None:
        return None, False
    changes = git("status", "--porcelain", "--", *files)
    return commit, bool(changes)
