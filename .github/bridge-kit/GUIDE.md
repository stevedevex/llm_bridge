# BRIDGE: a BA's guide

*From business ask to build-ready, faster.*

How a BA works a requirement with BRIDGE, day to day. What each command does is in the [README](README.md), and
setting BRIDGE up in a BA repo is its "Setting up a BA repo". Each agent has a page of its own in the
[agent guides](guides/README.md): what it needs, what it writes, what it leaves to you. The words BRIDGE uses are at
the end.

## How it works

- **Agents in Copilot's chat.** Each is started by a prompt, such as `/write-stories REQ-101`. It reads the work
  item's files, writes its own, and checks them with a `bridge-kit` command before it finishes.
- **You decide.** An agent drafts, checks and asks; it never approves. You approve a file by setting its `status`
  once you've reviewed it, and nothing is approved while its Open questions aren't answered.
- **Files, not chat, are the memory.** Everything about a requirement is in its work item, `work/<id>/`: what you
  gave, what the agents wrote, what you decided. A new chat, or a colleague, starts from there.
- **The preflight first.** Every agent checks the checkouts it reads before it starts. When it stops, it says why:
  fix that, and run the prompt again.

## A requirement, start to finish

| # | Step | Run | It writes | You |
|---|---|---|---|---|
| 1 | Start | `/requirement <id>`, or `/read-story <story> <id>` to begin from a GitLab story | The requirement and what you bring, as the work item's inputs: `work/<id>/inputs/` | Answer its questions |
| 2 | Impact | `/impact <id>` | `work/<id>/impact.md`: the components it touches, why, and their contract changes | Check every component, and anything below high confidence |
| 3 | An upstream's spec | `/explore-spec <spec> <what you need>`, naming the work item | A spec digest, `work/<id>/inputs/spec-digest-<upstream>.md`: where each item is in the spec | Say which items you mean |
| 4 | The model | `/model-change <id> <what the model needs>` | The change in the model's checkout, and its merge request description, `work/<id>/model-change.md` | Review it; the model's owners approve the merge request |
| 5 | Mapping | Fill `work/<id>/inputs/mapping-request.md` from `mappings/REQUEST.md`, then `/draft-mapping <id>` | A mapping spec per upstream operation, `mappings/<upstream>/<operation>.md` | Answer its open questions, then approve it |
| 6 | Stories | `/write-stories <id>` | One story per component, `work/<id>/stories/` | Approve each |
| 7 | Check | `/validate <id>` | A findings report, `work/<id>/validation-NN.md` | Work the findings in until it says ready |
| 8 | Publish | `/publish-stories <id>` | The approved stories as GitLab issues, after you approve its dry run | Approve the dry run |
| 9 | Tests | `/write-tests <id>` | The test cases that prove the stories' criteria, `work/<id>/tests/` | With the tester, approve each case |

Not every requirement needs every step: a wording change may have no model change or mapping. At any point,
`/requirement <id>`, or `.github/bridge-kit/bin/bridge-kit work status <id>`, says where the work item stands and
what's next. Each step's agent, and how to ask it, is on its page in the [agent guides](guides/README.md).

## Bringing in what you have

| You have | Run |
|---|---|
| A GitLab story, with its comments | `/read-story <story> [work item]` |
| A wiki page, or something the wiki says | `/read-wiki <what to find> [work item]` |
| A document: Excel, Word, PDF, PowerPoint, an email, an image | `/read-document <file> [work item]` |
| A stored payload, by its request id (dev or SIT) | `/read-payload <request id> [service]` |
| Existing code with no specs | `/reverse-engineer <component> <path>` |

With a work item named, each is kept as one of its inputs. An input never changes: a newer version of a story or a
document becomes a new input.

## When something stops

- **The preflight stops:** a checkout isn't where `bridge-kit.yaml` says, or is on another branch or remote. Fix it,
  or `bridge-kit.yaml`, and run the prompt again.
- **A command refuses (exit 2):** what was asked for isn't declared, such as a GitLab project, a service or a
  repo. It says what is declared.
- **Something outside said no (exit 1):** GitLab, MongoDB or Nexus refused or had nothing. It says what it got.
- **An agent asks:** answer in the chat, or under the file's Open questions. It never guesses an answer for you.

## Setting it up

Once per BA repo, by the README's "Setting up a BA repo". First copy `bridge-kit.example.yaml` to
`bridge-kit.yaml` and set its `environment`: every command runs inside it. Then the tools that draft the rest:
`bridge-kit workspace scan` (the repos in `bridge-kit.yaml`), `/profile-model` (the model's conventions),
`/profile-component`, `bridge-kit components build` and `bridge-kit components scan` (the component catalog, and
what each component's team keeps for its own AI tools), `/draft-glossary` (the glossary),
and `/reverse-engineer` (specs for existing code).

## The words BRIDGE uses

| Word | What it is |
|---|---|
| **Work item** | One requirement's folder, `work/<id>/` (`REQ-101`): its inputs, impact analysis, specs, stories and test cases |
| **Input** | A source kept in a work item: a GitLab story, a wiki page, a document. Never rewritten: refer to it by its file |
| **Package** | What the BA approves for the developers: `impact.md`, the model change, the mapping specs, the assembly spec and the stories, checked together by `/validate` |
| **Handoff** | Work crossing from one role to another, which BRIDGE carries with an artefact, a check and a person's approval: PO → BA, BA → developer, BA → tester |
| **Shared model** | The JSON schemas every service shares, in their own repo: the record the collecting service fills, and the summary built from it. The agents and FORMAT also call it the internal model |
| **Payload path** | A field's place in the model, from its root: `CustomerRecord.accounts[].status`. `[]` marks a list |
| **Slot** | In a model built of an identity and one slot per source, the part one source fills, and only it, as the model's `CONVENTIONS.md` says: `CustomerRecord.contactPreference` |
| **Upstream** | A system the collecting service calls for data |
| **Spec digest** | The Spec Explorer's summary of an upstream's spec: where each item you asked about is, and what it means |
| **Mapping spec** | How one upstream operation's data fills the model, a row per field, by `mappings/FORMAT.md` |
| **Lookup** | A code table a mapping spec uses, `lookups/<name>.md` |
| **Assembly spec** | How the payload is put together: which upstream is called when, with what, and what a failure does |
| **Mapping request** | What you tell the Mapping Drafter about one mapping, from `mappings/REQUEST.md` |
| **Rough mapping** | Your own working mapping, a spreadsheet or a document, kept as an input; its rows are your decisions |
| **Component catalog** | `architecture/components.yaml`: the components, the contracts each owns and consumes, their order |
| **Component profile** | `architecture/components/<name>.md`: what a component does in business words, and where changes go |
| **Glossary** | `architecture/glossary/<area>.yaml`: the business terms BAs use, and the payload paths each means |
| **Preflight** | `bridge-kit preflight`: whether the machine and every declared checkout are as `bridge-kit.yaml` says |
| **Local mode** | The agents use the checkouts already beside the BA repo; they never clone, fetch or pull |
