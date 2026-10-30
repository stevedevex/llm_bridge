"""bridge-kit payload, against a stand-in MongoDB: payloads read by request id only, from declared services, from dev or
SIT, once bridge-kit.yaml says those hold test data; the guard refusing everything else before any query; MongoDB's
types as plain JSON; each payload kept in .work/payloads/; and the connection string in no output, ever."""

import datetime as dt
import json
import shutil
import uuid

import pytest
import yaml
from bson.binary import Binary, UuidRepresentation
from bson.decimal128 import Decimal128
from bson.objectid import ObjectId
from conftest import LANDSCAPE, SHARED_MODEL
from fixtures.fake_mongo import FakeMongo

from bridge_kit import payloads
from bridge_kit.cli import main

URI = "mongodb://ba-reader:s3cret-test-only@mongo.example:27017/?authSource=admin"
REQUEST = "3f1c2b9e-8d4a-4c1e-9f2a-6b7d8e9f0a1b"
OTHER = "0b2c4d6e-8f0a-4b2c-9d4e-6f8a0b2c4d6e"
ENV = {"BRIDGE_KIT_TEST_MONGO_URI": URI, "BRIDGE_KIT_TEST_MONGO_ENV": "dev", "BRIDGE_KIT_TEST_DC_DB": "lending-dev",
       "BRIDGE_KIT_TEST_DC_COLLECTION": "collected", "BRIDGE_KIT_TEST_DC_RAW": "raw-responses",
       "BRIDGE_KIT_TEST_CS_DB": "lending-dev", "BRIDGE_KIT_TEST_CS_COLLECTION": "summaries"}


def collected(request=REQUEST) -> dict:
    return {"_id": ObjectId("65f0a1b2c3d4e5f601234567"), "requestId": request,
            "creditFile": {"entities": [{"legalName": "Harbour Foods Ltd",
                                         "valuedAt": dt.datetime(2026, 3, 31, 9, 30, tzinfo=dt.timezone.utc),
                                         "exposure": Decimal128("1250000.50")}]}}


def summary(request=REQUEST, representation=UuidRepresentation.STANDARD) -> dict:
    return {"_id": ObjectId("65f0a1b2c3d4e5f601234568"),
            "requestId": Binary.from_uuid(uuid.UUID(request), representation),
            "createdAt": dt.datetime(2026, 4, 1, 8, 0, tzinfo=dt.timezone.utc),
            "payload": {"memos": [{"legalName": "Harbour Foods Ltd", "narrative": "A long-standing customer."}]}}


def config() -> dict:
    data = yaml.safe_load((LANDSCAPE / "bridge-kit.yaml").read_text(encoding="utf-8"))
    data["workspace"]["repos"]["shared-model"]["path"] = str(SHARED_MODEL)

    def env(name):
        return {"from": "env", "env": f"BRIDGE_KIT_TEST_{name}"}

    data["integrations"] = {"mongodb": {
        "uri": env("MONGO_URI"), "environment": env("MONGO_ENV"), "test_data_only": True,
        "services": {"service-a-java": {"database": env("DC_DB"), "collection": env("DC_COLLECTION"),
                                                 "schema": "model-input",
                                                 "raw": {"collection": env("DC_RAW")}},
                     "service-b-python": {"database": env("CS_DB"), "collection": env("CS_COLLECTION"),
                                                "schema": "model-output", "payload_field": "payload"}}}}
    return data


@pytest.fixture
def mongo(tmp_path, monkeypatch):
    """A BA repo whose bridge-kit.yaml declares the stand-in MongoDB; returns the repo, the stand-in and a way to
    rewrite bridge-kit.yaml."""
    fake = FakeMongo({"lending-dev": {"collected": [collected()], "summaries": [summary()], "raw-responses": []}})
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)

    def write(data):
        (repo / ".github" / "bridge-kit" / "bridge-kit.yaml").write_text(yaml.safe_dump(data, sort_keys=False),
                                                                        encoding="utf-8")

    write(config())
    (repo / "architecture").mkdir()
    shutil.copy(LANDSCAPE / "architecture" / "components.yaml", repo / "architecture" / "components.yaml")
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(payloads, "make_client", fake.client)
    return {"fake": fake, "repo": repo, "write": write}


