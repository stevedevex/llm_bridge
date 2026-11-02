# bridge-kit

**New to BRIDGE? Start with the [guide](GUIDE.md):** how a BA works a requirement, step by step, and the words BRIDGE
uses; then each agent's page, in the [agent guides](guides/README.md). This README is the reference: the commands, the
agents, and setting BRIDGE up in a BA repo.

The bridge-kit package is the code behind the `bridge-kit` command line, run from the BA repo's root as
`.github/bridge-kit/bin/bridge-kit <command>`. Skills and prompts call its commands and never repeat their logic: what
can be worked out the same way every time is a command, and an agent runs it.

## Commands

| Command | Does |
|---|---|
| `bridge-kit gitlab status` | Who the GitLab token is, and whether each project and group `bridge-kit.yaml` declares answers at its declared path, and its wiki when it's read. Exit 1 on a problem |
| `bridge-kit gitlab issue get <ref> [--project] [--notes] [--links]` | One story: title, state, labels, milestone, assignees, author, dates, link and description; with `--notes` its comments (GitLab's system notes left out), with `--links` the stories it blocks, is blocked by or relates to. `<ref>` is `REQ-101` (a project's key), `<project>#101`, the story's GitLab link, or `101` with `--project` |
| `bridge-kit gitlab issue list [--project] [--label] [--milestone] [--state] [--search] [--author] [--limit]` | Stories in a declared project, latest updated first, one line each, paged to the end or the limit (50) |
| `bridge-kit gitlab issue links <ref> [--project]` | The stories one blocks, is blocked by or relates to |
| `bridge-kit gitlab issue create --project <p> --title <t> [--description-file <f>] [--label <l>]... [--yes]` | Creates a story. Like every write to GitLab, a dry run without `--yes` (what it would write, nothing sent), and only to a project declared `read-write`: any other is refused before a request (exit 2). `--yes` only once the BA has approved exactly that (the `gitlab-writing` skill) |
| `bridge-kit gitlab issue update <ref> [--project] [--title] [--description-file] [--label]... [--state close\|reopen] [--yes]` | Changes a story's title, description, labels or state; the description and labels given replace the story's own |
| `bridge-kit gitlab issue comment <ref> --body-file <f> [--project] [--yes]` | Adds a comment to a story |
| `bridge-kit gitlab issue link <ref> <target> [--project] [--yes]` | Links two stories: "relates to" |
| `bridge-kit gitlab epic get <group> <iid>` | An epic and its stories, where the GitLab tier has epics |
| `bridge-kit gitlab wiki list [--wiki <project or group>]` | A declared wiki's pages |
| `bridge-kit gitlab wiki get <slug> [--wiki <project or group>]` | One wiki page's Markdown |
| `bridge-kit gitlab wiki search <text> [--wiki <project or group>]` | The wiki pages holding some text, with the lines that match |
| `bridge-kit payload status` | Whether stored payloads can be read: the payload guard passed (`test_data_only: true`, the environment dev or SIT), MongoDB answering, and each declared service's collection there (its raw responses' too), named by their variables. Exit 1 on a problem, 2 when the guard refuses |
| `bridge-kit payload get <service> <request id>` | One service's stored payload for a request, by its UUID (stored as text or as a BSON UUID, standard or Java's legacy form), as plain JSON: dates as ISO text in UTC, decimals as numbers where that's exact, ids as text, MongoDB's `_id` left out and a wrapper unwrapped (`payload_field`). Kept in `.work/payloads/<service>/<request id>.json`. Exit 2 when the guard refuses (not declared, not confirmed, another environment, an undeclared service, not a UUID, a variable not set); 1 when there's none or MongoDB doesn't answer |
| `bridge-kit payload trace <request id>` | The same request in every declared service, side by side: the collecting service's payload beside the summary service's, the pair a golden example needs; a service with none says so |
| `bridge-kit payload check <service> <request id>` | One stored payload against the shared model, from the root its contract names in `architecture/components.yaml`: fields the model doesn't have, required ones missing, nulls, wrong types, values outside a code list, formats and patterns not met, by model path (a list's items as one path, counted). A date stored as midnight UTC is the date it is; the request id beside a payload isn't a finding; a payload that looks wrapped is named as one. Exit 1 when it finds anything |
| `bridge-kit payload profile <service> <request id>...` | The shape across several payloads of one service, as a table per model path: how often it's there and null, the types seen, list sizes, and the codes a field takes with their counts. A request with none is named and left out |
| `bridge-kit payload raw <request id> [upstream]` | The raw upstream responses behind a request, per upstream and operation, where a service keeps them (`raw` in `bridge-kit.yaml`); only one upstream's when it's named. Kept in `.work/payloads/<service>/<request id>.raw.json` |
| `bridge-kit knowledge term "<words>"` | What a business term means in the model: the glossary's terms that match (`architecture/glossary/<area>.yaml`, by name or synonym, exact ones first), each with its data elements; then the shared model's fields whose names or descriptions hold the words; then the business terms in the components' profiles; then the lines of the components' own glossaries the catalog points to (`knowledge: glossary`). Ten of each at most; when nothing matches, it says to ask the BA |
| `bridge-kit knowledge check` | Checks the glossary: each file in its shape (`templates/glossary.yaml`), each term defined once (a synonym counts), each with a definition, each data element a path of the model (a term with none is a warning). Exit 1 on an error |
| `bridge-kit knowledge show <component> [<kind>]` | A component's own knowledge, the files its team keeps for its AI tools that the catalog points to under `knowledge:`: without a kind, its pointers; with one, what they point to, read from the component's declared checkout (a `wiki:<page>` pointer names the command that reads it). The kinds: `glossary`, `lineage`, `anatomy`, `contracts`, `build-and-test`, `playbooks`, `privacy`, `versions`, `intake`, `other`. Exit 1 when a pointer's file isn't there, 2 for a component the catalog doesn't have |
| `bridge-kit work status <id>` | Where a work item stands, from its files, and the next step with the prompt that takes it: the requirement (an input to start from); the breakdown and the evaluation (its blocking questions answered), not needed once `impact.md` is there; `impact.md` (`validate impact`, its questions answered); the model change, when `impact.md` names the model's component; a mapping spec for each request, approved; the stories (`validate story`, approved); the latest validation's verdict; every story published; the test cases (`validate test-case`, every criterion covered, approved). It runs only the file checks |
| `bridge-kit stories publish <id> [--yes] [--maven-repo <repo>]... [--repository <url>]` | Creates a work item's approved stories as issues, each in its component's project (the catalog's `stories.project`, declared `read-write` with a key), with its labels and its Markdown, linked to the requirement's issue and to the stories it waits for ("relates to"). It needs `validate story` and the package check to pass. Each story's file then holds its id (`status: created`), and the requirement's issue a comment listing them. Without `--yes`, a dry run; a story with an id is never created again, so a run stopped part way goes on from there. Exit 1 when it's not ready, with every reason |
| `bridge-kit inputs add gitlab:<ref> \| wiki:<slug> --work-item <id> [--project] [--wiki]` | A story (with its comments and links) or a wiki page as the work item's next input, `work/<id>/inputs/NN-story-…md` or `NN-wiki-…md`, its folder made if needed: a header with its kind, source, link, version (the story's last update; the page's content hash), when it was read, its title as the summary and its raw form in `.work/sources/<id>/`. Added again, an unchanged source is already there; a changed one becomes a new input |
| `bridge-kit inputs add <file> --work-item <id> [--sheet] [--rows <n\|all>] [--headers-only] [--layout] [--description <file\|-> --by <who>]` | A document as the work item's next input, as `doc read` gives it: `kind` (`text`, `csv`, …), `source: file:<name>`, the file's hash as its version, its title as the summary, the options used and the warnings in its header; the original copied to `.work/sources/<id>/`, and a document's images beside it (`images:` in the header names the folder). Added again unchanged and with the same options, it's already there. An email's attachments that BRIDGE reads become inputs of their own, listed under it, each naming the email (`attached_to`); an attached image, or a kind it doesn't read, is listed as not added, with where it's kept. An image (PNG, JPEG, GIF, WebP) needs `--description` and `--by`: what an agent or the BA read in it, kept with `described_by`; a PDF takes one for its pages without text. Exit 2 on a wrong work item, file or description; 1 when the file can't be read |
| `bridge-kit export --to <a BA repo> [--dry-run] [--force]` | Writes BRIDGE into another BA repo: the agents, prompts and skills, the kit (its launchers, schemas, source, `pyproject.toml`, `uv.lock`, this README, the guide and the agent guides, `bridge-kit.example.yaml`, the agents' manifests), `templates/`, `mappings/FORMAT.md` and `REQUEST.md`, and the kit's `.gitignore` lines. Never that repo's own files, nor the kit's tests or its own `bridge-kit.yaml`. Each export rewrites the kit's files, removes those the kit no longer has, and records the commit, its files and their SHA-256 in `.github/bridge-kit/EXPORTED`. A kit file changed in that BA repo since the last export (neither what the last export wrote nor what this one would) stops it before anything is written, listed as `changed there`, exit 1: bring the change to BRIDGE's repo and export again, or `--force` to overwrite it. `--dry-run` lists what it would write. Exit 2 when the target isn't a folder or is the kit's own repo |
| `bridge-kit components build [--write]` | Assembles the component catalog, `architecture/components.yaml`, from the components' profiles (`architecture/components/<name>.md`, written by `/profile-component`): each profile's proposed entry (its `summary`, `stack`, `owns`, `consumes`, `external`) merged into its component's, with `profile` naming the file; the `order` worked out from the contracts, each contract's owner before its consumers; each contract's `source`. What only people set (`repo`, `stories`, `team`, `defines_schemas`, `knowledge`, `note`) is never changed. Errors: a contract owned twice, a cycle, a profile that's gone, a proposed entry that isn't the catalog's shape (not merged); warnings: a contract consumed that nobody owns, or owned without a kind. Prints the diff; `--write` writes the file when there's no error, in a fixed shape keeping its leading comment. Exit 1 on an error |
| `bridge-kit components scan [<component>] [--write]` | Each component's own AI layer, in the checkout of the repo the catalog names and `bridge-kit.yaml` declares: its `.github` instructions, skills, agents (whether each can edit) and prompts, each with the kind of knowledge its name and description suggest, and the `knowledge:` pointers that proposes for the catalog. Prompts and agents that edit are `playbooks`, the team's tools for a kind of change. `--write` adds the proposed pointers to each component the catalog has none for, never changing one that has; people review them. Reads only: it never writes in, or runs anything from, a component's repo. Exit 1 when a pointer's file isn't there |
| `bridge-kit doc read <file> [--sheet] [--rows <n\|all>] [--headers-only] [--layout]` | A document as Markdown, to look at before keeping it; its warnings on standard error. Plain text and Markdown as they are; CSV and TSV as a table with each row's number and each column's letter (`Rule (C)`); Excel (`.xlsx`, `.xlsm`), each sheet a table below its heading row (found under a title, the rows above listed), hidden sheets, rows and columns marked, values as Excel saved them (a formula's result, dates as ISO dates, percentages), merged cells spread, struck text as `~~text~~`, and under each table its comments, its formulas and its coloured cells and text as ranges; Word (`.docx`): headings from their styles with their numbers (`## 3.2 Scope`), lists with their labels as Word shows them, tables with merged cells spread, links, struck text, and `[comment N]`, `[^N]` and `[Image N: alt text]` where they are, with the comments (and the text they're on), footnotes, tracked changes (shown as if accepted; who did what) and images listed at the end; PDF: its bookmarks as contents, each page's text under `## Page N` (with its label when it has another), `--layout` keeping a page laid out so a table's columns stay apart, a page with no text named for Copilot to read as an image, JPEG images kept once each; a PDF locked by a password refused; PowerPoint (`.pptx`): each slide under `## Slide N: <title>` in the deck's order, hidden ones marked, its shapes in reading order (a placeholder placed where its layout puts it), bullets at their levels, tables, grouped shapes, SmartArt's text as a list, `[Image N: alt text]` for each picture (once however many slides show it), charts and videos named, and its speaker notes; HTML (`.html`, `.htm`, as a wiki or Outlook saves a page): headings, lists, links, quotes, a table of data as a table and one for layout as its cells, images from data URLs or beside the page kept; and email (`.eml`, and Outlook's `.msg`, read from its property streams): from, to, cc, date and subject, then its text part, or its HTML when there's no text or the HTML shows a pasted screenshot, its attachments listed (an attached message as `.eml`); a `.msg` with only an RTF body refused. A table of over 500 rows shows its first 200; `--sheet` picks sheets. Warns where values look like email addresses, IBANs or card numbers, never showing them. Refuses the old formats (`.doc`, `.xls`, `.ppt`), files locked by a password or a sensitivity label, and a file that isn't what its extension says, each with what to do. Exit 1 on a refusal |
| `bridge-kit workspace scan [<folder>] [--write]` | A draft of `bridge-kit.yaml`'s `workspace.repos` from the folders beside the BA repo: each checkout's remote, with any user or token taken out of the URL; the remote's default branch, or the current one, flagged, when git doesn't know it; `kind: wiki` for a project wiki; the model's repo named; every repo read-only. The environment's tools, at the versions found, as ranges. Then what differs from `bridge-kit.yaml`: repos it doesn't declare, repos it declares that aren't there, a different remote, branch or git. It never fetches or changes a checkout. `--write` adds only the repos `bridge-kit.yaml` doesn't declare, at the end of `workspace.repos`, its comments kept, and checks the file after |
| `bridge-kit preflight` | Whether this machine and every declared checkout are as `bridge-kit.yaml` says, before an agent acts on them (local mode): the config and its overrides pass their schemas; each tool under `environment.tools` runs and is in its version range, and each listed file exists; each repo's path exists and, unless `git: false`, is a git checkout of its own with the declared remote, on the declared branch (a read-write repo may be on a work branch), clean (a dirty read-only checkout warns or stops, as `dirty_read_only` says), and how far behind its upstream it is as of the last fetch. It never fetches, pulls or clones. When `bridge-kit.yaml` declares a GitLab, a GitLab line: who the token is, and whether each declared project, group and wiki answers at its declared path; an id naming another project or group stops, and anything else (no token, a token refused, a wiki that doesn't answer) warns, since only the agents that read GitLab need it. When it declares MongoDB, a MongoDB line: the guard, the connection and each collection; anything wrong warns. Exit 1 on a stop |
| `bridge-kit validate mapping <file>... [--model <schemas>] [--maven-repo <repo>]...` | Checks mapping specs: the header, every table and row against `mappings/FORMAT.md`, the shared model, the lookups and the assembly spec, and every source path against the upstream's spec: from a Maven repository folder when one is given, else resolved as `bridge-kit spec resolve` resolves it |
| `bridge-kit validate request <file>... [--model <schemas>] [--repository <url>]` | Checks a mapping request (`mappings/REQUEST.md`), the BA's input to the Mapping Drafter: the front matter names the upstream, operation, target and spec, the target is in the model, the spec resolves, and Purpose is written. Blank optional sections are reported as left for the drafter to ask about. A `rough_mapping` it names (the BA's own working mapping) must be an input beside the request holding the table `rough_mapping_table` names, or its only one, with two columns or more and a row; its warnings are passed on to the drafter |
| `bridge-kit validate digest <file>... [--repository <url>]` | Checks spec digests: every section written, rows numbered in order, and every operation and path named in "Where the data is" present in the spec, in what that operation returns |
| `bridge-kit validate model <id> [--no-build]` | Checks a model change: the conventions on what changed (`model.conventions` in `bridge-kit.yaml`, by default draft-07, kebab-case files, camelCase names, booleans without is or has, `UPPER_SNAKE_CASE` enums, required plural lists, nothing null, closed objects with titles, descriptions, the `Amount` money schema, ISO dates, currencies and countries; each can be set otherwise or off), the version in every version file the layout names, the example, the merge request description against the diff, and the model's build |
| `bridge-kit validate story <story or folder>...` | Checks stories as one set: each header against `templates/story.schema.json` and `architecture/components.yaml` (component, order, labels, contracts the component owns), the template's sections in order, Gherkin acceptance criteria numbered from AC-1, no schema change where `defines_schemas` is false, open questions empty to approve, and every `blocked_by` inside the set and before the story |
| `bridge-kit validate test-case <case or folder>...` | Test cases against `templates/test-case.md`, as one set. Errors: the header against `templates/test-case.schema.json`; the sections in order; every `{name}` the case uses defined in Test data; steps numbered from 1, each with an observable result; Checks along the data path for a system or end-to-end case across components; each story it verifies there and approved, with the criteria it names; `approved` and `created` only with Open questions empty, `created` with an id, `automated` with `automated_by`; across the set, each case number once and each file named `tc-<nn>-<slug>.md` for it. Warnings: vague words in a result ("works", "correct", "as expected"), more than ten steps, data never used, no **Never:** list, an Objective that doesn't name its criteria. Exit 1 on an error |
| `bridge-kit validate impact <id>` | Checks a requirement's impact analysis, `work/<id>/impact.md`, against `templates/impact.md` and the component catalog: the front matter and sections; each affected component a catalog component, with its Why, Contracts and Confidence; every catalog component under Affected components or Not affected, never both; contract changes only on contracts the component owns, each additive or breaking, and none on a schema by a component that doesn't define schemas; the External impact of a component with outside clients; confidence high, medium or low, a low one with a question; every cited package file there (a warning: `impact.md` comes before the files it names). Open questions are information. Exit 1 on an error |
| `bridge-kit validate package <id> [--maven-repo <repo>]... [--repository <url>] [--no-build]` | Checks a requirement package as a whole, for the developers' implementable check: every file's own check (the mapping specs, requests, digests, the model change, `impact.md`, the stories as a set), then across them: everything approved, nothing open and every file committed (a warning); one story per component `impact.md` names and no other; every file it cites, and the model change, implemented by a story, and every implemented file there; one model version and contract changes that agree with `impact.md` and the model change; every path the change adds filled by a mapping or assembly row (input side) or named in a story (output side, a warning); every mapping spec's assembly row with Called, Called with and If the call fails; and the requests and digests against the specs (a digest's item no row reads is a warning), each cell of the BA's rough mapping a row's Notes cite ("From the BA's rough mapping, `Mapping!D12`") there in the rough mapping its request names. The package is `work/<id>/` and what its stories implement |
| `bridge-kit tests coverage <id>` | Which of a work item's acceptance criteria its test cases verify: a table of each story's criteria with the cases (and their status), then the gaps. An error for a criterion no case verifies; warnings, from a criterion's words, for one whose Given or When names alternatives or failures with no alternate or error case, and for an accessibility, performance or security criterion with no case of that type. A story for a schema-only component is the model check's (`validate model`). Exit 1 on a gap |
| `bridge-kit model start <id>` | Starts a model change: records the shared model as it is (its schemas, examples and version files, where `model.layout` in `bridge-kit.yaml` says they are), as the base later diffs compare with |
| `bridge-kit model diff <id>` | Every difference from the base as payload paths, additive or breaking by the model's conventions, the version needed, and the consumers a breaking change hits |
| `bridge-kit model profile [<checkout>]` | The model's layout and conventions as its own files show them, as a `model:` block for `bridge-kit.yaml`: where the schemas are (flat or nested), the examples, the files that hold the version; then each convention `validate model` checks, run over every field through the same checks with each setting, counted, the setting 90% of the fields follow proposed, or off below that, and a few fields that don't follow it. The kit's default wins a tie. By default the repo `bridge-kit.yaml` names as `model.repo` |
| `bridge-kit spec resolve <file\|URL\|coordinates\|block\|-> [--repository <url>] [--pick <spec>]` | Finds and unpacks an upstream spec, however it's given, into `.work/specs/`, and classifies what it found. Used through the `spec-resolver` skill |
| `bridge-kit spec digest <same as resolve> --upstream <id> [--out <file>] [--force] [--repository <url>] [--pick <spec>]` | Writes a spec digest: the Spec Explorer's sections still to be written, above every operation of an OpenAPI spec or WSDL with every field it takes and returns. Operations that return the same fields are listed once |

