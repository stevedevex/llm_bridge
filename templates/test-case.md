# Test case template (`test-case@1`)

How a test case is written, whoever writes it (a tester, a BA, an agent), so every case has the same shape and anyone
can run it and get the same answer. The header's schema is `templates/test-case.schema.json`; a complete case is in
`templates/test-case.example.md`.

A test case proves one behaviour that one or more acceptance criteria ask for, with exact data and results anyone can
observe. It's the definition of a test, not a record of running it: when it ran, on which build, by whom and what
happened go in the test tool or the run's report, never in the case.

Cases are written from a work item's approved stories, once their acceptance criteria are settled. In local mode each
is a file: `work/<id>/tests/tc-<nn>-<slug>.md`, where `<nn>` is its number, two digits (`tc-02-no-preference.md`).

## What makes a case good

1. **One behaviour.** Two outcomes that can fail on their own are two cases. A case that fails says what broke.
2. **Independent and repeatable.** It sets up what it needs and undoes it after. It never relies on another case
   having run first, and run twice with the same data it gives the same result.
3. **Concrete.** Exact values in exact places: `SMS` in `contactPreference.channel`, not "a valid channel". Never
   "works", "correct", "as expected", "appropriate" or "relevant".
4. **Observable.** Each expected result is something a person who didn't write the case can see: a field's value, a
   label on a screen, a status code, a stored payload, a log line. "Nothing else changes" names what it looks at.
5. **Traceable.** It names the criteria it proves, by story and AC id. A criterion with no case is a gap in the tests;
   a case that proves no criterion is a gap in the story (ask the BA) or out of scope.
6. **Derived, not copied.** A case comes from its criteria by a technique (below), and says which. It names a criterion
   by its id and title, and never copies the criterion's Gherkin, which would drift from the story.
7. **Safe data.** Made up, or from a dev or SIT payload by its request id (`bridge-kit payload get`). Never production
   data; every name, address, email and number invented.
8. **Short.** Ten steps at most. More usually means two cases.
9. **Current.** When a criterion it proves or a version under `versions` changes, it goes back to `draft` until it's
   checked again.

## From criteria to cases

Every criterion gets at least one case on its main path. Then each technique asks what else the criterion implies:

| Technique | Gives a case for | For example |
|---|---|---|
| `equivalence` | Each class of input that should behave alike: one representative each | A customer with a preference, and one with none |
| `boundary` | The edges of every range, length, list and date: zero, one, the most, one past it | An empty code; a code with spaces around it; a date at midnight UTC |
| `decision-table` | Each combination of conditions a criterion lists, each its own case | "An unknown code, an empty code, or no preference" is three cases, not one |
| `state-transition` | Each allowed change of state, and one that isn't allowed | A preference that changes between two requests |
| `error-guessing` | What tends to break: case, spaces, an unknown code, a duplicate, an upstream that's slow or fails | A channel code the lookup doesn't list |

Every criterion with an error path gets a case on it, and every non-functional criterion (accessibility, performance,
security) a case of that `type`.

For a requirement to show the customer's preferred contact channel (`REQ-101`), five stories' criteria give six
cases. One end-to-end case carries the main path through every hop; the rules each component applies get cases of
their own, at the lowest level that can see them:

| Case | Proves | Criteria | Level | Path |
|---|---|---|---|---|
| TC-1 | A customer who chose SMS sees it on the customer panel, from the upstream (`test-case.example.md`) | ui AC-1; api, business AC-1; collection AC-1 | end-to-end | happy |
| TC-2 | A customer with no preference sees that on the panel | ui AC-2; api AC-2; collection AC-2 | system | alternate |
| TC-3 | `E`, `P` and `S` become `EMAIL`, `PHONE` and `SMS` | collection AC-1 | component | happy |
| TC-4 | An unknown code leaves the channel out, and doesn't fail the record | collection AC-2 | component | error |
| TC-5 | A client that doesn't know the new field still reads the customer | api AC-2 | contract | alternate |
| TC-6 | The contact line reads in order, with its accessible name, by keyboard and screen reader | ui AC-3 | system | happy |

The model's own story changes schemas: its criteria are checked when the change is (`bridge-kit validate model` and
the model's build), and at runtime by the data path rows of TC-1 and TC-2.

## Header

