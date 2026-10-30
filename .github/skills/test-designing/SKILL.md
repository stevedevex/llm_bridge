---
name: test-designing
description: Step-by-step procedure for writing a work item's test cases from its approved stories - by the test case template, each case derived from acceptance criteria by a technique, at the lowest level that can see the rule, with made-up data, observable results and checks along the data path - from the stories, impact.md, the mapping specs and the model change. Covers planning the cases, the header, each section, the data path's hops, open questions, and checking the set with bridge-kit validate test-case and bridge-kit tests coverage. Use when writing or rewriting a work item's test cases.
metadata:
  version: 0.1.0
  owner: ba-team
---

# Writing a work item's test cases

The goal is a set of cases a tester can run without asking, that together prove every acceptance criterion of the
work item's stories, and that say where a failure started. The format is `templates/test-case.md`, with a complete
case in `templates/test-case.example.md`; this skill says how to work out what goes in them. A case is worth its
precision: exact data, exact places to look, results anyone can see. A guessed behaviour costs a tester a false
failure, or a real one missed.

## 1. Read the package

1. The stories, `work/<id>/stories/*.md`, approved or created. If any is a draft, stop: cases are written from
   approved criteria. Each criterion is an `### AC-<n>:` heading over a gherkin block.
2. `work/<id>/impact.md`: its **Data elements** table gives the hops a value passes through, in the catalog's order,
   and where it is at each (a path, a field, a screen). Those are the rows of a case's data path.
3. The files the stories implement: the mapping specs (each row's rule, its codes, its default, what happens when
   the source is missing), the assembly spec (when an upstream is called, with what, and what a failure does), and
   `work/<id>/model-change.md` (the paths it adds, the model's new version). Rules there are the decision tables
   behind a criterion's words.
4. `architecture/components.yaml` and each affected component's profile, when it has one: the endpoints, screens and
   operations a step names.
5. Real payloads, only when the BA gives request ids, with the `payload-reading` skill: they show a field's shape, how
   often it's null, which codes occur. Never copy a value from one into a case.

## 2. Plan the cases

Before writing a file, list the cases, each a line: what it proves, the criteria by story and AC id, its level, its
path and its technique. Then show the BA the plan with your reply.

1. **Each criterion's main path,** once. A value that crosses components gets one end-to-end case that follows it
   through every hop: it carries the main path of each hop's criteria.
2. **Each technique, in turn** (the template's "From criteria to cases"):
   - **equivalence:** one case per class that should behave alike: one, many, none;
   - **boundary:** the edges: an empty list, zero, the most, a date at midnight UTC, spaces in a value;
   - **decision-table:** each condition a criterion lists is its own case: "no customer id, an empty result, or a
     fault" is three;
   - **state-transition:** each allowed change, and one that isn't;
   - **error-guessing:** a code the mapping doesn't list, a duplicate, an upstream that's slow or fails.
3. **The lowest level that can see a rule.** A mapping rule is a `component` case of the service that applies it;
   a contract between two components is a `contract` case; the user's view is a `system` or `end-to-end` case. Don't
   prove at the screen what a component case proves more simply.
4. **Every error path** a criterion or the assembly spec names gets an `error` case, and every accessibility,
   performance or security criterion a case of that `type`.
5. **A schema change** in the model's own story is checked by `validate model` and the model's build, not by a case.
6. **One behaviour a case.** If a case would prove two outcomes that can fail on their own, split it.

## 3. Write each case

`work/<id>/tests/tc-<nn>-<slug>.md`, `<nn>` its number, two digits; `case: TC-<n>` the same number.

1. **Header:** from the template. `status: draft`, `id: null`, `environment: sit` unless the story says dev,
   `automation: candidate` or `manual`, `versions` from the model change and the stories (the model's version, each
   API's), `verifies` each story by its path with the criteria the case proves.
2. **Objective:** one sentence, naming each criterion by id and title, and what sets this case apart from its
   neighbours.
3. **Preconditions:** what must be true before step 1, each checkable: the environment and versions, each stub and
   what it answers, the user and role, the data that must or mustn't exist.
4. **Test data:** every value, named once, `{entity}`, with why it was chosen (the class or the boundary) and its
   source. Values are always made up: names, numbers, emails, identifiers. Reuse the model's own examples where they
   fit.
5. **Steps:** one action a row, each with a result someone else can observe. Name the data in braces. Ten steps at
   most.
6. **Checks along the data path:** for a `system` or `end-to-end` case whose value crosses components, a row per hop
   from `impact.md`'s Data elements, in the catalog's order. For a stored hop, the command that shows it:
   `bridge-kit payload get <service> {request}` and the path, and `bridge-kit payload check` where the model's shape
   is the point. For an API, the call and the field. For a screen, the section and what it shows.
7. **Pass criteria:** every step's result and every hop; the tolerances that apply (order the story doesn't fix,
   rounding, a date stored as midnight UTC); and under `**Never:**` what must not happen.
8. **Cleanup:** what to undo, often the stub's answer; "None." when the case only reads.
9. **Automation notes:** when it helps: the level to automate at, selectors by accessible name, what's hard to
   control.
10. **Open questions:** anything the stories, the specs or the profiles don't say that a result depends on: the
    wording on a screen, where an environment shows a request id, an order nobody fixed. Each names who should
    answer. Never settle one yourself.

## 4. Check the set

1. Run `.github/bridge-kit/bin/bridge-kit validate test-case work/<id>/tests` and fix every error. Read each warning:
   change the case, or say in your reply why it stands.
2. Run `.github/bridge-kit/bin/bridge-kit tests coverage <id>`. An error is a criterion no case verifies: add one. A
   warning is a hint from a criterion's words: add the alternate, error or non-functional case it asks for, or say
   why the criterion doesn't need one.

## 5. Writing again

When the BA or the tester answers questions, or a story changes:

- Keep every case's number: a case that no longer applies becomes `retired`, with a line under Open questions saying
  why. Never renumber.
- A case whose criteria or versions changed goes back to `draft`.
- Add cases with the next free numbers.
- Run both checks again.

## 6. Never

- **Never approve a case.** It stays `draft`; the tester and the BA approve.
- **Never invent behaviour.** A result the stories don't fix is an open question, not a guess.
- **Never copy a value** from a real payload, a document or a GitLab story into test data: shapes and codes only.
- **Never write outside** `work/<id>/tests/` and `.work/tmp/`. A story that seems wrong is a question for the BA, not
  an edit.
