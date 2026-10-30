---
description: Change the internal data model for a requirement, and write its merge request description
agent: model-designer
argument-hint: "<work item id> <what the model needs>"
---

Change the internal data model for work item ${input:id:the work item id, e.g. REQ-101}. It needs:
${input:needs:what the model needs, one item per line, or the fix}. ${input:digest:the Spec Explorer's digest for a new
upstream, if there is one, or none}
