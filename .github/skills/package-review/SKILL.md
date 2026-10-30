---
name: package-review
description: Step-by-step procedure for reviewing a requirement package as each component's developer would, before the developers' implementable check - running bridge-kit validate package, then reading every story with the files it implements and listing the questions a developer would have to ask - contradictions between files, rules two developers would code differently, behaviour no file gives - each with its file, row or criterion, who answers it and whether it blocks. Covers what is and isn't a finding, and the report's format in work/<id>/validation-NN.md. Use when validating a work item's package.
metadata:
  version: 0.1.1
  owner: ba-team
---

# Reviewing a requirement package as its developers

The goal is a package each component's team can build from without coming back to ask. `bridge-kit validate package`
finds what's missing or inconsistent in the files' shape: a story for every component, every file approved, one
model version. What it can't find is whether the words say enough: a rule two developers would code differently, a
Note that says something other than its row, a criterion that contradicts a spec. That's your part. Read as the
developer who has to build it tomorrow, with nobody to ask.

You report; you never fix. Every finding goes back to whoever owns the file.

## 1. Run the package check

Run `.github/bridge-kit/bin/bridge-kit validate package <id>` as its own command. Copy its errors and warnings into your
report's Package check section as it gives them. Don't turn them into findings of your own and don't argue with them:
an error blocks the package whatever you find.

If the command can't run at all (no work folder, no `impact.md`), report that and stop.

## 2. Read the package

1. `work/<id>/inputs/requirement.md`: what was asked, including the cases it names (nothing there, a failure, an
   empty state).
2. `work/<id>/impact.md`: the components affected, why, and their contract changes. The Impact Analyzer writes it
   (or the BA, from `templates/impact.md`); the package check has already run `bridge-kit validate impact` on it.
3. `work/<id>/decisions.md`: what's been decided, by whom. A decision answers a question; don't ask it again.
4. Each story in `work/<id>/stories/`, and with it every file its `implements` names: the model change
   (`work/<id>/model-change.md`), the mapping specs, the assembly spec.
5. `mappings/FORMAT.md` for what each rule and If missing value means, and `templates/story.md`'s Component details
   for what each component's team needs.
6. The inputs' open questions (`work/<id>/inputs/`, such as the spec digest's): each should be answered by now, in
   a spec or in `decisions.md`.

## 3. Read as each component's developer

For each story, take that component's place and ask of everything it implements: could I build this, and test it,
without asking anyone? Look in the other files before you call something missing: a fact may be stated once, in
another file.

**A mapping spec, row by row:**

- **Rule and If missing agree with the Notes.** A Note that says the row behaves otherwise than its If missing (or
  hints at it: "the whole balance goes") is a contradiction. An `omit` on a field its object can't be without must
  say what happens to the object.
- **Conditions have every branch:** what each value gives, and what any other value gives.
- **Derivations can be computed as written:** every input named, the formula, rounding and scale.
- **Dates and times are fixed:** which of the upstream's dates, the date part or the instant, which time zone, what
  precision.
- **Amounts, units and scales:** the currency, the scale, a sign convention.
- **Lists:** the order, duplicates, and how one item is chosen when the target takes one ("the latest": by which
  date, and on a tie?).
- **Codes:** what happens to a code no lookup row has, when there's no Otherwise.

**The assembly row:** when the upstream is called, with every value its request needs, what each kind of failure
does, and what its branch holds when the call isn't made or returns nothing.

**The model change:** each added field's type, whether it's required, its allowed values, and the version; every
consumer it breaks named.

**Each story:**

- Every acceptance criterion agrees with the spec rows it touches. A criterion that expects another value than the
  row gives, or a case the spec handles otherwise, is a contradiction.
- Every criterion can be run: a Given a tester can set up, a When, a Then they can check.
- Its Component details hold what the template lists for its component.
- What the requirement asks reaches the component that shows it: a case the requirement names (a customer with
  nothing to show) has a criterion in the stories that carry it.

**Across stories:** a field keeps its name and meaning on every hop from the model to the screen, or the story that
renames it says so; the empty and error states agree from where the data is collected to where it's shown.

## 4. What is a finding

A finding is a question a developer would have to ask before or while building, or a contradiction between two
files. For each, decide:

- **Blocking:** the developer can't build it right without the answer: a contradiction, missing behaviour, a rule
  two developers would code differently.
- **Not blocking:** they can build it, but someone should confirm: a Note that could be clearer, an assumption worth
  stating.
- **Who answers:** the BA (what something means, what's shown), the upstream team (what the upstream sends), the
  model's owners, or the component's team.

Not a finding:

- Wording, style or layout.
- A fact another file of the package gives.
- What a decision in `decisions.md` already settles.
- How a team builds it: class names, code structure, libraries. The package says what, not how.
- Work for a later requirement.
- Anything `bridge-kit validate package` already reported.

Write a finding as the question the developer would ask, with what's unclear: "Row 1.4 omits a missing currency,
but the balance needs one: is the whole balance left out, as the Note implies?", not "Row 1.4 is unclear".

## 5. Write the report

Write `work/<id>/validation-NN.md`, `NN` the next free number from `01`. Never change an earlier report.

```markdown
---
work_item: REQ-101
validated_by: spec-validator@0.1.0
package_check: pass                   # bridge-kit validate package: pass (no error) or fail
verdict: ready                        # ready: the check passes and no finding blocks; else not ready
---

# Validation 01: REQ-101

## Verdict

Ready for the developers' implementable check.

## Findings

| # | File | Where | Question | Who answers | Blocking |
|---|---|---|---|---|---|
| 1 | `mappings/upstream-1/get-customer.md` | row 1.1 | What does `channel` hold for a code the lookup doesn't have? | the BA | yes |

## Package check

No errors or warnings.
```

- **Verdict:** "Ready for the developers' implementable check." when the package check passes and no finding
  blocks; else "Not ready:" and how many findings block, and the package check's errors.
- **Findings:** one row each, blocking first. File is the path in the BA repo, in backticks. Where is `row <n>`,
  `AC-<n>`, `assembly row <n>`, `header` or `section <name>`. Blocking is `yes` or `no`. "None." under the heading
  when there's no finding.
- **Package check:** the command's errors and warnings as it gave them, or "No errors or warnings."
