import pytest
from fastapi import HTTPException
from api.routes.short_links import (
    ShortLinkCreate,
    UTMPreset,
    _append_utm_params,
    _generate_slug,
    create_short_link,
    delete_short_link,
    delete_utm_preset,
    list_short_links,
    list_utm_presets,
    save_utm_preset,
)


class _FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self, items=None):
        self.docs = {d.get("code") or d.get("id"): d for d in (items or [])}
        self.inserted = []

    async def find_one(self, query):
        if "code" in query:
            return self.docs.get(query["code"])
        if "id" in query:
            return self.docs.get(query["id"])
        return None

    async def insert_one(self, doc):
        self.inserted.append(doc)
        key = doc.get("code") or doc.get("id")
        if key:
            self.docs[key] = doc
        return doc

    def find(self, query):
        user_id = query.get("user_id")
        matched = [d for d in self.docs.values() if not user_id or d.get("user_id") == user_id]
        return _FakeCursor(matched)

    async def delete_one(self, query):
        key = query.get("code") or query.get("id")
        if key in self.docs:
            del self.docs[key]
            from types import SimpleNamespace
            return SimpleNamespace(deleted_count=1)
        from types import SimpleNamespace
        return SimpleNamespace(deleted_count=0)

    async def delete_many(self, query):
        return None


class _FakeDB:
    def __init__(self):
        self.short_links = _FakeCollection()
        self.short_link_clicks = _FakeCollection()
        self.utm_presets = _FakeCollection()


def test_append_utm_params():
    url = "https://unravler.com/blog?category=tech"
    params = {
        "utm_source": "twitter",
        "utm_medium": "social",
        "utm_campaign": "launch",
    }
    result = _append_utm_params(url, params)
    assert "utm_source=twitter" in result
    assert "utm_medium=social" in result
    assert "utm_campaign=launch" in result
    assert "category=tech" in result


def test_generate_slug():
    slug = _generate_slug(6)
    assert len(slug) == 6
    assert slug.isalnum()


@pytest.mark.asyncio
async def test_create_and_list_short_link():
    db = _FakeDB()
    user = {"user_id": "u123"}
    req = ShortLinkCreate(
        original_url="https://example.com/product",
        utm_source="linkedin",
        utm_campaign="spring_sale",
    )
    created = await create_short_link(req, current_user=user, db=db)
    assert created.code is not None
    assert "utm_source=linkedin" in created.final_url
    assert created.original_url == "https://example.com/product"

    # List
    links = await list_short_links(current_user=user, db=db)
    assert len(links) == 1
    assert links[0].code == created.code


@pytest.mark.asyncio
async def test_utm_presets_crud():
    db = _FakeDB()
    user = {"user_id": "u123"}
    preset_req = UTMPreset(
        name="Twitter Default",
        utm_source="twitter",
        utm_medium="social",
        utm_campaign="organic",
    )
    saved = await save_utm_preset(preset_req, current_user=user, db=db)
    assert saved.name == "Twitter Default"
    assert saved.utm_source == "twitter"

    presets = await list_utm_presets(current_user=user, db=db)
    assert len(presets) == 1

    await delete_utm_preset(saved.id, current_user=user, db=db)
    presets_after = await list_utm_presets(current_user=user, db=db)
    assert len(presets_after) == 0
