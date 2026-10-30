---
description: Read a document the BA brings - a spreadsheet, a Word or PDF document, slides, an email, a saved page - and say what it holds; keep it as a work item's input when one is named
argument-hint: "<file> [work item]"
---

Read ${input:file:the document's path, e.g. ~/Downloads/rough-mapping.xlsx} with the `document-reading` skill. If
work item ${input:id:the work item it belongs to, e.g. REQ-102, or none} is named, keep it as its input with
`bridge-kit inputs add` and read that file; otherwise read it with `bridge-kit doc read`.

Then tell me what it holds, briefly, citing where each point is: a page, a sheet and cell, a slide. Pass on every
warning BRIDGE gave, and say what you'd ask me about: colours, struck-through rows, tracked changes, comments, hidden
sheets, pages without text, images that may matter. Say where the document is silent rather than filling the gap.