Every command but `spec digest` takes `--json`. The `gitlab` commands read only the projects and groups
`bridge-kit.yaml` declares: anything else is refused before a request is made (exit 2), and the token, from its
declared source, is sent as a header and never printed. GitLab's errors are one line each (exit 1). Exit codes: `0`
success, `1` a stop condition (a check's errors, a spec resolution that needs the BA), `2` a usage error.

## Launchers

- **`bin/bridge-kit-run <command>`** runs a command inside the toolchain environment `bridge-kit.yaml` declares:
  `micromamba run -n <name> <command>`, or the command as it is with `manager: none` (the tools already on the PATH).
  It reads `environment.manager` and `environment.name` itself, so the schema keeps them plain words written as a
  block, and `bridge-kit.local.yaml` may name another environment. When the environment can't start it says why in one
  line (no micromamba on the PATH, no such environment, a name or manager it can't use, overrides turned off with a
  local file there) and exits 1; without a command it exits 2; otherwise the command's own exit code.
- **`bin/bridge-kit-mcp`** starts the MCP server the same way: below, "The MCP server".
- **`bin/bridge-kit`** runs through it: `bridge-kit-run uv run --no-dev python -m bridge_kit`, so the kit and every tool
  it starts (Maven, git) come from that environment. uv's virtual environment for the kit is the BA repo's
  `.work/venvs/bridge-kit`, never the toolchain environment. Without uv in the environment it says so in one line.

## The MCP server

`bin/bridge-kit-mcp` serves the `gitlab` calls as MCP tools, for an IDE whose Copilot allows MCP servers. The reads,
marked read-only: `bridge_kit_status`, `gitlab_get_issue`, `gitlab_list_issues`, `gitlab_issue_links`,
`gitlab_get_epic`, `gitlab_list_wiki_pages`, `gitlab_get_wiki_page`, `gitlab_search_wiki`, and the payload reads
`payload_status`, `payload_get`, `payload_trace`, `payload_check`, `payload_profile` and `payload_raw`. The writes, not
marked read-only so the IDE asks the BA to confirm each call, and only to `read-write` projects:
`gitlab_create_issue`, `gitlab_update_issue`, `gitlab_add_note`, `gitlab_link_issues`. They call the same code as the
commands, so they read only what `bridge-kit.yaml` declares, through the same guards, and a failed read answers with
the command's one line. It's a small server of the kit's own over stdio (`src/bridge_kit/mcp/`), not the MCP SDK,
which the kit's tests use only to talk to it. Each call is logged, with who made it and without a token or a
connection string, in `.work/logs/bridge-kit.jsonl`, which the payload commands share. The command line stays the way
to keep a story or a page as an input (`bridge-kit inputs add`).

Each person registers it once, in their own settings, outside the repo, with the launcher's absolute path
(`<the BA repo>/.github/bridge-kit/bin/bridge-kit-mcp`). The formats as of 2026-10; check the client's own
documentation if one has moved on:

- **VS Code:** the user's `mcp.json` (*MCP: Open User Configuration*):
  `{"servers": {"bridge-kit": {"type": "stdio", "command": "<the launcher>"}}}`.
- **IntelliJ** (the GitHub Copilot plugin): its MCP settings open an `mcp.json` in the same `servers` format.
- **Copilot CLI:** `~/.copilot/mcp-config.json`:
  `{"mcpServers": {"bridge-kit": {"type": "local", "command": "<the launcher>", "args": [], "tools": ["*"]}}}`.

The server reads the token from where `bridge-kit.yaml` says, in the IDE's environment: an `env` source needs the
variable set where the IDE starts, so a `file` or `command` source is often simpler there. It speaks the protocol's
handshake versions 2024-11-05 to 2025-11-25; a client that tries the newer `server/discover` first gets "method not
found", and whether it then falls back to the handshake is up to the client.

## Configuration

`bridge-kit.yaml`, beside this README, is the kit's one configuration: the environment the tools come from, every repo
an agent may read or write (its mode, path, remote, branch, access and writers), the shared model (its repo, consumers,
layout and conventions), the integrations (the Maven repository, GitLab, MongoDB), the work items' names, and the
workspace and write rules. Every command that reads it checks it first, against `schema/bridge-kit.schema.json` and
the rules a schema can't say (a writer only on a read-write repo, a git repo's remote and branch, the model repo
declared), and stops on any problem. `bridge-kit.example.yaml` explains every field, with placeholders, to write it
from.

