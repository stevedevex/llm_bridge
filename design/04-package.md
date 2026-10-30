# BRIDGE design: the package

A requirement package is a set of files, each with a fixed shape and a command that checks it. The shapes live in
`templates/` and `mappings/FORMAT.md`; the agents and the checks read them from there. This document describes each
file, with `REQ-101` as the example.

| File | Shape | Written by | Checked by |
|---|---|---|---|
| Spec digest | `spec-digest@1` | Spec Explorer, over `spec digest`'s listing | `validate digest` |
| `impact.md` | `templates/impact.md` | Impact Analyzer | `validate impact` |
| The model change and `model-change.md` | The model's `CONVENTIONS.md` | Model Designer | `validate model` |
| Mapping request | `mappings/REQUEST.md` | The BA | `validate request` |
| Mapping spec, lookup, assembly spec | `mappings/FORMAT.md` | Mapping Drafter, Reverse Engineer | `validate mapping` |
| Story | `templates/story.md` | Story Writer | `validate story` |
| Validation report | Its agent's instructions | Spec Validator | `validate package` |
| Test case | `templates/test-case.md` | Test Designer | `validate test-case`, `tests coverage` |
| Glossary | `templates/glossary.yaml` | `/draft-glossary`, the BA | `knowledge check` |

## Spec digest

What an upstream's spec offers, in business words, and where the BA's data is in it. `bridge-kit spec digest` writes
the listing (every operation, with every field it takes and returns: path, type, required, allowed values,
description), so it's complete by construction; the Spec Explorer writes the sections above it:

- **Summary:** what the spec offers.
- **Where the data is:** each item asked for, with the operation and field path exactly as the spec names them, its
  type, its codes and what it means. For `REQ-101`: `GET /customers/{id}`, `contactPreference.channelCode`, a string
  with the codes `E`, `P` and `S`.
- **Not available:** what the spec doesn't have, and each near match rejected, with why.
- **Open questions:** what the spec leaves unclear.

`validate digest` checks every section is written and every operation and path named is in the spec.

## Impact analysis

`impact.md` follows the requirement's data through the components in the catalog's order:

- **Data elements:** each piece of data, and where it is in each component, or that it's missing there. Every
  missing hop is work for that component.
- **Affected components:** for each, the evidence (a schema path, a spec, a mapping row, a file and line, a profile),
  the contracts it owns that change and whether additively or not, the impact on external clients, and a confidence.
- **Not affected:** every other component in the catalog, with why.
- **Open questions:** each term it couldn't place, and what the requirement leaves open.

For `REQ-101`, the channel is missing from `shared-model`, `service-a-java`, `service-c-java`, `service-d-java` and
`ui-react`; `service-d-java`'s API faces external clients, so the change is additive and flagged; `service-b-python`
is not affected.

## The model change

The Model Designer changes the shared model's schemas, examples and version files in its checkout, by its
`CONVENTIONS.md`. `bridge-kit model start` records the model as it was; `model diff` lists every change as a payload
path, additive or breaking, the version that follows, and, for a breaking change, the consumers it hits, searched in
their repos. `validate model` checks the conventions on what changed, the version in every version file, the
example, the description against the diff, and the model's build.

`model-change.md` is the merge request description: what changed and why, the consumers, the open questions. For
`REQ-101`: `CustomerRecord.contactPreference.channel`, an enum of `EMAIL`, `PHONE` and `SMS`, an additive change
and a minor version.

## Mapping specs

**The mapping request** is the BA's own: copied from `mappings/REQUEST.md` into the work item, it names the upstream
and operation, the target path, the spec and the digest, and gives the purpose, the rules, codes and calling details
the BA knows, and who to ask. It can name the BA's rough mapping, a spreadsheet or Word table kept as an input.

**A mapping spec** says how one upstream operation fills the model: `mappings/<upstream>/<operation>.md`. Its
header names the upstream, its category (REST, SOAP, JDBC or MAP), its spec, the operation, the target path, the
model version it was written against, and its status (`draft`, `approved`, `implemented`). It is driven by the
model: one table per target object, one row per field, whatever else the upstream sends.

