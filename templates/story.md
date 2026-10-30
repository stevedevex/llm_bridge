# Story template (`story@1`)

How a user story is written, whichever BA or agent writes it, so every story has the same shape. The Story Writer and
`bridge-kit validate story` follow this file; skills point to it rather than repeat it. The header's schema is
`templates/story.schema.json`.

A requirement gets one story per affected component, in the order of `architecture/components.yaml`: each contract's
owner before its consumers, so the shared model comes first. In local mode each story is a file:
`work/<id>/stories/<component>-<nn>-<slug>.md`, where `<nn>` is its order, two digits
(`service-d-java-05-contact-channel.md`).

## Header

```yaml
---
template: story@1
id: null                              # set when it's created in GitLab, e.g. SVD-311
parent: REQ-101                       # the requirement
component: service-d-java             # a component in architecture/components.yaml
title: Return the customer's preferred contact channel from the customer API
status: draft                         # draft | approved | created
order: 5                              # the component's order in the catalog
blocked_by: [S4]                      # the stories it waits for: S<order> until created, then their GitLab ids
contracts:                            # every contract this story changes, and how
  - { contract: service-d-api, change: additive }
implements: []                        # the package files it carries out, by path in the BA repo
labels: [component::presentation]     # the component's labels in the catalog
---
```

- A story is blocked by the story of each component whose contract it consumes and that changes in the same set.
  A story never comes before one it's blocked by, so `order` and `blocked_by` agree.
- `contracts` lists the contracts this story's component **owns** and changes: `additive` when every consumer keeps
  working, `breaking` when one has to change. A contract the story only consumes isn't listed; its change is in the
  story that owns it.
- `implements` names the package's files by their path in the BA repo. In a git checkout a path is pinned to the
  commit it was approved at: `mappings/upstream-1/get-customer.md@3f9c2a1`.

## Body

Nine sections, with these headings, in this order:

| # | Heading | Required | Holds |
|---|---|---|---|
| 1 | `## Story` | Yes | One sentence: "As a *role*, I want *capability*, so that *benefit*." The role is a business one (a relationship manager), never a component |
| 2 | `## Context` | Yes | Why, in two to four sentences, naming the parent requirement |
| 3 | `## Scope` | Yes | `**In scope:**` and `**Out of scope:**`, each with bullets |
| 4 | `## Contracts and data` | Yes | A table: Contract, Change, Fields, Notes. One row per contract in the header; the fields by their payload or API path. "None." when the story changes no contract |
| 5 | `## Acceptance criteria` | Yes | One or more criteria, each a `### AC-<n>: <title>` heading and a `gherkin` block with Given, When and Then. Numbered from 1, without gaps |
| 6 | `## Component details: <component>` | Yes | What this component's team needs, by its part (below); `<component>` is the header's |
| 7 | `## Dependencies` | Yes | `- Blocked by:` and `- Blocks:`, each the stories by reference and component, or "none" |
| 8 | `## Non-functional` | When relevant | Performance, security, personal data, logging, audit |
| 9 | `## Open questions` | Empty to approve | Anything unresolved, each naming who should answer. "None." when there's nothing |

An acceptance criterion:

````markdown
### AC-1: The customer API returns the preferred contact channel

```gherkin
Given a customer whose preferred contact channel is SMS
When a client asks the customer API for that customer
Then the response's contactPreference.channel is SMS
```
````

## Component details

What a component's team needs depends on its part in the system, as its profile and the catalog describe it:

| Its part | Covers |
|---|---|
| The UI (`ui-react`) | The screens and components affected; the loading, empty and error states; accessibility; designs, if any |
| An API with external clients (`service-d-java`) | The external API impact: breaking or not, the API version, what external clients are told, and the API gateway change |
| Business logic (`service-c-java`) | Which calls change, their order, and the error handling between services |
| A collecting service (`service-a-java`) | The upstream and the mapping specs involved, the assembly change, and what happens when the upstream fails |
| A summary service (`service-b-python`) | The output sections affected, calculation or narrative, and the output schema version it consumes. Never a schema change: that's the shared model's story |
| The shared model (`shared-model`) | The schema changes (additive or breaking), the version bump, and the consumers affected |
