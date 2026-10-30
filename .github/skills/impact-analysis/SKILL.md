---
name: impact-analysis
description: Step-by-step procedure for working out which components a BA's requirement touches and how - turning its business words into data elements, following each one through every component in the catalog's order to find where it stops, placing changes that aren't about data by the components' profiles, classifying each contract change as additive or breaking, giving each a confidence, and writing work/<id>/impact.md from templates/impact.md. Use when analysing a requirement's impact, or checking whether a component is touched.
metadata:
  version: 0.1.1
  owner: ba-team
---

# Analysing a requirement's impact

The goal is `impact.md` a BA can review without reading code and a Story Writer can turn into stories: every
component the requirement touches, why, with the evidence beside each claim, how each one's contracts change, and how
sure that is. A component wrongly left out costs a team a surprise late; one wrongly put in costs a story nobody
needs. When the evidence doesn't settle it, say so with a lower confidence and a question, never a guess.

The format is `templates/impact.md`. The components, their order and their contracts are
`architecture/components.yaml`. What each component does is its **profile**, the file its catalog entry names under
`profile` (`architecture/components/<name>.md`). Its examples use a made-up model (`CustomerRecord`, `REQ-101`).

## 1. Read the requirement

The work item's requirement (`work/<id>/inputs/requirement.md`), or what the BA gave instead: a GitLab story (read
with the `gitlab-reading` skill), or documents (the `document-reading` skill), kept as the work item's inputs. Also the
work item's model change (`work/<id>/model-change.md`), mapping requests and spec digests, when they exist: they say
what's already decided.

Write down, in the BA's words: what's asked, for whom, and the cases it names (nothing there, a failure, an empty
state).

## 2. Read the components

- `architecture/components.yaml`: each component's `order`, the contracts it `owns` and `consumes`, `external` and
  `defines_schemas`.
- Every component's profile: What it does and doesn't do, Business areas and data, Contracts, Screens or
  Operations, Where changes go, and Signs a requirement touches it.

A component without a profile is read from its checkout, when `bridge-kit.yaml` declares one, as the
`/profile-component` prompt would: its README, build files, specs and entry points. Say so in its Why, and give it no
more than medium confidence.

## 3. Turn the business words into data elements

For each thing the requirement asks to see, keep or change:

1. **The glossary first:** `bridge-kit knowledge term "<the BA's words>"` gives the glossary's terms that match, with
   their data elements, then the model's fields and the profiles' business terms that match.
2. **The internal model.** Search its schemas' names and descriptions for the BA's words and their synonyms
   (`grep -rn -i "<word>" <model checkout>/<schemas folder>/`, the folder `model.layout.schemas` in `bridge-kit.yaml`
   names). A field whose description means what's asked is the data element: write its path from the payload root.
3. **The profiles' Business areas and data** tie business terms to fields and screens in each component.
4. **The work item's model change** names the paths it adds: an element that isn't in the model yet is one of those.
5. **A term you can't place** becomes an open question, naming who should answer. Never place it on a guess. Once
   the BA settles one, it belongs in the glossary (`architecture/glossary/<area>.yaml`): say so.

## 4. Follow each element through the components

Walk the components the data passes through, in the catalog's order. For each, say whether it has the element
today, with where, or that it's missing, or that you can't tell:

| Component's kind | Has the element when | Look in |
|---|---|---|
| The model (owns the schemas) | a schema has the path | its schemas; the model change |
| A collecting service (fills the model from upstreams) | a mapping spec's row fills the path | `mappings/`, by the target field; the assembly spec |
| A service that consumes the model or another's API | it reads the field and passes it on | its profile's data and operations; its checkout, by the field's name or its generated getter |
| An API another component or a client calls | its spec has the field | the spec its profile names, in its checkout |
| The UI | a screen shows it | its profile's Screens; its checkout, by the screen's component |

Every missing hop is work for that component. Write the result as the Data elements table: a row per element, a
column per component, each cell where it is or "missing".

Look in a checkout only when `bridge-kit.yaml` declares it, read-only, and cite the file and line. When the profile and
the code disagree, the code wins, and say so.

## 5. Place what isn't about data

A change to behaviour, wording, layout, a calculation, access or error handling has no lineage. Place it by the
profiles: What it does, Where changes go, Signs a requirement touches it. When two components could own it, put it
in the one whose profile says so, with medium confidence, and ask under Open questions.

## 6. Each affected component's contract changes

Only the contracts the component **owns**. A contract it consumes changes in its owner's section, never its own.

- **Additive:** a new optional field, a new endpoint or operation, a new enum value a consumer may ignore.
- **Breaking:** a field removed, renamed or moved; a type changed; a new required field; a value that means
  something else now. For the model's schema contracts, the model change's `bridge-kit model diff` says which, when
  there is one.
- **A component that never defines a schema** (`defines_schemas: false`) changes no schema contract. A new output
  field is the model's component's change, and this one consumes it.
- **External impact,** for a component whose contracts outside clients use (`external` in the catalog): whether
  they're affected, the API version, what the gateway and the clients must do, or none.

## 7. Confidence

- **High:** the code, a spec or a schema says it, cited by file and line.
- **Medium:** only a profile says it, or the code shows it but not all of it.
- **Low:** inferred. A low one is also an open question: what would settle it, and who answers.

## 8. Write impact.md

`work/<id>/impact.md`, from `templates/impact.md`:

- the front matter (the work item, the requirement's title);
- the Data elements table, and a sentence on what it shows;
- under Affected components, a `###` per affected component, named as the catalog names it, with its Why (the
  evidence, the package files that say so by their path in backticks), Contracts, External impact where it applies,
  and Confidence;
- under Not affected, every other component of the catalog, each with why it isn't touched;
- Open questions, each naming who should answer, or "None."

## 9. Check it

```bash
.github/bridge-kit/bin/bridge-kit validate impact <id>
```

Run it as its own command, and fix every error. It checks that every catalog component is accounted for, the
contract changes against what each component owns, the external impact, the confidence, and the files cited.

## 10. Analysing again

When `impact.md` is already there (the requirement or the package changed), update it in place: keep each answered
question with its answer, and say in the Why what changed since.
