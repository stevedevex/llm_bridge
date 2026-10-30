---
name: spec-resolver
description: Use when you need an upstream system's spec files and someone gives you the spec in any form - a file, pasted spec content, a URL, Maven coordinates, or a pasted <dependency> or <artifactItem> block. Resolves and unpacks it from Nexus and says what it found.
metadata:
  version: 0.1.1
  owner: ba-team
---

# Spec resolver

The single way to get an upstream spec. Never fetch or unpack specs any other way, and never run anything from a
resolved jar: only read its files.

## Run it

```bash
.github/bridge-kit/bin/bridge-kit spec resolve "<what you were given>" --json
```

| You were given | Pass |
|---|---|
| A file or folder in the workspace | Its path |
| Spec content pasted into the chat | `-`, with the content on standard input |
| A URL | The URL |
| `groupId:artifactId:version` | The coordinates |
| A `<dependency>` or `<artifactItem>` block | The whole block, quoted |

## Read the result

| `status` | Do |
|---|---|
| `resolved` | Use `specs[0].path`. Its `format` says what it is: `openapi-3`, `swagger-2`, `wsdl` (its imported XSDs are in `includes`), `xsd`, or `classes` |
| `choose` | Several specs were found. List them for the BA, then resolve again with `--pick <path>` |
| `ask` | Ask the BA the question in `message`, e.g. which version a `${property}` stands for |
| `error` | Tell the BA what `message` says; don't work around it |

- For `classes` (a MAP vendor jar), read the API with `javap -cp <location> -public <class>`, where `location` is the
  folder the classes were unpacked into.
- Put `coordinates` into the spec digest and into the mapping header's `spec:` field.
- Everything lands in the git-ignored `.work/specs/` cache and is reused from there.
- `bridge-kit spec digest` takes the same inputs and resolves them the same way, then lists every operation and field
  (see the `spec-exploring` skill).
