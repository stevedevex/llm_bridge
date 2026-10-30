# The shared model: conventions

A made-up model, for the kit's tests. Every schema follows these rules, which are the kit's defaults.

## Structure

The collected payload is a `CustomerRecord`: one customer. Every part of it is one of two kinds.

- **Identity:** who the customer is and which accounts they hold, from the customer directory: the record's own
  fields (`customerId`, `name`, ...) and each account's (`accountId`, `status`, ...).
- **Slots:** the data, **one slot per source**. Each upstream fills a slot of its own and nothing else:
  `contactPreference` on the record, `balance` on each account.

```
CustomerRecord                 identity, then its slot
├── contactPreference          ContactPreferenceSlot ← upstream-1, the customer API
└── accounts[]                 Account: identity, then its slot
    └── balance                BalanceSlot           ← upstream-2, the balances
```

- A slot sits on the record when its source describes the customer, and on the account when it describes one
  account.
- A slot is an object in its own file, `<name>-slot.json`, titled `<Name>Slot`, and required on its parent: it's
  always there, even when its source has nothing.
- **A new upstream gets a new slot.** Data from a source that already has a slot goes into that slot.

The model also holds the summary service's output, a second root, `CustomerSummary`, written from one record. It has
no slots, and its names describe the summary, not the input field they come from.

## Files

- One schema per object, in `schemas/`, with a kebab-case file name. No subfolders.
- JSON Schema draft-07. `title` is the class name.
- `additionalProperties: false` on every object, and a `description` on every property.
- Each root has an example in `examples/`, named after its file (`customer-record.example.json`).

## Names and types

- Fields are camelCase; booleans without `is` or `has` (`joint`); lists plural (`accounts`).
- Dates are strings with format `date`; money is `amount.json`; currencies ISO 4217 and countries ISO 3166-1
  alpha-2, upper case; coded values are enums in UPPER_SNAKE_CASE, our own.
- Lists are always present and required; other fields are left out when unknown. Nothing is `null`.

## Versions

- The version is in `pom.xml` and `python/pyproject.toml`, and they're equal.
- **Patch:** text only. **Minor:** a new optional field, object, enum value or list. **Major:** a new slot, or
  anything removed, renamed, retyped or made required.

## Who uses it

`service-a-java` fills `CustomerRecord`; `service-b-python` reads it and writes `CustomerSummary`; `service-c-java`
and `service-d-java` pass both on.
