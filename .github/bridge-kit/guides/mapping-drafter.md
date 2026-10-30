# Mapping Drafter

Drafts the mapping spec for how one upstream operation's data fills the shared model, a row per field, by
`mappings/FORMAT.md`: each field's source, its rule, what happens when it's missing, and its codes. It drafts from
what you give it, never from code, and leaves every business decision to you.

| | |
|---|---|
| **Start it** | `/draft-mapping <id> [<upstream> <operation>]` |
| **`<id>`** | The work item, such as `REQ-101` |
| **`[<upstream> <operation>]`** | Which request, when the work item has more than one |
| **Before you run it** | A mapping request in `work/<id>/inputs/`: `mapping-request.md`, or one `mapping-request-<operation>.md` per operation, filled in from `mappings/REQUEST.md`; the model change, when the model has no place for the data yet; the digest, for a new upstream |
| **It reads** | The request; the target's schemas in the model; the upstream's fields (the digest, `bridge-kit spec digest`, or a vendor jar); `mappings/FORMAT.md`, shared lookups, the assembly spec, reviewed specs as examples; your rough mapping, when the request names it; real payloads, when you give request ids |
| **It writes** | `mappings/<upstream>/<operation>.md`; `lookups/<name>.md`; the target's row in `assembly/<root>.md`; on a second turn, `work/<id>/decisions.md` |
| **It checks with** | `bridge-kit validate request` first, then `bridge-kit validate mapping <file>` |
| **You decide** | Every row marked `proposed`: a fallback, a default, a filter, a field left out, a choice between two fields |

## The mapping request

Copy `mappings/REQUEST.md` to `work/<id>/inputs/mapping-request.md` and fill in its header (the work item, the
upstream and operation, the target payload path, the spec, the digest, your rough mapping and its sheet) and its
sections: the purpose, and whatever rules, codes and calling details you know. The more you settle there, the fewer
rows come back as questions.

## Two turns

1. **The draft:** every field of the target with its source by meaning; your request's rules and your rough
   mapping's rows applied, each citing its cell; every other business decision `proposed`, with a question.
2. **Your answers:** write them under the questions, and run `/draft-mapping <id>` again. It works each answer into
   its row, records what, who and why in `decisions.md`, keeps every unanswered question as it is, and asks again
   where an answer opens something new.

## Tips

- What the request asks for and the model doesn't have comes back under "Proposed internal model changes": that's
  the Model Designer's.
- A row from your rough mapping that doesn't fit the spec, the model or FORMAT comes back as a question, not a
  silent change. Struck, coloured, commented or hidden rows aren't taken as decisions.
- A draft stays `draft` until you approve it.

## When it stops

- **`validate request` reports errors:** the request is missing something; it says what to add.
- **A source it can't find in the spec:** it asks rather than inventing one.

Related: [Spec Explorer](spec-explorer.md), [Model Designer](model-designer.md), the `mapping-drafting` and
`mapping-format` skills, `mappings/FORMAT.md`.
