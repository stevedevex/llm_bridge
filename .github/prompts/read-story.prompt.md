---
description: Read a GitLab story, with its comments and linked stories, and say what it asks; keep it as a work item's input when one is named
argument-hint: "<story: REQ-101 or its link> [work item]"
---

Read the GitLab story ${input:story:REQ-101, <project>#101 or its GitLab link} with the `gitlab-reading` skill, its
comments and linked stories included. If work item ${input:id:the work item it belongs to, e.g. REQ-102, or none}
is named, keep the story as its input with `bridge-kit inputs add` and read that file.

Then tell me, from the story alone: what it asks for and who for; its acceptance criteria, if it has any; what the
comments decided or still ask; and what it depends on. Say where the story is silent rather than filling the gap.
