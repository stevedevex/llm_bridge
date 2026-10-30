# Agent guides

One page per agent: what it's for, how to start it and with what, what it needs first, what it reads and writes,
how it checks its own work, what it leaves to you, and what to do when it stops. The [guide](../GUIDE.md) shows the
order of a requirement's steps; the [README](../README.md) has every command.

| Agent | Use it to | Start it | Page |
|---|---|---|---|
| Requirements Analyst | Start a requirement, see where it stands, work your answers in | `/requirement <id> [what you want]` | [requirement-analyst.md](requirement-analyst.md) |
| Impact Analyzer | Find which components a requirement touches, and why | `/impact <id>` | [impact-analyzer.md](impact-analyzer.md) |
| Spec Explorer | Find what an upstream's spec offers, and where your data is in it | `/explore-spec <spec> <what you need>` | [spec-explorer.md](spec-explorer.md) |
| Model Designer | Change the shared model, or learn it already has what's asked | `/model-change <id> <what the model needs>` | [model-designer.md](model-designer.md) |
| Mapping Drafter | Draft a mapping spec from your mapping request | `/draft-mapping <id> [<upstream> <operation>]` | [mapping-drafter.md](mapping-drafter.md) |
| Story Writer | Write one story per affected component | `/write-stories <id>` | [story-writer.md](story-writer.md) |
| Spec Validator | Check the package as the developers would, before you approve it | `/validate <id>` | [spec-validator.md](spec-validator.md) |
| Test Designer | Write the test cases that prove the stories' criteria | `/write-tests <id>` | [test-designer.md](test-designer.md) |
| Reverse Engineer | Write the specs existing code never had | `/reverse-engineer <component> <path>` | [reverse-engineer.md](reverse-engineer.md) |
| No agent | Read a source, publish stories, set a BA repo up | The standalone prompts | [prompts.md](prompts.md) |

## What every agent does

- **Starts with the preflight.** It checks that the checkouts it may read are where `bridge-kit.yaml` says, on the
  right branch and remote. If the preflight stops, the agent stops and says why: fix that and start again.
- **Writes only its own files,** each listed on its page, and never touches another agent's or another repo's.
- **Drafts, never approves.** Everything it writes is a `draft` until you review it and set its status. Whatever it
  can't settle from the files, it asks, under the file's Open questions, naming who should answer.
- **Checks its own work** with a `bridge-kit` command before it finishes, and tells you the result.
- **Runs one command at a time,** so Copilot's tool approval can match each one by how it starts.
- **Never uses client data:** it describes fields and behaviour, never values from real records.
- **Ends its reply** with the checkouts the preflight confirmed and their commits: the versions it read.

## Starting one

In the IDE's Copilot chat, type `/` and pick the prompt, such as `/write-stories`; it asks for its arguments, or you
type them after it: `/write-stories REQ-101`. Every prompt starts its agent. From the Copilot command line, `copilot
--agent=<name>` starts an agent by its name, such as `story-writer`. The Requirements Analyst also offers the next
specialist as a button in VS Code.

A work item id is the requirement's key in GitLab, such as `REQ-101`: the agents keep everything about it in
`work/REQ-101/`.

The `bridge-kit` commands on these pages are yours to run too, from the BA repo's root, such as
`.github/bridge-kit/bin/bridge-kit validate impact REQ-101`: the same check the agent ran, and what it found.
