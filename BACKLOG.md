# Backlog: what BRIDGE doesn't do yet

What's known to be missing, each with what it waits on and what it would change.

**A gap found while using BRIDGE goes here,** as a line in general words: never a team's own system names, codes or
data, since this repo is public. The change is made in BRIDGE's repo, and reaches a BA repo with its next pull, or
`bridge-kit export`. A kit file changed in a BA repo stops the next export, which lists it: bring each such change
here as a line, or as the change itself. Take a line out once it's built.

| Gap | Waits on | Would change |
|---|---|---|
| **The model's work branch.** `model start` on a git checkout: a work branch, then the push and the merge request after the BA's approval. Today the model's checkout must be a plain folder (`git: false`) | Git access from where the agents run | `model start`, the Model Designer's last step |
| **Clone mode.** The kit cloning and pulling the declared repos itself (`rules.workspace.clone_root`). Today every checkout must already be there (local mode) | Git access, and each repo's remote | The preflight, `workspace scan` |
| **GitLab attachments.** A story's attached files kept as inputs. Today a story's text, comments and links are read | The GitLab version's API for uploads | `gitlab issue get`, `inputs add` |
| **Confluence.** Reading pages from Confluence, as the GitLab wiki is read | Whether the teams keep their pages there | A reader beside `gitlab wiki`, `/read-wiki` |
| **A work item's state.** A `state.yaml`, a log of each agent's run, and archiving a finished work item (`work_items.archive`). Today `work status` works out where a work item stands from its files alone | Whether the files are enough in practice | `work status`, the Requirements Analyst |
| **Output specs.** A spec of what the summary service writes, with agents to draft it (an Output Spec Writer) and its examples (an Example Builder) | The output spec's format, agreed with the summary service's team | A template, two agents, the summary service's stories |
| **The lineage and screens index.** Which model field reaches which API field and screen, read from the component repos, for the Impact Analyzer. Today it follows a field by the profiles, the glossary and the checkouts | The real component repos | The Impact Analyzer, `knowledge term` |
| **Publishing test cases** to the testers' tool, as `stories publish` does for stories | Which tool the testers use (Xray, Zephyr, TestRail, GitLab's own) and who approves the cases | A `tests publish` command, the Test Designer |
| **Masking.** Personal data in a document is found and warned about, never masked | Whether documents carry real client data | `doc read`, `inputs add` |
| **CODEOWNERS, an agent catalog and CI.** Owners' approval of changes to the BA repo's specs, a generated list of the agents, and the kit's tests run on each change | The GitLab setup | `.gitlab-ci.yml`, `CODEOWNERS` |
| **Tests on a whole requirement package.** The kit's tests cover the model, payloads, the glossary and specs on their fixtures; `validate request`, `mapping`, `impact`, `test-case` and `package`, `tests coverage`, `work status` and `stories publish` have none in this repo | Time: they're checked on the first real requirement | `tests/fixtures/`, a package for the running example |
| **The agents' first real runs.** Each agent's instructions were tried on a made-up landscape; none has run on a real requirement | A BA repo set up for a real system | Each agent's instructions, where a run shows a gap |

## Left out on purpose

- **Agents for the developers** (implementing a mapper from an approved spec, writing its tests): developers work from
  the package with Copilot as they choose. BRIDGE gives them the context, not the code.
- **The developer → tester handoff,** for the same reason: BRIDGE carries PO → BA, BA → developer and BA → tester.
