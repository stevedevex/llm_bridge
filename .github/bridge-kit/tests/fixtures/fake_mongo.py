"""A stand-in MongoDB for the payload tests: the few calls of pymongo's client the kit makes (`admin.command("ping")`,
`list_collection_names`, `find_one` and `find` with an equality or `$in` filter), over databases of collections of
documents a test gives it, recording every query.

    fake = FakeMongo({"lending-dev": {"payloads": [{"requestId": "...", "creditFile": {...}}]}})
    fake.queries   # [(database, collection, filter)]
    fake.uris      # the connection strings it was made with

`fail` makes every call raise that error, as a MongoDB that doesn't answer would.
"""

from __future__ import annotations

import copy


class FakeMongo:
    def __init__(self, data: dict | None = None, fail: Exception | None = None):
        self.data = data or {}
        self.fail = fail
        self.queries: list[tuple[str, str, dict]] = []
        self.uris: list[str] = []
        self.admin = _Database(self, "admin")

    def client(self, uri: str) -> FakeMongo:
        """Stands in for `payloads.make_client`."""
        self.uris.append(uri)
        return self

    def __getitem__(self, name: str) -> _Database:
        return _Database(self, name)

    def _check(self) -> None:
        if self.fail is not None:
            raise self.fail


class _Database:
    def __init__(self, mongo: FakeMongo, name: str):
        self.mongo, self.name = mongo, name

    def __getitem__(self, name: str) -> _Collection:
        return _Collection(self.mongo, self.name, name)

    def command(self, name: str) -> dict:
        self.mongo._check()
        if name != "ping":
            raise NotImplementedError(name)
        return {"ok": 1.0}

    def list_collection_names(self) -> list[str]:
        self.mongo._check()
        return list(self.mongo.data.get(self.name, {}))


class _Collection:
    def __init__(self, mongo: FakeMongo, database: str, name: str):
        self.mongo, self.database, self.name = mongo, database, name

    def _documents(self, query: dict) -> list[dict]:
        self.mongo._check()
        self.mongo.queries.append((self.database, self.name, query))
        documents = self.mongo.data.get(self.database, {}).get(self.name, [])
        return [copy.deepcopy(d) for d in documents if all(_matches(_field(d, k), v) for k, v in query.items())]

    def find_one(self, query: dict) -> dict | None:
        found = self._documents(query)
        return found[0] if found else None

    def find(self, query: dict) -> list[dict]:
        return self._documents(query)


def _field(document: dict, path: str):
    value = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _matches(value, condition) -> bool:
    if isinstance(condition, dict) and set(condition) == {"$in"}:
        return any(type(value) is type(c) and value == c for c in condition["$in"])
    return value == condition
