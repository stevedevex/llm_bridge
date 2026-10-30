---
description: Check a requirement package before the developers' implementable check, and report what a developer would have to ask
agent: spec-validator
argument-hint: "<work item id>"
---

Validate the requirement package of work item ${input:id:the work item id, e.g. REQ-101}: run the package check,
then read each story with the files it implements as that component's developer. Write the report to
`work/<id>/validation-NN.md`; change nothing else.
