# Impact analysis template (`impact@1`)

How a requirement's impact analysis is written: which components the requirement touches, why, how each one's
contracts change, and how sure that is. It's `work/<id>/impact.md`. The Story Writer writes one story per component it
names, and `bridge-kit validate package` checks the package against it. The Impact Analyzer writes it; a BA can
too, from this template.

Before writing it, read the profile of each component the requirement may touch, `architecture/components/<name>.md`:
what it does, its business areas and data, its contracts, and its **Signs a requirement touches it**. Then the package
files the work item has so far: the model change, the mapping specs, the assembly spec.

## The file

````markdown
---
work_item: REQ-101
requirement: <the requirement's title>
---

# Impact: REQ-101, <the requirement's title>

## Data elements

| Data element | <a column per component the data passes through, in the catalog's order> |
|---|---|
| <the data, in business words> | <for each component: where it is there (a path, a field, a screen), or missing> |

<A sentence on what the table shows: which hops are missing, so which components have work.>

## Affected components

### <a component, as architecture/components.yaml names it>

- **Why:** <what in it changes, and where: the file, the endpoint, the screen; the package files that say so, by
  their path in backticks, e.g. `mappings/upstream-1/get-customer.md`, `work/REQ-101/model-change.md`>
- **Contracts:** <each contract it owns that changes, `<contract>` additive or breaking, with why; or none>
- **External impact:** <only for a component whose contracts outside clients use: breaking or not, the API version,
  what a gateway or a client must do; or none>
- **Confidence:** <high, medium or low, and for anything below high, why>

## Not affected

- <a component someone might expect here>: <why it isn't touched>

## Open questions

- <who should answer, and the question>
````

## What its readers rely on

- **One `###` heading per affected component, under Affected components,** named exactly as the catalog names it.
  Each gets one story; a component not here gets none.
- **The Contracts line:** each change as `` `<contract>` additive `` or `` `<contract>` breaking ``, only for contracts
  the component owns. The stories' `contracts` must agree with it, and with the model change.
- **Package files in backticks, by their path in the BA repo** (`mappings/…`, `assembly/…`, `work/<id>/…`): each
  one a story must implement.
- **Open questions:** "None.", or each question with its answer below it (`Answer (the BA): …`). The package isn't
  ready while one is open.
- **Confidence:** a low-confidence item becomes an open question in its component's story.

## Rules

- **Every component the data passes through is looked at**, in the catalog's order: each is either under Affected
  components or under Not affected, with why.
- **A schema change belongs to the model's component.** A component that never defines a schema (its
  `defines_schemas: false` in the catalog) consumes the new one, and lists no schema contract of its own.
- **Facts from the code cite it:** a file, an endpoint, a screen. What's inferred says so, and lowers the confidence.