def example(name: str) -> dict:
    return json.loads((SHARED_MODEL / "examples" / f"{name}.example.json").read_text(encoding="utf-8"))


def run(capsys, *args) -> tuple[int, str, str]:
    code = main(["payload", *args])
    out = capsys.readouterr()
    assert "s3cret" not in out.out + out.err  # the connection string is in no output, ever
    return code, out.out, out.err


def test_status_says_the_environment_and_that_each_declared_collection_answers(mongo, capsys):
    code, out, _ = run(capsys, "status")

    assert code == 0, out
    assert out.splitlines() == [
        "Environment: dev, test data only",
        "Connection: OK",
        "service-a-java payloads: answers (BRIDGE_KIT_TEST_DC_DB, BRIDGE_KIT_TEST_DC_COLLECTION)",
        "service-a-java raw responses: answers (BRIDGE_KIT_TEST_DC_DB, BRIDGE_KIT_TEST_DC_RAW)",
        "service-b-python payloads: answers (BRIDGE_KIT_TEST_CS_DB, BRIDGE_KIT_TEST_CS_COLLECTION)",
        "MongoDB: OK"]
    assert mongo["fake"].uris == [URI]


def test_status_finds_a_collection_that_isn_t_there(mongo, capsys):
    del mongo["fake"].data["lending-dev"]["summaries"]

    code, out, _ = run(capsys, "status")

    assert code == 1
    assert ("PROBLEM service-b-python payloads: the database BRIDGE_KIT_TEST_CS_DB names has no collection "
            "BRIDGE_KIT_TEST_CS_COLLECTION names") in out
    assert out.endswith("MongoDB: 1 problem(s)\n")


def test_get_returns_the_payload_as_plain_json_and_keeps_it(mongo, capsys):
    code, out, _ = run(capsys, "get", "service-a-java", REQUEST)

    assert code == 0, out
    kept = mongo["repo"] / ".work" / "payloads" / "service-a-java" / f"{REQUEST}.json"
    assert out.startswith(f"service-a-java payload {REQUEST}, from dev; kept in "
                          f".work/payloads/service-a-java/{REQUEST}.json\n")
    expected = {"requestId": REQUEST, "creditFile": {"entities": [{
        "legalName": "Harbour Foods Ltd", "valuedAt": "2026-03-31T09:30:00Z", "exposure": 1250000.5}]}}
    assert json.loads(kept.read_text(encoding="utf-8")) == expected
    assert json.loads(out.split("\n\n", 1)[1]) == expected
    assert mongo["fake"].queries[0][:2] == ("lending-dev", "collected")


def test_get_as_json_says_where_it_came_from(mongo, capsys):
    code, out, _ = run(capsys, "get", "service-a-java", REQUEST, "--json")

    data = json.loads(out)
    assert code == 0
    assert (data["service"], data["request_id"], data["environment"]) == ("service-a-java", REQUEST, "dev")
    assert data["payload"]["creditFile"]["entities"][0]["exposure"] == 1250000.5


@pytest.mark.parametrize("representation", [UuidRepresentation.STANDARD, UuidRepresentation.JAVA_LEGACY])
def test_a_request_id_stored_as_a_bson_uuid_is_found_and_a_wrapped_payload_unwrapped(mongo, capsys, representation):
    mongo["fake"].data["lending-dev"]["summaries"] = [summary(representation=representation)]

    code, out, _ = run(capsys, "get", "service-b-python", REQUEST.upper(), "--json")

    assert code == 0, out
    assert json.loads(out)["payload"] == {"memos": [{"legalName": "Harbour Foods Ltd",
                                                     "narrative": "A long-standing customer."}]}


def test_a_wrapped_payload_whose_field_isn_t_there_says_so(mongo, capsys):
    data = config()
    data["integrations"]["mongodb"]["services"]["service-b-python"]["payload_field"] = "body.payload"
    mongo["write"](data)

    code, _, err = run(capsys, "get", "service-b-python", REQUEST)

    assert code == 1
    assert "has no body.payload: check payload_field in bridge-kit.yaml" in err


def test_a_request_with_no_payload_says_so(mongo, capsys):
    code, _, err = run(capsys, "get", "service-a-java", OTHER)

    assert code == 1
    assert err.strip() == f"No service-a-java payload has requestId {OTHER} in dev"


