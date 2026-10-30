"""The JSON Schema (draft-07) keywords bridge-kit's own schemas use, and no more, so the kit needs no schema library:
`type`, `const`, `enum`, `pattern`, `minLength`, `maxLength`, `minimum`, `items`, `minItems`, `uniqueItems`,
`required`, `properties` and `additionalProperties` (false, or the schema every other property must meet)."""

from __future__ import annotations

import re


def problems(value, schema: dict, unknown: str = "isn't allowed") -> list[str]:
    """What's wrong with `value` against `schema`, each with where it is (`workspace.repos.x.mode`). A property the
    schema doesn't allow is reported as "<where>: <name> <unknown>"."""
    found: list[str] = []

    def check(value, rule: dict, where: str) -> None:
        if "const" in rule and value != rule["const"]:
            found.append(f"{where} must be {rule['const']}")
        if "enum" in rule and value not in rule["enum"]:
            found.append(f"{where} must be one of {', '.join(map(str, rule['enum']))}")
        kinds = rule.get("type")
        if kinds:
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if not any(_is(value, kind) for kind in kinds):
                found.append(f"{where} must be {' or '.join(kinds)}")
                return
        if isinstance(value, str):
            if len(value) < rule.get("minLength", 0) or len(value) > rule.get("maxLength", len(value)):
                found.append(f"{where} has the wrong length")
            if "pattern" in rule and not re.search(rule["pattern"], value):
                found.append(f"{where} doesn't match {rule['pattern']}")
        if isinstance(value, int) and not isinstance(value, bool) and value < rule.get("minimum", value):
            found.append(f"{where} must be at least {rule['minimum']}")
        if isinstance(value, list):
            if len(value) < rule.get("minItems", 0):
                found.append(f"{where} needs at least {rule['minItems']} item(s)")
            if rule.get("uniqueItems") and len({repr(v) for v in value}) != len(value):
                found.append(f"{where} has duplicates")
            for i, item in enumerate(value):
                check(item, rule.get("items") or {}, f"{where}[{i}]")
        if isinstance(value, dict):
            for name in rule.get("required") or []:
                if name not in value:
                    found.append(f"{where}: {name} is missing" if where else f"{name} is missing")
            properties = rule.get("properties") or {}
            others = rule.get("additionalProperties")
            for name, item in value.items():
                inner = f"{where}.{name}" if where else str(name)
                if name in properties:
                    check(item, properties[name], inner)
                elif others is False:
                    found.append(f"{where + ': ' if where else ''}{name} {unknown}")
                elif isinstance(others, dict):
                    check(item, others, inner)

    check(value, schema, "")
    return found


def _is(value, kind: str) -> bool:
    return {"string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool),
            "array": isinstance(value, list), "object": isinstance(value, dict), "null": value is None,
            "boolean": isinstance(value, bool)}.get(kind, True)
