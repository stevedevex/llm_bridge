# Model Designer

Changes the shared model, the JSON schemas every service shares, for a requirement: a new field, a coded value, a
fix, or the place a new upstream's data goes. Or it finds the model already has what's asked. Every service
depends on the model, so it reuses before it adds, and asks before it changes anything it isn't sure of.

| | |
|---|---|
| **Start it** | `/model-change <id> <what the model needs>` |
| **`<id>`** | The work item, such as `REQ-101` |
| **`<what the model needs>`** | The data items, one a line, in business words; or the fix to an existing field |
| **The digest** | The prompt asks for it: the Spec Explorer's digest, for data from a new upstream; or none |
| **Before you run it** | The model's repo declared read-write in `bridge-kit.yaml`, with `model-designer` among its writers; its layout and conventions set there (`/profile-model` proposes them); its `CONVENTIONS.md` |
| **It reads** | The model's checkout and its `CONVENTIONS.md`; the digest; a GitLab story or documents you name; real payloads by request id, when you give them (`payload-reading`) |
| **It writes** | The change in the model's checkout (schemas, examples, version files); `work/<id>/model-change.md`, the merge request description |
| **It checks with** | `bridge-kit model start <id>` before changing; `bridge-kit model diff <id>`; `bridge-kit validate model <id>`, which also runs the model's build |
| **You decide** | The change, and whether to raise the merge request; the model's owners review and merge it |

## What it gives you

- **The change:** each item asked for at its payload path, or the existing field it reused, in the model's own names
  and codes (the upstream's belong in the mapping specs).
- **Its kind and version:** additive or breaking, and the version that follows, set in every version file.
- **The consumers it breaks,** for a breaking change, by `model diff`.
- **The merge request description,** `model-change.md`: what changed and why, the consumers, the open questions.

## Tips

- It models only what's asked, never an upstream's whole shape. Anything else that looks needed becomes a question.
- Give it request ids of real payloads (dev or SIT) when the shape matters: nulls, list sizes, the codes that occur.
- It never pushes or opens the merge request: that's yours, once you've reviewed the description.

## When it stops

- **The model's repo isn't declared, or its path doesn't exist:** fix `bridge-kit.yaml`.
- **`validate model` fails:** a convention, the version, the example or the build; it fixes what it can and says
  what's left.

Related: [Spec Explorer](spec-explorer.md) (its digest), [Mapping Drafter](mapping-drafter.md), the
`model-designing` skill, `/profile-model`.