def test_trace_puts_the_request_in_each_service_side_by_side(mongo, capsys):
    code, out, _ = run(capsys, "trace", REQUEST, "--json")

    assert code == 0, out
    found = json.loads(out)["payloads"]
    assert list(found) == ["service-a-java", "service-b-python"]
    assert found["service-a-java"]["creditFile"]["entities"][0]["legalName"] == "Harbour Foods Ltd"
    assert found["service-b-python"]["memos"][0]["narrative"] == "A long-standing customer."


def test_trace_says_which_service_has_none(mongo, capsys):
    mongo["fake"].data["lending-dev"]["summaries"] = []

    code, out, _ = run(capsys, "trace", REQUEST)

    assert code == 0
    assert "## service-b-python\n\nNone for this request.\n" in out


def test_trace_with_no_payload_anywhere_fails(mongo, capsys):
    code, _, err = run(capsys, "trace", OTHER)

    assert code == 1
    assert f"No declared service has a payload for {OTHER} in dev" in err


def _without_mongodb(data):
    del data["integrations"]["mongodb"]


def _not_confirmed(data):
    data["integrations"]["mongodb"]["test_data_only"] = False


@pytest.mark.parametrize("change, env, args, message", [
    (_without_mongodb, {}, ("status",), "bridge-kit.yaml declares no MongoDB: add integrations.mongodb"),
    (_not_confirmed, {}, ("status",), "doesn't say dev and SIT hold test data only"),
    (None, {"BRIDGE_KIT_TEST_MONGO_ENV": "prod"}, ("status",),
     "Payloads are read from dev or SIT only, and BRIDGE_KIT_TEST_MONGO_ENV says prod"),
    (None, {"BRIDGE_KIT_TEST_MONGO_ENV": None}, ("status",),
     "No MongoDB environment: the environment variable BRIDGE_KIT_TEST_MONGO_ENV isn't set"),
    (None, {}, ("get", "ui-react", REQUEST),
     "ui-react isn't a declared service: service-a-java, service-b-python"),
    (None, {}, ("get", "service-a-java", '{"$ne": null}'), "isn't a request id"),
    (None, {}, ("trace", "REQ-142"), "REQ-142 isn't a request id"),
])
def test_the_guard_refuses_before_any_query(mongo, capsys, monkeypatch, change, env, args, message):
    if change:
        data = config()
        change(data)
        mongo["write"](data)
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name)
        else:
            monkeypatch.setenv(name, value)

    code, _, err = run(capsys, *args)

    assert code == 2
    assert message in err
    assert mongo["fake"].queries == []


def test_a_database_variable_not_set_says_which(mongo, capsys, monkeypatch):
    monkeypatch.delenv("BRIDGE_KIT_TEST_DC_COLLECTION")

    code, _, err = run(capsys, "get", "service-a-java", REQUEST)

    assert code == 2
    assert ("No MongoDB collection for service-a-java: the environment variable BRIDGE_KIT_TEST_DC_COLLECTION "
            "isn't set") in err


def test_no_connection_string_says_where_it_was_looked_for(mongo, capsys, monkeypatch):
    monkeypatch.delenv("BRIDGE_KIT_TEST_MONGO_URI")

    code, _, err = run(capsys, "get", "service-a-java", REQUEST)

    assert code == 1
    assert "No MongoDB connection string: the environment variable BRIDGE_KIT_TEST_MONGO_URI isn't set" in err


def test_a_mongodb_error_never_shows_the_connection_string(mongo, capsys):
    mongo["fake"].fail = TimeoutError(f"No servers answered at {URI}, timed out\nmore detail")

    code, _, err = run(capsys, "get", "service-a-java", REQUEST)

    assert code == 1
    assert err.strip() == "MongoDB: TimeoutError: No servers answered at <connection string> timed out"


def test_a_connection_string_the_driver_refuses_says_so_without_it(mongo, capsys, monkeypatch):
    def refuse(uri):
        raise ValueError(f"Invalid URI {uri}")

    monkeypatch.setattr(payloads, "make_client", refuse)

    code, out, _ = run(capsys, "status")

    assert code == 1
    assert "PROBLEM connection: The MongoDB connection string isn't one the driver can use" in out