```yaml
---
template: test-case@1
id: null                              # set when it's created in the test tool or GitLab, e.g. QA-1207
case: TC-2                            # its number in the work item, until it has an id
parent: REQ-101                       # the requirement
title: A customer with no contact preference sees that on the customer panel
status: draft                         # draft | approved | created | retired
level: system                         # component | contract | integration | system | end-to-end
type: functional                      # functional | accessibility | performance | security | data
path: alternate                       # happy | alternate | error
technique: equivalence                # equivalence | boundary | decision-table | state-transition | error-guessing
priority: high                        # high | medium | low: what a failure would cost
verifies:                             # the criteria it proves, by story
  - story: work/REQ-101/stories/ui-react-06-contact-channel.md
    criteria: [AC-2]
versions:                             # what it was written against
  model-input: 3.1.0
  service-d-api: v2
environment: sit                      # dev | sit: never production
automation: candidate                 # manual | candidate | automated
automated_by: null                    # the automated test's path and name, once there is one
---
```

- **`level`:** `component` is one component on its own, its neighbours stubbed; `contract` is the agreement between
  two (a schema, an API) checked from both sides; `integration` is two or more components together; `system` is the
  whole system through its interface; `end-to-end` is a user's journey across it, from the upstream to the screen.
- **`path`:** `happy` is the criterion's main path; `alternate` is another valid one (none, empty, another branch);
  `error` is a failure: an upstream fault, bad input, no access.
- **`priority`:** `high` when a failure blocks the requirement's purpose or loses or misstates data; `medium` when it
  degrades it and there's a workaround; `low` when it's cosmetic.
- **`status`:** `draft` until it's reviewed. `approved` once the BA confirms it tests what the criteria mean and the
  tester confirms it can be run, with Open questions empty. `created` once it's in the test tool, with its `id`.
  `retired` when it no longer applies: it's kept, with a line under Open questions saying why.
- **`verifies`:** each story by its path in the BA repo, pinned to a commit in a git checkout
  (`work/REQ-101/stories/ui-react-06-contact-channel.md@3f9c2a1`), and the criteria by their ids there.
- **`versions`:** the model's version, and each API's, by the names the component catalog gives them. A case run
  against another version may pass for the wrong reason.

## Body

Nine sections, with these headings, in this order:

| # | Heading | Required | Holds |
|---|---|---|---|
| 1 | `## Objective` | Yes | One sentence in business words: what the case proves, naming each criterion by id and title, and what makes this case different from its neighbours ("for a customer who chose SMS") |
| 2 | `## Preconditions` | Yes | Bullets, each checkable before the first step: the environment and the versions deployed there; settings and feature switches; the user and their role; each stub standing in for an upstream, and what it answers; the data that must, or mustn't, exist |
| 3 | `## Test data` | Yes | A table: Name, Value, Why (the class or boundary it stands for), Source (made up, a stub, `bridge-kit payload get <service> <request id>`, or a step). Steps and results name the data in braces, `{customer}`, so a value is written once |
| 4 | `## Steps` | Yes | A table: #, Action, Expected result. One action a row, numbered from 1, each with a result someone else can observe |
| 5 | `## Checks along the data path` | When the data passes through more than one component | A table: Hop, Where to look, Expected. A row per component the data passes through, in the catalog's order, as the impact analysis's Data elements row names them: when the last step fails, the first hop that's wrong is where it broke |
| 6 | `## Pass criteria` | Yes | When the case passes: every step's expected result holds; the tolerances that apply (order, rounding, time zones); and under `**Never:**`, what must not happen |
| 7 | `## Cleanup` | Yes | What to undo afterwards so the next run starts the same, or "None." |
| 8 | `## Automation notes` | When relevant | Where it's automated, or how it could be: the level to automate it at, selectors that won't break (accessible names, test ids), and what's hard to control (time, order, other users) |
| 9 | `## Open questions` | Empty to approve | Anything unresolved, each naming who should answer. "None." when there's nothing |

Steps, with the data named:

```markdown
| # | Action | Expected result |
|---|---|---|
| 1 | Sign in as `{manager}` | The home page shows `{manager}`'s name |
| 2 | Open the customer panel of `{customer}` | The panel's heading is "Ada Lindqvist" |
| 3 | Look at the contact section | It says "Preferred contact: no preference given" |
```

The data path, for a value that crosses the system:

```markdown
| Hop | Where to look | Expected |
|---|---|---|
| Upstream | The stub's request log | One `GET /customers/{customer}` call, answered with no `contactPreference` |
| Internal model | `bridge-kit payload get service-a-java {request}`: `CustomerRecord.contactPreference` | Not there |
| Customer API | `GET /v2/customers/{customer}`: `contactPreference` | Not there |
| UI | The customer panel's contact section | "Preferred contact: no preference given" |
```
