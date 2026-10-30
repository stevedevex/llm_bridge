---
description: Write a work item's test cases from its approved stories, by the test case template, and check their coverage
agent: test-designer
argument-hint: "<work item id>"
---

Write the test cases for work item ${input:id:the work item id, e.g. REQ-101} from its approved stories, its
`impact.md` and the files the stories implement. Show me the plan of cases first, then write them to
`work/<id>/tests/`, and check them with `bridge-kit validate test-case` and `bridge-kit tests coverage`.
