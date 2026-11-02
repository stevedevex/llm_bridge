# The standalone prompts

Prompts with no agent of their own: any Copilot chat can run them, each with its skill. With a work item named,
what a reading prompt reads is kept as one of its inputs, `work/<id>/inputs/NN-....md`, and never changed after:
a newer version becomes a new input.

## Reading what you have

| Prompt | Use it to | Arguments | It writes |
|---|---|---|---|
| `/read-story` | Read a GitLab story with its comments and linked stories, and say what it asks | `<story>`: `REQ-101`, `<project>#101` or its link; `[work item]` | The story as an input, when a work item is named |
| `/read-wiki` | Find what the GitLab wiki says, and answer from its pages | `<what to find, or a page's slug>`; `[work item]` | Each page relied on as an input, when a work item is named |
| `/read-document` | Read a document and say what it holds, with every warning | `<file>`: Excel, Word, PDF, PowerPoint, HTML, an email (`.eml`, `.msg`), an image; `[work item]` | The document as an input, when a work item is named |
| `/read-payload` | Read a stored payload, check it against the model, say what real data shows | `<request id>`: its UUID; `[service]` | Each payload in the git-ignored `.work/payloads/` |

- **GitLab and the wiki:** only the projects, groups and wikis `bridge-kit.yaml` declares, with your own token, which
  no agent ever sees.
- **Documents:** BRIDGE warns where values look like personal data (emails, IBANs, card numbers) without showing
  them, and refuses locked files and the old formats (`.doc`, `.xls`, `.ppt`). Copilot reads images itself.
- **Payloads:** dev or SIT only, by request id only, once `bridge-kit.yaml` says those hold test data.

## Publishing

| Prompt | Use it to | Arguments | It writes |
|---|---|---|---|
| `/publish-stories` | Create a work item's approved stories as GitLab issues | `<id>` | The issues, linked to the requirement and to each other; each story's GitLab id in its file |

It runs a dry run first and shows you what it would create; it creates them only after your OK in the chat. A story
already in GitLab is never created again.

## Setting a BA repo up

| Prompt | Use it to | Arguments | It writes |
|---|---|---|---|
| `/profile-component` | Read one component's repo and write its profile: what it does, its data, contracts, screens, where changes go | `<the component's folder>`; `<its name in the catalog>` | `architecture/components/<name>.md`, then `bridge-kit components build` assembles the catalog, and `bridge-kit components scan` points it to each team's own AI layer |
| `/profile-model` | Propose the model's layout and conventions, with the evidence; draft its `CONVENTIONS.md` when it has none | `[the model's checkout]`, by default the one `bridge-kit.yaml` names | `.work/setup/model-profile.md`, and a draft `.work/setup/CONVENTIONS.md` for the model's owners |
| `/draft-glossary` | Draft a business area's terms, each with its definition's source, its synonyms and its model paths | `<area>`, such as `customer-record`; `[where to look first]` | `architecture/glossary/<area>.yaml`, checked by `bridge-kit knowledge check` |

These read only: `/profile-component` and `/profile-model` never change, build or run anything in the repo they read,
and never write in it. A profile, a conventions draft or a glossary is a draft for you, an architect or the model's
owners to review.

Related: the [guide](../GUIDE.md), "Bringing in what you have"; the README's "Setting up a BA repo".
