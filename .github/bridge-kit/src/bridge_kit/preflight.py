"""`bridge-kit preflight`: whether this machine and every declared checkout are as `bridge-kit.yaml` says, before an
agent acts on them. Local mode: every repo is already checked out.

1. The config: `bridge-kit.yaml` and `bridge-kit.local.yaml` pass their schemas and rules. Nothing else is checked
   otherwise.
2. The environment: each tool under `environment.tools` runs and has a version in its range, and each listed file
   exists. The preflight runs through `bridge-kit-run`, so the tools it finds are the environment's.
3. GitLab, when `bridge-kit.yaml` declares it: the token from its source, accepted, and each declared project, group
   and wiki answering at its declared path. An id that names another project or group than declared stops, since a
   read would go to the wrong place; anything else warns (no token, a token refused, GitLab out of reach, a wiki
   that doesn't answer), since only the agents that read GitLab need it.
   MongoDB, when it's declared: through the payload guard (test data confirmed, dev or SIT), the connection, and
   each declared collection answering. Anything wrong warns: only the agents that read payloads need it.
4. Each repo: its path exists; unless `git: false`, it's a git checkout of its own, with the declared remote among its
   remotes, on the declared branch (a read-write repo may be on a work branch), clean (a dirty read-only checkout
   warns or stops, as `rules.workspace.dirty_read_only` says), and how far behind its upstream it is as of the last
   fetch. It never fetches, pulls or clones.

A stop condition makes the command exit 1, and an agent stops when it does.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bridge_kit.config import ConfigError, Config, Repo, config_dir, load_config
from bridge_kit.paths import repo_root

# How each tool says its version; any other tool is asked `<tool> --version`
VERSION_COMMANDS = {"java": ["java", "-version"], "mvn": ["mvn", "-v"], "npm": ["npm", "-v"]}
VERSION = re.compile(r"(\d+(?:\.\d+)*)")
JAVA_VERSION = re.compile(r'version "(\d+(?:\.\d+)*)')


@dataclass
class ToolCheck:
    tool: str
    wanted: str
    version: str | None  # None: it didn't run
    ok: bool
    detail: str = ""


@dataclass
class RepoCheck:
    repo: str
    mode: str
    path: str  # as declared
    branch: str = ""
    commit: str = ""
    status: str = "OK"
    severity: str = "ok"  # ok | warning | stop
    overridden: bool = False


@dataclass
class Preflight:
    config: str
    environment: str = ""
    gitlab: str = ""  # the GitLab line, when one is declared
    mongodb: str = ""  # the MongoDB line, when one is declared
    tools: list[ToolCheck] = field(default_factory=list)
    files: list[tuple[str, bool]] = field(default_factory=list)
    nexus: str = ""
    repos: list[RepoCheck] = field(default_factory=list)
    stops: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.stops

    def to_dict(self) -> dict:
        return {**asdict(self), "ok": self.ok}


def preflight(root: Path | None = None) -> Preflight:
    root = (root or repo_root()).resolve()
    shown = (config_dir(root) / "bridge-kit.yaml").relative_to(root).as_posix()
    try:
        config = load_config(root)
    except ConfigError as e:
        report = Preflight(shown)
        report.stops.append(str(e))
        return report
    report = Preflight(shown + (", with bridge-kit.local.yaml" if config.local_file else ""))
    _check_environment(config, report)
    if config.gitlab is not None:
        _check_gitlab(config, report)
    if config.mongodb is not None:
        _check_mongodb(config, report)
    report.nexus = (f"{config.nexus_url} (bridge-kit.yaml)" if config.nexus_url else
                    "not in bridge-kit.yaml: the spec resolver uses BRIDGE_KIT_NEXUS_URL or a mirror in settings.xml")
    rules = config.rules.get("workspace") or {}
    for repo in config.repos.values():
        report.repos.append(_check_repo(repo, config, rules))
    for check in report.repos:
        if check.severity == "stop":
            report.stops.append(f"{check.repo}: {check.status}")
        elif check.severity == "warning":
            report.warnings.append(f"{check.repo}: {check.status}")
    return report


def _check_environment(config: Config, report: Preflight) -> None:
    env = config.environment
    report.environment = (f'micromamba "{env.name}"' if env.manager == "micromamba" else
                          "none: the tools on the PATH")
    for tool, wanted in env.tools.items():
        check = _check_tool(tool, wanted)
        report.tools.append(check)
        if not check.ok:
            report.stops.append(f"{tool}: {check.detail}")
    for name in env.files:
        exists = Path(name).expanduser().exists()
        report.files.append((name, exists))
        if not exists:
            report.stops.append(f"{name} doesn't exist: the environment needs it")


def _check_gitlab(config: Config, report: Preflight) -> None:
    from bridge_kit.auth import TokenError
    from bridge_kit.gitlab import GitLab, GitLabError, status

    gitlab = config.gitlab
    try:
        lines, problems, mismatched = status(GitLab(gitlab))
    except (TokenError, GitLabError) as e:
        report.gitlab = f"{gitlab.url}: not checked: {e}"
        report.warnings.append(f"GitLab: {e}; the gitlab commands and tools won't work until it's fixed")
        return
    wikis = sum(p.wiki for p in gitlab.projects.values()) + sum(g.wiki for g in gitlab.groups.values())
    who = lines[0].removeprefix("Token: ").split(" (", 1)[0]
    report.gitlab = (f"{who} on {gitlab.url}: {len(gitlab.projects)} project(s), {len(gitlab.groups)} group(s), "
                     f"{wikis} wiki(s): " + ("OK" if not problems else f"{len(problems)} problem(s)"))
    for problem in problems:
        (report.stops if problem in mismatched else report.warnings).append(f"GitLab: {problem}")


def _check_mongodb(config: Config, report: Preflight) -> None:
    from bridge_kit.auth import TokenError
    from bridge_kit.payloads import PayloadError, Payloads, read_status

    try:
        _, data = read_status(Payloads(config))
    except (TokenError, PayloadError) as e:
        report.mongodb = f"not checked: {e}"
        report.warnings.append(f"MongoDB: {e}; the payload commands and tools won't work until it's fixed")
        return
    answering = sum(": answers (" in line for line in data["lines"])
    report.mongodb = (f"{data['environment']}: {len(config.mongodb.services)} service(s), {answering} collection(s) "
                      "answer: " + ("OK" if data["ok"] else f"{len(data['problems'])} problem(s)"))
    report.warnings += [f"MongoDB: {problem}" for problem in data["problems"]]


def _check_tool(tool: str, wanted: str) -> ToolCheck:
    command = VERSION_COMMANDS.get(tool, [tool, "--version"])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return ToolCheck(tool, wanted, None, False, f"doesn't run in the environment ({type(e).__name__})")
    output = result.stdout + result.stderr
    found = (JAVA_VERSION if tool == "java" else VERSION).search(output)
    if result.returncode != 0 or not found:
        return ToolCheck(tool, wanted, None, False, f"`{' '.join(command)}` gives no version")
    version = found.group(1)
    if not in_range(version, wanted):
        return ToolCheck(tool, wanted, version, False, f"{version} is there, and bridge-kit.yaml needs {wanted}")
    return ToolCheck(tool, wanted, version, True)


def in_range(version: str, wanted: str) -> bool:
    """Whether a version meets a range such as `>=3.9`, `>=21, <26` or `*`."""
    if wanted.strip() == "*":
        return True
    have = _numbers(version)
    for part in wanted.split(","):
        match = re.fullmatch(r"\s*(>=|<=|>|<|==)?\s*(\d+(?:\.\d+)*)\s*", part)
        if not match:
            return False
        operator, bound = match.group(1) or "==", _numbers(match.group(2))
        width = max(len(have), len(bound))
        a, b = have + (0,) * (width - len(have)), bound + (0,) * (width - len(bound))
        if not {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b, "==": a == b}[operator]:
            return False
    return True


def _numbers(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in version.split("."))


def _check_repo(repo: Repo, config: Config, rules: dict) -> RepoCheck:
    check = RepoCheck(repo.name, repo.mode, repo.declared_path, overridden=repo.overridden)

    def problem(severity: str, status: str) -> RepoCheck:
        check.severity, check.status = severity, status
        return check

    if not repo.path.is_dir():
        if repo.mode == "clone":
            return problem("stop", f"not at {repo.declared_path}, and the kit can't clone yet: check it out there")
        return problem("stop", f"not at {repo.declared_path}: check it out there, or correct the path")
    if not repo.git:
        check.status = "OK, a plain folder (git: false)"
        return check
    top = _git(repo.path, "rev-parse", "--show-toplevel")
    if top is None or Path(top).resolve() != repo.path.resolve():
        return problem("stop", f"{repo.declared_path} isn't a git checkout of its own")
    check.branch = _git(repo.path, "rev-parse", "--abbrev-ref", "HEAD") or ""
    check.commit = _git(repo.path, "rev-parse", "--short", "HEAD") or ""
    remotes = (_git(repo.path, "remote", "-v") or "").split()
    if repo.remote and _url(repo.remote) not in {_url(r) for r in remotes}:
        return problem("stop", f"its remotes aren't {repo.remote}: it's another repo at the declared path")
    on_work_branch = repo.access == "read-write" and check.branch.startswith(config.work_branch_prefix)
    if repo.branch and check.branch != repo.branch and not on_work_branch:
        allowed = repo.branch + (f" or a {config.work_branch_prefix} branch" if repo.access == "read-write" else "")
        return problem("stop", f"on {check.branch}, and bridge-kit.yaml says {allowed}")
    changed = [line for line in (_git(repo.path, "status", "--porcelain") or "").splitlines() if line.strip()]
    upstream, behind = _behind(repo.path)
    lag = (f"{behind} commit(s) behind {upstream} as of the last fetch: pull only with the BA's OK" if behind else
           f"up to date with {upstream} as of the last fetch" if upstream else "no upstream to compare with")
    if changed and repo.access == "read-only":
        severity = "stop" if rules.get("dirty_read_only") == "stop" else "warning"
        return problem(severity, f"read-only, but {len(changed)} file(s) changed in it; {lag}")
    check.status = "OK" + (f", {len(changed)} changed file(s)" if changed else "") + f"; {lag}"
    if behind:
        check.severity = "warning"
    return check


def _behind(path: Path) -> tuple[str | None, int]:
    """The checkout's upstream, and how many of its commits the checkout doesn't have, from what was last fetched."""
    upstream = _git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        return None, 0
    count = _git(path, "rev-list", "--count", "HEAD..@{u}") or "0"
    return upstream, int(count) if count.isdigit() else 0


def _git(path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=60,
                                check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _url(remote: str) -> str:
    return remote.strip().rstrip("/").removesuffix(".git")


def format_preflight(report: Preflight) -> str:
    lines = [f"Config:      {report.config}: {'OK' if report.environment else 'STOP'}"]
    if not report.environment:  # the config stopped it
        lines += ["", *report.stops, "", "Preflight: STOP: agents stop here"]
        return "\n".join(lines)
    tools = ", ".join(f"{t.tool} {t.version or 'missing'}" for t in report.tools) or "none listed"
    tools_ok = all(t.ok for t in report.tools)
    lines.append(f"Environment: {report.environment}: {tools}: {'OK' if tools_ok else 'STOP'}")
    if report.files:
        lines.append("Files:       " + ", ".join(f"{name} {'OK' if ok else 'missing'}" for name, ok in report.files))
    if report.gitlab:
        lines.append(f"GitLab:      {report.gitlab}")
    if report.mongodb:
        lines.append(f"MongoDB:     {report.mongodb}")
    lines += [f"Nexus:       {report.nexus}", "",
              "| Repo | Mode | Path | Branch | Commit | Status |", "|---|---|---|---|---|---|"]
    for r in report.repos:
        mode = r.mode + (" (overridden)" if r.overridden else "")
        lines.append(f"| {r.repo} | {mode} | {r.path} | {r.branch or '-'} | {r.commit or '-'} | "
                     f"{'STOP: ' if r.severity == 'stop' else 'WARNING: ' if r.severity == 'warning' else ''}"
                     f"{r.status} |")
    if report.stops:
        lines += ["", "Stops:"] + [f"  - {s}" for s in report.stops]
    if report.warnings:
        lines += ["", "Warnings:"] + [f"  - {w}" for w in report.warnings]
    lines += ["", "Preflight: " + (f"OK, {len(report.warnings)} warning(s)" if report.ok else
                                   f"STOP, {len(report.stops)} stop(s), {len(report.warnings)} warning(s): agents "
                                   f"stop here")]
    return "\n".join(lines)
