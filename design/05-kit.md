# BRIDGE design: the kit

`bridge-kit` is the Python package and command line in `.github/bridge-kit/` that the agents run. It does everything
that must come out the same every time: reading specs, stories, documents and payloads; checking every file the
agents write; and writing to GitLab. Skills and prompts call its commands and never repeat their logic, so a rule
lives in one place and a BA can run any check by hand.

## The commands

| Purpose | Commands |
|---|---|
| Set up and confirm | `preflight`, `workspace scan`, `components build`, `model profile`, `gitlab status`, `payload status` |
| Read | `gitlab issue get` / `list` / `links`, `gitlab epic get`, `gitlab wiki list` / `get` / `search`, `doc read`, `spec resolve`, `spec digest`, `knowledge term`, `payload get` / `trace` / `check` / `profile` / `raw` |
| Keep as an input | `inputs add`: a story, a wiki page or a document, as the work item's next input |
| Check | `validate digest` / `impact` / `model` / `request` / `mapping` / `story` / `test-case` / `package`, `knowledge check`, `tests coverage`, `work status` |
| Change the model | `model start`, `model diff` |
| Write out | `stories publish`; `gitlab issue create` / `update` / `comment` / `link` |
| Update a BA repo | `export` |

Most commands also print JSON, with `--json`. Exit codes mean the same everywhere: 0 when all is well; 1 when a
check finds a problem or something outside said no (GitLab, a Maven repository, MongoDB), with what it got; 2 when
what was asked for isn't declared, with what is.

## Configuration

`bridge-kit.yaml`, beside the kit, is BRIDGE's one configuration, checked against
`schema/bridge-kit.schema.json`:

| Section | Holds |
|---|---|
| `environment` | Where the toolchain comes from (a micromamba environment, or the `PATH`), each tool's version range, and the files it needs, such as Maven's `settings.xml` |
| `workspace` | Every repo an agent may read or write, by the name the agents use: its path beside the BA repo, remote, base branch, access (`read-only` or `read-write`), the agents that may write it, its build |
| `model` | The shared model's repo, its consumers (searched when a change breaks them), its layout (schemas, examples, version files) and its conventions |
| `integrations` | The Maven repository for specs; GitLab's URL, projects (each with its key) and groups, and where the token is; MongoDB's services, and where the connection string is |
| `work_items` | How a work item's id and folder are formed, and where its stories go |
| `rules` | What the preflight does on a missing path, a wrong branch or a dirty checkout; that other repos are written only on a `feature/` work branch; that outputs record every repo's commit |
| `defaults` | What every agent inherits: the actions that need the BA's approval (cloning, pulling, pushing, opening a merge request, creating or changing an issue), and made-up data only. A manifest may tighten them, never loosen them |

`bridge-kit.example.yaml` is the starting point, every value a placeholder. `bridge-kit.local.yaml`, git-ignored,
holds one person's overrides: a repo's path, the environment's name. Some rules are fixed: a checkout on the wrong
remote always stops a run, and no checkout is ever deleted.

## Running it

| Launcher | Does |
|---|---|
| `bin/bridge-kit-run <command>` | Runs a command inside the toolchain environment `bridge-kit.yaml` declares, or as it is when the tools are on the `PATH` |
| `bin/bridge-kit` | Runs the kit through it, with uv, in its own virtual environment in `.work/venvs/bridge-kit`. Its five packages (PyYAML, openpyxl, pypdf, olefile, pymongo) are locked in `uv.lock`; behind a mirror, `UV_DEFAULT_INDEX` names it |
| `bin/bridge-kit-mcp` | Starts the MCP server the same way |

**The MCP server** serves the GitLab and payload calls as tools, for an IDE whose Copilot runs MCP servers. Reads are
marked read-only; writes are not, so the IDE asks the BA to confirm each one. Each person registers it once in their
own IDE settings, with the launcher's path; nothing about it lives in the repo. It calls the same code as the
commands, through the same guards.

Everything the kit caches or keeps for itself is in the git-ignored `.work/`: resolved specs, the originals of
inputs, stored payloads, scratch files and the audit log.

## The preflight

`bridge-kit preflight` runs first in every agent. It checks that `bridge-kit.yaml` and its overrides pass their
schemas; that every tool runs and is in its version range, and every listed file exists; and that every declared
repo is at its path, a git checkout with the declared remote, on the declared branch (a read-write repo may be on a
work branch), clean, and how far behind its remote it was at the last fetch. When GitLab or MongoDB is declared, it
checks they answer. It never fetches, pulls or clones. It ends in `STOP` with every reason, or with the table of
checkouts and their commits that the agent may use.

## Connections

- **GitLab.** The kit reads only the projects, groups and wikis `bridge-kit.yaml` declares, with the BA's own personal
  access token, which comes from an environment variable, a file or a command and is never in the repo or seen by an
  agent. A GitLab with its own certificate authority names it in `tls.ca_file`. It writes only to projects declared
  `read-write`, and every write is a dry run until it's given `--yes`, which an agent passes only once the BA has
  approved exactly that write.
- **Upstream specs.** `spec resolve` takes a spec as a file, a URL, Maven coordinates or a pasted dependency block,
  fetches it from the Maven repository with Maven, unpacks it into `.work/specs/` and says what it found: OpenAPI,
  Swagger or WSDL. Nothing in a resolved jar is ever run.
- **Documents.** `doc read` turns a document into Markdown: text, CSV, Excel, Word, PDF, PowerPoint, HTML and email
  (`.eml`, `.msg`, with their attachments). A spreadsheet keeps its sheets, hidden rows, merged cells, struck text,
  comments and colours; an image is described by the agent or the BA, with who described it. It warns where values
  look like personal data without showing them, and refuses locked files and the old binary formats.
- **Stored payloads.** The `payload` commands read a service's stored payloads from MongoDB by request id only, from
  dev or SIT only, and only once `bridge-kit.yaml` says those hold test data. They check a payload against the shared
  model, compare the same request across services, and profile the shape of several. Payloads are kept in
  `.work/payloads/`, never in the repo.
- **The audit log.** Every MCP call and payload read is logged in `.work/logs/bridge-kit.jsonl`, with who made it,
  never with a token or a connection string.

## Updating a BA repo

`bridge-kit export --to <a BA repo>` writes BRIDGE into another BA repo: the agents, prompts and skills, the kit,
the templates, `FORMAT.md` and `REQUEST.md`, and the kit's lines in `.gitignore`. It never writes the BA repo's own
files: `bridge-kit.yaml`, `architecture/`, the mapping and assembly specs, lookups and work items. Each export
removes the kit's files that are gone, and records the commit it came from and each file's SHA-256 in
`.github/bridge-kit/EXPORTED`. A kit file changed in that BA repo since the last export stops the export before it
writes anything, and is listed: a change to bring back to BRIDGE's repo, where every change is made. `--force`
overwrites such files; `--dry-run` lists everything first. What BRIDGE doesn't do yet is in `BACKLOG.md`.
