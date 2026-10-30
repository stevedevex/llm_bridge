"""payload check and profile, on payloads made from the fixture model's own examples: the examples match the model,
each kind of break is found by its model path (a list's items as one path, counted), a date stored as midnight UTC is
the date it is, the request id beside a payload isn't a finding, a wrapped payload is named as one, and a profile
gives each path's presence, nulls, types, list sizes and codes."""

import json

from conftest import SHARED_MODEL

from bridge_kit.payload_check import check, profile, render_check, render_profile, wrapped

EXAMPLES = SHARED_MODEL / "examples"
REQUEST = "3f1c2b9e-8d4a-4c1e-9f2a-6b7d8e9f0a1b"


def example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.example.json").read_text(encoding="utf-8"))


def texts(found) -> list[str]:
    return [f.text for f in found]


def test_the_model_s_own_examples_match_it(model):
    assert check(model, "CustomerRecord", example("customer-record")) == []
    assert check(model, "CustomerSummary", example("customer-summary")) == []


def test_each_kind_of_break_is_found_by_its_model_path(model):
    payload = example("customer-record")
    payload["nickname"] = "Al"
    del payload["name"]
    payload["displayName"] = None
    payload["segment"] = "VIP"
    payload["phone"] = "01632 960123"
    account = payload["accounts"][0]
    account["balance"]["bookedBalance"]["value"] = "2450.75"
    account["openingDate"] = "01/07/2019"

    assert texts(check(model, "CustomerRecord", payload)) == [
        "CustomerRecord.nickname: not in the model",
        "CustomerRecord.name: required, missing",
        "CustomerRecord.displayName: null",
        "CustomerRecord.accounts[].balance.bookedBalance.value: wrong type: string",
        "CustomerRecord.segment: not one of its codes: VIP",
        "CustomerRecord.accounts[].openingDate: not its format: 01/07/2019",
        "CustomerRecord.phone: not its format: 01632 960123",
    ]


def test_the_same_break_in_many_items_is_one_finding_counted(model):
    payload = example("customer-record")
    payload["accounts"][0]["status"], payload["accounts"][1]["status"] = "DORMANT", "SUSPENDED"

    assert texts(check(model, "CustomerRecord", payload)) == [
        "CustomerRecord.accounts[].status: not one of its codes: DORMANT, SUSPENDED (2 times)"]


def test_a_date_stored_as_midnight_utc_is_the_date_it_is(model):
    payload = example("customer-record")
    account = payload["accounts"][0]

    account["openingDate"] = "2019-07-01T00:00:00Z"
    assert check(model, "CustomerRecord", payload) == []
    account["openingDate"] = "2019-07-01T09:30:00Z"
    assert texts(check(model, "CustomerRecord", payload)) == [
        "CustomerRecord.accounts[].openingDate: not its format: 2019-07-01T09:30:00Z"]


def test_the_request_id_beside_a_payload_isn_t_a_finding(model):
    payload = {"requestId": REQUEST, **example("customer-record")}

    assert check(model, "CustomerRecord", payload, ("requestId",)) == []
    assert texts(check(model, "CustomerRecord", payload)) == ["CustomerRecord.requestId: not in the model"]


def test_a_wrapped_payload_is_named_as_one(model):
    found = check(model, "CustomerRecord", {"customerRecord": example("customer-record")})

    assert texts(found) == ["CustomerRecord.customerRecord: not in the model",
                            "CustomerRecord.accounts: required, missing",
                            "CustomerRecord.contactPreference: required, missing",
                            "CustomerRecord.customerId: required, missing", "CustomerRecord.name: required, missing"]
    assert wrapped(found, "CustomerRecord")
    assert "name the payload's field as payload_field in bridge-kit.yaml" in \
        render_check("service-a-java", REQUEST, "CustomerRecord", found)


def test_a_profile_gives_each_path_s_presence_nulls_types_sizes_and_codes():
    shapes = profile("CustomerRecord", [
        {"accounts": [{"status": "OPEN", "currency": None}, {"status": "CLOSED"}]},
        {"accounts": [{"status": "OPEN", "currency": "GBP"}]}])
    by_path = {s.path: s for s in shapes}

    assert by_path["CustomerRecord.accounts"].sizes == [2, 1]
    status = by_path["CustomerRecord.accounts[].status"]
    assert (status.present, status.nulls, dict(status.values), status.coded) == (3, 0, {"OPEN": 2, "CLOSED": 1}, True)
    currency = by_path["CustomerRecord.accounts[].currency"]
    assert (currency.present, currency.nulls, dict(currency.types)) == (2, 1, {"string": 1})
    text = render_profile("service-a-java", ["a", "b"], shapes)
    assert "| `CustomerRecord.accounts` | 2 |  | array | 1–2 |  |" in text
    assert "| `CustomerRecord.accounts[].status` | 3 |  | string |  | OPEN (2), CLOSED (1) |" in text
