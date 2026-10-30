# Requirements Analyst

Your main assistant for a requirement, from its first notes to a package the specialists can build. It gathers the
requirement, breaks it into parts, finds the gaps before anyone builds on them, records your answers, and tells you,
at any point, where the work item stands and which specialist is next. It doesn't do the specialists' work.

| | |
|---|---|
| **Start it** | `/requirement <id> [what you want]` |
| **`<id>`** | The work item: the requirement's key, such as `REQ-101` |
| **`[what you want]`** | To start it (from a GitLab story, a document or your words), to evaluate it, to work your answers in, or just where it stands. Left out, it says where it stands |
| **Before you run it** | Nothing: it can start a work item from scratch |
| **It reads** | The work item's files; a GitLab story (`gitlab-reading`) or documents (`document-reading`) you name; the glossary, the model and the component profiles, to place a business term |
| **It writes** | `work/<id>/inputs/` (the requirement and its sources), `breakdown.md`, `evaluation-NN.md`, `decisions.md` |
| **It checks with** | `bridge-kit work status <id>`, before and after each step |
| **You decide** | Every answer to its questions; when a step's work is good enough to approve |

## Asking it

- `/requirement REQ-101 start it from the story REQ-101` — reads the story with its comments, keeps it as an input,
  writes the breakdown and the first evaluation.
- `/requirement REQ-101 here are my answers: ...` — records each answer as a decision, and evaluates again.
- `/requirement REQ-101` — where it stands: each step in one line, and the next one, with its specialist and prompt.

## What it gives you

- **The breakdown:** the requirement split into parts, each tied to the kind of spec it needs (a model change, a
  mapping, a story).
- **Each evaluation:** gaps, ambiguities, conflicts and what can't be tested, each a question naming who answers;
  the blocking ones stay until they're answered.
- **The status:** ten steps, from the requirement to approved test cases, each done, to do, with problems or not
  needed; and the next step.

## Tips

- Answer in the chat or in the evaluation file; either way it records your answer in `decisions.md`, with who
  decided. A decision it didn't hear from you, it never writes.
- A business word it can't place in the model is a question, not a guess: answer it, or add the term to the
  glossary (`/draft-glossary`).
- It never moves past a step with problems: fix them, or ask the specialist again.

## When it stops

- **The preflight stopped:** fix what it says (a checkout's path, branch or remote) and run it again.
- **It says a step has problems:** the status names the file and what's wrong; the step's specialist fixes it.

Related: [Impact Analyzer](impact-analyzer.md) (usually next), the `requirement-analysis` skill.
