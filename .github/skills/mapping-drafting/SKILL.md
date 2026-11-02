---
name: mapping-drafting
description: Step-by-step procedure for drafting a mapping spec from a BA's mapping request, without code - listing the target's fields, reading the upstream's spec, its digest, a vendor jar or a database query, choosing each row's source, rule, If missing and lookup, taking the rows the BA's rough mapping settles, leaving the other business decisions to the BA as proposed rows with questions, and adding the target's assembly row. Use when drafting or redrafting a mapping spec for an upstream operation.
metadata:
  version: 0.5.2
  owner: ba-team
---

# Drafting a mapping spec

The goal is a draft the BA mostly confirms: every row the spec, the model and FORMAT settle, filled in right, and
every business decision left open with a clear question, never guessed. The format is `mappings/FORMAT.md` (the
`mapping-format` skill says how to write it); this skill says how to work out what goes in it.

## 1. Read the request and list the target

1. Read the request: its front matter (`upstream`, `operation`, `target`, `spec`, `digest`) and every section. The
   Purpose says what the data is for; Known rules, Codes and Calling are the BA's answers in advance. A blank
   section means the BA doesn't know: its questions are yours to ask. When it names a `rough_mapping`, read section 9
   before you draft: the BA's own mapping settles the rows it covers.
2. Read the target's schema in the model's checkout, and the schema of every object and list inside it. List every
   field with its type, whether it's required, its allowed values and its description. The description says what
   the field means; it's often what settles a source.
3. Look in `assembly/` for a row whose Branch is the target. If there is one, the mapping file it names is the file
   you write, and the row says how the upstream is called.
4. Look at the reviewed specs in `mappings/` and their lookups for the way this team writes rows: Source roots,
   rule choices, lookups, notes. Copy the style, never the content.
5. The collecting service's own knowledge, when the catalog points to it: its `glossary` (what the upstream's codes
   mean) and `lineage` (which upstream already fills which field), with
   `.github/bridge-kit/bin/bridge-kit knowledge show <component> <kind>`. It's the team's writing, not code: use it to
   understand a code or a field, and still take every source from the spec.

## 2. Get the upstream's fields

- **A digest** (the request names it): read its Where the data is first, then look fields up in its listing with
  `grep -n`.
- **An OpenAPI spec or a WSDL** without a digest: generate the listing with
  `.github/bridge-kit/bin/bridge-kit spec digest "<spec as the request gives it>" --upstream <upstream> --out
  .work/tmp/spec-digest-<upstream>.md` (it creates the folder), and search it. Read only the operation the request
  names.
- **A vendor jar:** `.github/bridge-kit/bin/bridge-kit spec resolve <coordinates> --json` gives its location; read the
  response class and each class it holds with `javap -cp <jar> <class>`. A property is its getter, without `get`.
- **A database:** the query and the table definition attached to the work item. Sources are the query's column
  aliases; the definition's comments give units, codes and what an empty value means.

Never read the service's code, and never resolve a spec any way but these.

## 3. Draft each row

For each target field, in the schema's order, with nested objects and lists in tables of their own (FORMAT):

1. **Source.** The field whose description means what the target's description means. When several look right,
   choose the one whose description fits best and name the others in Notes as near matches you rejected. When none
   fits, say so: never stretch a field that only looks similar.
   - **The first table's Source root is a path.** For REST it starts at the top of the response body: a property
     or a chain of them, in `code` (`Data.Policy[]`), or the body itself, written without `code` ("the response
     body"). Never a schema's name: the digest's Returns line names the schema only as a type, and a property may
     have the same name. For SOAP it starts at the response element (`GetPoliciesResponse`).
   - **Where paths start:** the first table's at its Source root; a nested table's at its parent row's source,
     whatever its Source root line says. Under a parent row `Policy[]`, a field of each policy's `Premium` object is
     `Premium.Amount`, never `Amount`. Write a nested table's Source root line as that parent row's item or object
     ("each `Policy` of row 2"), never a narrower path.
   - **One path, the value's own field:** when a rule picks an entry of a list (the identifier whose scheme is
     IBAN), the source is the field the value is, `Identifier[].Value`, and the test goes in Details.
2. **Rule.** By FORMAT's rule types. The usual ones: a value as it is, or converted without losing anything, is
   `copy`, and so is a list of plain values (strings, numbers) taken as they are; a pattern, a case change or keeping
   only the date of a date-time is `format`; a code into our enum is `lookup`; arithmetic, such as scaling to the
   units the spec states, is `derive`; a list of objects is `list`, with its own table.
   - A code into our enum is a `lookup` even when the codes are spelled exactly as our values (`OPEN` → `OPEN`): the
     lookup lists every code the spec allows and says what an unknown one gives. The one exception is codes that
     are our values in another case (`Retail` → `RETAIL`): that's `format`, `upper case`.
