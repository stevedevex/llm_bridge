---
name: gitlab-reading
description: How to read GitLab with BRIDGE - a story (an issue) with its comments and linked stories, a list of stories by label or milestone, an epic, and the pages of a project's or the pod's wiki, found by search - and how to save a story or a wiki page as a work item's input. Only the projects and wikis bridge-kit.yaml declares; the token is never the agent's. Use when a BA names a story (REQ-101, a GitLab link), asks what the wiki says, or a work item starts from a story.
metadata:
  version: 0.1.1
  owner: ba-team
---

# Reading GitLab

BRIDGE reads GitLab for you with the BA's own token, and only what `.github/bridge-kit/bridge-kit.yaml` declares under
`integrations.gitlab`: its projects (each with a key, such as `REQ`) and its groups. Every command below goes through
the launcher, `.github/bridge-kit/bin/bridge-kit`, and prints Markdown; add `--json` when you need the fields
themselves. Run each command on its own, never in a loop, a pipe or a chain: tool approvals match a command by how it
starts.

## 1. Which command answers what

| The BA wants | Run |
|---|---|
| Whether GitLab is set up: who the token is, which projects and wikis answer | `bridge-kit gitlab status` |
| One story, with what was said on it and what it depends on | `bridge-kit gitlab issue get <story> --notes --links` |
| Stories by label, milestone, state, text or author | `bridge-kit gitlab issue list --label <labels> --milestone <title> --state opened --search <text>` |
| What a story blocks, is blocked by, relates to | `bridge-kit gitlab issue links <story>` |
| An epic and its stories | `bridge-kit gitlab epic get <group> <number>` |
| The wiki's pages | `bridge-kit gitlab wiki list --wiki <project or group>` |
| What the wiki says about something | `bridge-kit gitlab wiki search <text> --wiki <project or group>`, then `wiki get` on the pages it finds |
| One wiki page | `bridge-kit gitlab wiki get <slug> --wiki <project or group>` |
| A story or a page kept for a work item | `bridge-kit inputs add gitlab:<story> --work-item <id>`, or `wiki:<slug> --wiki <name>` |

## 2. Naming a story

- By its id, the project's key and its number: `REQ-101`.
- By the project's declared name: `ba-requirements#101`.
- By its link, as the BA pastes it: `https://<gitlab>/<group>/<project>/-/issues/101`.
- A bare number, `101`, is looked for in the default project, or the one `--project` names.

Read every story the BA names, and a linked story only when the question needs it. Read the comments too: what was
decided or still asked is often there, not in the description.

## 3. Wikis

- `--wiki` names a declared project whose wiki is read, or a declared group (the pod's wiki). With only one wiki
  declared it can be left out.
- A page's slug is its path, as `wiki list` shows it (`onboarding/checklist`), not its title.
- To find what the wiki says, search first and read the pages that match: don't read every page.

## 4. Keeping it as an input

When you work on a work item, keep what you read from GitLab as its input, so the next agent and the BA see the same
thing: `bridge-kit inputs add gitlab:<story> --work-item <id>` saves the story with its comments and links as
`work/<id>/inputs/NN-story-….md`; a page becomes `NN-wiki-….md`. Then read that file rather than the chat.

- Added again, a story that hasn't changed is reported as already there; a changed one becomes a new input. Use the
  latest.
- Never rewrite an input or copy a story's text into another file: refer to the input by its path.
- Tell the BA to look at a new input before committing it: a story may hold data that mustn't be committed.

## 5. When it fails

The commands say why in one line:

- **Exit 2: not declared, or not a story's name.** Say what `bridge-kit.yaml` declares and ask the BA which they meant,
  or to declare it. Never look for another way into GitLab.
- **Exit 1: GitLab said no.** A refused token, no access, nothing there, or a feature this GitLab's tier lacks
  (epics, group wikis). Show the BA the line and stop: the BA fixes the token's source or the id.

## 6. Never

- **Never handle the token.** Don't ask for it, read it, print it, or look in environment variables or files for it:
  BRIDGE reads it from where `bridge-kit.yaml` says, and only BRIDGE sees it.
- **Never write to GitLab while reading.** These commands only read. Writing (publishing stories, creating or
  changing one, a comment, a link) is the `gitlab-writing` skill's, each after the BA's approval.
- **Never call GitLab's API yourself** (`curl`, a script): only through BRIDGE, which keeps to what's declared.
