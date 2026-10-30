---
name: spec-exploring
description: Step-by-step procedure for reading an upstream spec (OpenAPI or WSDL) on a BA's behalf - generating its digest, finding where the data the BA asked about is, and writing the answer in business terms - with what to watch for in specs. Use when exploring a spec, answering "where do we get X from this upstream?", or checking a spec digest.
metadata:
  version: 0.2.0
  owner: ba-team
---

# Exploring an upstream spec

The goal is an answer a BA can act on without reading the spec: which operation gives each piece of data they need,
the exact field, what it means, and what the spec doesn't have. Specs are often far larger than the question, so work
from the question, not from the spec.

## 1. Generate the digest

```bash
.github/bridge-kit/bin/bridge-kit spec digest "<the spec as you were given it>" --upstream <upstream> --out <file>
```

- Pass the spec exactly as given: a path, a URL, coordinates, or the whole dependency block, quoted. For content
  pasted into the chat, pass `-` with the content on standard input.
- If it says several specs were found, or asks a question (such as which version a `${property}` stands for), ask the
  BA. When you can't ask, write the question under Open questions and stop.
- The file has the four sections you write at the top, then **Operations**: an index of every operation (with whether
  it only reads), and for each one what it takes and what it returns, with every field's path, type, whether it's
  required, its allowed values and its description. Operations that return the same fields say so instead of listing
  them again.

## 2. Find each item

For each item the BA asked about, in the order asked:

1. **Pick the operation.** Search the index and the summaries, then the returned fields (`grep -n` on the file). Prefer
   an operation that only reads. One that creates, changes, releases or controls something is never the source, even
   when it returns the same data. Prefer the operation that returns what the BA needs for every record they need it
   for, over one that checks or fetches one thing someone already has.
2. **Pick the field.** Read the description of every candidate, not just its name. A record often holds several
   fields that each look like the answer (several dates, amounts or names). Choose the one whose description means
   what the BA asked; name the others in Notes as near matches you rejected, and why.
3. **Point at the value.** Use the path exactly as the listing writes it, down to the field that holds the value.
   Point at a wrapper object only when the value is spread over its fields, such as an amount and its currency; then
   say in Notes which field holds what. When one of its fields holds the value and the others only describe it, point
   at that field, even when the description sits on the wrapper.
4. **Explain the value.** For a code, say which values mean what the BA asked (e.g. which status means "current"),
   from the descriptions. Say when the field is optional and what its absence means, if the spec says.
5. **When two fields could both be the answer** and the spec doesn't say which is used, give the more specific one,
   name the other in Notes, and ask under Open questions which one the upstream fills.
6. **When the spec doesn't have it,** say so. Don't stretch a field that only looks related.

## 3. Check what each operation needs

- Inputs the call needs that we may not have, such as an id of the upstream's own, become open questions: how do we
  get it for the records we have?
- Headers or context the call needs are for the developers: mention them in the Summary only if they're unusual.

## 4. Write the sections

| Section | What goes in it |
|---|---|
| Summary | Three to six sentences in business terms: what the upstream is for, which operation answers the BA's question and why, anything surprising |
| Where the data is | One row per item the BA asked about, numbered in the order asked (see below) |
| Not available | Each item the spec doesn't have, the near matches you rejected and why. If everything is there, say so |
| Open questions | A list. Each question says who should answer it: the BA, the upstream team or the developers |

The **Where the data is** table:

| Column | Holds |
|---|---|
| # | The item's number, in the order the BA asked |
| Asked for | The BA's words |
| Operation | As the listing names it, e.g. `GetCustomer` or `GET /customers/{id}`. `—` when the spec doesn't have it |
| Path | One path in a `code span`, as the listing writes it. `—` when the spec doesn't have it |
| Type | The field's type, as the listing gives it |
| Notes | Which codes mean what, units, when it's absent, near matches rejected |

- **Where the spec came from.** If it didn't come from Nexus (a file, pasted content or a URL), the digest's `spec:`
  field is empty. Say under Open questions that the upstream team needs to publish the spec jar to Nexus, with its
  Maven coordinates, before developers can build from it.
- Never list the spec back in the sections, and never change the generated Operations section.

## 5. Check the digest

```bash
.github/bridge-kit/bin/bridge-kit validate digest <file>
```

It checks that every section is written, the rows are numbered in order, and every operation and path you named
exists in the spec, in what that operation returns. Fix every error. A warning about a path's list marker means
writing it as the spec does.
