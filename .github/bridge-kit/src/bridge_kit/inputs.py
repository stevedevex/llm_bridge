"""`bridge-kit inputs add`: what a BA brings, as a work item's next input. An input is a Markdown file in
`work/<id>/inputs/`, numbered in the order it came, with a header naming its kind, its source and link, its version,
when it was read, its title as the summary, and where its raw form is: `.work/sources/<id>/`, which git ignores.

Inputs never change once added. Added again, a source whose version is the one already there is reported as already
there; a changed one becomes a new input, beside the earlier.

Sources so far: `gitlab:<ref>`, a story with its comments and links (its version, its last update);
`wiki:<slug>`, a wiki page (its version, its content's hash); and a file, a document `bridge_kit.documents` reads or an
image an agent describes (its version, the file's hash; its raw form, the file itself, copied). A file added with
other options (`--rows all`, say) is a new input too. An email's attachments that bridge-kit reads become inputs of
their own, each naming the email's (`attached_to`).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from bridge_kit.markdown import FormatError, read_markdown

if TYPE_CHECKING:
    from bridge_kit.documents import Document, Options

WORK_ITEM = re.compile(r"[A-Z][A-Z0-9]{1,9}-\d+")


DESCRIBED = ("image", "pdf")  # the kinds an agent or the BA may describe: an image, a PDF's pages without text


class InputError(Exception):
    """The input can't be added: the work item's id is wrong, or the source isn't one bridge-kit reads."""


@dataclass
class Added:
    file: str  # the input, by path in the BA repo
    status: str  # added | unchanged | changed (added beside an earlier one)
    summary: str
    earlier: str | None = None  # the input with the same source, when there is one
    warnings: list[str] = field(default_factory=list)  # a document's
    attached: list[Added] = field(default_factory=list)  # an email's attachments, added as inputs of their own
    not_added: list[str] = field(default_factory=list)  # and those that weren't, each with why

    def to_dict(self) -> dict:
        return asdict(self)


def work_folder(ba_repo: Path, work_item: str, create: bool = False) -> Path:
    """The work item's folder, with or without its slug; made as `work/<id>/` when there's none and `create`."""
    if not WORK_ITEM.fullmatch(work_item):
        raise InputError(f"{work_item} isn't a work item's id: a project's key and a number, e.g. REQ-101")
    found = sorted(p for p in (ba_repo / "work").glob(f"{work_item}*")
                   if p.is_dir() and (p.name == work_item or p.name.startswith(f"{work_item}-")))
    if found:
        return found[0]
    if not create:
        raise InputError(f"No work folder for {work_item} in {ba_repo / 'work'}")
    return ba_repo / "work" / work_item


