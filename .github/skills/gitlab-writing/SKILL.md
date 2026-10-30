---
name: gitlab-writing
description: How to write to GitLab with BRIDGE, only ever after the BA approves exactly what will be written - publishing a work item's approved stories as issues in each component's project, creating or updating one story, commenting on one, and linking two. Only the projects bridge-kit.yaml declares read-write; the token is never the agent's. Use when the BA asks to publish stories, or to create, update, comment on or link a GitLab story.
metadata:
  version: 0.1.0
  owner: ba-team
---

# Writing to GitLab

What BRIDGE writes to GitLab, the BA's whole team sees, so nothing is written that the BA hasn't approved, as it
will read. BRIDGE writes only to projects `.github/bridge-kit/bridge-kit.yaml` declares `access: read-write`, and
refuses every other project before any request. Every command goes through the launcher,
`.github/bridge-kit/bin/bridge-kit`; run each on its own, never in a loop, a pipe or a chain.

## 1. The approval

Before any write, show the BA exactly what will be written: the project, the title, the labels, the description or
the comment as it will read, the link. Write only once the BA says so in the chat, to that. A change to what was
approved needs approving again. Approval for one write isn't approval for the next.

- **The commands** are a dry run without `--yes`: run the dry run, show its output to the BA, and run the same
  command with `--yes` only after the BA's OK.
- **The MCP tools** (`gitlab_create_issue`, `gitlab_update_issue`, `gitlab_add_note`, `gitlab_link_issues`) write at
  once: call one only after the BA's OK. The IDE asks the BA to confirm each call as well; that's a second check, not
  the approval.

## 2. Publishing a work item's stories

The stories the Story Writer wrote, once the BA has approved them (`status: approved` in each) and the package check
passes:

1. Run `bridge-kit stories publish <id>`, the dry run. It lists each issue it would create: the story, the project, the
   title, the labels, what it relates to. Or it says, all at once, what stops it: a draft story, a project that isn't
   declared read-write or has no key, a story or package check that fails. Tell the BA what stops it, and stop there.
2. Show the BA the list, and wait for the OK.
3. Run `bridge-kit stories publish <id> --yes`. It creates each issue in its component's project, links each to the
   requirement's issue and to the stories it waits for ("relates to"), writes each story's id into its file
   (`id: SVD-311`, `status: created`), and comments on the requirement's issue with the list.
4. Tell the BA the ids, and that the story files changed: they commit them.

A story that has an id is created already: running it again creates only those without one. If it stops part way
(GitLab refused one), the ones before have their ids: once the cause is fixed, run it again, with the BA's OK.

## 3. One story

| The BA wants | Command | MCP tool |
|---|---|---|
| A new story | `bridge-kit gitlab issue create --project <name> --title <title> --description-file <file> --label <label>` | `gitlab_create_issue` |
| A story's title, description, labels, or closed or reopened | `bridge-kit gitlab issue update <story> --title … --description-file … --label … --state close` | `gitlab_update_issue` |
| A comment on a story | `bridge-kit gitlab issue comment <story> --body-file <file>` | `gitlab_add_note` |
| Two stories linked | `bridge-kit gitlab issue link <story> <other story>` | `gitlab_link_issues` |

Write a description or a comment to a file under `.work/tmp/` first, show it to the BA, and pass the file. An
update's description and labels replace the story's own: read the story first (`bridge-kit gitlab issue get <story>`)
and start from what it has.

## 4. When it fails

- **Exit 2: not declared, read-only, or not a story's name.** Say what `bridge-kit.yaml` declares. Making a project
  read-write is the BA's change to `bridge-kit.yaml`, never yours.
- **Exit 1: GitLab said no** (the token lacks the `api` scope, or the access), or a story or package check fails.
  Show the BA the line. `bridge-kit gitlab status` says whether the token can write.

## 5. Never

- **Never write what the BA hasn't approved,** as it reads, in the chat.
- **Never close, reopen or relabel a story the BA didn't ask about,** and never delete anything: BRIDGE can't.
- **Never handle the token,** and never call GitLab's API yourself (`curl`, a script).
- **Never put client data in GitLab:** a story describes fields and behaviour, never values from real records.
