---
name: mapping-format
description: How mapping specs, lookups and the assembly spec are written and checked in this repo. Use whenever you write, change or review a file under mappings/, lookups/ or assembly/.
metadata:
  version: 0.4.2
  owner: ba-team
---

# Mapping spec format

The format is defined in `mappings/FORMAT.md`. Read it before writing; this skill doesn't repeat its rules, it only
shows a small example and how to check your work.

## Example

An invented upstream, to show the shape. Two rows of a top table and a nested table:

```markdown
---
upstream: customer-registry
category: REST
spec: com.example.upstream.registry:customer-registry-spec:2.0.0
operation: GET /customers/{id}
target: Customer
target_schema_version: 3.1.0
status: draft
---

## Customer

**Source root:** `data.customer`

| # | Target field | Source | Rule | Details | If missing | Notes |
|---|---|---|---|---|---|---|
| 1 | customerId | id |  |  | error |  |
| 2 | homeAddress | addresses[] | condition | The first address whose `kind` is HOME | omit |  |

## Customer.homeAddress

**Source root:** the address chosen in row 2

| # | Target field | Source | Rule | Details | If missing | Notes |
|---|---|---|---|---|---|---|
| 2.1 | postCode | postalCode | format | upper case, no spaces | omit |  |
```

A reverse-engineered spec adds `origin: reverse-engineered` to the header and the `Code` and `Confidence` columns.

Points that are easy to get wrong:

- Paths start at the payload root (`CustomerRecord.accounts[]...`); a source's file targets its part of the model, as
  the model's CONVENTIONS.md describes it (its slot, in a model of slots). A list row names the list it comes from
  (`records[]`); for JDBC, the query (`ACCOUNTS_BY_CUSTOMER`).
- Source holds one path; other fields a rule reads go in Details. Only `combine` joins several with `+`.
- A type conversion that keeps the whole value is still `copy`, but keeping only the date of a date-time is
  `format`; falling back to another source is a `condition`, and so is one code tested for a yes or no; a default
  for a missing value goes in If missing, in one pair of backticks (`GBP`); arithmetic, including unit scaling, is
  `derive`, even when the row also falls back or tests. A blank value counts as missing only where Notes say so.
- The "Upstream fields not mapped" section is optional: leave it out unless someone asked for it.

## Check your work

```bash
.github/bridge-kit/bin/bridge-kit validate mapping mappings/<upstream>/<operation>.md
```

Fix every error. Warnings need a reason in Notes or a fix. Add `--maven-repo <folder>` when you have the spec jars
locally, so source paths are checked against the spec too.