def add_input(ba_repo: Path, work_item: str, kind: str, source: str, name: str, version: str, summary: str,
              body: str, raw: object, url: str = "", raw_suffix: str = ".json", extra: dict | None = None,
              images: dict[str, bytes] | None = None, attachments: dict[str, bytes] | None = None) -> Added:
    """Writes the input, or finds it already there. `name` is the file's name after its number; `raw` what the
    source gave, kept in `.work/sources/`: bytes as they are, anything else as JSON. `extra` adds to the header,
    after the summary; its `options`, when there are any, must match for an input to be already there. `images` and
    `attachments`, a document's, each go in a folder beside the raw form, which the header names."""
    extra = {k: v for k, v in (extra or {}).items() if v is not None}
    folder = work_folder(ba_repo, work_item, create=True) / "inputs"
    folder.mkdir(parents=True, exist_ok=True)
    earlier = [(path, header) for path, header in _inputs(folder)
               if header.get("kind") == kind and str(header.get("source")) == source]
    if earlier:
        last_path, last = earlier[-1]
        if str(last.get("version")) == version and last.get("options") == extra.get("options"):
            return Added(_relative(last_path, ba_repo), "unchanged", str(last.get("summary") or summary))
    number = max([int(m.group(1)) for p in folder.glob("*.md") if (m := re.match(r"(\d+)-", p.name))] or [0]) + 1
    path = folder / f"{number:02d}-{name}.md"
    raw_path = ba_repo / ".work" / "sources" / work_item / f"{number:02d}-{name}{raw_suffix}"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(raw, bytes):
        raw_path.write_bytes(raw)
    else:
        raw_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    header = {"kind": kind, "source": source, "url": url or None, "version": version,
              "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": summary, **extra,
              "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "raw": _relative(raw_path, ba_repo)}
    for key, files in (("images", images), ("attachments", attachments)):
        if files:
            kept = raw_path.parent / f"{number:02d}-{name}-{key}"
            kept.mkdir(exist_ok=True)
            for file, data in files.items():
                (kept / file).write_bytes(data)
            header[key] = _relative(kept, ba_repo)
    front = yaml.safe_dump({k: v for k, v in header.items() if v is not None}, sort_keys=False, allow_unicode=True,
                           width=1000)
    path.write_text(f"---\n{front}---\n\n{body.rstrip()}\n", encoding="utf-8")
    status = "changed" if earlier else "added"
    return Added(_relative(path, ba_repo), status, summary, _relative(earlier[-1][0], ba_repo) if earlier else None)


def add_file(ba_repo: Path, work_item: str, path: Path, options: Options, description: str | None = None,
             by: str | None = None, attached_to: str | None = None, depth: int = 0) -> tuple[Added, Document]:
    """A file as the work item's next input: a document read by `bridge_kit.documents`, or an image with what an agent
    or the BA says it shows. A PDF may take a description too, for its pages without text. An email's attachments
    that bridge-kit reads are added after it, each as an input of its own, but images, which need a description first,
    and anything attached three emails deep."""
    from bridge_kit.documents import IMAGE_HELP, Document, DocumentError, Options, kind_of, personal, read_document

    work_folder(ba_repo, work_item, create=True)  # its id checked before anything is read
    kind = kind_of(path)
    if description is not None:
        if kind not in DESCRIBED:
            raise InputError(f"{path.name} doesn't take --description: only an image or a PDF does, since bridge-kit "
                             "reads the rest itself")
        if not description.strip():
            raise InputError("The description is empty: write what the image shows, then pass it")
        if not by:
            raise InputError("--description needs --by: who wrote it, the agent's name or the BA's")
    if kind == "image":
        if description is None:
            raise DocumentError(IMAGE_HELP.format(name=path.name))
        document = Document("image", path.stem, f"# {path.stem}\n\n`{path.name}`, an image, as {by} described "
                                                f"it.\n\n{description.strip()}\n")
        if found := personal.warning("The description", [description]):
            document.warnings.append(found)
    else:
        document = read_document(path, options)
        if description is not None:
            document.markdown = (f"{document.markdown.rstrip()}\n\n## Read from its pages' images, by {by}\n\n"
                                 f"{description.strip()}\n")
    data = path.read_bytes()
    extra = {"options": options.to_header(), "described_by": by if description is not None else None,
             "attached_to": attached_to, "warnings": document.warnings or None}
    added = add_input(ba_repo, work_item, document.kind, f"file:{path.name}", slug(path.stem), file_hash(data),
                      document.title, document.markdown, data, raw_suffix=path.suffix.lower(), extra=extra,
                      images=document.images, attachments=document.attachments)
    added.warnings = document.warnings
    if document.attachments and added.status != "unchanged":
        kept = ba_repo / ".work" / "sources" / work_item / f"{Path(added.file).stem}-attachments"
        for name in document.attachments:
            file = kept / name
            try:
                if depth >= 2:
                    raise DocumentError(f"{name} is attached three emails deep: add it yourself, from "
                                        f"{_relative(file, ba_repo)}")
                if kind_of(file) == "image":
                    raise DocumentError(f"{name} is an image: read it, then add it with --description and --by, "
                                        f"from {_relative(file, ba_repo)}")
                attached, _ = add_file(ba_repo, work_item, file, Options(), attached_to=added.file, depth=depth + 1)
                added.attached.append(attached)
            except DocumentError as e:
                added.not_added.append(str(e))
    return added, document


def _inputs(folder: Path) -> list[tuple[Path, dict]]:
    found = []
    for path in sorted(folder.glob("*.md")):
        try:
            found.append((path, read_markdown(path.read_text(encoding="utf-8")).front_matter))
        except FormatError:
            continue
    return found


def _relative(path: Path, ba_repo: Path) -> str:
    return path.resolve().relative_to(ba_repo.resolve()).as_posix()


def content_hash(text: str) -> str:
    return file_hash(text.encode("utf-8"))


def file_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "input"
