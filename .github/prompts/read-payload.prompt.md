---
description: Read a stored payload by its request id, check it against the internal model, and say what the real data shows
argument-hint: "<request id> [service]"
---

Read the stored payloads for request ${input:request:the request's UUID} with the `payload-reading` skill: with
`payload trace` when no service is named, otherwise with `payload get` for
${input:service:a service, e.g. service-a-java, or none}. Then run `payload check` on each payload found.

Then tell me: which services have a payload for it, from which environment, and where each is kept; what `check`
found, by model path, and what each finding likely means; and what you'd ask me before using the payload in a spec or
an example. Don't paste whole payloads: quote only the fields you talk about.