`bridge-kit.local.yaml` beside it, git-ignored, holds one person's overrides: only a repo's `mode` and `path`, the
environment's `name`, and where their GitLab token and MongoDB connection string are
(`schema/bridge-kit.local.schema.json`).

`integrations.gitlab` declares the GitLab the `gitlab` commands read: its URL, each project (id, path, key for its
work item ids, access, whether its wiki is read), each group (its wiki, its epics), the default project, where the
token is (`env`, an owner-only `file`, or a `command` that prints it) and, for a self-managed GitLab on its own
certificate authority, `tls.ca_file`.

Defaults that come from it: the shared model for `validate mapping` and `validate request` (else `--model`), and the
Maven repository for the spec resolver (`integrations.nexus.url`, after `--repository` and the `BRIDGE_KIT_NEXUS_URL`
environment variable; else a mirror in `settings.xml`). `BRIDGE_KIT_REPO_ROOT` names the repo the kit works on, when
it isn't the one the kit is in.

## Setting up a BA repo

This is what it takes, in local mode, before the first agent runs on real checkouts.

**Find out first:**

- [ ] How the machine provides Java, Maven, Python, uv and git: a micromamba environment (its name), or on the PATH.
- [ ] Whether it reaches a Python package index or a mirror. uv installs the kit's five packages (PyYAML, openpyxl,
  pypdf, olefile, pymongo) once, on the first `bridge-kit` command. `uv.lock` names pypi.org: behind a mirror, set
  `UV_DEFAULT_INDEX` to the mirror's URL (or `index-url` in a `uv.toml`), and uv resolves against it.
