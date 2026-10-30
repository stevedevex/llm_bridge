"""bin/bridge-kit-run and bin/bridge-kit: a command runs inside the environment bridge-kit.yaml declares, or as it is
with `manager: none`, and an environment that can't start says why in one line. A stand-in micromamba records what it's
asked and runs the command with the PATH the environment would give."""

import os
import subprocess
from pathlib import Path

import pytest
from conftest import KIT

BIN = KIT / "bin"
SYSTEM_PATH = "/usr/bin:/bin"  # sh, awk and grep, without micromamba or uv
FAKE_MICROMAMBA = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
if [ "$1 $2" = "env list" ]; then
    printf '  Name         Active  Path\\n  base                 /opt/mamba\\n  team-tools           /opt/mamba/envs/team-tools\\n'
    exit 0
fi
if [ "$1" = "run" ] && [ "$2" = "-n" ]; then
    shift 3
    PATH="$FAKE_ENV_PATH" exec "$@"
fi
exit 9
"""


def environment(manager: str, name: str | None = None) -> str:
    return f"environment:\n  manager: {manager}   # where the tools come from\n" + \
        (f"  name: \"{name}\"\n" if name else "") + "  tools:\n    git: \"*\"\n"


@pytest.fixture
def layout(tmp_path):
    """A BA repo whose bridge-kit.yaml a test writes, a stand-in micromamba, and the log it writes."""
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "micromamba").write_text(FAKE_MICROMAMBA, encoding="utf-8")
    (tools / "micromamba").chmod(0o755)
    return {"repo": repo, "tools": tools, "log": tmp_path / "micromamba.log"}


def write(layout, text: str, local: str | None = None) -> None:
    kit = layout["repo"] / ".github" / "bridge-kit"
    (kit / "bridge-kit.yaml").write_text("bridge-kit:\n  version: 0.1.0\n" + text + "workspace:\n  repos: {}\n",
                                     encoding="utf-8")
    if local is not None:
        (kit / "bridge-kit.local.yaml").write_text(local, encoding="utf-8")


def run(layout, *command: str, micromamba: bool = True, env_path: str = SYSTEM_PATH,
        launcher: str = "bridge-kit-run") -> subprocess.CompletedProcess:
    path = (f"{layout['tools']}:" if micromamba else "") + SYSTEM_PATH
    env = {"PATH": path, "HOME": os.environ.get("HOME", "/tmp"), "BRIDGE_KIT_REPO_ROOT": str(layout["repo"]),
           "FAKE_LOG": str(layout["log"]), "FAKE_ENV_PATH": env_path}
    return subprocess.run([str(BIN / launcher), *command], env=env, capture_output=True, text=True, check=False)


def asked(layout) -> list[str]:
    return layout["log"].read_text(encoding="utf-8").splitlines() if layout["log"].exists() else []


def test_without_a_manager_the_command_runs_as_it_is(layout):
    write(layout, environment("none"))

    result = run(layout, "sh", "-c", 'echo "ran: $*"; exit 4', "x", "one", "two")

    assert (result.returncode, result.stdout) == (4, "ran: one two\n")
    assert asked(layout) == []


def test_with_micromamba_the_command_runs_in_the_declared_environment(layout):
    write(layout, environment("micromamba", "team-tools"))

    result = run(layout, "sh", "-c", 'echo "in env: $PATH"', "x")

    assert (result.returncode, result.stdout) == (0, f"in env: {SYSTEM_PATH}\n")
    assert asked(layout) == ["env list", "run -n team-tools sh -c echo \"in env: $PATH\" x"]


def test_bridge_kit_local_yaml_names_another_environment(layout):
    write(layout, environment("micromamba", "base"), local="environment:\n  name: team-tools\n")

    assert run(layout, "true").returncode == 0
    assert asked(layout)[-1] == "run -n team-tools true"


def test_overrides_turned_off_with_a_local_file_stop(layout):
    write(layout, environment("micromamba", "team-tools") + "rules:\n  workspace:\n    allow_local_overrides: false\n",
          local="environment:\n  name: base\n")

    result = run(layout, "true")

    assert result.returncode == 1
    assert result.stderr == ("bridge-kit-run: bridge-kit.yaml turns overrides off, but there's a "
                             "bridge-kit.local.yaml: remove it\n")


@pytest.mark.parametrize("config, micromamba, message", [
    (environment("micromamba", "team-tools"), False,
     "micromamba isn't on the PATH, and bridge-kit.yaml says the tools come from its environment team-tools"),
    (environment("micromamba", "other-tools"), True,
     "there's no micromamba environment named other-tools: the environment's setup has to provide it"),
    (environment("micromamba", "team tools"), True, "environment.name must be a plain word, not 'team tools'"),
    (environment("micromamba"), True, "environment.name must be a plain word, not ''"),
    (environment("conda", "team-tools"), True, "environment.manager is conda; it must be micromamba or none"),
    ("environment: {manager: none}\n", True, "can't read environment.manager from"),
])
def test_an_environment_that_can_t_start_says_why_in_one_line(layout, config, micromamba, message):
    write(layout, config)

    result = run(layout, "true", micromamba=micromamba)

    assert result.returncode == 1
    assert result.stderr.startswith(f"bridge-kit-run: {message}") and result.stderr.count("\n") == 1, result.stderr


def test_no_bridge_kit_yaml_and_no_command(layout):
    assert run(layout, "true").stderr == (
        f"bridge-kit-run: no bridge-kit.yaml at {layout['repo']}/.github/bridge-kit/bridge-kit.yaml: copy "
        "bridge-kit.example.yaml to it and set its environment first\n")
    write(layout, environment("none"))
    assert run(layout).returncode == 2


def test_bridge_kit_runs_through_bridge_kit_run_with_uv_from_the_environment(layout):
    uv = subprocess.run(["sh", "-c", "command -v uv"], capture_output=True, text=True, check=True).stdout.strip()
    write(layout, environment("micromamba", "team-tools"))

    result = run(layout, "validate", "--help", launcher="bridge-kit", env_path=f"{Path(uv).parent}:{SYSTEM_PATH}")

    assert result.returncode == 0, result.stderr
    assert "usage: bridge-kit validate" in result.stdout
    assert "\nrun -n team-tools sh -c" in "\n".join(asked(layout))  # its script runs over several lines


def test_bridge_kit_says_when_the_environment_has_no_uv(layout):
    write(layout, environment("micromamba", "team-tools"))

    result = run(layout, "validate", "--help", launcher="bridge-kit")

    assert (result.returncode, result.stderr) == (1, "bridge-kit: uv isn't in the environment bridge-kit.yaml "
                                                     "declares\n")
