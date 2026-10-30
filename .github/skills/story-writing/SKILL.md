---
name: story-writing
description: Step-by-step procedure for writing a requirement package's user stories - one per affected component, from the story template, ordered contract first - from the work item's impact.md, the requirement and the package files it cites, against the component catalog and each component's profile. Covers which components get a story, the header (order, blocked_by, contracts, implements), each section's content, open questions, and checking the set with bridge-kit validate story. Use when writing or rewriting a work item's stories.
metadata:
  version: 0.2.2
  owner: ba-team
---

# Writing a requirement's stories

The goal is a set of stories each component's team can build from without asking: one story per component the
requirement touches, each saying what that team changes and how anyone can tell it's done, in the order the work can
be done. The format is `templates/story.md`; this skill says how to work out what goes in it. Never write prose to
pad a story: a team needs the facts, the contract changes and the criteria.

## 1. Read the package

1. `work/<id>/inputs/requirement.md`: who wants what and why. Its role ("a relationship manager") is the role in every
   story's sentence.
2. `work/<id>/impact.md`: the impact analysis, the Impact Analyzer's or the BA's, in the shape of
   `templates/impact.md`. Its **Affected components** are the stories you write, one each; its **Not affected**
   components get no story. For each affected component it gives why (the evidence), the contract changes (additive
   or breaking), the confidence, and for a component with outside clients the external impact.
3. Every package file `impact.md` cites: the model change (`work/<id>/model-change.md`), mapping specs, the
   assembly spec. Read them for the facts a team needs (versions, field paths, how an upstream is called, what
   happens when it fails), never to second-guess the impact.
4. `architecture/components.yaml`: each component's `order`, the contracts it `owns` and `consumes`, its story
   `labels`, and `defines_schemas: false` on a component that never defines a schema.
5. Each affected component's **profile**, the file its catalog entry names under `profile`
   (`architecture/components/<name>.md`), when it has one. It says, each fact citing the file it comes from:
   - where a kind of change goes in it (Where changes go);
   - its screens or its operations;
   - its business terms and data;
   - how it's built and tested.

   Use it for the facts a team needs in its story: the screen, the endpoint, the module the work is in, the test
   command. It never adds a component to the set or takes one out: `impact.md` decides that. When the profile and
   `impact.md` disagree (a screen the profile puts in another component, say), ask under the story's Open
   questions.
6. `templates/story.md`: the header, the nine sections, and what each component's section covers.

## 2. Decide the set

- **One story per component under Affected components**, and no other. If you think another component has work,
  don't write a story for it: ask under that requirement's open questions, in the story closest to it.
- Each story's **order** is the component's `order` in the catalog, and its reference is `S<order>` (`S1` for
  `shared-model`). File it as `work/<id>/stories/<component>-<nn>-<slug>.md`, `<nn>` the order in two digits.
- **`blocked_by`:** a story waits for the owner of every contract it consumes that another story in the set changes.
  Work it out from the catalog: for each contract in the component's `consumes`, if a story in this set lists that
  contract under `contracts`, add that story's `S<order>`. Nothing else blocks it: a component whose contracts don't
  change in this set isn't a dependency, however the work is scheduled. For example, if a set changes `model-output`
  (owned by `shared-model`, `S1`) and `service-c-api` (owned by `service-c-java`, `S4`), `service-d-java`, which
  consumes `service-c-api`, is blocked by `S4` only.
- **`contracts`:** only the contracts this story's component **owns** and that `impact.md` says change, with the
  change it gives (`additive` or `breaking`). A contract the story only consumes isn't listed: its change is in its
  owner's story.
- **`implements`:** the package files `impact.md` cites for this component, by their path in the BA repo
  (`mappings/<upstream>/<operation>.md`, `assembly/customer-record.md`, `work/<id>/model-change.md`). None when it cites
  none.
- **A component that never defines a schema never changes one** (`defines_schemas: false`). A new or changed output
  field is the story of the component that owns the model's contracts; the other component's story consumes it, and
  lists no schema contract.

## 3. Write each story

The header as the template shows it: `template: story@1`, `id: null`, `parent` the work item, `status: draft`, the
`labels` the catalog gives the component, and a `title` that says what it delivers in business words.

Then the sections, in the template's order:

1. **Story:** "As a *role*, I want *capability*, so that *benefit*", the requirement's role and benefit, the
   capability this component gives.
2. **Context:** two to four sentences: the requirement by its id, and why this component has work (from `impact.md`).
3. **Scope:** In scope and Out of scope, as bullets. Out of scope names what the other stories do, so nobody does it
   twice.
4. **Contracts and data:** a row per contract in the header (Contract, Change, Fields by payload or API path,
   Notes), or "None." when the story changes no contract.
5. **Acceptance criteria:** Gherkin scenarios a tester can run against this component alone, numbered `AC-1` on.
   Cover what the requirement asks, and the cases it names: nothing there, a failure, an empty state.
6. **Component details: `<component>`**, everything the template's table lists for the component's part, as its
   profile and the catalog describe it, with the facts from the package, and from its profile where the package
   doesn't say: where in the component the work goes (its Where changes go), the screens or operations it touches,
   citing the profile's files. A fact from the profile is "per its profile", since nobody has checked it against this
   requirement:
   - The shared model (it owns the model's contracts): each schema change by path, additive or breaking, the version
     it bumps to, and the consumers affected, from the model change.
   - A collecting service (it fills the model from upstreams): the upstream and its operation, the mapping spec, the
     assembly spec's row (what it's called with, and what happens when the upstream fails or there's nothing to call
     it with).
   - A summary service (`defines_schemas: false`): the output sections it fills; whether that's calculation or
     narrative; the output schema version it consumes.
   - Business logic: which calls and responses change, their order, and the error handling between services.
   - An API with external clients (`external` in the catalog): the external impact as `impact.md` gives it: breaking
     or not, the API version, what external clients are told and when, and the API gateway change (or that there's
     none).
   - The UI: the screens and components, and the loading, empty and error states; accessibility.
7. **Dependencies:** `- Blocked by:` and `- Blocks:`, each as references and components ("S1
   (shared-model)"), or "none".
8. **Non-functional**, when something applies: personal data, performance, audit.
9. **Open questions:** every open question and every **low-confidence** item `impact.md` gives for this component,
   each naming who should answer. Never settle one yourself, and never write around it in another section. "None."
   when there's nothing.

## 4. Check the set

- Run `.github/bridge-kit/bin/bridge-kit validate story work/<id>/stories` on the whole folder, as its own command, and
  fix every error. Read each warning: a dependency warning means a `blocked_by` the contract rule wants is missing.
- Every story stays `status: draft`: the BA approves, and only after its open questions are answered. Once the BA
  has approved the set, `/publish-stories <id>` creates them in GitLab (the `gitlab-writing` skill), never before.

## 5. Writing again

When `work/<id>/stories/` already has stories, update them in place: never a second story for a component. A story
that's no longer needed is reported to the BA, not deleted.
