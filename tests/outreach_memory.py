"""Small atomic Mongo-style fake for execution fault tests; no provider traffic."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def value(doc, path):
    parts = path.split(".")
    for index, part in enumerate(parts):
        if isinstance(doc, list):
            return [value(item, ".".join(parts[index:])) for item in doc]
        if not isinstance(doc, dict) or part not in doc:
            return None
        doc = doc[part]
    return doc


def matches(doc, query):
    for key, expected in query.items():
        if key == "$expr":
            left, right = expected["$gt"]
            left = value(doc, left[1:])
            right = datetime.now(timezone.utc) if right == "$$NOW" else right
            if left is None or not left > right:
                return False
            continue
        if key == "$or":
            if not any(matches(doc, branch) for branch in expected):
                return False
            continue
        if key == "$and":
            if not all(matches(doc, branch) for branch in expected):
                return False
            continue
        actual = value(doc, key)
        if isinstance(expected, dict):
            if not any(op.startswith("$") for op in expected):
                if actual != expected:
                    return False
                continue
            for op, operand in expected.items():
                if op == "$exists" and (actual is not None) != operand:
                    return False
                if op == "$ne" and (actual == operand or isinstance(actual, list) and operand in actual):
                    return False
                if op == "$in" and actual not in operand:
                    return False
                if op == "$nin" and actual in operand:
                    return False
                if op in {"$lt", "$lte", "$gt", "$gte"}:
                    if actual is None:
                        return False
                    if op == "$lt" and not actual < operand:
                        return False
                    if op == "$lte" and not actual <= operand:
                        return False
                    if op == "$gt" and not actual > operand:
                        return False
                    if op == "$gte" and not actual >= operand:
                        return False
        elif isinstance(actual, list) and not isinstance(expected, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


def assign(doc, path, val):
    parts = path.split(".")
    for part in parts[:-1]:
        doc = doc.setdefault(part, {})
    doc[parts[-1]] = deepcopy(val)


def apply(doc, update, inserted=False):
    for key, val in update.get("$set", {}).items():
        assign(doc, key, val)
    if inserted:
        for key, val in update.get("$setOnInsert", {}).items():
            assign(doc, key, val)
    for key, val in update.get("$inc", {}).items():
        assign(doc, key, (value(doc, key) or 0) + val)
    for key in update.get("$unset", {}):
        parent = doc
        parts = key.split(".")
        for part in parts[:-1]:
            parent = parent.get(part, {})
        parent.pop(parts[-1], None)
    for key, val in update.get("$addToSet", {}).items():
        existing = value(doc, key) or []
        if val not in existing:
            assign(doc, key, existing + [val])
    for key, val in update.get("$pull", {}).items():
        assign(doc, key, [item for item in (value(doc, key) or []) if item != val])
    for key, val in update.get("$push", {}).items():
        assign(doc, key, (value(doc, key) or []) + [val])


class Cursor:
    def __init__(self, docs):
        self.docs = deepcopy(docs)

    def sort(self, *args):
        ordering = args[0] if isinstance(args[0], list) else [(args[0], args[1] if len(args) > 1 else 1)]
        for path, direction in reversed(ordering):
            self.docs.sort(key=lambda doc: (value(doc, path) is not None, value(doc, path)), reverse=direction < 0)
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
        return self

    def skip(self, count):
        self.docs = self.docs[count:]
        return self

    async def to_list(self, length=None):
        return deepcopy(self.docs if length is None else self.docs[:length])


class Collection:
    def __init__(self, docs=None):
        self.docs = deepcopy(docs or [])

    async def find_one(self, query, projection=None, *, sort=None):
        if sort:
            return next(iter(self.find(query).sort(sort).docs), None)
        return next((deepcopy(doc) for doc in self.docs if matches(doc, query)), None)

    def find(self, query=None, projection=None):
        return Cursor([doc for doc in self.docs if matches(doc, query or {})])

    async def count_documents(self, query):
        return sum(matches(doc, query) for doc in self.docs)

    async def distinct(self, field, query=None):
        return list({value(doc, field) for doc in self.docs if matches(doc, query or {})})

    async def insert_one(self, doc):
        if any(doc.get("_id") is not None and d.get("_id") == doc["_id"] for d in self.docs):
            raise DuplicateKeyError("duplicate")
        self.docs.append(deepcopy(doc))
        return SimpleNamespace(inserted_id=doc.get("_id"))

    async def insert_many(self, documents):
        for document in documents:
            await self.insert_one(document)
        return SimpleNamespace(inserted_ids=[doc.get("_id") for doc in documents])

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if matches(doc, query):
                before = deepcopy(doc)
                apply(doc, update)
                return SimpleNamespace(matched_count=1, modified_count=int(before != doc))
        if upsert:
            doc = {k: v for k, v in query.items() if not k.startswith("$") and not isinstance(v, dict)}
            apply(doc, update, inserted=True)
            await self.insert_one(doc)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=doc.get("_id"))
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def find_one_and_update(self, query, update, return_document=ReturnDocument.BEFORE):
        for doc in self.docs:
            if matches(doc, query):
                before = deepcopy(doc)
                apply(doc, update)
                return deepcopy(doc) if return_document == ReturnDocument.AFTER else before
        return None

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if matches(doc, query):
                apply(doc, update)
                count += 1
        return SimpleNamespace(matched_count=count, modified_count=count)

    async def replace_one(self, query, document, upsert=False):
        for doc in self.docs:
            if matches(doc, query):
                doc.clear()
                doc.update(deepcopy(document))
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            await self.insert_one(document)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, query):
        for doc in self.docs:
            if matches(doc, query):
                self.docs.remove(doc)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class Database:
    def __init__(self, **collections):
        self.collections = {k: Collection(v) for k, v in collections.items()}

    def __getattr__(self, name):
        return self.collections.setdefault(name, Collection())
