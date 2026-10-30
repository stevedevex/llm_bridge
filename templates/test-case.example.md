---
template: test-case@1
id: null
case: TC-1
parent: REQ-101
title: A customer who chose SMS sees it on the customer panel, from the upstream to the panel
status: draft
level: end-to-end
type: functional
path: happy
technique: equivalence
priority: high
verifies:
  - story: work/REQ-101/stories/ui-react-06-contact-channel.md
    criteria: [AC-1]
  - story: work/REQ-101/stories/service-d-java-05-contact-channel.md
    criteria: [AC-1]
  - story: work/REQ-101/stories/service-c-java-04-contact-channel.md
    criteria: [AC-1]
  - story: work/REQ-101/stories/service-a-java-02-contact-channel.md
    criteria: [AC-1]
versions:
  model-input: 3.1.0
  service-d-api: v2
  upstream-1-customer-api-spec: 4.2.0
environment: sit
automation: candidate
automated_by: null
---

## Objective

Proves, from the upstream to the screen, that a customer's preferred contact channel reaches the customer panel:
ui-react's AC-1 (*The panel shows the preferred contact channel*), carried by each hop's AC-1 before it, and the
collecting service's lookup (collection AC-1). Unlike TC-2 (no preference) and TC-4 (an unknown code), the customer
chose SMS.

## Preconditions

- SIT runs every service on the shared model's `model-input` 3.1.0, and service-d-java's customer API v2.
- upstream-1 is stubbed in SIT: `GET /customers/{customer-id}` answers with `contactPreference.channelCode` `{code}`;
  for any other customer, with no `contactPreference`.
- `{customer}` exists in SIT with `{customer-id}`, and no other customer has that id.
- `{manager}` can sign in with the relationship manager role.

## Test data

| Name | Value | Why | Source |
|---|---|---|---|
| `{manager}` | `ba.tester.01` | A relationship manager, the stories' role | SIT's test users |
| `{customer}` | `CU-000042`, "Ada Lindqvist" | A customer with a preference | Made up |
| `{customer-id}` | `CU-000042` | That customer's id in upstream-1 | Made up |
| `{code}` | `S` | The code upstream-1 sends for SMS (collection AC-1) | The stub |
| `{request}` | The id of the request behind step 2's panel | It ties the hops together | Step 3 |

## Steps

| # | Action | Expected result |
|---|---|---|
| 1 | Sign in in SIT as `{manager}` | The home page shows `{manager}` signed in |
| 2 | Search for `CU-000042`, and open `{customer}`'s panel | The panel's heading is "Ada Lindqvist" |
| 3 | Note the id of the request behind the panel as `{request}` (open question 2) | A UUID |
| 4 | Look at the panel's contact section | It says "Preferred contact: SMS" (open question 1) |
| 5 | Check each hop of the data path, below, for `{request}` | Each hop holds what its row says |

## Checks along the data path

| Hop | Where to look | Expected |
|---|---|---|
| Upstream | The stub's request log | One `GET /customers/{customer-id}` call, answered with `channelCode` `{code}` |
| Internal model | `bridge-kit payload get service-a-java {request}`: `CustomerRecord.contactPreference.channel` | `SMS`. And `bridge-kit payload check service-a-java {request}` finds nothing |
| Business API | service-c-java's `GET /customers/CU-000042`: `contactPreference.channel` | `SMS` |
| Customer API | service-d-java's `GET /v2/customers/CU-000042`: `contactPreference.channel` | `SMS` |
| UI | The panel's contact section | Step 4's line |

## Pass criteria

- Every step's expected result holds, and so does every hop's row.
- The code is translated once, by the collecting service: every hop after it holds `SMS`, never `S`.
- **Never:** an error on the panel; another customer's preference; the code `S` shown on the panel.

## Cleanup

Remove the stub's answer for `{customer-id}`, so the next case sets its own.

## Automation notes

- Automate it below the screen first: the data path's rows up to the customer API as an integration test against the
  stub, and the UI row as a component test of the customer panel with the customer API stubbed. Keep the end-to-end
  run for a release's checks.
- Find the contact section by its accessible name (ui AC-3), never by position or style.
- The request id ties the hops together: an automated run needs it from the response or the logs (open question 2).

## Open questions

1. Does the panel show the channel as a word ("SMS") or with an icon too? The ui-react story says only that it shows
   the preferred contact channel. (The BA)
2. Where does SIT show the id of the request behind a panel, for the data path's checks: a response header, or a
   service's log? (service-a-java's team)
