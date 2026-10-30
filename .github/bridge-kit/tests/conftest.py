"""Shared fixtures. `LANDSCAPE` is the tests' own BA repo files, in BRIDGE's general names: its `bridge-kit.yaml`, its
component catalog and its glossary. Beside it, where its `bridge-kit.yaml` looks for them, the shared model
(`SHARED_MODEL`: `CustomerRecord` and `CustomerSummary`, at 3.0.0) and the collecting service (`SERVICE`). `SPECS`
holds the upstreams' specs, which `maven_repo` packs into jars."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from bridge_kit.internal_model import InternalModel

KIT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LANDSCAPE = FIXTURES / "landscape"
SHARED_MODEL = FIXTURES / "shared-model"
SCHEMAS = SHARED_MODEL / "schemas"
SERVICE = FIXTURES / "service-a-java"
SPECS = FIXTURES / "specs"
UPSTREAM_1 = "com.example.upstream1:customer-api-spec:4.2.0"
UPSTREAM_2 = "com.example.upstream2:customer-directory-soap-spec:1.3.0"


def edit(path: Path, old: str, new: str) -> None:
    """Replaces text that must occur exactly once."""
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} times in {path.name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


@pytest.fixture
def model() -> InternalModel:
    return InternalModel(SCHEMAS)


@pytest.fixture
def model_layout(tmp_path: Path) -> Path:
    """A BA repo made of the landscape (its bridge-kit.yaml where the kit reads it, its catalog and glossary), with
    copies of the shared model and the collecting service beside it, for changes to the model. Returns the BA repo."""
    ba_repo = tmp_path / "ba-repo"
    (ba_repo / ".github" / "bridge-kit").mkdir(parents=True)
    shutil.copyfile(LANDSCAPE / "bridge-kit.yaml", ba_repo / ".github" / "bridge-kit" / "bridge-kit.yaml")
    shutil.copytree(LANDSCAPE / "architecture", ba_repo / "architecture")
    shutil.copytree(SHARED_MODEL, tmp_path / "shared-model")
    shutil.copytree(SERVICE, tmp_path / "service-a-java")
    return ba_repo


@pytest.fixture(scope="session")
def maven_repo(tmp_path_factory) -> Path:
    """A Maven repository folder with each upstream's spec jar, as its team publishes it: SPECS/<group>/<artifact>/
    <version>/ zipped into <group path>/<artifact>/<version>/<artifact>-<version>.jar, with a pom beside it."""
    repo = tmp_path_factory.mktemp("maven-repo")
    for folder in sorted(p for p in SPECS.glob("*/*/*") if p.is_dir()):
        version, artifact, group = folder.name, folder.parent.name, folder.parent.parent.name
        target = repo.joinpath(*group.split("."), artifact, version)
        target.mkdir(parents=True)
        with zipfile.ZipFile(target / f"{artifact}-{version}.jar", "w") as jar:
            for file in sorted(f for f in folder.rglob("*") if f.is_file()):
                jar.write(file, file.relative_to(folder).as_posix())
        (target / f"{artifact}-{version}.pom").write_text(
            f'<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>{group}'
            f"</groupId><artifactId>{artifact}</artifactId><version>{version}</version></project>\n", encoding="utf-8")
    return repo