def raw_responses() -> list[dict]:
    return [{"_id": ObjectId(), "requestId": REQUEST, "upstream": "contacts", "operation": "lookupContacts",
             "response": {"people": [{"name": "Ana Silva"}]}},
            {"_id": ObjectId(), "requestId": REQUEST, "upstream": "accounts", "operation": "getBalances",
             "response": {"Data": {"Balance": [{"Amount": {"Amount": "1250.50", "Currency": "GBP"}}]}}},
            {"_id": ObjectId(), "requestId": OTHER, "upstream": "accounts", "operation": "getBalances", "response": {}}]


def test_raw_gives_each_upstream_s_responses_for_the_request(mongo, capsys):
    mongo["fake"].data["lending-dev"]["raw-responses"] = raw_responses()

    code, out, _ = run(capsys, "raw", REQUEST, "--json")

    assert code == 0, out
    responses = json.loads(out)["raw"]["service-a-java"]
    assert [(r["upstream"], r["operation"]) for r in responses] == [("accounts", "getBalances"),
                                                                    ("contacts", "lookupContacts")]
    kept = mongo["repo"] / ".work" / "payloads" / "service-a-java" / f"{REQUEST}.raw.json"
    assert json.loads(kept.read_text(encoding="utf-8")) == responses


def test_raw_for_one_upstream(mongo, capsys):
    mongo["fake"].data["lending-dev"]["raw-responses"] = raw_responses()

    code, out, _ = run(capsys, "raw", REQUEST, "contacts")

    assert code == 0, out
    assert "### contacts / lookupContacts" in out and "accounts" not in out
    assert mongo["fake"].queries[-1][2]["upstream"] == "contacts"


def test_raw_with_none_says_so(mongo, capsys):
    code, _, err = run(capsys, "raw", REQUEST, "accounts")

    assert code == 1
    assert f"No raw responses for {REQUEST} from accounts in dev" in err


@pytest.mark.parametrize("args, message", [
    ((REQUEST, '{"$ne": null}'), "isn't an upstream's name"),
    (("not-a-uuid",), "isn't a request id"),
])
def test_raw_refuses_what_isn_t_a_request_or_an_upstream(mongo, capsys, args, message):
    code, _, err = run(capsys, "raw", *args)

    assert code == 2
    assert message in err
    assert mongo["fake"].queries == []


def test_raw_needs_a_service_that_keeps_them(mongo, capsys):
    data = config()
    del data["integrations"]["mongodb"]["services"]["service-a-java"]["raw"]
    mongo["write"](data)

    code, _, err = run(capsys, "raw", REQUEST)

    assert code == 2
    assert "No declared service keeps raw upstream responses" in err


def call(tool: str, arguments: dict) -> tuple[bool, str]:
    """One tool call to the MCP server, in this process so the stand-in serves it: (is it an error, its text)."""
    from bridge_kit.mcp.server import Server

    result = Server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": tool, "arguments": arguments}})["result"]
    return result["isError"], result["content"][0]["text"]


def test_the_mcp_tools_read_payloads_through_the_same_guard(mongo):
    mongo["fake"].data["lending-dev"]["raw-responses"] = raw_responses()

    error, text = call("payload_status", {})
    assert not error and text.endswith("MongoDB: OK\n")
    error, text = call("payload_get", {"service": "service-a-java", "request_id": REQUEST})
    assert not error and text.startswith(f"service-a-java payload {REQUEST}, from dev")
    error, text = call("payload_profile", {"service": "service-a-java", "request_ids": [REQUEST]})
    assert not error and text.startswith("service-a-java: 1 payload(s)")
    error, text = call("payload_raw", {"request_id": REQUEST, "upstream": "contacts"})
    assert not error and "### contacts / lookupContacts" in text
    assert call("payload_get", {"service": "service-a-java", "request_id": "REQ-142"}) == (
        True, "REQ-142 isn't a request id: payloads are looked up by their UUID request id only")


def test_without_a_mongodb_each_payload_tool_says_what_to_add(mongo):
    data = config()
    del data["integrations"]["mongodb"]
    mongo["write"](data)

    error, text = call("payload_trace", {"request_id": REQUEST})

    assert error and text.startswith("bridge-kit.yaml declares no MongoDB: add integrations.mongodb")


