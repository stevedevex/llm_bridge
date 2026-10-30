---
name: model-designing
description: Step-by-step procedure for changing the internal data model (the JSON schemas every service shares) for a BA's requirement - finding what the model already has, placing, naming and typing new fields by the model's conventions, fixing a field in place, setting the version, listing the consumers a breaking change hits, and writing the merge request description. Use when changing the internal model, or checking whether it already holds some data.
metadata:
  version: 0.3.1
  owner: ba-team
---

# Designing a change to the internal model

The goal is the smallest change that gives the BA what they asked for, in the model's own names and conventions,
with nothing broken that nobody was told about. The model's rules are in `CONVENTIONS.md` in its checkout: this skill
says how to apply them, never what they are, so read it first. Where its files are, and the rules `bridge-kit validate
model` checks, are in `.github/bridge-kit/bridge-kit.yaml` (`model.layout`, `model.conventions`), set from the same
CONVENTIONS. Where this skill names a rule, it's the kit's default, as an example: follow your model's. Its examples
(`CustomerRecord`, `REQ-101`) use a made-up model.

## 1. List what's asked

Number the items in the order the BA asked. For a fix, the item is the field and what's wrong with it.

For data from a new upstream, read the digest's sections at the top (Summary, Where the data is, Not available, Open
questions). Its Notes say what each value means, its codes, its units and when it's absent; that decides the type.
Look up a field in the generated Operations listing only to see its allowed values (`grep -n` on the file). Never
read the listing end to end, and never model a field because the upstream offers it.

## 2. Look for it in the model first

For each item:

1. Look the BA's words up in the glossary first: `.github/bridge-kit/bin/bridge-kit knowledge term "<words>"` gives the
   terms that match with their data elements, and the model's fields whose names or descriptions match. Then
   search the schemas for words from the BA's request and from its meaning, in names and descriptions:
   `grep -rn -i "<word>" <checkout>/<schemas folder>/`, the folder `model.layout.schemas` names. Try the synonyms a BA
   might use.
2. Read the description of every candidate. A field whose description means what was asked is the answer, whatever
   it's called: it's **reused**, and nothing changes for it.
3. When a field is close but not the same (another period, another party, a different unit), don't stretch it and
   don't add a near duplicate: ask under Open questions which is meant.

When every item is already there, the schemas don't change: still run `bridge-kit model start` and, at the end,
`bridge-kit validate model`, and write the description with `change: none`, the reused fields and a Changes table
without rows.

## 3. Design each new field

- **Where:** by the model's structure, as its CONVENTIONS.md describes it: which object holds which source's data,
  and where a new source's data goes. In a model built of an identity and one slot per source, as in the examples,
  each upstream fills its own slot (`CustomerRecord.contactPreference`).
  - Find the item's source: the upstream the request or the digest names. If the model already has a place for that
    source's data, the field goes there; inside it, on the object the data describes (an account's field on the
    account).
  - A source the model has no place for yet gets one where CONVENTIONS says, in its own file, named and titled as the
    model's others are, required on its parent: in a model built of slots, a **new slot**. Data that comes as a list
    (several per record) is a list in it, named for what each item is, holding a new object.
  - Never put a source's data where another source's goes. When CONVENTIONS doesn't say where a new source's data
    goes, ask under Open questions before adding it.
- **Name:** by CONVENTIONS. Say what it means to the business, never what the upstream calls it, and keep the model's
  style: look at its neighbours.
