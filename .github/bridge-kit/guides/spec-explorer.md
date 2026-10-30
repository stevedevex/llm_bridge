# Spec Explorer

Reads an upstream system's spec for you (OpenAPI, Swagger or WSDL) and says in business terms what data it offers
and where the data you asked about is. The Model Designer and the Mapping Drafter work from its digest, so it marks
what it isn't sure of rather than guessing.

| | |
|---|---|
| **Start it** | `/explore-spec <spec> <what you need>` |
| **`<spec>`** | The spec as you have it: a file in the workspace, pasted content, a URL, Maven coordinates (`group:artifact:version`), or a pasted `<dependency>` or `<artifactItem>` block |
| **`<what you need>`** | The data you're looking for, one item a line; or "what does it offer?" |
| **The work item** | The prompt asks for it: name it, such as `REQ-101`, so the digest is kept with it; or none |
| **Before you run it** | Nexus reachable, for a spec given by coordinates (`bridge-kit spec resolve` tells you) |
| **It reads** | The spec, only through the spec resolver; a GitLab story or documents you name, as what to find |
| **It writes** | `work/<id>/inputs/spec-digest-<upstream>.md`, or `work/explore/spec-digest-<upstream>.md` without a work item |
| **It checks with** | `bridge-kit validate digest <file>` |
| **You decide** | Which of the spec's fields mean your data, when it offers near matches |

## What the digest holds

- **Summary:** what the spec offers, in business words.
- **Where the data is:** each item you asked about, with the operation and the field path exactly as the spec names
  them, its type, its codes, and what it means.
- **Not available:** what you asked for that the spec doesn't have, and any near match it rejected, with why.
- **Open questions:** what the spec leaves unclear.
- Below them, the listing `bridge-kit spec digest` generated: every operation and field. The agent never edits it.

## Asking it

- `/explore-spec com.example.upstream1:customer-api-spec:4.2.0` with "preferred contact channel, when it was given"
  for `REQ-101`.
- `/explore-spec https://<host>/openapi.json` with "what does it offer?", and no work item.

## Tips

- Ask for the business items you need, not the whole spec: a long spec is searched, never read end to end.
- An item under Not available isn't a failure: it's a question for the upstream team, or a sign the data comes from
  elsewhere.

## When it stops

- **The spec can't be resolved:** Nexus isn't reachable, or the coordinates are wrong. `bridge-kit spec resolve
  <coordinates>` says which.
- **`validate digest` reports errors:** it fixes them before it finishes.

Related: [Model Designer](model-designer.md), [Mapping Drafter](mapping-drafter.md), the `spec-exploring` and
`spec-resolver` skills.
