---
description: Create a work item's approved stories as GitLab issues, in each component's project, once the BA has seen the list and said so
argument-hint: "<work item id>"
---

Publish the stories of work item ${input:id:the work item id, e.g. REQ-101} with the `gitlab-writing` skill: run the
dry run, show me what it would create (or what stops it), and wait for my OK before you run it with `--yes`. Then
tell me each story's GitLab id, and that the story files changed.
