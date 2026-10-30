# Mapping spec format

How mapping specs, lookups and the assembly spec are written. Agents and validators follow this file; skills point to
it rather than repeat it. Its examples use a made-up model and upstreams (`CustomerRecord`, `upstream-1` and
`upstream-2`): they show the shape, not names to use.

## Mapping specs

One file per upstream operation: `mappings/<upstream>/<operation>.md`, where `<upstream>` is the upstream's id and
`<operation>` a kebab-case name for the operation (`get-customer`, `get-accounts`).

### Header

```yaml
---
upstream: upstream-1                     # the upstream's id
category: REST                           # REST | SOAP | JDBC | MAP
spec: com.example.upstream1:customer-api-spec:4.2.0   # spec jar; a file in this repo until it's in Nexus; for JDBC, the query's name
operation: GET /customers/{id}           # as the spec names it; for JDBC, the query's name; for MAP, Interface.method
target: CustomerRecord.contactPreference   # the branch of the internal model this file fills, from the payload root
target_schema_version: 3.1.0             # internal model version the file was written against
status: draft                            # draft | approved | implemented
origin: reverse-engineered               # only when written from existing code
---
```

### Tables

A mapping spec is driven by the internal model: it has one row per field of each target object, whatever the upstream
offers. Upstream fields the model doesn't need get no row, however many there are.

One table per target object, headed by the object's path from the payload root, e.g.
`CustomerRecord.accounts[].balance`, never from a nested object's own schema (`Account.balance`). Nested objects and
list items get their own table below it, numbered from their row in the parent (rows 6.1, 6.2 …).

What a file targets follows the model's structure (its CONVENTIONS.md): a source's mapping fills **its slot**, so its
first table is the slot (`CustomerRecord.contactPreference`), with a row for each of the slot's fields, and the
slot's lists get their own tables below it (rows 1.1, 1.2 …). The identity's mapping fills the root's own fields:
`CustomerRecord`.

Above each table:

- **Source root:** where the table's source paths start, e.g. `Data.Account[]`. Paths in the table are relative to it.
  Its first `code` span is the path; any other words explain it. A nested table's paths are relative to its parent
  row's source, so its Source root line is there for the reader.
- **Filter** (optional): which items of a source list are left out, e.g. "accounts with `Status` Deleted".

| Column       | Holds                                                                                                    |
|--------------|----------------------------------------------------------------------------------------------------------|
| #            | Row number                                                                                               |
| Target field | The internal model field, by its name in the schema                                                      |
| Source       | Where the value comes from, relative to the source root (see below)                                      |
| Rule         | How the value is made (see rule types). Blank means `copy`                                               |
| Details      | What the rule needs: the lookup's name, the format pattern, the condition or derivation in plain English |
| If missing   | What happens when the source has no value (see below). Required                                          |
| Notes        | Anything a reader needs, and `proposed` for sources not yet confirmed                                    |

