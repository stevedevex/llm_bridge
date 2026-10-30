# Test Designer

Writes the test cases a tester runs to prove a work item's acceptance criteria, by `templates/test-case.md`: each
case one behaviour, with exact made-up data, results anyone can see, and, when a value crosses components, a check at
every hop, so a failure says where it started.

| | |
|---|---|
| **Start it** | `/write-tests <id>` |
| **`<id>`** | The work item, such as `REQ-101` |
| **Before you run it** | The stories approved (or created in GitLab); `impact.md`; the files the stories implement |
| **It reads** | The stories' criteria; `impact.md`'s Data elements (the hops); the mapping specs and the assembly spec (their rules become decision tables); the model change; the component profiles; real payloads, when you give request ids, for shapes only |
| **It writes** | `work/<id>/tests/tc-<nn>-<slug>.md`, one case a file |
| **It checks with** | `bridge-kit validate test-case work/<id>/tests` and `bridge-kit tests coverage <id>` |
| **You decide** | With the tester, each case's approval; every result the stories don't fix |

## How it plans

It shows you the plan before it writes: each case, what it proves, its criteria, its level, its path and its
technique.

1. Each criterion's main path once; a value that crosses components gets one end-to-end case through every hop.
2. Then each technique: one case per class of input (one, many, none); the edges (empty, zero, the most, midnight
   UTC); each condition a criterion lists (three conditions, three cases); state changes; what tends to break (an
   unknown code, a slow upstream).
3. Each case at the lowest level that can see its rule: a mapping rule at the service, the user's view at the screen.
4. Every error path and every accessibility, performance or security criterion gets its own case.

## What `tests coverage` tells you

A table of every criterion and the cases that verify it, then the gaps: a criterion no case verifies (an error), and,
from a criterion's wording, one that names failures with no error case, or reads as accessibility with no case of
that type (warnings).

## Tips

- A case stays `draft` until the tester and you approve it; an open question keeps it there.
- Its data is always made up; payloads only tell it what real data looks like.
- When a story changes, run it again: it keeps every case's number, sends changed ones back to draft, and retires
  what no longer applies.

## When it stops

- **A story is still a draft:** approve the stories first.
- **`validate test-case` or `tests coverage` reports errors:** it fixes them before it finishes.

Related: [Story Writer](story-writer.md), the `test-designing` skill, `templates/test-case.md` and its example.