| # | Target field | Source | Rule | Details | If missing | Notes |
|---|---|---|---|---|---|---|
| 1 | `channel` | `contactPreference.channelCode` | `lookup` | `contact-channel` | `omit` | |

- **Rules:** `copy` (the default), `constant`, `lookup`, `format`, `combine`, `condition`, `list`, `derive`, `not
  mapped`, and `TBD` for an open question that blocks.
- **If missing:** `error`, `omit` (the model never holds null), `skip` (the list item), a default, or `empty list`.
- **After the tables:** proposed model changes, open questions, and optionally the upstream fields not mapped.
- **From existing code,** a spec is marked `origin: reverse-engineered` and adds a Code column (file and line) and a
  Confidence column to every row.

**A lookup** translates one code table: `lookups/<name>.md`, with the target field it produces, a table of source
codes and target values, and what any other code produces. `contact-channel` turns `E`, `P` and `S` into `EMAIL`,
`PHONE` and `SMS`, and omits anything else.

**The assembly spec** says which mapping fills each branch of a payload, how often each upstream is called and with
what, how its result attaches, and what a failed call does: `assembly/<root>.md`, one per root of the shared model.

When the Mapping Drafter works from the BA's rough mapping, each row it takes cites its cell; struck, coloured,
commented or hidden rows aren't taken as decisions, and the package check confirms every cited cell is still there.

## Stories

One file per affected component, `work/<id>/stories/<component>-<nn>-<slug>.md`, `<nn>` the component's order. The
header names the component, its order, the stories it's blocked by, every contract it changes and how, the package
files it implements, its labels, and its status (`draft`, `approved`, `created`) and GitLab id once created. The body:

1. **Story:** "As a *business role*, I want *capability*, so that *benefit*."
2. **Context, scope** in and out, and **contracts and data**, a row per contract with the fields by path.
3. **Acceptance criteria,** `AC-1` on, each in Given, When and Then.
4. **Component details** that team needs: the screens and their states for a UI; the API version and what external
   clients are told for an API; the calls and their errors for business logic; the upstream, mapping and assembly
   for a collecting service; the schema change, version and consumers for the shared model.
5. **Dependencies, non-functional** needs, and **open questions**.

`ui-react`'s story for `REQ-101`: *As a relationship manager, I want to see a customer's preferred contact channel
on the customer panel, so that I contact them the way they asked.* Its `AC-2` covers a customer with no preference.

## Validation report

`work/<id>/validation-NN.md`, numbered on from `01` each run. A verdict (ready for the developers or not: ready only
when the package check passes and no finding blocks), then each finding as the question a developer would ask,
pinned to its file and its row, criterion or section, whether it blocks, and who answers: the BA, the upstream's
team, the model's owners or the component's team.

## Test cases

One case a file, `work/<id>/tests/tc-<nn>-<slug>.md`, each proving one behaviour. The header gives what it verifies
(criteria, by story), its level (component, contract, integration, system, end-to-end), type, path (happy,
alternate, error), technique (equivalence, boundary, decision table, state transition, error guessing), priority,
the versions it was written against, its environment (dev or SIT, never production) and how it's automated. The
body: objective, preconditions, test data (every value made up, named once), steps with results someone else can
observe, the checks along the data path (one per component, in the catalog's order, so a failure says where it
started), pass criteria, cleanup and open questions.

`bridge-kit tests coverage` lists every criterion with the cases that verify it; a criterion with none is an error,
and a criterion that names failures with no error case, or reads as accessibility with no such case, a warning. For
`REQ-101`: one end-to-end case through every hop, a decision table over the three codes, an unknown code, and the
customer with no preference.

## Glossary

`architecture/glossary/<area>.yaml`, one file per business area: each term as BAs say it, its definition and where
that comes from, its synonyms, and its data elements by payload path. `bridge-kit knowledge term "<words>"` finds a
term, then the model's fields and the profiles' business words that match, and says to ask when nothing does.
