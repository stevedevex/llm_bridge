---
description: Draft a business area's glossary terms - each with its definition from a cited source, its synonyms and its internal model paths - from the model, the component profiles, the wiki and documents, and check them
argument-hint: "<area, e.g. customer-record> [where to look first]"
---

Draft the glossary terms of the ${input:area:business area, e.g. customer-record} area with the `glossary-drafting`
skill, into `architecture/glossary/<area>.yaml` by `templates/glossary.yaml`, each term with the source of its
definition. Start from ${input:sources:where to look first, e.g. a wiki page or a document, or leave empty}, then
the model, the component profiles and the wiki. Check them with `bridge-kit knowledge check`.

Then tell me: the terms you wrote, each with its source; the terms you left out because nothing defines them, or
because sources disagree; any synonym that's already another term's; and the check's result.
