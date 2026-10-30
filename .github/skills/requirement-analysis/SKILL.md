---
name: requirement-analysis
description: Step-by-step procedure for taking a BA's requirement from its first notes to a package the specialists can build - gathering it as the work item's inputs, breaking it into parts each tied to a kind of spec, evaluating it for gaps, ambiguity and testability, working the BA's answers in as decisions, and handing off to the next specialist by bridge-kit work status. Covers the shapes of breakdown.md, evaluation-NN.md and decisions.md. Use when a BA brings a new requirement, or asks where a work item stands or what's next.
metadata:
  version: 0.1.2
  owner: ba-team
---

# Analysing a requirement

The goal is a requirement the specialists can work from without guessing: split into parts each one of them can
take, with its gaps found and asked about before anyone builds on them. You don't design the model, draft mappings
or write stories: the specialists do. You make sure each starts from a clear requirement, and you tell the BA where
the work item stands and what's next. Every command goes through `.github/bridge-kit/bin/bridge-kit`, each on its own.

## 1. Where it stands

Run `bridge-kit work status <id>` first, every time. It lists the work item's steps (the requirement, the breakdown, the
evaluation, the impact, the model change, the mapping specs, the stories, the validation, publishing), each done, to
do, with problems or not needed, and the next step. Work on that step if it's yours (sections 2 to 5); otherwise hand
off (section 6).

## 2. The requirement, as inputs

Everything the requirement comes from is an input of the work item (`work/<id>/inputs/`):

- a GitLab story: `bridge-kit inputs add gitlab:<story> --work-item <id>` (the `gitlab-reading` skill);
- documents, emails, images: `bridge-kit inputs add <file> --work-item <id>` (the `document-reading` skill);
- what the BA says in the chat: `work/<id>/inputs/requirement.md`, in the BA's words, with who asked and when. Write
  it only from what the BA said, and show it to the BA.

## 3. The breakdown

`work/<id>/breakdown.md`: the requirement split into parts, each one tied to the kind of spec that carries it.

````markdown
---
work_item: REQ-101
requirement: <the requirement's title>
---

# Breakdown: REQ-101

<Two or three sentences: what's asked, for whom, and why.>

## Parts

| # | Part, in business words | Kind of spec | Who takes it | From |
|---|---|---|---|---|
| 1 | The customer's preferred contact channel, on the customer panel | model change, mapping spec, UI | Impact Analyzer first | `inputs/01-story-req-101.md` |

## Cases it names

- <the cases the requirement names: nothing there, a failure, an empty state, an exception>

## Out of scope

- <what someone might expect here that the requirement doesn't ask for>
````

The kinds of spec: a model change (new or changed fields), a mapping spec (data from an upstream), an assembly
change (when or how an upstream is called), an output (what the summary shows), a UI or API
change with data already there. When the parts are clear, the next step is the impact analysis (`/impact <id>`):
which components each part touches.

## 4. The evaluation

`work/<id>/evaluation-NN.md`, `NN` the next number from `01`: the requirement checked part by part, before anyone
builds on it.

````markdown
---
work_item: REQ-101
evaluated: 2026-10-29
---

# Evaluation 01: REQ-101

## Blocking questions

- The BA: what does the panel show for a customer with no preference?

## Other questions

- The upstream team: can a customer have more than one preferred channel?

## Checked

- <each part, and what was checked: the model has it or not, the glossary's term, an existing mapping>
````

- **Gaps:** a case the requirement doesn't say (nothing there, a failure, an empty state).
- **Ambiguity:** words two people would read two ways; a business term the glossary doesn't have (`bridge-kit
  knowledge term "<words>"` finds what the glossary, the model and the profiles have).
- **Testability:** a part nobody could tell is done.
- **Conflicts:** with what the model, the assembly spec or an existing mapping already says.

A question that changes what's built is **blocking**: the work doesn't go on until it's answered. Each question
names who should answer. "None." under a heading when there's none.

## 5. The answers, as decisions

When the BA answers (below the question, as `Answer (the BA): …`, or in the chat), record each one in
`work/<id>/decisions.md`, adding to it:

```markdown
## 2026-10-29: a customer with no preference is shown as having none

- **What:** breakdown part 1: the panel says "Preferred contact: no preference given"
- **Who:** the BA
- **Why:** the answer: "say so, rather than leave it blank"
```

Never change an earlier evaluation: when the answers change the requirement, write the next evaluation, and the
blocking questions it still has.

## 6. Handing off

When the next step is a specialist's, say so, and how to start it:

| Next step | The specialist | Prompt |
|---|---|---|
| Impact | Impact Analyzer | `/impact <id>` |
| An upstream's spec to understand | Spec Explorer | `/explore-spec <spec> <what to find>` |
| Model change | Model Designer | `/model-change <id>` |
| Mapping specs | Mapping Drafter | `/draft-mapping <id>` |
| Stories | Story Writer | `/write-stories <id>` |
| Validation | Spec Validator | `/validate <id>` |
| Publishing | (the BA's OK, then the command) | `/publish-stories <id>` |
| Tests | Test Designer | `/write-tests <id>` |

In VS Code the agent's handoffs offer them as buttons. Never do a specialist's work yourself, and never move past a
step with problems: tell the BA what they are.

## 7. Never

- **Never write what a specialist owns:** the model, mapping specs, `impact.md`, stories, validation reports.
- **Never answer a question for the BA,** or write a decision the BA didn't make.
- **Never guess a term:** ask.
- **No client data** in the work item: describe fields and behaviour, never values from real records.
