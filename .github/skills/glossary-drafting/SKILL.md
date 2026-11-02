---
name: glossary-drafting
description: Step-by-step procedure for drafting a business area's glossary - the terms BAs use, each with its definition from a cited source, its synonyms and the internal model paths it means - from the model's titles and descriptions, the component profiles, the wiki, documents, mapping specs and lookups, by templates/glossary.yaml, checked with bridge-kit knowledge check. Use when setting up or growing architecture/glossary/<area>.yaml.
metadata:
  version: 0.1.1
  owner: ba-team
---

# Drafting a glossary area

The glossary is how the agents place a BA's words in the model: `bridge-kit knowledge term "<words>"` finds a term by
its name or a synonym and gives the model paths it means, for the Requirements Analyst, the Impact Analyzer, the
Model Designer and the Story Writer. A wrong definition misleads every one of them, so a term is worth its source.
The format is `templates/glossary.yaml`; one file per business area, `architecture/glossary/<area>.yaml`.

## 1. Read what's there

1. `architecture/glossary/*.yaml`: the terms already defined, in every area. A term is defined once across them all,
   a synonym included.
2. `bridge-kit knowledge term "<words>"` for the area's main words: what the glossary, the model's fields and the
   component profiles already say about each.

## 2. Gather the terms

From each source, the words BAs and the business use for the area's data, and what each one means:

- **The model:** the area's objects and fields, by their titles and descriptions (written for a business reader),
  and their code lists' values. The schemas are in the model's checkout, where `bridge-kit.yaml`'s `model.layout`
  says.
- **The component profiles,** `architecture/components/*.md`: their **Business areas and data** and **Screens**
  sections, the words the screens and the APIs use, each with where it is.
- **The wiki,** with the `gitlab-reading` skill (`bridge-kit gitlab wiki search <word>`), and the documents the BA
  gives, with the `document-reading` skill: definitions in the business's own words.
- **The mapping specs and lookups** in the BA repo (`mappings/`, `lookups/`): the rule and the code table behind a
  field.
- **The components' own glossaries,** the files the catalog points to as `glossary`: `bridge-kit knowledge term`
  lists their matching lines. Their codes and acronyms become terms, each with its source (the component and file).

## 3. Write each term

- **Its name:** as BAs say it, lower case unless it's an acronym (`IBAN`).
- **`definition`:** one sentence, in business words, from a source. When none defines it, or two sources disagree,
  don't write the term: list it in your reply as a question for the BA.
- **`synonyms`:** the other words a source uses for it: a screen's label, a document's, the wiki's. A synonym that's
  already another term's is a conflict: ask, don't choose.
- **`data`:** every model path it means, one a line, by payload path (`CustomerRecord.contactPreference.channel`). A
  term that isn't data (a process, a role) has none, and says so in its `note`.
- **`source`:** where the definition comes from: `schemas/contact-preference.json, channel's description`,
  `architecture/components/ui-react.md, Screens`, `wiki, customers/contact-preferences`, a work item's input by its
  file.
- **`note`:** only what a reader needs: who settled it, a near-word that means something else.

Add to the area's file when it exists. Never remove or rewrite a term someone wrote: propose the change in your
reply.

## 4. Check it

Run `.github/bridge-kit/bin/bridge-kit knowledge check` and fix every error: a path that isn't the model's, a term or
synonym defined twice, a term with no definition. Read each warning: a term with no data element either gets one or
says in its note that it isn't data.

## 5. Never

- **Never invent a definition.** No source, no term: it's a question for the BA.
- **Never copy** client data, a value from a record, a payload or a sample: terms and their meanings only.
- **Never write outside** `architecture/glossary/` and `.work/tmp/`.
