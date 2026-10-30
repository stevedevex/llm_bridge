"""`bridge-kit workspace scan`: a draft of `bridge-kit.yaml`'s `workspace.repos` from the folders beside the BA repo,
for a person to review.

For each folder: whether it's a git checkout; its remote, with any user or token taken out of the URL; the branch to
declare, the remote's default (where origin's HEAD points, as git last fetched it) so a checkout on a work branch
doesn't make that the declared one, else the current branch, flagged; `kind: wiki` for a project wiki's checkout; and
whether it looks like the internal model's repo (a folder of JSON Schemas). Every repo is proposed read-only: access,
writers, a build and `model.repo` are the BA's to set. Also the environment's tools, each at the version found, as a
range. Then what differs from `bridge-kit.yaml`: repos it doesn't declare, repos it declares that aren't there, and a
different remote or branch.

It never fetches, pulls or changes a checkout. `--write` adds only the repos `bridge-kit.yaml` doesn't declare, at
the end of its `workspace.repos`, its comments kept, and never changes an entry that's there. It checks the entries it
adds, and that the file still reads with them; the rest of the file, its placeholders included while it's being
written, is the preflight's to check.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

TOOLS = ("java", "mvn", "python", "uv", "git", "node", "npm")
USERINFO = re.compile(r"^(\w[\w+.-]*://)[^/@]+@")
SCHEMA_KEY = re.compile(r'"\$schema"\s*:')


@dataclass
class Found:
    name: str
    path: str  # relative to the BA repo
    git: bool
    remote: str | None = None
    branch: str | None = None
    branch_is_current: bool = False  # git doesn't know the remote's default: it's the checkout's current branch
    wiki: bool = False
    model: bool = False  # it looks like the internal model's repo

    def entry(self) -> dict:
        """Its entry under workspace.repos, as the scan proposes it."""
        entry = {"mode": "local", "path": self.path, "access": "read-only"}
        if self.wiki:
            entry["kind"] = "wiki"
        if not self.git:
            entry["git"] = False
        else:
            entry.update({k: v for k, v in (("remote", self.remote), ("branch", self.branch)) if v})
        return entry


@dataclass
class Scan:
    folder: str
    found: list[Found] = field(default_factory=list)
    tools: dict[str, str] = field(default_factory=dict)  # tool -> its version
    missing: list[str] = field(default_factory=list)  # found, not in bridge-kit.yaml
    gone: list[str] = field(default_factory=list)  # in bridge-kit.yaml, not found
    differs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**asdict(self), "repos": {f.name: f.entry() for f in self.found},
                "environment": {"tools": ranges(self.tools)}}


def scan(ba_repo: Path, folder: Path | None = None, declared: dict | None = None) -> Scan:
    """The folders in `folder` (the BA repo's parent by default), against `declared` (workspace.repos as written)."""
    ba_repo = ba_repo.resolve()
    folder = (folder or ba_repo.parent).resolve()
    result = Scan(str(folder))
    for child in sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if child.resolve() == ba_repo:
            continue
        result.found.append(_inspect(child, ba_repo))
    result.tools = _tools()
    declared = declared or {}
    by_path = {str((ba_repo / str(e.get("path", ""))).resolve()): name for name, e in declared.items()}
    for found in result.found:
        name = by_path.get(str((ba_repo / found.path).resolve()), found.name if found.name in declared else None)
        if name is None:
            result.missing.append(found.name)
            continue
        entry = declared[name]
        if found.git and entry.get("git", True):
            for key in ("remote", "branch"):
                if getattr(found, key) and entry.get(key) and getattr(found, key) != entry[key]:
                    result.differs.append(f"{name}: {key} is {getattr(found, key)} here, {entry[key]} in "
                                          "bridge-kit.yaml")
        if found.git != bool(entry.get("git", True)):
            result.differs.append(f"{name}: {'a git checkout' if found.git else 'a plain folder'} here, "
                                  f"git: {str(entry.get('git', True)).lower()} in bridge-kit.yaml")
    paths = {str((ba_repo / f.path).resolve()) for f in result.found}
    result.gone = [name for name, e in declared.items() if str((ba_repo / str(e.get("path", ""))).resolve()) not in
                   paths and not (ba_repo / str(e.get("path", ""))).is_dir()]
    for found in result.found:
        if found.branch_is_current:
            result.notes.append(f"{found.name}: git doesn't know the remote's default branch, so its current branch, "
                                f"{found.branch}, is proposed: check it")
        if found.model:
            result.notes.append(f"{found.name} looks like the internal model's repo: set it read-write with writers "
                                "[model-designer] and its build, and name it as model.repo")
    return result


def _inspect(child: Path, ba_repo: Path) -> Found:
    name = re.sub(r"[^a-z0-9]+", "-", child.name.lower()).strip("-")
    found = Found(name, os.path.relpath(child, ba_repo), (child / ".git").exists(), model=_looks_like_model(child))
    if not found.git:
        return found
    remotes = (_git(child, "remote") or "").split()
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else None)
    if remote:
        url = _git(child, "remote", "get-url", remote)
        found.remote = USERINFO.sub(r"\1", url) if url else None
        head = _git(child, "symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD")
        if head:
            found.branch = head.removeprefix(f"{remote}/")
    if not found.branch:
        found.branch = _git(child, "branch", "--show-current") or None
        found.branch_is_current = bool(found.branch)
    found.wiki = bool(found.remote and found.remote.rstrip("/").endswith(".wiki.git"))
    return found


