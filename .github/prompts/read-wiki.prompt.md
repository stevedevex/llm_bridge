---
description: Find what the pod's GitLab wiki says about something, or read one of its pages; keep a page as a work item's input when one is named
argument-hint: "<what to find, or a page's slug> [work item]"
---

Use the `gitlab-reading` skill to find what the GitLab wiki says about ${input:topic:what to look for, or a page's
slug such as onboarding/checklist}: search it, then read the pages that match (or the page named). If work item
${input:id:the work item it's for, e.g. REQ-102, or none} is named, keep each page you rely on as its input with
`bridge-kit inputs add`.

Then answer from those pages, naming the page each point comes from. Say what the wiki doesn't cover rather than
filling the gap.