Every field of the target object gets a row, except fields that the [assembly spec](#assembly-spec) fills from another
mapping file.

A row for a nested object or list names the source object or list it's built from; the object's own table follows.
Its rule is blank when the source object maps field by field, `list` for a list, and `condition` or `derive` when the
source object has to be chosen (for example "the latest statement").

A slot's list row names the list it comes from, relative to the slot table's Source root: `Balance[]`,
`Account[]`, `records[]`. For JDBC, each row the query returns is an item, so the row names the query:
`ACCOUNTS_BY_CUSTOMER`.

### Source names

| Category | How sources are named                                            | Example                                        |
|----------|------------------------------------------------------------------|------------------------------------------------|
| REST     | Property path from the OpenAPI spec, `.` between levels          | `Account[].Identification`                     |
| SOAP     | Element path from the WSDL and XSDs, `/` between levels          | `CustomerReference/ContactPreference`          |
| JDBC     | Column name or alias from the SQL query; the query's name for the list of its rows | `ACCT_OPEN_DT`, `ACCOUNTS_BY_CUSTOMER` |
| MAP      | Property path on the vendor's response class, `.` between levels | `phoneList[].cntryDialCd`                      |

- `[]` marks a list.
- `request:<name>` is a value the payload was requested with, not an upstream field, e.g. `request:customerId`.
- Source holds one path: the field the value mainly comes from. Only a `combine` row lists several, joined by `+`.
  Any other field a rule reads (a fallback, a condition's test, a second operand) is named in Details, in `code`.

### Rule types

| Rule         | Meaning                                                                                                                                                                                                                            |
|--------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `copy`       | The value as it is. Converting its type while keeping all of it (number to string, `xsd:date` to date) or removing padding doesn't make it a `format`. The default, written as a blank                                          |
| `constant`   | A fixed value, given in Details                                                                                                                                                                                                    |
| `lookup`     | Translate a code with a lookup table in `lookups/<name>.md`, a table of codes whatever type they give; Details names the table                                                                                                       |
| `format`     | Change how the value is written, by a rule: a date or number pattern, a case change, or keeping only part of it, such as the date of a date-time. E.g. `yyyyMMdd → yyyy-MM-dd`, `upper case`, `date-time → date: the date part as sent` |
| `combine`    | Build the value from several sources; Details gives the recipe                                                                                                                                                                     |
| `condition`  | Choose between sources or values by a test, including falling back to another source ("`A`; if missing, `B`"); Details give the tests in order. One code tested for a yes or no is a condition too: `Y` → true; anything else → false. A default used when the source is missing isn't a condition: it goes in If missing |
| `list`       | Map each item of a source list; the item's table follows                                                                                                                                                                           |
| `derive`     | Anything else, in plain English: arithmetic, including scaling units (thousands to units) or moving a decimal point, or choosing a list item by comparing values ("the latest"). A row with arithmetic anywhere is a derive, even when it also falls back or tests: Details give the whole recipe. Gets extra tests and a developer review |
| `not mapped` | Deliberately left empty; Notes give the reason                                                                                                                                                                                     |
| `TBD`        | An open question that blocks implementation                                                                                                                                                                                        |

**When two rules fit,** arithmetic anywhere makes the row a `derive`; otherwise a choice by a test is a `condition`. A
default for a missing value is never a rule: it's the row's If missing.

### If missing

**Missing** means the source isn't sent or is null: an absent element, a nil `JAXBElement`, a SQL `NULL`. A blank
value (empty, or only spaces) counts as missing only where the row's Notes say "a blank value counts as missing", as
when an upstream sends blanks for nothing, or the code treats a blank as missing (`isEmpty`, `isBlank`, after a trim).
Its default then goes in If missing like any other, and the rule stays what it is without it.

| Value         | Meaning                                                       |
|---------------|---------------------------------------------------------------|
| `error`       | The payload fails                                             |
| `omit`        | The field is left out (the internal model never holds `null`) |
| `skip`        | The whole list item is left out                               |
| A default     | This value is used, in one pair of backticks: `GBP`, `false`, `0` |
| `empty list`  | For lists: an empty list                                      |

### Sections after the tables

1. **Proposed internal model changes:** fields the internal model is missing. They feed the Model Designer.
2. **Open questions:** anything still unresolved. Must be empty for `status: approved`.
3. **Upstream fields not mapped** (optional): upstream fields that might be worth mapping later. Leave it out unless
   someone asked what else the upstream offers, and never list a whole spec.

### Reverse-engineered specs

Files written from existing code have `origin: reverse-engineered` and two more columns after Notes:

| Column     | Holds                                                                                                                                                                                      |
|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Code       | Where the code sets the field: `File.java:line`, several lines or ranges as `File.java:12,30-34`, several files separated by `;`. Add the path when the file name isn't unique in the repo |
| Confidence | `high`, `medium` or `low`. Low when the code is unclear, or looks different from what was probably intended; Notes say why                                                                 |

## Lookups

One file per code table: `lookups/<name>.md`.

```yaml
---
name: contact-channel
target: CustomerRecord.contactPreference.channel   # the internal model field it produces
---
```

A table with columns `Source code`, `Target value` and `Notes`, then one line:

- **Otherwise:** what an unknown code produces: a value, or `omit`, `skip` or `error`.

## Assembly spec

One file per payload root: `assembly/<root>.md`, e.g. `assembly/customer-record.md`. It says which mapping fills each
branch of the payload (the identity, then every slot), how each upstream is called and how its result attaches.

| Column            | Holds                                                          |
|-------------------|----------------------------------------------------------------|
| #                 | Row number                                                     |
| Branch            | The payload path the row fills                                 |
| Mapping           | The mapping file that fills it                                 |
| Called            | How often: once per payload, or once per item of a parent list |
| Called with       | The request values, and where they come from                   |
| Attaches          | How the result joins the payload                               |
| If the call fails | `error` (the payload fails), or what the branch holds instead  |