def _looks_like_model(child: Path) -> bool:
    """A folder, at most three levels down, holding two JSON Schemas or more."""
    for folder in [child, *[p for p in child.rglob("*") if p.is_dir() and len(p.relative_to(child).parts) <= 3
                            and ".git" not in p.parts and "node_modules" not in p.parts and "target" not in p.parts]]:
        schemas = 0
        for file in folder.glob("*.json"):
            try:
                head = file.read_text(encoding="utf-8", errors="ignore")[:2000]
            except OSError:
                continue
            schemas += bool(SCHEMA_KEY.search(head))
            if schemas >= 2:
                return True
    return False


def _git(folder: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=30,
                                check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _tools() -> dict[str, str]:
    from bridge_kit.preflight import _check_tool

    found = {}
    for tool in TOOLS:
        check = _check_tool(tool, "*")
        if check.version:
            found[tool] = check.version
    return found


def ranges(tools: dict[str, str]) -> dict[str, str]:
    """Each tool at least the version found: java and node by their major version, the rest by major and minor."""
    out = {}
    for tool, version in tools.items():
        parts = version.split(".")
        out[tool] = ">=" + (parts[0] if tool in ("java", "node") else ".".join(parts[:2]))
    return out


def render(result: Scan) -> str:
    repos = {f.name: f.entry() for f in result.found}
    lines = [f"Scanned {result.folder}: {len(result.found)} folder(s)", "",
             "workspace:", "  repos:"]
    block = yaml.safe_dump(repos, sort_keys=False, default_flow_style=False).rstrip("\n").split("\n")
    lines += ["    " + line for line in block] if repos else ["    {}"]
    if result.tools:
        lines += ["", "environment:", "  tools:"] + [f'    {t}: "{r}"' for t, r in ranges(result.tools).items()]
    lines += ["", "Compared with bridge-kit.yaml:"]
    lines += [f"- not declared: {name} (--write adds it, read-only)" for name in result.missing]
    lines += [f"- declared, not found: {name}" for name in result.gone]
    lines += [f"- differs: {d}" for d in result.differs]
    if not (result.missing or result.gone or result.differs):
        lines.append("- the same repos, remotes and branches")
    lines += ([""] + [f"Note: {n}" for n in result.notes]) if result.notes else []
    return "\n".join(lines) + "\n"


def write_missing(config_file: Path, result: Scan) -> list[str]:
    """Adds the repos the scan found and bridge-kit.yaml doesn't declare, at the end of workspace.repos, as text so
    the file's comments stay; returns their names. The entries are checked against the schema's, and the file must
    still read with them; otherwise it's left as it was."""
    from bridge_kit.config import ConfigError, _schema
    from bridge_kit.schema import problems

    names = [f for f in result.found if f.name in result.missing]
    if not names:
        return []
    text = config_file.read_text(encoding="utf-8")
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if re.fullmatch(r"  repos:\s*(#.*)?", line) and
                  any(re.fullmatch(r"workspace:\s*(#.*)?", lines[j]) for j in range(i))), None)
    if start is None:
        raise ConfigError(f"{config_file} has no workspace.repos to add to")
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("    ")
                                or lines[end].lstrip().startswith("#") and lines[end].startswith("   ")):
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    entries = {f.name: f.entry() for f in names}
    schema = _schema("bridge-kit.schema.json")["properties"]["workspace"]["properties"]["repos"]["additionalProperties"]
    found = [f"workspace.repos.{name}{p.removeprefix('value')}" for name, entry in entries.items()
             for p in problems(entry, schema, unknown="isn't a field of a repo")]
    block = yaml.safe_dump(entries, sort_keys=False, default_flow_style=False)
    added = ["    " + line for line in block.rstrip("\n").split("\n")]
    new = "\n".join(lines[:end] + added + lines[end:])
    try:
        repos = ((yaml.safe_load(new) or {}).get("workspace") or {}).get("repos") or {}
    except yaml.YAMLError as e:
        found.append(f"the file wouldn't read as YAML: {str(e).splitlines()[0]}")
    else:
        found += [f"workspace.repos.{name} wouldn't read back as it was written" for name, entry in entries.items()
                  if repos.get(name) != entry]
    if found:
        raise ConfigError(f"{config_file} is left as it was: the repos added wouldn't pass:\n"
                          + "\n".join(f"  {p}" for p in found))
    config_file.write_text(new, encoding="utf-8")
    return [f.name for f in names]


def scan_json(result: Scan) -> str:
    return json.dumps(result.to_dict(), indent=2)
