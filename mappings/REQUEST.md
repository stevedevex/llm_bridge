---
work_item: <id>            # the work item it belongs to, e.g. REQ-101
upstream: <upstream>       # the upstream's id, as mapping specs name it, e.g. upstream-1
operation: <operation>     # as the upstream's spec names it, e.g. GetCustomer or GET /customers/{id}
target: <payload path>     # the slot (or the identity) it fills, from the payload root, e.g. CustomerRecord.contactPreference
spec: <spec>               # as given: Maven coordinates, a file in this repo (until it's in Nexus), or a URL
digest: <file>             # the Spec Explorer's digest, if there is one: work/<id>/inputs/spec-digest-<upstream>.md
rough_mapping: <file>      # your own working mapping, if you have one, kept as an input: work/<id>/inputs/NN-<name>.md
rough_mapping_table: <name>  # its sheet (or Table N, in a Word document), when it has more than one
---

# Mapping request: <upstream>, <operation>

A copy of this template, filled in, goes in the work item: `work/<id>/inputs/mapping-request.md`, or
`mapping-request-<operation>.md` when the work item maps several operations. The Mapping Drafter drafts the mapping
spec from it. Only the front matter and Purpose are required. **Leave a section blank when you don't know**: the
drafter asks instead of guessing, and its questions come back to you. Check it with
`.github/bridge-kit/bin/bridge-kit validate request <file>`. Its examples use a made-up model and upstreams.

**If you've worked the mapping out yourself**, in a spreadsheet or a table in a Word document, keep that file as an
input (`.github/bridge-kit/bin/bridge-kit inputs add <file> --work-item <id>`) and name the input it makes in
`rough_mapping`. Leave it as you wrote it, in your own columns: the drafter takes each of its rows that fits the spec
and the model as your decision, citing its cell, and asks about the rest. Rows you've struck through, hidden, coloured
without a legend or commented on, it doesn't take as settled. Delete both lines if you have none.

## Purpose

_To be written._ What the data is for, item by item, in business words: "the channel the customer chose to be
contacted on", not the upstream's field names.

## Known rules

Fallbacks, defaults, filters, units and time zones, as far as you know them, one per line: "when the channel code is
missing, leave the channel out"; "leave out closed accounts".

## Codes

What the upstream's codes mean, where its spec doesn't say: "`S` is SMS, whatever the phone number's country".

## Calling

Which identifier the call takes, and what a failure means: "called once per customer, with the customer's id";
"if it fails, the payload fails".

## Who to ask

Who answers each kind of question: the BA, the upstream team, the developers.

## Samples

Request ids of real payloads, or raw responses, in dev or SIT, to check the draft against.
