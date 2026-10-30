"""MongoDB payload samples: the payloads services store, looked up by request id and nothing else. Every call goes
through the guard first: `bridge-kit.yaml` must say dev and SIT hold test data only (`test_data_only: true`), the
environment must be dev or SIT, the service declared, the request id a UUID.

Every name comes from an environment variable `bridge-kit.yaml` names: the connection string, the environment, each
database and collection. The connection string holds a password, so it's read like the GitLab token, and no output,
log line or error carries it. MongoDB's own types come back as plain JSON (dates as ISO text, decimals as numbers
where that's exact, ids and UUIDs as text), and each payload fetched is kept in the git-ignored
`.work/payloads/<service>/<request id>.json`. `payload check` and `profile` read the payloads by the model's paths,
from the root the service's contract names in the component catalog (`payload_check.py`).
"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import json
import os
import re
import uuid
from pathlib import Path

from bridge_kit.auth import TokenError
from bridge_kit.config import Config, MongoConfig, MongoService
from bridge_kit.paths import repo_root, work_dir

ENVIRONMENTS = ("dev", "sit")
REQUEST_ID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
UPSTREAM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
CONNECTION_STRING = re.compile(r"mongodb(?:\+srv)?://\S+")
TIMEOUT_MS = 10_000


class PayloadError(Exception):
    """A payload can't be read: MongoDB didn't answer, or answered with an error."""


class Refused(PayloadError):
    """The guard refused the call before any query was made."""


class Missing(PayloadError):
    """MongoDB answered, and has nothing for that request id."""


def make_client(uri: str):
    """pymongo's client for the connection string; tests put a stand-in here."""
    from pymongo import MongoClient

    return MongoClient(uri, appname="bridge-kit", tz_aware=True, serverSelectionTimeoutMS=TIMEOUT_MS,
                       connectTimeoutMS=TIMEOUT_MS, socketTimeoutMS=TIMEOUT_MS)


def guarded(config: Config) -> tuple[MongoConfig, str]:
    """bridge-kit.yaml's MongoDB and the environment's name, once the guard lets them through."""
    mongo = config.mongodb
    if mongo is None:
        raise Refused("bridge-kit.yaml declares no MongoDB: add integrations.mongodb (see bridge-kit.example.yaml)")
    if not mongo.test_data_only:
        raise Refused("bridge-kit.yaml doesn't say dev and SIT hold test data only: set integrations.mongodb."
                      "test_data_only: true once it's confirmed they hold no copies of client data")
    environment = _variable(mongo.environment, "environment").lower()
    if environment not in ENVIRONMENTS:
        raise Refused(f"Payloads are read from dev or SIT only, and {mongo.environment} says {environment}")
    return mongo, environment


def declared_service(mongo: MongoConfig, name: str) -> MongoService:
    if name not in mongo.services:
        raise Refused(f"{name} isn't a declared service: {', '.join(mongo.services) or 'there are none'}")
    return mongo.services[name]


def request_id(value: str) -> str:
    """A request id as given, once it's a UUID: the only thing a payload is looked up by."""
    value = value.strip()
    if not REQUEST_ID.fullmatch(value):
        raise Refused(f"{value} isn't a request id: payloads are looked up by their UUID request id only")
    return value


