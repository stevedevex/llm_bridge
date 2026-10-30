"""What a correct Model Designer leaves for a few changes to the fixture's shared model: the changed schemas, example
and version, and the merge request description. Used to check `validate model` on right and wrong changes.

    solve(change, ba_repo, base)   changes the model ba_repo's bridge-kit.yaml names, and writes the description
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from bridge_kit.config import load_config
from bridge_kit.model_change import diff_models

EXAMPLE = ("examples", "customer-record.example.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def add_property(schema: dict, name: str, prop: dict, after: str, required: bool = False) -> None:
    """Adds a property after another one, keeping the order of the rest."""
    props = {}
    for key, value in schema["properties"].items():
        props[key] = value
        if key == after:
            props[name] = prop
    schema["properties"] = props
    if required:
        schema["required"].append(name)


def set_version(model: Path, version: str) -> None:
    for file in (model / "pom.xml", model / "python" / "pyproject.toml"):
        text = file.read_text(encoding="utf-8")
        text = re.sub(r"<version>3\.0\.0</version>", f"<version>{version}</version>", text, count=1)
        text = re.sub(r'^version = "3\.0\.0"', f'version = "{version}"', text, count=1, flags=re.M)
        file.write_text(text, encoding="utf-8")


def write_description(ba_repo: Path, base: Path, work_item: str, title: str, summary: str,
                      reused: list[tuple[str, str]] = (), questions: list[str] = ()) -> None:
    """The description, filled from the diff as the skill says: every change, every consumer a breaking change hits."""
    config = load_config(ba_repo)
    diff = diff_models(base, config.model.path, config)
    changes = "\n".join(f"| `{c.path}` | {c.detail} | {c.bump} |" for c in diff.top_changes)
    rows = "\n".join(f"| {asked} | `{path}` |" for asked, path in reused)
    affected = diff.affected_consumers()
    if affected:
        consumers = "| Consumer | How it's affected | Where |\n|---|---|---|\n" + "\n".join(
            f"| {component} | Uses the changed field | {', '.join(Path(f).name for f in files) or 'not checked out'} |"
            for component, files in affected.items())
    else:
        consumers = "None broken: the change is additive."
    risks = "".join(f"\n\nRisk: {c.risk}" for c in diff.changes if c.risk)
    text = f"""---
work_item: {work_item}
repo: shared-model
branch: feature/{work_item}
base_version: {diff.base_version}
version: {diff.version}
change: {diff.change_kind}
---

# {title}

## Summary

{summary}

## Changes

| Path | Change | Kind |
|---|---|---|
{changes}

## Reused

| Asked for | Path |
|---|---|
{rows}

## Consumers affected

{consumers}{risks}

## Open questions

