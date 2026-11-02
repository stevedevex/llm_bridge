# Story Writer

Writes the user stories for a requirement package: one per component the requirement touches, by
`templates/story.md`, each telling that component's team what changes and how anyone can tell it's done, in the
order the work can be done. A team builds from its story, so it states facts and leaves open what isn't settled.

| | |
|---|---|
| **Start it** | `/write-stories <id>` |
| **`<id>`** | The work item, such as `REQ-101` |
| **Before you run it** | `work/<id>/impact.md`, passing `bridge-kit validate impact <id>`; the package files it cites (the model change, mapping specs, the assembly spec) |
| **It reads** | The requirement; `impact.md` and every file it cites; the component catalog, each affected component's profile and its team's own knowledge; a GitLab story or documents you name |
| **It writes** | `work/<id>/stories/<component>-<nn>-<slug>.md`, one per affected component, `<nn>` its order |
| **It checks with** | `bridge-kit validate story work/<id>/stories` |
| **You decide** | Each story's approval; every open question it carries over from `impact.md` |

## What each story holds

- **The header:** the component, its order (the catalog's, contract first: each contract's owner before its
  consumers, so the shared model first), the stories it's blocked by, the contracts it changes, the package files it
  implements, its labels.
- **The story** ("As a ..., I want ..., so that ..."), its context, its scope in and out, its contracts and data.
- **Acceptance criteria,** `AC-1` on, each in Given, When and Then: what the Test Designer turns into test cases.
- **Component details** for that team, its dependencies, anything non-functional, and its open questions.

## Tips

- When the catalog points to a team's own agents and prompts (`knowledge: playbooks`), its story names the ones that
  fit the work, so the team starts from its own tools.
- Its components are exactly `impact.md`'s Affected components: to change the set, change `impact.md`.
- A low-confidence item or an open question in `impact.md` comes through to the story's Open questions; a story
  isn't approved while they're open.
- It writes local files only. Publishing them to GitLab is `/publish-stories <id>`, after `/validate <id>`.

## When it stops

- **No `impact.md`, or `validate impact` reports errors:** run `/impact <id>` first, or fix it.
- **`validate story` reports errors:** it fixes them before it finishes.

Related: [Impact Analyzer](impact-analyzer.md), [Spec Validator](spec-validator.md), [Test Designer](test-designer.md),
the `story-writing` skill, `templates/story.md`.
