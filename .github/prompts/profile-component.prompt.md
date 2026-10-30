---
description: Read one component's repo and write its profile for the component catalog - what it does in business words, its part in the flow, its business areas and data, its contracts, its screens or operations, where changes go, where it stores payloads, and a proposed catalog entry, each fact with the file it comes from
argument-hint: "<the component's folder, e.g. ../service-c-java> <its name in the catalog, e.g. service-c-java>"
---

# Profile a component

Read the component in ${input:folder:its checkout, e.g. ../service-c-java}, which the catalog calls
${input:name:its name in architecture/components.yaml, e.g. service-c-java}, and write down what it is and what it
does, for the BAs who plan stories across components. They think in business terms ("show the preferred contact
channel on the customer panel"); this profile is how they, and their agents, tell whether a requirement touches this
component, and where in it the work goes.

## Rules

- **Read only.** Never change, build, install or run anything in the component's folder. The one command you may run
  is `git -C <folder> log -1 --format="%h %cs"`, for the commit you read.
- **Cite every fact:** the file it comes from, by its path from the component's root, with a line where it helps.
  A fact you inferred says "(inferred)" and from what. Never write a guess as a fact.
- **Never copy** a secret, a password, a token, a key, a connection string, an internal host's address, or a value
  from a sample, a test or a configuration file. Name a dependency by what it is ("the collecting service's API"),
  never by its URL.
- **Read by structure, not file by file:** build files, specs, entry points, packages, routes, configuration; search
  for what you need, and stop once you have a pattern. A large repo is fine read this way.
- **Business words come from the code's own:** API descriptions, screen titles, labels and translations, class and
  package names, comments, the README. When nothing names a thing in business terms, don't invent a name: ask under
  Open questions.

## What to read

1. **What it is:** the README and docs; the build files (`pom.xml`, `build.gradle`, `package.json`,
   `pyproject.toml`); the CI file; the modules or top-level folders.
2. **What it says of itself to its own AI agents,** when it has them: the Copilot customization in its `.github`
   folder (`copilot-instructions.md`, `instructions/*.instructions.md`, its agents and prompts) and any `AGENTS.md`.
   They often name the modules, the build and test commands and the conventions. Take them as leads: confirm each
   fact in the code or the build files before you write it, and cite that file.
3. **What it offers:** its API specs (OpenAPI, WSDL, JSON Schema) and the controllers or handlers behind them; for a
   UI, its routes, pages, menus, and their titles.
4. **What it uses:** clients generated from other components' specs (the build's generator configuration says from
   which); other HTTP clients and the services they call; message topics or queues; databases (data sources,
   migrations, repositories); its organisation's shared libraries.
5. **Its data:** the models it reads and writes, above all types generated from another component's schema or API,
   and which of their fields it uses; and whether it stores what it receives or produces by request (repositories,
   collection names in its configuration).
6. **How it's built and tested:** the commands, from the build files, the CI and the README.

## What to write

Read `architecture/components.yaml` first, if the workspace has one: use the names it gives components and contracts,
so the profile's entry joins the catalog without renaming anything. Then write
`architecture/components/<name>.md`; in a workspace without `architecture/components.yaml`, write
`component-profile-<name>.md` at its root. If the profile is there already, write it again from what you read now,
keeping the answers given under its Open questions.

The profile, every section in this order, each table's rows citing their file:

````markdown
---
component: <name>
folder: <the folder you read>
commit: <its commit and date, from git, or unknown>
profiled: <today's date>
part: <the UI, an API with external clients, business logic, a collecting service, a summary service, the shared model>
status: draft
---

# <name>

<Two or three sentences: what it does, for whom, in business words.>

## What it does

- <a responsibility, in business words> (`<file>`)

## What it doesn't do

- <what a BA might look for here but is done elsewhere, and where> (`<file>`)

## Business areas and data

| Business term | What it is here | Where |
|---|---|---|
| preferred contact channel | `contactPreference.channel`, shown on the Customer panel | `src/app/customer/CustomerPanel.tsx` |

## Contracts

### Owns

| Contract | Kind | File | What it offers |
|---|---|---|---|

### Consumes

| Contract or dependency | Kind | How it's used | Where |
|---|---|---|---|

## Screens

<For a UI: each screen by its business name (its title), its route, what it shows, and the API calls it makes, saying
which aren't made through a generated client. For an API: call this section Operations, and group the operations by
business area, each with its method and path, or its operation's name, and what it's for.>

## Where changes go

| A change like | Goes in | Where |
|---|---|---|
| A new field shown on a panel | <the panel, its view model, the API client's model> | <their folders> |

## Build and test

| What | Command | From |
|---|---|---|

## Stored payloads

<Only when it stores, by request, what it receives or produces, as in a document database: the database and the
collection, by the names of the settings or environment variables that hold them, never their values; the field that
holds the request id; whether the payload sits in a field of its own; whether it keeps the raw upstream responses,
and where. Otherwise: None.>

## Signs a requirement touches it

- <words, data or screens in a requirement that point here>

## Proposed catalog entry

```yaml
<name>:
  summary: <one line, in business words>
  stack: <java, python, react, json-schema, ...>
  owns: [<the contracts it owns>]
  consumes: [<the contracts it consumes>]
  external: <true when clients outside the organisation use what it owns, else false>
contracts:
  <a contract it owns>: { kind: <openapi, json-schema, wsdl, events or database>, file: <its path in the repo> }
```

## Open questions

- Which team owns it?
- Which GitLab project and labels do its stories go to?
- <anything you couldn't tell, or weren't sure of>
````

- **Contracts:** a contract is what another component builds against: an API's spec, a schema, events, a shared
  database. Use the catalog's name for one it already has (`service-c-api`); name a new one `<name>-api`,
  `<name>-events` and so on. A dependency that isn't another component's contract (an outside service, a database of
  its own) goes in Consumes all the same, by what it is.
- **Its part:** the one that fits what it does best: what its team is asked for in a story depends on it (a UI's
  screens and states; an external API's versions and clients; business logic's calls and error handling; a collecting
  service's upstreams and mappings; a summary service's output; the shared model's schemas). A component that never
  decides a schema, only follows one, says so under Open questions, for the catalog's `defines_schemas: false`. When
  no part fits, say so there too.
- **Proposed catalog entry:** keep exactly this shape, with only these fields: it's merged into the catalog as it is.
  Who owns the component and where its stories go aren't in it: people set those in the catalog, from the Open
  questions.

## When you finish

Reply with the file you wrote, its part, the contracts it owns and consumes, where it stores payloads, and its open
questions. Say what you couldn't read,
and why.