{chr(10).join(f'- {q}' for q in questions) or 'None.'}
"""
    folder = ba_repo / "work" / work_item
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model-change.md").write_text(text, encoding="utf-8")


def contact_channel(model: Path) -> dict:
    schema = _load(model / "schemas" / "contact-preference-slot.json")
    add_property(schema, "channel", {"type": "string", "enum": ["EMAIL", "PHONE", "SMS"],
                                     "description": "The customer's preferred contact channel: email, phone or text "
                                                    "message."}, "email")
    _save(model / "schemas" / "contact-preference-slot.json", schema)
    example = _load(model.joinpath(*EXAMPLE))
    example["contactPreference"]["channel"] = "SMS"
    _save(model.joinpath(*EXAMPLE), example)
    set_version(model, "3.1.0")
    return {"work_item": "REQ-101", "title": "Add the customer's preferred contact channel",
            "summary": "Adds the channel the customer asked to be contacted by to the customer API's slot, as our own "
                       "codes. Additive."}


def overdraft_limit(model: Path) -> dict:
    schema = _load(model / "schemas" / "account.json")
    add_property(schema, "overdraftLimit", {"$ref": "amount.json",
                                            "description": "The overdraft limit agreed for the account: the most the "
                                                           "customer may overdraw."}, "currency")
    _save(model / "schemas" / "account.json", schema)
    example = _load(model.joinpath(*EXAMPLE))
    example["accounts"][0]["overdraftLimit"] = {"value": 500.00, "currency": "GBP"}
    _save(model.joinpath(*EXAMPLE), example)
    set_version(model, "3.1.0")
    return {"work_item": "REQ-111", "title": "Add the agreed overdraft limit",
            "summary": "Adds each account's agreed overdraft limit, as an amount. Additive."}


def consents(model: Path) -> dict:
    _save(model / "schemas" / "consent.json", {
        "$schema": "http://json-schema.org/draft-07/schema#", "title": "Consent",
        "description": "One thing the customer agreed to, or refused.", "type": "object", "additionalProperties": False,
        "required": ["purpose", "given"],
        "properties": {
            "purpose": {"type": "string", "enum": ["MARKETING", "PROFILING", "THIRD_PARTIES"],
                        "description": "What the consent is for."},
            "given": {"type": "boolean", "description": "Whether the customer agreed."},
            "recordedDate": {"type": "string", "format": "date", "description": "Date the answer was recorded."}}})
    _save(model / "schemas" / "consent-slot.json", {
        "$schema": "http://json-schema.org/draft-07/schema#", "title": "ConsentSlot", "type": "object",
        "additionalProperties": False, "description": "The consent register's slot on the record.",
        "required": ["consents"],
        "properties": {"consents": {"type": "array", "items": {"$ref": "consent.json"},
                                    "description": "The customer's answers, one per purpose asked about."}}})
    schema = _load(model / "schemas" / "customer-record.json")
    add_property(schema, "consents", {"$ref": "consent-slot.json",
                                      "description": "What the consent register holds for the customer."},
                 "contactPreference", required=True)
    _save(model / "schemas" / "customer-record.json", schema)
    example = _load(model.joinpath(*EXAMPLE))
    example["consents"] = {"consents": [{"purpose": "MARKETING", "given": False, "recordedDate": "2025-09-30"}]}
    _save(model.joinpath(*EXAMPLE), example)
    set_version(model, "4.0.0")
    return {"work_item": "REQ-112", "title": "Add the customer's consents",
            "summary": "Adds a slot for the consent register, with the customer's answers. Breaking: a new slot."}


def contact_time_codes(model: Path) -> dict:
    schema = _load(model / "schemas" / "contact-preference-slot.json")
    schema["properties"]["contactTime"] = {
        "type": "string", "enum": ["MORNING", "AFTERNOON", "EVENING", "ANY_TIME"],
        "description": "When the customer prefers to be contacted: in the morning, the afternoon or the evening, or "
                       "at any time."}
    _save(model / "schemas" / "contact-preference-slot.json", schema)
    example = model.joinpath(*EXAMPLE)
    example.write_text(example.read_text(encoding="utf-8").replace('"weekday mornings"', '"MORNING"'), encoding="utf-8")
    set_version(model, "4.0.0")
    return {"work_item": "REQ-113", "title": "Make the contact time our own codes",
            "summary": "The contact time becomes a coded value. Breaking: its type changes.",
            "questions": ["Developers: the customer API's mapping needs a lookup from what the customer said."]}


def display_name_exists(model: Path) -> dict:
    return {"work_item": "REQ-114", "title": "The name the customer goes by: already in the model",
            "summary": "The model already has it as displayName. Nothing changes.",
            "reused": [("the name the customer goes by", "CustomerRecord.displayName")]}


SOLUTIONS = {
    "contact-channel": contact_channel,
    "overdraft-limit": overdraft_limit,
    "consents": consents,
    "contact-time-codes": contact_time_codes,
    "display-name-exists": display_name_exists,
}


def solve(change: str, ba_repo: Path, base: Path) -> str:
    """Applies the change's solution to the model ba_repo's bridge-kit.yaml names; returns the work item."""
    model = load_config(ba_repo).model.path
    answer = SOLUTIONS[change](model)
    write_description(ba_repo, base, answer["work_item"], answer["title"], answer["summary"],
                      answer.get("reused", []), answer.get("questions", []))
    return answer["work_item"]