def test_every_payload_read_is_audited_from_both_front_ends_without_secrets(mongo, capsys):
    run(capsys, "get", "service-a-java", REQUEST)
    run(capsys, "get", "service-a-java", OTHER)
    call("payload_trace", {"request_id": REQUEST})

    log = (mongo["repo"] / ".work" / "logs" / "bridge-kit.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(line) for line in log.splitlines()]
    assert [(line["via"], line["tool"], line["ok"]) for line in lines] == [
        ("cli", "payload get", True), ("cli", "payload get", False), ("mcp", "payload_trace", True)]
    assert lines[0]["arguments"] == {"service": "service-a-java", "request_id": REQUEST}
    assert lines[1]["error"] == f"No service-a-java payload has requestId {OTHER} in dev"
    assert all(line["who"] for line in lines)
    assert "s3cret" not in log and "Harbour Foods" not in log


def test_the_preflight_says_whether_payloads_can_be_read(mongo):
    from bridge_kit.preflight import format_preflight, preflight

    report = preflight(mongo["repo"])

    assert report.mongodb == "dev: 2 service(s), 3 collection(s) answer: OK"
    assert "MongoDB:     dev: 2 service(s), 3 collection(s) answer: OK" in format_preflight(report)
    assert not [w for w in report.warnings + report.stops if w.startswith("MongoDB")]


def test_payloads_that_can_t_be_read_only_warn_in_the_preflight(mongo):
    from bridge_kit.preflight import preflight

    data = config()
    data["integrations"]["mongodb"]["test_data_only"] = False
    mongo["write"](data)

    report = preflight(mongo["repo"])

    assert report.mongodb.startswith("not checked: bridge-kit.yaml doesn't say dev and SIT hold test data only")
    assert any(w.startswith("MongoDB: ") for w in report.warnings)
    assert not any(s.startswith("MongoDB") for s in report.stops)
    assert mongo["fake"].uris == []


def test_check_finds_where_a_stored_payload_breaks_the_model(mongo, capsys):
    payload = example("customer-record")
    payload["segment"] = "VIP"
    mongo["fake"].data["lending-dev"]["collected"] = [{"_id": ObjectId(), "requestId": REQUEST, **payload}]

    code, out, _ = run(capsys, "check", "service-a-java", REQUEST)

    assert code == 1
    assert out.splitlines() == [
        f"service-a-java payload {REQUEST} against the model's CustomerRecord",
        "- CustomerRecord.segment: not one of its codes: VIP",
        f"Kept in .work/payloads/service-a-java/{REQUEST}.json"]


def test_check_of_a_payload_that_matches_the_model_passes(mongo, capsys):
    mongo["fake"].data["lending-dev"]["summaries"] = [{**summary(), "payload": example("customer-summary")}]

    code, out, _ = run(capsys, "check", "service-b-python", REQUEST, "--json")

    data = json.loads(out)
    assert code == 0, out
    assert (data["root"], data["findings"], data["wrapped"]) == ("CustomerSummary", [], False)


def test_check_needs_the_contract_s_root_in_the_catalog(mongo, capsys):
    catalog = mongo["repo"] / "architecture" / "components.yaml"
    catalog.write_text(catalog.read_text(encoding="utf-8").replace(" root: CustomerRecord,", ""), encoding="utf-8")

    code, _, err = run(capsys, "check", "service-a-java", REQUEST)

    assert code == 2
    assert "model-input has no root in architecture/components.yaml" in err
    assert mongo["fake"].queries == []


def test_profile_reads_each_request_and_names_one_with_none(mongo, capsys):
    third = "7a6b5c4d-3e2f-4a1b-8c9d-0e1f2a3b4c5d"
    mongo["fake"].data["lending-dev"]["collected"].append(collected(OTHER))

    code, out, _ = run(capsys, "profile", "service-a-java", REQUEST, OTHER, third)

    assert code == 0, out
    assert out.startswith("service-a-java: 2 payload(s)\n")
    assert "| `CustomerRecord.creditFile.entities[].legalName` | 2 |  | string |  | Harbour Foods Ltd (2) |" in out
    assert out.endswith(f"None for {third}\n")