def _variable(name: str, what: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise Refused(f"No MongoDB {what}: the environment variable {name} isn't set")
    return value


def id_values(value: str) -> list:
    """The ways a service may store a request id: as text, in either case, or as a BSON UUID (the standard form, or
    Java's legacy one)."""
    from bson.binary import Binary, UuidRepresentation

    found = uuid.UUID(value)
    texts = list(dict.fromkeys([value, value.lower(), value.upper()]))
    return [*texts, Binary.from_uuid(found, UuidRepresentation.STANDARD),
            Binary.from_uuid(found, UuidRepresentation.JAVA_LEGACY)]


class Payloads:
    """Reads stored payloads by request id from the services bridge-kit.yaml declares, through the guard."""

    def __init__(self, config: Config):
        self.config = config
        self.mongo, self.environment = guarded(config)
        self._client = None
        self._model = None

    @property
    def client(self):
        if self._client is None:
            from bridge_kit.auth import read_token

            uri = read_token(self.mongo.uri, "MongoDB", "connection string")
            try:
                self._client = make_client(uri)
            except Exception:  # noqa: BLE001 - its message may carry the connection string
                raise PayloadError("The MongoDB connection string isn't one the driver can use") from None
        return self._client

    def run(self, call):
        """Runs one call to MongoDB; an error comes back without the connection string or anything after it."""
        try:
            return call()
        except (PayloadError, TokenError):
            raise
        except Exception as e:  # noqa: BLE001 - pymongo's errors, or the stand-in's
            message = CONNECTION_STRING.sub("<connection string>", str(e).splitlines()[0] if str(e) else "")[:300]
            raise PayloadError(f"MongoDB: {type(e).__name__}: {message}" if message else
                               f"MongoDB: {type(e).__name__}") from None

    def collection(self, service: MongoService, raw: bool = False):
        database = _variable(service.database, f"database for {service.name}")
        name = _variable(service.raw.collection if raw else service.collection,
                         f"{'raw responses ' if raw else ''}collection for {service.name}")
        return self.client[database][name]

    def root(self, service: MongoService) -> str:
        """The model's schema a service's payloads start from: the root its contract names in the component catalog."""
        from bridge_kit.components import CATALOG
        from bridge_kit.stories import CatalogError, load_catalog

        try:
            contract = load_catalog(repo_root()).contracts.get(service.schema) or {}
        except CatalogError as e:
            raise Refused(str(e)) from None
        if not contract.get("root"):
            raise Refused(f"{service.schema} has no root in {CATALOG.as_posix()}: the schema {service.name}'s payloads "
                          "start from, e.g. root: CustomerRecord")
        return str(contract["root"])

    def model(self):
        if self._model is None:
            from bridge_kit.internal_model import open_model

            self._model = open_model(self.config.model.path, self.config.model_layout)
        return self._model

    def payload(self, service_name: str, request: str) -> tuple[dict, Path]:
        """One service's payload for a request, as plain JSON, and where it's kept."""
        service = declared_service(self.mongo, service_name)
        request = request_id(request)
        query = {service.id_field: {"$in": id_values(request)}}
        document = self.run(lambda: self.collection(service).find_one(query))
        if document is None:
            raise Missing(f"No {service.name} payload has {service.id_field} {request} in {self.environment}")
        payload = plain(unwrap(document, service))
        return payload, keep(service.name, request, payload)


def unwrap(document: dict, service: MongoService):
    """The payload in a stored document: its payload_field when it wraps one, otherwise all of it but MongoDB's _id."""
    if not service.payload_field:
        return {k: v for k, v in document.items() if k != "_id"}
    value = document
    for part in service.payload_field.split("."):
        if not isinstance(value, dict) or part not in value:
            raise PayloadError(f"The stored {service.name} document has no {service.payload_field}: check "
                               "payload_field in bridge-kit.yaml")
        value = value[part]
    return value


def plain(value):
    """MongoDB's types as plain JSON: dates as ISO text in UTC, decimals as numbers where that's exact (otherwise
    text), ids and UUIDs as text, other binary as base64."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dt.datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
        return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, decimal.Decimal):
        return _number(value)
    if isinstance(value, (uuid.UUID, dt.date)):
        return str(value)
    from bson.binary import Binary, UuidRepresentation
    from bson.decimal128 import Decimal128

    if isinstance(value, Decimal128):
        return _number(value.to_decimal())
    if isinstance(value, Binary) and value.subtype in (3, 4):
        legacy = UuidRepresentation.JAVA_LEGACY if value.subtype == 3 else UuidRepresentation.STANDARD
        return str(value.as_uuid(legacy))
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return str(value)  # ObjectId, Timestamp, Regex and the rest


def _number(value: decimal.Decimal):
    """A decimal as a JSON number: an integer when it's whole, a float when that keeps every digit (15 or fewer)."""
    if not value.is_finite():
        return str(value)
    if value == value.to_integral_value() and abs(value) < 2 ** 53:
        return int(value)
    return float(value) if len(value.normalize().as_tuple().digits) <= 15 else str(value)


def keep(service: str, request: str, payload) -> Path:
    path = work_dir() / "payloads" / service / f"{request}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def shown(path: Path) -> str:
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


# --- What the commands and the MCP tools print: (text, data) ---------------------------------------------------------


def read_status(payloads: Payloads) -> tuple[str, dict]:
    lines, problems = [f"Environment: {payloads.environment}, test data only"], []
    try:
        payloads.run(lambda: payloads.client.admin.command("ping"))
        lines.append("Connection: OK")
    except PayloadError as e:
        problems.append(f"connection: {e}")
    if not problems:
        for service in payloads.mongo.services.values():
            kinds = [(False, service.collection, "payloads")] + \
                ([(True, service.raw.collection, "raw responses")] if service.raw else [])
            for raw, variable, what in kinds:
                try:
                    database = _variable(service.database, f"database for {service.name}")
                    name = _variable(variable, f"collection for {service.name}")
                    names = payloads.run(lambda: payloads.client[database].list_collection_names())
                except PayloadError as e:
                    problems.append(f"{service.name} {what}: {e}")
                    continue
                if name in names:
                    lines.append(f"{service.name} {what}: answers ({service.database}, {variable})")
                else:
                    problems.append(f"{service.name} {what}: the database {service.database} names has no collection "
                                    f"{variable} names")
    text = "\n".join(lines + [f"PROBLEM {p}" for p in problems]) + "\n" + \
        ("MongoDB: OK\n" if not problems else f"MongoDB: {len(problems)} problem(s)\n")
    return text, {"environment": payloads.environment, "lines": lines, "problems": problems, "ok": not problems}


def read_payload(payloads: Payloads, service: str, request: str) -> tuple[str, dict]:
    payload, path = payloads.payload(service, request)
    text = f"{service} payload {request}, from {payloads.environment}; kept in {shown(path)}\n\n" + \
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return text, {"service": service, "request_id": request, "environment": payloads.environment,
                  "kept": shown(path), "payload": payload}


def read_trace(payloads: Payloads, request: str) -> tuple[str, dict]:
    """The same request in every declared service, side by side: the collecting service's payload beside what the
    summary service made of it."""
    request = request_id(request)
    found: dict[str, dict | None] = {}
    sections = []
    for name in payloads.mongo.services:
        try:
            payload, path = payloads.payload(name, request)
        except Missing:
            found[name] = None
            sections.append(f"## {name}\n\nNone for this request.\n")
            continue
        found[name] = payload
        sections.append(f"## {name}\n\nKept in {shown(path)}\n\n" + json.dumps(payload, indent=2, ensure_ascii=False)
                        + "\n")
    if not any(v is not None for v in found.values()):
        raise Missing(f"No declared service has a payload for {request} in {payloads.environment}")
    text = f"Request {request}, from {payloads.environment}\n\n" + "\n".join(sections)
    return text, {"request_id": request, "environment": payloads.environment, "payloads": found}


def read_check(payloads: Payloads, service_name: str, request: str) -> tuple[str, dict, int]:
    """A payload against the model; exit 1 when anything's found."""
    from bridge_kit.internal_model import ModelError
    from bridge_kit.payload_check import check, render_check, wrapped

    service = declared_service(payloads.mongo, service_name)
    root = payloads.root(service)
    try:
        model = payloads.model()
    except ModelError as e:
        raise Refused(str(e)) from None
    if root not in model.roots:
        raise Refused(f"{root}, {service.schema}'s root, isn't a schema of the internal model")
    payload, path = payloads.payload(service_name, request)
    findings = check(model, root, payload, () if service.payload_field else (service.id_field,))
    text = render_check(service_name, request, root, findings) + f"Kept in {shown(path)}\n"
    data = {"service": service_name, "request_id": request, "environment": payloads.environment, "root": root,
            "kept": shown(path), "wrapped": wrapped(findings, root),
            "findings": [{"kind": f.kind, "path": f.path, "count": f.count, "seen": f.seen} for f in findings]}
    return text, data, 1 if findings else 0


def read_profile(payloads: Payloads, service_name: str, requests: list[str]) -> tuple[str, dict]:
    """The shape across several payloads of one service; a request with none is named and left out."""
    from bridge_kit.payload_check import profile, render_profile

    service = declared_service(payloads.mongo, service_name)
    root = payloads.root(service)
    requests = [request_id(r) for r in requests]
    found, missing = [], []
    for request in requests:
        try:
            found.append((request, payloads.payload(service_name, request)[0]))
        except Missing:
            missing.append(request)
    if not found:
        raise Missing(f"No {service_name} payload for any of the {len(requests)} request(s) in {payloads.environment}")
    shapes = profile(root, [p for _, p in found])
    text = render_profile(service_name, [r for r, _ in found], shapes) + \
        ("".join(f"\nNone for {r}" for r in missing) + "\n" if missing else "")
    data = {"service": service_name, "environment": payloads.environment, "root": root,
            "requests": [r for r, _ in found], "missing": missing,
            "paths": [{"path": s.path, "present": s.present, "nulls": s.nulls, "types": dict(s.types),
                       "list_sizes": [min(s.sizes), max(s.sizes)] if s.sizes else None,
                       "values": dict(s.values) if s.coded else None} for s in shapes]}
    return text, data


def read_raw(payloads: Payloads, request: str, upstream: str | None = None) -> tuple[str, dict]:
    """The raw upstream responses behind a request, where a service keeps them, per upstream and operation; only one
    upstream's when it's named."""
    services = [s for s in payloads.mongo.services.values() if s.raw]
    if not services:
        raise Refused("No declared service keeps raw upstream responses: add raw: under the service in "
                      "bridge-kit.yaml, if it stores them")
    request = request_id(request)
    if upstream is not None and not UPSTREAM.fullmatch(upstream):
        raise Refused(f"{upstream} isn't an upstream's name")
    found: dict[str, list] = {}
    sections = []
    for service in services:
        raw = service.raw
        query = {raw.id_field: {"$in": id_values(request)}, **({raw.upstream_field: upstream} if upstream else {})}
        documents = payloads.run(lambda: list(payloads.collection(service, raw=True).find(query)))
        if not documents:
            continue
        responses = sorted((plain({k: v for k, v in d.items() if k != "_id"}) for d in documents),
                           key=lambda r: (str(r.get(raw.upstream_field, "")), str(r.get(raw.operation_field, ""))))
        found[service.name] = responses
        path = keep(service.name, f"{request}.raw", responses)
        sections.append(f"## {service.name}: {len(responses)} raw response(s), kept in {shown(path)}\n")
        for response in responses:
            sections.append(f"### {response.get(raw.upstream_field, '?')} / "
                            f"{response.get(raw.operation_field, '?')}\n\n"
                            + json.dumps(response, indent=2, ensure_ascii=False) + "\n")
    if not found:
        raise Missing(f"No raw responses for {request}{f' from {upstream}' if upstream else ''} in "
                      f"{payloads.environment}")
    text = f"Request {request}, from {payloads.environment}\n\n" + "\n".join(sections)
    return text, {"request_id": request, "environment": payloads.environment, "upstream": upstream, "raw": found}
