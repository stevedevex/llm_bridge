# Impact Analyzer

Turns a requirement's business words into the components it touches, with the evidence for each, so you can review
the impact without reading code. The Story Writer writes one story per component it names: a component wrongly left
out surprises a team late, and one wrongly put in is a story nobody needs.

| | |
|---|---|
| **Start it** | `/impact <id>` |
| **`<id>`** | The work item, such as `REQ-101` |
| **Before you run it** | The requirement as an input (`work/<id>/inputs/`), or a GitLab story you name; the component catalog (`architecture/components.yaml`) and the components' profiles |
| **It reads** | The requirement and what the work item already has (a model change, mapping requests, digests); the catalog, every component's profile and own knowledge (its team's lineage and anatomy, first), the shared model; the declared checkouts, read-only |
| **It writes** | `work/<id>/impact.md`, by `templates/impact.md` |
| **It checks with** | `bridge-kit validate impact <id>` |
| **You decide** | Which components really change, every item below high confidence, every open question |

## What `impact.md` holds

- **Data elements:** each piece of data the requirement is about, followed through the components in the catalog's
  order: where it is in each, or that it's missing. Every missing hop is work for that component.
- **Affected components:** for each, why (the evidence: a schema path, a spec, a mapping row, a file and line, a
  profile), the contracts it owns that change (additive or breaking), the external impact where it has outside
  clients, and the confidence.
- **Not affected:** every other component of the catalog, with why.
- **Open questions:** each term it couldn't place, and everything the requirement leaves open, naming who answers.

## Tips

- Its accuracy rests on the catalog and the profiles: write them first, with `/profile-component` and `bridge-kit
  components build`, and keep the glossary growing (`/draft-glossary`).
- Read the evidence beside each claim, and every confidence below high; that's where it's least sure.
- A component that defines no schemas (the catalog's `defines_schemas: false`) never gets a schema change: that's
  the model's component's story.

## When it stops

- **The preflight stopped:** fix what it says, and run it again.
- **`validate impact` reports errors:** it fixes them before it finishes; if one stays, its reply says which.

Related: [Requirements Analyst](requirement-analyst.md), [Story Writer](story-writer.md) (works from `impact.md`),
the `impact-analysis` skill, `templates/impact.md`.
