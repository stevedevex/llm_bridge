---
name: payload-reading
description: How to read the payloads services store in MongoDB with BRIDGE - one service's payload for a request, the same request across services side by side, a payload checked against the internal model, the shape across several payloads, and the raw upstream responses behind one. By request id only, from dev or SIT only, as bridge-kit.yaml declares; the connection string is never the agent's. Use when a BA gives a request id, asks what real data looks like, or a mapping or a model change needs checking against real payloads.
metadata:
  version: 0.1.0
  owner: ba-team
---

# Reading stored payloads

Services store the payloads they make in MongoDB, each under the request's id, a UUID. BRIDGE reads them for you, from
dev or SIT only, from the services `.github/bridge-kit/bridge-kit.yaml` declares under `integrations.mongodb`, and only
once it says those environments hold test data. Every command below goes through the launcher,
`.github/bridge-kit/bin/bridge-kit`, and prints Markdown; add `--json` when you need the fields themselves. Run each
command on its own, never in a loop, a pipe or a chain: tool approvals match a command by how it starts.

## 1. Which command answers what

| The BA wants | Run |
|---|---|
| Whether payloads can be read: the environment, which collections answer | `bridge-kit payload status` |
| One service's payload for a request | `bridge-kit payload get <service> <request id>` |
| The same request in every service: what the collecting service produced, and what the summary service made of it | `bridge-kit payload trace <request id>` |
| Where a real payload differs from the internal model | `bridge-kit payload check <service> <request id>` |
| What real payloads look like across requests: how often a field is filled or null, list sizes, the codes that occur | `bridge-kit payload profile <service> <request id> <request id> ...` |
| The raw upstream responses behind a request, where the service keeps them | `bridge-kit payload raw <request id> [upstream]` |

Services go by their names in `architecture/components.yaml`, such as `service-a-java`. The BA gives the
request ids: ask for them, and never guess one or look for one. The same commands are tools on BRIDGE's MCP server
(`payload_get`, `payload_trace`, ...), when your chat has it.

## 2. Reading what comes back

- **A payload** is JSON in the model's shape: dates as ISO text in UTC, decimals as numbers. Each one is kept in the
  git-ignored `.work/payloads/<service>/<request id>.json`: refer to that file rather than pasting the payload.
- **`check`** lists what it finds by model path (`CustomerRecord.accounts[].status`), a list's items as one path,
  counted: not in the model, required and missing, null, the wrong type, not one of its codes, not its format. Each
  finding is a fact about that one payload: say which request it came from. When it says the payload looks wrapped,
  the BA sets `payload_field` in `bridge-kit.yaml`; don't work around it.
- **`profile`** gives a row per path: how often it's there, how often null, the types seen, list sizes, and the codes
  a coded field takes, with counts. A few payloads say little about the rest: say how many you read.

## 3. Using them in the work

- **Mapping a field:** before writing its rule, see whether real payloads have it, how often it's filled, and which
  codes occur. A code that occurs and the spec doesn't list is an open question, not a guess.
- **Changing the model:** see the real shape first: nulls, list sizes, codes. A field real payloads never fill is a
  question for the BA, not a reason to drop it.
- **Golden examples:** `trace` gives a real input beside the output made from it. An example built from a payload goes
  to the BA to review before it's committed.

## 4. When it fails

The commands say why in one line:

- **Exit 2: refused before any query.** MongoDB not declared, test data not confirmed, an environment other than dev
  or SIT, a service that isn't declared, a request id that isn't a UUID, a variable that isn't set. Show the BA the
  line: the BA fixes `bridge-kit.yaml` or the environment. Never try another environment.
- **Exit 1: nothing there, or MongoDB didn't answer.** Show the line, and ask the BA for another request id or to check
  the connection.

## 5. Never

- **Never handle the connection string.** Don't ask for it, read it, print it, or look in environment variables or
  files for it: BRIDGE reads it from where `bridge-kit.yaml` says, and only BRIDGE sees it.
- **Never read MongoDB another way** (`mongosh`, a driver, a script): only through BRIDGE, which keeps to request ids,
  dev and SIT.
- **Never commit a payload,** or copy one into a spec, a story or the chat beyond the fields you're talking about:
  test data can look like real people and companies.
- These commands only read. Nothing in BRIDGE writes to MongoDB.
