# BRIDGE

**Business Requirements Intelligence & Delivery Generation Engine.** *From business ask to build-ready, faster.*

BRIDGE is the BA's AI kit: it helps BAs turn business needs into complete, checked specs with AI agents, and keeps
every decision with people. A BA brings a requirement in business words; the agents, in GitHub Copilot's chat, turn
it with the BA into a package every affected team can build from: the components it touches and why, the change to
the shared data model, the mapping specs that fill it from the upstream systems, one story per component, and the
test cases that prove them. `bridge-kit`, the command line behind the agents, checks every file they write.

## What's here

This repo is a BA repo: set up for a system, it is where that system's requirements are worked.

```text
README.md
LICENSE
BACKLOG.md              what BRIDGE doesn't do yet, and where a gap found in use goes
design/                 how BRIDGE works: the landscape, a requirement's steps, the agents, the package, the kit
.github/
  agents/               the agents Copilot runs, one file each
  prompts/              the prompts that start them, and the standalone prompts
  skills/               the know-how the agents load
  bridge-kit/           the command line, its configuration's schema and example, the agents' manifests
templates/              the shapes of the impact analysis, stories, test cases and glossary
mappings/
  FORMAT.md             how mapping specs, lookups and assembly specs are written
  REQUEST.md            the BA's mapping request
```

A BA repo set up for a system also holds what it knows of that system and its work, written there by the setup
tools and the agents: `.github/bridge-kit/bridge-kit.yaml`, the component catalog, profiles and glossary in
`architecture/`, the mapping specs in `mappings/<upstream>/`, `lookups/` and `assembly/`, and one work item per
requirement in `work/`.

## Setting up a BA repo

1. **Take this repo as the BA repo,** checked out beside the repos of the system's components and its shared model.
2. **Write `bridge-kit.yaml`:** copy `.github/bridge-kit/bridge-kit.example.yaml` to
   `.github/bridge-kit/bridge-kit.yaml`, and name where the toolchain comes from first.
3. **Describe the landscape,** in order: the repos (`bridge-kit workspace scan --write`), GitLab, the component
   catalog (`/profile-component`, then `bridge-kit components build`), the shared model (`/profile-model`), the
   glossary (`/draft-glossary`), and the mapping specs of existing code (`/reverse-engineer`).
   [The landscape](design/01-landscape.md) describes each step.
4. **Run `bridge-kit preflight`.** Once it passes, start a requirement with `/requirement <id>` in Copilot's chat.

`bridge-kit` runs from the BA repo's root as `.github/bridge-kit/bin/bridge-kit <command>`. To bring BRIDGE into a
BA repo that already exists, `bridge-kit export --to <that repo>` writes the kit's files and leaves the repo's own
alone.

Working a requirement, step by step, is the [guide](.github/bridge-kit/GUIDE.md), with a page per agent in the
[agent guides](.github/bridge-kit/guides/README.md); every command, and the setup checklist in full, is in the kit's
[README](.github/bridge-kit/README.md).

## What it needs

- **GitHub Copilot,** in IntelliJ, VS Code or the Copilot CLI.
- **The toolchain:** Java 21 or later, Maven 3.9 or later, Python 3.11 or later, uv and git, on the `PATH` or in a
  micromamba environment.
- **GitLab,** for the stories and the wiki; **a Maven repository,** for the upstreams' specs; and, to read stored
  payloads, **MongoDB**.

## What's missing

What BRIDGE doesn't do yet, each with what it waits on, is in [BACKLOG.md](BACKLOG.md); so is how a gap found while
using it gets back here.

## The design

| Document | Covers |
|---|---|
| [Overview](design/00-overview.md) | What BRIDGE is, who does what, the handoffs it carries, its principles, how it spends AI credits |
| [The landscape](design/01-landscape.md) | What each component stands for, and how a BA repo learns the real ones |
| [A requirement, start to finish](design/02-requirement-flow.md) | The work item, the ten steps, approval, the package check, the hand-over |
| [The agents](design/03-agents.md) | How the agents work together, the rules they follow, each agent |
| [The package](design/04-package.md) | Each file a requirement package is made of, and what checks it |
| [The kit](design/05-kit.md) | `bridge-kit`, its configuration, the preflight, its connections |

## Licence

MIT: see [LICENSE](LICENSE).
