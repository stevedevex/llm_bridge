"""What a good Story Writer leaves for each story case: one story per expected component, in the template's shape, with
the header the case expects, every fact it looks for, and the open questions it expects asked.

    reference_stories(case_folder, out, repo)   writes them under out/, in the case's stories folder
"""

from __future__ import annotations

from pathlib import Path

import yaml

from bridge_kit.stories import load_catalog


def reference_stories(case: Path, out: Path, repo: Path) -> list[Path]:
    expected = yaml.safe_load((case / "expected.yaml").read_text(encoding="utf-8"))["stories"]
    catalog = load_catalog(repo)
    folder = out / expected["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    work_item = expected["work_item"]
    entries = expected["expected"]
    refs = {e["component"]: f"S{catalog.order(e['component'])}" for e in entries}
    blocks = {e["component"]: [c["component"] for c in entries if e["component"] in c["blocked_by"]] for e in entries}
    questions = {q["component"]: q["words"] for q in expected.get("open_questions") or []}
    written = []
    for entry in entries:
        component = entry["component"]
        order = catalog.order(component)
        header = {
            "template": "story@1", "id": None, "parent": work_item, "component": component,
            "title": f"The {component} part of {work_item}", "status": "draft", "order": order,
            "blocked_by": [refs[b] for b in entry["blocked_by"]],
            "contracts": [{"contract": c, "change": change} for c, change in entry["contracts"].items()],
            "implements": entry["implements"], "labels": catalog.labels(component),
        }
        facts = "; ".join(str(words[0]) for words in entry.get("facts") or []) or "what the requirement asks"
        rows = "\n".join(f"| `{c}` | {change} | as the impact analysis says | |"
                         for c, change in entry["contracts"].items())
        table = f"| Contract | Change | Fields | Notes |\n|---|---|---|---|\n{rows}" if rows else "None."
        asked = f"- BA: what about {questions[component][0]}?" if component in questions else "None."

        def listed(components: list[str]) -> str:
            return ", ".join(f"{refs[c]} ({c})" for c in components) or "none"

        body = f"""## Story

As a relationship manager, I want {component} to do its part of {work_item}, so that the requirement is met.

## Context

Part of {work_item}: {facts}.

## Scope

**In scope:**

- {facts}

**Out of scope:**

- Anything the requirement doesn't ask for.

## Contracts and data

{table}

## Acceptance criteria

### AC-1: The requirement holds

```gherkin
Given the requirement {work_item}
When {component} makes its change
Then {facts}
```

## Component details: {component}

{facts}

## Dependencies

- Blocked by: {listed(entry["blocked_by"])}
- Blocks: {listed(blocks[component])}

## Open questions

{asked}
"""
        file = folder / f"{component}-{order:02d}-{work_item.lower()}.md"
        file.write_text(f"---\n{yaml.safe_dump(header, sort_keys=False)}---\n\n{body}", encoding="utf-8")
        written.append(file)
    return written