- [ ] The Maven repository's URL for the upstreams' spec jars, or the mirror in `~/.m2/settings.xml`.
- [ ] The shared model's repo, its build command, and the remote and base branch of every repo the agents read.
- [ ] Whether the Copilot CLI is there, and which folder IntelliJ and VS Code open: the BA repo or the folder that
  holds every checkout, which decides whose `.github` agents a BA sees.
- [ ] GitLab: its URL, version and tier (epics and group wikis need a paid tier), whether its certificate is from its
  own certificate authority (`tls.ca_file`), the token a BA may create (a personal access token with `read_api`, and
  `api` to publish stories), the projects stories live in, and the wiki (a project's or a group's).
- [ ] Copilot: whether the organisation's policy lets a BA attach images and PDFs (on Business and Enterprise, GitHub
  keeps them about 24 hours), whether Copilot in IntelliJ takes images, and whether it may run MCP servers.
- [ ] Documents: whether sensitivity labels encrypt them, and a real `.msg` read with `bridge-kit doc read` (the reader
  is tested against a writer of the kit's own).
- [ ] A made-up sample of a BA's rough mapping: its columns, and whether its colours mean something.
- [ ] MongoDB: whether dev and SIT hold test data only, never copies of client data (until that's confirmed,
  `test_data_only` stays false and every payload command refuses); a read-only database user; how a service stores a
  payload (the request id's field, and whether the document wraps the payload in a field of its own); and whether
  the collecting service keeps the raw upstream responses.

**Take BRIDGE in.** Either BRIDGE's repo is the BA repo, checked out beside the components' repos and the shared
model's, or BRIDGE is exported into a BA repo that already exists, from a checkout of BRIDGE's repo:

```bash
.github/bridge-kit/bin/bridge-kit export --to <the BA repo> --dry-run
```

- [ ] Look at the list, then run it again without `--dry-run`. It writes the agents, prompts and skills, the kit,
  `templates/`, `mappings/FORMAT.md` and `REQUEST.md`, and the kit's two `.gitignore` lines; it never writes the BA
  repo's own files (`bridge-kit.yaml`, `architecture/`, specs, lookups, work items). `.github/bridge-kit/EXPORTED`
  records the commit it came from.
- [ ] Export again whenever the kit changes: the kit's files are rewritten, the BA repo's kept, and a file the kit
  no longer has is removed. Change the kit through `bridge-kit.yaml`, never by editing its files: a kit file changed
  here stops the next export, which lists it to bring back to BRIDGE's repo.

**Write:**

- [ ] `bridge-kit.yaml`, from `bridge-kit.example.yaml`:
  - **first, the environment:** copy the example to `bridge-kit.yaml` and set `environment.manager`, `none` when the
    tools are on the PATH, or `micromamba` with the environment's `name`. Every `bridge-kit` command runs inside it,
    so none runs, `--help` included, until it's set;
  - every checkout beside the BA repo with its remote and branch: start from
    `.github/bridge-kit/bin/bridge-kit workspace scan`, which drafts them from the checkouts, and the tools' versions
    (`--write` adds the repos, while the rest is still placeholders), then set each repo's access, the model repo's
    writers and build;
  - the model's repo, build and consumers;
  - the Maven repository's URL;
  - `integrations.gitlab`: the URL, the projects with their keys, the group or project wiki. Each BA's token source
    goes in their own `bridge-kit.local.yaml`, never in `bridge-kit.yaml`;
  - `integrations.mongodb`: the names of the variables that hold the connection string, the environment and each
    service's database and collection (their values go in the machine's environment, never in the repo), each
    service's id field and contract, `payload_field` and `raw` where they apply, and `test_data_only: true` only
    once it's confirmed. A BA may say where their own connection string is in `bridge-kit.local.yaml`.
- [ ] The model's layout and conventions in `bridge-kit.yaml` (`model.layout`, `model.conventions`): run
  `/profile-model`, which proposes both from the model's own files with the evidence (`bridge-kit model profile`), and
  check them against the model's `CONVENTIONS.md`: where its schemas are (and whether in subfolders), its examples
  folder or none, the files that hold its version, and each rule `validate model` checks, set to the model's own or
  off. Each has a default, which a model may not follow (booleans that start with `is`, abbreviated names, another
  JSON Schema draft). The Model Designer's final check is `validate model`, so this comes before it runs.
- [ ] `CONVENTIONS.md` in the model's checkout, if it has none: the Model Designer and the Mapping Drafter read it.
  `/profile-model` drafts it in `.work/setup/`; agree it with the model's owners, who commit it, since it's their repo.
- [ ] `architecture/components.yaml`, from the components themselves:
  1. run `/profile-component` on each component's checkout;
  2. then `.github/bridge-kit/bin/bridge-kit components build --write`;
  3. fill in what only people know (`stories`, a team, `defines_schemas`) from the profiles' Open questions, and have
     an architect review it.

  The Impact Analyzer, the Story Writer and the package check read it.
- [ ] A glossary, `architecture/glossary/<area>.yaml`, from `templates/glossary.yaml`: the business terms BAs use,
  each with the model paths it means and where its definition comes from. `/draft-glossary <area>` drafts an area
  from the model, the profiles, the wiki and documents; review every term. Start with a few areas; the agents look
  terms up in it, and `bridge-kit knowledge check` keeps it valid.
- [ ] An assembly spec, `assembly/<root>.md`, as FORMAT's Assembly spec section says, with at least the rows of the
  upstreams being worked on: `/reverse-engineer` writes the rows of each existing collector it reads, with its mapping
  specs and lookups; the Mapping Drafter adds a row to it, and the package check needs each mapping spec's row.
- [ ] Optionally, `bridge-kit-mcp` in each BA's IDE settings (above, "The MCP server").

**Check** before any agent runs:

- [ ] `.github/bridge-kit/bin/bridge-kit preflight` ends in OK: the environment, every tool's version, every
  checkout's remote and branch, and a GitLab line with no warning.
- [ ] `.github/bridge-kit/bin/bridge-kit gitlab status`: the token, and each project and wiki at its declared path.
- [ ] `.github/bridge-kit/bin/bridge-kit payload status`, once MongoDB is declared: the environment, and each
  collection answering; then `payload check` on one request a BA knows.
- [ ] `.github/bridge-kit/bin/bridge-kit spec resolve <one upstream's group:artifact:version>` resolves: the Maven
  repository is reachable.
- [ ] `.github/bridge-kit/bin/bridge-kit doc read <a real document>`, one of each kind the BAs use.
- [ ] The agents show up in Copilot (`/explore-spec` and the others in the IDE's prompt list, or
  `copilot --agent=spec-explorer`).

**First runs:**

1. `/read-story` on a real story, and `/read-document` on a real document: they need only GitLab and the kit. Then
   `/impact` on a real requirement, once the component profiles are written.
2. The Spec Explorer on one upstream's spec, since it needs only the Maven repository.
3. The Reverse Engineer on one existing collector, to give the BA a mapping spec in FORMAT to start from.
4. The Model Designer once the model's conventions are set.
5. The Test Designer on a work item whose stories are approved: `/write-tests <id>`, then `tests coverage`.

## Agents

Each agent is `.github/agents/<name>.agent.md`, started by its prompt in `.github/prompts/`, and loads its skills
from `.github/skills/`. Its manifest, `agents/<name>/manifest.yaml` beside this README, says what it takes, writes
and checks with; Copilot never reads it, the kit's tests do.

| Agent | Name | Prompt | Skills |
|---|---|---|---|
| Requirements Analyst | `requirement-analyst` | `/requirement` (in VS Code, it hands off to the specialists) | `requirement-analysis`, `gitlab-reading`, `document-reading` |
| Impact Analyzer | `impact-analyzer` | `/impact` | `impact-analysis`, `gitlab-reading`, `document-reading` |
| Spec Explorer | `spec-explorer` | `/explore-spec` | `spec-exploring`, `spec-resolver`, `gitlab-reading`, `document-reading` |
| Model Designer | `model-designer` | `/model-change` | `model-designing`, `gitlab-reading`, `document-reading`, `payload-reading` |
| Mapping Drafter | `mapping-drafter` | `/draft-mapping` | `mapping-drafting`, `mapping-format`, `spec-resolver`, `document-reading`, `payload-reading` |
| Story Writer | `story-writer` | `/write-stories` | `story-writing`, `gitlab-reading`, `document-reading` |
| Spec Validator | `spec-validator` | `/validate` | `package-review` |
| Test Designer | `test-designer` | `/write-tests` | `test-designing`, `payload-reading` |
| Reverse Engineer | `reverse-engineer` | `/reverse-engineer` | `reverse-engineering`, `mapping-format`, `spec-resolver` |

What each agent is for, how a BA starts it, what it needs first and what it leaves to the BA: its page in the
[agent guides](guides/README.md).

The standalone prompts start no agent; any Copilot chat runs them:

| Prompt | Skill | Does |
|---|---|---|
| `/read-story <story> [work item]` | `gitlab-reading` | Reads a GitLab story, with its comments, and keeps it as an input |
| `/read-wiki <what to find, or a page's slug> [work item]` | `gitlab-reading` | Finds what the wiki says, and keeps a page as an input |
| `/read-document <file> [work item]` | `document-reading` | Reads a document the BA brings, an image read by Copilot itself, and keeps it as an input |
| `/read-payload <request id> [service]` | `payload-reading` | Reads a stored payload from dev or SIT, its shape and what the model makes of it |
| `/publish-stories <id>` | `gitlab-writing` | Creates a work item's approved stories in GitLab, after the BA's OK to the dry run |
| `/profile-component <folder> <name>` | | Reads one component's repo and writes its profile, `architecture/components/<name>.md`, for `bridge-kit components build` |
| `/profile-model [<checkout>]` | | Runs `bridge-kit model profile`, reads the model's own words, and writes `.work/setup/model-profile.md` (the `model:` block, with the evidence) and, when the model has none, a draft `CONVENTIONS.md` for its owners, never writing in their repo |
| `/draft-glossary <area> [where to look first]` | `glossary-drafting` | Drafts a business area's terms, each with its definition's source, into `architecture/glossary/<area>.yaml` |

`tests/test_agent_files.py` checks every agent file against the fields Copilot reads, every manifest against
`schema/manifest.schema.json` (its fields, their kinds and the values each may take) and against its agent and
skills, every skill against the Agent Skills format, every prompt's agent, that every agent starts with the preflight,
and that every `bridge-kit` command an agent, skill or prompt names in code exists.

## Source checks per category

| Category | Checked against |
|---|---|
| REST | The OpenAPI spec in the jar: the operation's success response body |
| SOAP | The XSDs in the jar, and any written inside its WSDLs: element paths from a global element |
| MAP | The vendor jar's classes, through `javap`: bean properties from a class |
| JDBC | Not checked: the columns come from the service's own query |

## Code

| Module | Holds |
|---|---|
| `cli.py` | The command line |
| `paths.py` | Where the kit, its repo and `.work/` are |
| `config.py`, `schema.py` | `bridge-kit.yaml` and its overrides: the declared repos, the shared model and its consumers; the JSON Schema keywords the kit's own schemas use |
| `markdown.py` | Front matter, sections, paragraphs and pipe tables |
| `preflight.py` | `bridge-kit preflight` |
| `workspace_scan.py` | `bridge-kit workspace scan`: `workspace.repos` drafted from the checkouts |
| `export.py` | `bridge-kit export`: what ships into another BA repo, and nothing else |
| `auth.py`, `guard.py`, `gitlab.py` | The GitLab token (and MongoDB's connection string) from its source; what's declared and may be read; the client, `bridge-kit gitlab` |
| `publish.py` | `bridge-kit stories publish`: approved stories created as GitLab issues |
| `payloads.py` | `bridge-kit payload`: the guard, MongoDB's client, payloads as plain JSON, kept in `.work/payloads/` |
| `payload_check.py` | `payload check` and `profile`: a payload against the model, and the shape of several |
| `audit.py` | The one audit log, `.work/logs/bridge-kit.jsonl`, for MCP calls and payload reads |
| `mcp/server.py` | `bridge-kit-mcp`: the GitLab calls and the payload reads as MCP tools, over stdio |
| `documents/` | Documents as Markdown: each kind's reader, the tables they share, the personal-data check |
| `inputs.py` | `bridge-kit inputs add`: a work item's inputs |
| `rough_mapping.py` | The BA's rough mapping: its tables, the one a request names, the cells a spec cites |
| `work_status.py` | `bridge-kit work status`: where a work item stands, and the next step |
| `knowledge.py` | `bridge-kit knowledge term` and `check`: the glossary |
| `components.py` | `bridge-kit components build`: the component catalog from the components' profiles |
| `component_knowledge.py` | `bridge-kit components scan` and `knowledge show`: a component's own AI layer, and the catalog's pointers to it |
| `internal_model.py` | The shared model's JSON schemas: payload paths and their fields |
| `model_change.py` | `bridge-kit model start` and `diff`: a change's base, the differences and their version impact |
| `model_profile.py` | `bridge-kit model profile`: the model's layout and conventions, from its files |
| `specs.py` | Spec jars, and resolving source paths for REST, SOAP and MAP |
| `spec_resolver.py` | `bridge-kit spec resolve`; the Maven route runs `.github/skills/spec-resolver/pom.xml` |
| `spec_digest.py` | `bridge-kit spec digest`: every operation and field of an OpenAPI spec or WSDL, written as a digest |
| `mappings.py` | Mapping specs, lookups and the assembly spec |
| `stories.py` | User stories and the component catalog they're written against |
| `test_cases.py` | Test cases as `templates/test-case.md` defines them |
| `case_coverage.py` | `bridge-kit tests coverage`: a work item's criteria and the cases that verify them |
| `validators/` | `bridge-kit validate`: `mapping.py`, `request.py`, `digest.py`, `model.py`, `story.py`, `test_case.py`, `impact.py`, and `package.py`, which runs them all on a work item and checks the files against each other |

## Tests

```bash
cd .github/bridge-kit && uv run pytest
```

They run on the tests' own BA repo files, `tests/fixtures/landscape/` (a `bridge-kit.yaml`, a component catalog and a
glossary, in BRIDGE's general names), with GitLab and MongoDB faked and every document they read written by the tests.
The `dev` group in `pyproject.toml` adds what only the tests use: pytest, the MCP SDK (to talk to the server), and
python-docx and python-pptx (to write Word and PowerPoint files to read).
