# Reverse Engineer

Reads code that already exists, one collector at a time, and writes what a BA would have written for it had specs
existed: its mapping specs, its lookups and its rows in the assembly spec. The code shows what was built, which isn't
always what was meant, so everything it writes is a draft for a BA and a developer to review together.

| | |
|---|---|
| **Start it** | `/reverse-engineer <component> <path>` |
| **`<component>`** | The repo, as `bridge-kit.yaml` names it, such as `service-a-java` |
| **`<path>`** | The path inside it, usually one collector's folder |
| **Before you run it** | The component and the model's repo declared in `bridge-kit.yaml`, with their checkouts in place; Nexus reachable, for the upstreams' specs |
| **It reads** | The code, read-only; each upstream's spec, through the spec resolver; the target's schemas in the model; `mappings/FORMAT.md` |
| **It writes** | `mappings/<upstream>/<operation>.md`, `lookups/<name>.md`, rows in `assembly/<root>.md`, and notes for the reviewers in `work/reverse/<component>/notes.md` |
| **It checks with** | `bridge-kit validate mapping <files>` |
| **You decide** | With a developer, whether each row is what was meant; every low-confidence row |

## What it gives you

- **Mapping specs** marked `origin: reverse-engineered` and `draft`, every row with the code it comes from and a
  confidence: high, medium or low.
- **Lookups** for each code table in the code, and the **assembly rows** for each call: when it's made, with what,
  and what a failure does.
- **Notes** for the reviewers: what's unclear, and anything that looks unintended. It writes what the code does,
  never what it should have done.

## Tips

- Start with two or three representative collectors, not all of them: review those first, and the rest go faster.
- A row at low confidence, or one its notes call possibly unintended, is a question for the component's developers.
- When a file it would write exists, it adds to it or corrects it, and says so in its notes; it never drops rows
  another source wrote.

## When it stops

- **The component isn't declared, or its path doesn't exist:** fix `bridge-kit.yaml`.
- **A spec can't be resolved:** Nexus isn't reachable, or the module's coordinates are wrong.

Related: [Mapping Drafter](mapping-drafter.md) (drafts new mappings), the `reverse-engineering`, `mapping-format` and
`spec-resolver` skills, `mappings/FORMAT.md`.
