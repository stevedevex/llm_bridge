# Spec Validator

Checks a requirement package before you approve it and hand it to the developers, as each component's developer
would read it: what they'd have to come back and ask. It never fixes anything; every finding goes to whoever owns the
file.

| | |
|---|---|
| **Start it** | `/validate <id>` |
| **`<id>`** | The work item, such as `REQ-101` |
| **Before you run it** | The package: `impact.md`, the model change, `decisions.md`, the stories, and the files they implement |
| **It reads** | The whole package; `templates/story.md` and `mappings/FORMAT.md`, for what each part must give |
| **It writes** | Its report, `work/<id>/validation-NN.md`, `NN` the next free number |
| **It checks with** | `bridge-kit validate package <id>`, every file's own check and what the files must agree on |
| **You decide** | Each finding's answer, and when to approve the package |

## What the report holds

- **The verdict:** ready for the developers' "implementable" check, or not. Ready only when the package check passes
  and no finding blocks.
- **The findings:** each a question a developer would ask, pinned to its file and its row, criterion or section;
  whether it blocks (they can't build it right without the answer); and who answers: you, the upstream team, the
  model's owners or the component's team.
- **The package check's result:** every error stands as it is.

## What `validate package` checks

Every file's own validator; everything approved and nothing left open; one story per affected component and none
for another; every cited file implemented by a story; one model version and contract changes that agree across the
files; every new model path with an owner; every mapping spec with its assembly row; the requests and the digests
agreeing with the specs; and every cell of your rough mapping a spec cites.

## Tips

- Run it again after each round of fixes: each report gets the next number, so you can see what changed.
- A finding isn't about wording or style: it's a question a developer would really have to ask.

## When it stops

- **The preflight stopped:** fix what it says, and run it again.

Related: [Story Writer](story-writer.md), `/publish-stories` (next, once it's ready), the `package-review` skill.
