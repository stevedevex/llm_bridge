---
description: Read the internal model's checkout and propose its layout and conventions for bridge-kit.yaml, with the evidence, and draft its CONVENTIONS.md when it has none, for the model's owners to review
argument-hint: "[the model's checkout, e.g. ../shared-model]"
---

# Profile the internal model

Work out how the internal model in ${input:folder:its checkout, or leave empty for the repo bridge-kit.yaml names as
model.repo} is laid out and written, so `bridge-kit.yaml` can say so and `bridge-kit validate model` checks a change
against the model's own conventions, not the kit's defaults. The Model Designer and the Mapping Drafter read the
model's `CONVENTIONS.md`; if it has none, draft one for the model's owners.

## Rules

- **Read only in the model's checkout.** Never change, build, install or run anything there, and never write a file
  in it: the model belongs to its owners. The one command you may run there is
  `git -C <folder> log -1 --format="%h %cs"`, for the commit you read.
- **Write only** in the BA repo's `.work/setup/`, which git ignores.
- **Evidence for every rule:** the counts `bridge-kit model profile` gives, and a schema or field as an example. A
  rule you inferred from a few cases says so. Never state a convention the files don't show.
- **Never copy** a secret, a host's address, or a value from an example file beyond what a rule needs to show.

## What to do

1. Run `.github/bridge-kit/bin/bridge-kit model profile <folder>` on its own (without a folder, it reads the repo
   `bridge-kit.yaml` names). It gives the layout (where the schemas are, flat or nested, the examples folder, the
   files that hold the version) and each convention `validate model` checks, with how many fields follow each
   setting, and the setting the model already follows proposed (90% of the fields or more), or off.
2. Read the model's own words about itself: its README, its build files (how the Java classes and the Pydantic models
   are generated, and what they need of a schema), any `CONVENTIONS.md`, `CONTRIBUTING.md` or style notes, and a few
   schemas of different kinds: a root, an object several others use, one with codes, one with money and dates.
3. Write `.work/setup/model-profile.md`:
   - **The `model:` block for `bridge-kit.yaml`,** as the command gave it, with any change you'd make and why (a rule
     the command proposed off that the README says is meant, a folder it found that the build doesn't use).
   - **Each convention:** the setting, its counts, and the fields that don't follow it, each a question for the owners
     when it isn't plainly an old exception.
   - **What the command can't see:** the model's structure (its roots, how parts nest, how sources fill it), how
     versions are bumped and released, who consumes it; each from the files that say so.
4. If the model has no `CONVENTIONS.md`, also write `.work/setup/CONVENTIONS.md`, a draft for the owners, with these
   sections, each rule from step 1 or 2 with its evidence:
   - `## Structure`: the roots, the objects most others use, how the parts nest and what fills each.
   - `## Files`: where the schemas are, the JSON Schema draft, file names, titles.
   - `## Names`: field names, booleans, lists, code values.
   - `## Types`: nulls, closed objects, money, dates, currencies, countries, descriptions.
   - `## Versions`: what makes a change patch, minor or major, and which files hold the version.
   - `## Who uses it`: the components that consume it, as the build or the README names them.
   - `## Open questions`: each rule the files don't settle, for the owners.
   If it has one, don't draft another: say where the profile agrees with it and where it doesn't.

## When you finish

Reply with the `model:` block to put in `bridge-kit.yaml`, the conventions proposed off and why, the files you wrote
in `.work/setup/`, the open questions for the model's owners, and the commit of the model you read. Say that the
owners review `CONVENTIONS.md` and commit it to their repo themselves, and that `bridge-kit.yaml` takes the block once
they agree.