3. **If missing.** From the model: a field it requires is `error`; one it doesn't is `omit`. A list the model
   requires is `empty list`; an optional list is `omit`, like any optional field.
   - **A default the spec or the table definition states** ("empty for records before 2019, which are all in EUR")
     goes in If missing as the value, in one pair of backticks, `EUR`, and the rule stays what it is without it
     (`copy`). It's knowable, not the BA's decision, and never a `condition` (FORMAT).
   - **The request's rules settle If missing too.** Apply each rule to every column it decides: "a policy with no
     number is left out" makes the number row's If missing `skip`, as well as anything else the rule says.
   - Any other default, or leaving out the whole item, is the BA's decision, below.
4. **Required fields in optional objects.** When the table is done, check every object in it, at any depth and
   inside list items too: does its parent require it? If not, each field the model requires inside it can, when
   missing, either fail the payload or leave the whole object out. That's the BA's decision. Write `error` on every
   such row, mark each `proposed`, and ask one question naming the object and each target field, as the model
   spells them: "BA: when `Fee/Amount` or `Fee/Currency` is missing, should the payload fail, or should the whole
   `annualFee` be left out? Its `value` and `currency` are required."
5. **Lookup.** Write `lookups/<name>.md` from the codes' descriptions: every code the spec allows, mapped to our
   enum's value that means the same. What an unknown code gives (Otherwise) is the BA's decision.

## 4. Leave the BA's decisions to the BA

These are the BA's to make, not yours: a fallback to another field; a default when the value is missing; a filter
that leaves items out; leaving a field unmapped on purpose; which of two fields to use when the spec doesn't say;
what an unknown code gives; time zones and units the spec doesn't state; whether a missing required value in an
optional object fails the payload or leaves the object out.

- If the request's Known rules, Codes or Calling give it, apply it as given, and say in Notes it's from the request.
  If the BA's rough mapping gives it, apply it as section 9 says.
- Otherwise write your best proposal in the row, put `proposed` in its Notes, and ask under Open questions, naming
  the target field as the model spells it, in backticks, and who should answer: "BA: when `ShortName` is missing,
  should `tradingName` fall back to `RegisteredName`, or be left out?" A question that names only the upstream's
  field (`Fee/Amount`), or the target in other words ("the yearly fee"), doesn't say which row it's about.
- The marker always goes in the row's Notes, even when what's open is in a lookup: a code the spec doesn't
  describe, or what an unknown code gives. Mark the lookup's lines too if it helps, but the row is what the BA
  approves, and a row without the marker reads as settled.
- A field the model doesn't require and the Purpose doesn't ask for: whether to fill it is the BA's call. Map it as
  you would, mark it `proposed`, and ask: "BA: the request doesn't ask for `nickname`. Fill it from `ShortName`, or
  leave it not mapped?" A field the model requires is always mapped.
- When the request names a field the spec doesn't have, don't use it. Use the spec's field that fits, if one
  clearly does, and ask; never write a source the spec doesn't have.

## 5. What the model doesn't have

What the request asks for that the target has no field for goes under "Proposed internal model changes": the data,
the upstream field it would come from, and its type. Never add a row for a field the model doesn't have.

## 6. The assembly row

When `assembly/` has no row for the target, add one to the payload root's assembly spec, `assembly/<root>.md`: the
root the target's path starts at, as the model's contract in `architecture/components.yaml` names it (`root:`), in
kebab case (`assembly/customer-record.md` for `CustomerRecord`).

| Column | What goes in it |
|---|---|
| Branch | The target |
| Mapping | Your file, under `mappings/` |
| Called | Once per payload, or once per item of the list the target sits in, as the model's structure has it |
| Called with | The request's Calling; otherwise your proposal, and a question |
| Attaches | Where the result joins the payload: the target, as the model's CONVENTIONS.md describes it (in a model of slots, the slot on its parent) |
| If the call fails | The request's Calling; otherwise your proposal, and a question |

## 7. Write the header and check it

