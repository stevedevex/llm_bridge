---
name: reverse-engineering
description: Step-by-step procedure for reverse-engineering existing code into mapping specs, lookups and assembly spec entries, with what to watch for in the code. Use when writing specs for an existing collector or other existing mapping code, or when checking a reverse-engineered spec.
metadata:
  version: 0.5.1
  owner: ba-team
---

# Reverse-engineering existing code

The goal is the spec a BA would have written: every field of the internal model the code fills, where it comes from
in the upstream's own spec, and how it's transformed. Source names are always the upstream spec's names, never Java
names. The examples here (`CustomerRecord`, `upstream-1`) use a made-up model.

**Work from the internal model, not the upstream.** Upstream specs are often far larger than what's used. Start from
the model's fields, find where the code sets each one, and look up only those paths in the spec. Never read a long
spec end to end, and never list the fields nobody uses.

## 1. Find the calls and the mapping code

Start at the path you were given and follow the code until you know, for each upstream call:

- **Who calls it and with what:** the client, port, DAO or vendor interface, and the method called.
- **Where its response is mapped:** the mapper class and every helper, utility or base class it calls. Follow calls
  across classes and packages: a value is often set in one class and transformed in another.
- **Who calls the collector:** the assembler or orchestrator that decides the order of calls, what each is called
  with, where the result attaches, and what happens when the call fails.

## 2. Resolve each upstream's spec

| Category | Where the coordinates or source names are | Operation, as the header names it |
|---|---|---|
| REST | The collector module's POM: the `artifactItem` unpacked in `generate-resources`, and the code generator's input spec | `GET /path` from the OpenAPI spec |
| SOAP | The same, for the WSDL and its XSDs | The WSDL operation, e.g. `GetThings` |
| JDBC | No spec: the SQL in the code; the column names or aliases of its `SELECT` are the source names | The query's name in the code |
| MAP | The vendor jar dependency in the module's POM; the jar's classes are the spec | `Interface.method` |

Resolve REST, SOAP and MAP specs with `bridge-kit spec resolve <groupId:artifactId:version> --json` (see the
`spec-resolver` skill), then look up the paths you need in the resolved spec. Generated classes rename things
(`getIBAN()` for `IBAN`, `getAddressLine()` for `AddressLine`): always write the spec's name.

## 3. Read the target in the internal model

Find the internal model path the collector fills and read its schema, and the schemas of every nested object, in the
internal model's checkout. Every field of every target object gets a row; nothing else does.

A collector fills its source's part of the model, as the model's CONVENTIONS.md describes it, and that's its target:
in a model built of an identity and one slot per source, its source's slot (`CustomerRecord.contactPreference`), or
the identity for the collector that fills the root's own fields. A list row names the list the items come from
(`records[]`); for JDBC, the query that returns them. Write every path from the payload root, e.g.
`CustomerRecord.accounts[].balance`, never from a nested object's own schema (`Account.balance`).

## 4. Trace every field

For each target field, find every place the code sets it, on every path through the code, and trace the value back
to the upstream accessor, then to the spec path. Watch for:

| In the code | In the spec |
|---|---|
| A field set more than once | The value that wins on each path. The last unconditional assignment overrides earlier ones |
| Commented-out code, unused private methods, unreachable branches | Nothing: they don't map anything |
| A code table: `switch`, `if` chain over several codes, `Map`, `EnumMap` | `lookup`, with the table written to `lookups/<name>.md` and the default branch as Otherwise |
| One code tested for a yes or no: `"Y".equals(flag)`, `flag == 1` | `condition`: `Y` → true; anything else → false. Not a lookup |
| The value as it is, a type conversion (number to string, XML date to date), trimming padding | `copy` (a blank Rule) |
| A date or number pattern, a case change, keeping only the date of a date-time (`toLocalDate()`) | `format`, with the exact pattern, e.g. `yyyyMMdd → yyyy-MM-dd`, `date-time → date: the date part as sent` |
| A choice by a test, including falling back to another source ("`A`; if missing, `B`") | `condition`, with the tests in order. A default for a missing value isn't one: it goes in If missing |
| Arithmetic, including scaling units or moving a decimal point, or choosing a list item by comparing values | `derive`, saying exactly what the code does. Still `derive` when it also falls back or tests (`a × 1000`, else `b − c`): the whole recipe goes in Details |
| Concatenation of several sources | `combine`, with the recipe |
| A fixed value | `constant` |
| Nothing ever sets the field | `not mapped`, with "never set in the code" as the reason |