- **Type:** by the CONVENTIONS types table, from what the value means:
  - Money is the model's money schema, referenced with `$ref` (`model.conventions.money` names its title, by default
    `Amount`): never a number with a separate currency, never a new money object.
  - A date is a date even when the upstream sends a date and time, unless the time matters to the business.
  - A value from a fixed list is an enum of our own codes, written as CONVENTIONS says (by default
    UPPER_SNAKE_CASE). Add `OTHER` when the BA says other values occur, or the upstream has values the BA didn't ask
    to tell apart.
  - "Whether it's X" is a boolean when X is yes or no; when the upstream has several states and the BA may need them,
    an enum of our own states is better. Say which you chose, and why, in the description.
  - When the upstream's values don't follow our convention (codes that aren't ISO, other units), model it by our
    convention and say under Open questions that the mapping must translate it, or ask the BA what the field holds.
- **Required:** lists as CONVENTIONS says (by default required always, an empty list meaning none). Other fields are
  optional, unless every record has them and the business can't do without them; when unsure, optional.
- **Description:** for a business reader: what it is, its unit or format, and what it means when it's absent.
- **A new object:** as CONVENTIONS says (by default: a `title`, its class name; `additionalProperties: false`; a
  description). Its own file, named as CONVENTIONS says, when it's used in more than one place; inline otherwise, or
  its own file if the model keeps objects of that kind in files.

Model only the items asked. When something else looks needed (a field that qualifies another, an id to tell
records apart), ask under Open questions instead of adding it.

## 4. Fixing an existing field

Change it in place: same name, same place. Renaming or moving it removes the old field for every consumer, so do it
only when the BA asks for exactly that. Update its description to match. A type change is breaking whatever the
reason; the diff lists who it hits.

When the fix means its mapping spec must change too (it now needs a lookup, a conversion), say so under Consumers
affected: the Mapping Drafter and the developers pick it up from there.

## 5. Make the change

1. Run `.github/bridge-kit/bin/bridge-kit model start <id>` before your first edit. It records the model as it is, as
   the base every later diff compares with.
2. Edit the schemas. Keep each file's layout: two-space JSON, the existing order of keys, new fields next to related
   ones.
3. When the model has examples (`model.layout.examples`), update each payload root's example
   (`examples/customer-record.example.json`) so it uses every object and the new fields, with synthetic values that
   look real. For a changed field, the example's value must fit its new type.

## 6. Classify and version it

Run `.github/bridge-kit/bin/bridge-kit model diff <id>`. It lists every difference from the base, classified by the
CONVENTIONS version rules, with the version the change needs and, for a breaking change, every consumer it hits:
the files in checked-out repos that use the changed fields, and the components that aren't checked out.

- If it shows a difference you didn't mean, undo it.
- Set the version it says in every version file the layout names (`model.layout.version_files`; by default
  `pom.xml` and `python/pyproject.toml`).
- Never argue a breaking change down to additive. If the BA would rather avoid a breaking change, offer the
  alternative under Open questions; don't choose it for them.

## 7. Write the merge request description

`work/<id>/model-change.md`, in this shape:

````markdown
---
work_item: REQ-101
repo: shared-model   # the model's repo, as bridge-kit.yaml's model.repo names it
branch: feature/REQ-101-<short-slug>
base_version: 1.4.0
version: 1.5.0
change: additive            # additive | breaking | patch | none, as the diff says
---

# <What the change does, in a few words>

## Summary

Two to five sentences for the BA and developer who review it: what was asked, what changes, why it's additive or
breaking.

## Changes

| Path | Change | Kind |
|---|---|---|
| `CustomerRecord.contactPreference.channel` | New optional field: an enum of our own codes | minor |

## Reused

| Asked for | Path |
|---|---|
| the BA's words | `CustomerRecord.accounts[].status` |

## Consumers affected

What each consumer must do, or "None broken: the change is additive." For a breaking change, a table:

| Consumer | How it's affected | Where |
|---|---|---|
| <component> | What breaks, and what it must do | `<File>.java:<line>`, or not checked out |

## Open questions

- Who should answer (the BA, the upstream team, the developers), and the question.
````

- Changes has one row per difference the diff lists at the top level (fields inside a new object come with it), with
  the path exactly as the diff writes it.
- Reused has a row per item that was already there; leave the table without rows when nothing was.
- Consumers affected names every component and file the diff lists for a breaking change, and every risk it names.
- Open questions: a list, or "None."

## 8. Check it

```bash
.github/bridge-kit/bin/bridge-kit validate model <id>
```

It checks the conventions on everything the change touched, the version in every version file against the diff,
that the example uses every object, that the description says what the diff says and names every consumer a breaking
change hits, and it runs the model's build (Java classes, Pydantic models, and the tests of the schemas and the
example). Fix every error and run it again. Warnings are for you to judge: fix them or say in the description why not.