- The header: `upstream` and `spec` as the request gives them (a file in this repo while the spec isn't in Nexus),
  `operation` as the spec names it, `target`, `target_schema_version` (the model's version: `bridge-kit model diff`
  prints it, from the first version file `model.layout` names, `pom.xml` by default) and `status: draft`.
- No `Code` or `Confidence` column: those are for reverse-engineered specs.
- Run `.github/bridge-kit/bin/bridge-kit validate mapping <file>` and fix every error: it reads the model
  `bridge-kit.yaml` declares, by its layout. An error about a source means the spec doesn't have it: look again, don't
  argue with it. When every source in a table fails, the Source root is wrong. If the validator says sources aren't
  checked, say so in your reply.

## 8. A second turn: the questions have answers

When the work item already has a draft and some of its Open questions have an answer below them (`Answer (BA): …`,
`Answer (the upstream team): …`), you redraft that file rather than start again:

1. **Read every answer first.** Each one settles the row its question names. An answer can settle more than one
   column: "fall back to `RegisteredName`; a policy with neither is left out" is the rule, the Details and If missing
   (`skip`).
2. **Work it into the row,** by FORMAT, as you would a rule from the request: Source, Rule, Details, If missing, and
   its lookup when the answer is about codes or what an unknown one gives. Then take `proposed` out of the row's Notes
   and say there instead that it was decided, by whom: "Decided by the BA (see decisions.md)".
3. **Take the question and its answer out of Open questions.** Nothing answered stays there.
4. **Record each answer** in `work/<id>/decisions.md`, adding to it if it exists. One entry per answer:

   ```markdown
   ## 2026-10-27: `tradingName` falls back to `RegisteredName`

   - **What:** `mappings/insurer/get-policies.md` row 3, `tradingName`: `ShortName`, else `RegisteredName`
     (`condition`); a policy with neither is left out (`skip`)
   - **Who:** the BA
   - **Why:** the answer: "use the registered name; every policy has one"
   ```

   What names the file, the row and the target field as the model spells it, and says what the row now does. Who is
   whoever the answer names. Why quotes or sums up the answer; when it gives no reason, say it was the answer to your
   question.
5. **Keep every unanswered question** as it is, under Open questions, with its row still `proposed`. Don't answer it
   yourself.
6. **Ask again when an answer opens something new:** a code nobody mentioned, a case the answer doesn't cover. Add the
   new question under Open questions, and leave its row `proposed`.
7. Leave every row nobody answered about as it was, then run the validator (section 7).

In your reply, list the rows you settled, the questions still open, and any new ones.

## 9. The BA's rough mapping

When the request names a `rough_mapping`, it's an input holding the mapping the BA worked out on their own: read the
table `rough_mapping_table` names (an Excel sheet's, under `## Sheet: <name>`; a Word document's, after `Table N:`), or
its only one. It keeps the BA's row numbers and, for a sheet, each column's letter. It's the BA's work: the rows it
settles, it settles as the request's Known rules do.

1. **Its columns.** Tell from the headings which column holds the source (the upstream's field), the target (our
   field), the rule, and notes. BAs word them their own way: "Upstream attribute", "From", "Maps to", "Model field",
   "Transformation". When you can't tell which is which, ask once under Open questions, and draft as usual meanwhile.
2. **The rows for this target.** A rough mapping may cover several operations or upstreams. Take the rows whose
   target is in this file's target, and leave the others aside.
3. **Each target field's row,** found by meaning: the BA may write "preferred channel" for
   `contactPreference.channel`, or an older name for the field.
4. **A row that fits is the BA's decision.** It fits when its source is a field the spec has (the same path, or a name
   that clearly means one field of the spec: "contact pref" for `ContactPreference/Channel`), its target a field the
   model has, and its rule one FORMAT can express. Draft it as the BA wrote it, in FORMAT's terms: "trim and upper case"
   is `format`; "map with the country table" a `lookup`; "default EUR" an If missing of `EUR`; "use the trading name,
   else the registered name" a `condition`. A fallback, a default or a filter it states is settled: don't ask it again.
   Don't mark the row `proposed`; write in its Notes where it comes from, by the cell of its rule (or of its target,
   when it has no rule):

   > From the BA's rough mapping, `Mapping!D12`

   The sheet as the request names it (`Table 2` for a Word table), then the column's letter and the row's number; for
   a CSV, the cell alone (`D12`). The package check follows each one.
5. **A row that doesn't fit is a question.** Mark it `proposed`, cite its cell in Notes too, and ask, quoting the BA's
   words:
   - a source the spec doesn't have: use the spec's field that clearly fits, if one does, and ask: "BA: the rough
     mapping (`Mapping!B7`) takes `prefChannel`, which the spec doesn't have; `ContactPreference/Channel` fits. Use
     it?"
   - a target the model doesn't have: under "Proposed internal model changes", citing the cell, never as a row;
   - a rule FORMAT can't express, or one that reads two ways: propose one reading, and ask which the BA meant.
6. **What the rough mapping marks isn't settled:**
   - A struck-through row (`~~…~~`) was dropped: don't take it. When it was the field's only row, draft as usual and
     ask whether the field was dropped on purpose.
   - Coloured rows (listed under the sheet's table, as Coloured cells and Coloured text): follow the sheet's legend
     when it has one (rows above its table, or a note, saying what each colour means). Without one, ask once what the
     colours mean, and mark the coloured rows `proposed` until the answer.
   - A comment on a row's cells (listed under Comments): an open question becomes yours to ask; a note that settles
     something settles it.
   - A hidden row (`12 (hidden)`), or a row in a hidden column: don't take it, and say so in your reply.
7. **The request and the rough mapping disagree** (the request's Known rules say one thing, a row another): mark the
   row `proposed` and ask, quoting both. Neither wins on its own.
8. **A target field no row covers** is drafted as usual, by sections 3 and 4.
9. **In your reply,** say which rows you took from the rough mapping, which became questions and why, which you left
   aside (other targets, struck, hidden), and which target fields it didn't cover.

The rough mapping never changes once kept. On a second turn, an answer about one of its rows is worked in and
recorded like any other (section 8), and the row's Notes then cite the decision rather than the cell.