**Source holds one path:** the field the value mainly comes from. Name any other field the rule reads (a fallback,
a test, a second operand) in Details, in `code`. Only a `combine` row lists several sources, joined by `+`.

**When the source is missing**, the code's handling becomes "If missing". Judge it by what happens to the payload:
a throw that a caller catches isn't an `error`; write what the caller does instead.

| The code | If missing |
|---|---|
| Throws, and nothing catches it before the payload fails | `error` |
| Leaves the field null, skips setting it, or a caller drops the whole object | `omit` |
| Drops the list item (`continue`, a filter, returning null that a caller filters out) | `skip` |
| Uses a fallback: a default value, `Optional.orElse`, a ternary | The default, in one pair of backticks: `GBP` |
| Treats a blank value as missing too (`isEmpty`, `isBlank`, after a trim) and gives it the same default | The default, and in Notes: a blank value counts as missing. The rule stays what it is (`copy`), not a `condition` |
| Leaves an empty list | `empty list` |

**Category specifics:**

- **JDBC:** a column read by position (`rs.getString(n)`) is the column at that position in the `SELECT` list: count
  them. The query's `WHERE` becomes the table's Filter line; any unit conversion belongs in Details.
- **SOAP with JAXB:** a `JAXBElement` that is nil counts as missing.
- **Lists:** a list of objects gets its own table; note any filter or ordering the code applies.

## 5. Judge confidence and give code references

| Confidence | When |
|---|---|
| `high` | Traced end to end, no doubt about the source, rule and If missing |
| `medium` | Traced, but something is inferred: a convention, an untested branch, a value set far from its source |
| `low` | Unclear, or the code looks different from what was probably intended |

- Code looks unintended when names and behaviour disagree, when it relies on something the spec doesn't promise, or
  when two paths disagree. Write what the code does, set `low`, and explain the doubt in Notes.
- Use `low` sparingly: only for rows a reviewer should change or take to the BA. That's when the code relies on
  something about its input the spec doesn't promise, and the value would be wrong if it didn't hold (an order, a
  format), or when its behaviour contradicts the field's name or purpose. If your Details say the code "assumes"
  such a thing, the row is `low`.
- Ordinary null handling, type conversions, defaults and checks are not doubts: describe them and keep `high`.
- A **required** value the code never checks for is a doubt. Nothing guards it, so a missing one would leave a
  required field out, become a value nobody chose (`getLong` gives `0` for a NULL), or crash the call. Write what the
  code would do in If missing, not what was probably intended, set `low`, and say in Notes what was probably
  intended. A list counts too: a required list the code reads without a null check is `error`, `low`. An optional
  field left out when it's missing is ordinary: `omit`, and `high`.
- Something you couldn't check (a spec that wouldn't resolve, a command that was refused) is `medium`, with what you
  couldn't check in Notes. It isn't `low`.
- Expect a handful of `low` rows in a spec, not most of them.
- The Code column gives `File.java:line` for the line that sets the field, plus the lines where the transformation
  happens when that's elsewhere (a helper, a row mapper): `File.java:12,30-34`, several files separated by `;`.

## 6. Write the assembly spec rows

One row per branch the code fills (see `mappings/FORMAT.md`, Assembly spec): the mapping file, how often the call is
made (once per payload, or once per parent item), what it's called with and where those values come from, how the
result attaches, and what the branch holds when the call fails, as the catch blocks show.

## 7. Check before finishing

- `bridge-kit validate mapping <files>` reports no errors, and each warning is fixed or
  answered in the row's Notes.
- Read every row's Rule again against the table in section 4:
  - a `format` gives a pattern (`yyyyMMdd → yyyy-MM-dd`) or a case change; a type conversion that keeps all of the
    value (`String.valueOf`, a number to a string, an XML date to a date) is `copy`;
  - a `condition` chooses between sources or values; a default for a missing or blank value is If missing instead;
  - a `lookup` is a table of codes; one code tested for a yes or no is a `condition`;
  - a row with arithmetic anywhere is `derive`.
- Every target field has a row; every row has a code reference (except `not mapped` ones) and a confidence.
- Every code table is a lookup, and every lookup is used.
- Leave out the optional "Upstream fields not mapped" section unless you were asked for it.
- The notes file lists every low-confidence row and every question for the BA or the developers.
