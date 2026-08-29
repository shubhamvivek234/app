import pytest
from fastapi import HTTPException
from api.routes.bio_pages import (
    BioCustomLink,
    BioPageConfig,
    BioTheme,
    get_my_bio_page,
    get_public_bio_page,
    save_my_bio_page,
    track_bio_link_click,
)


class _FakeBioCollection:
    def __init__(self):
        self.pages = {}

    async def find_one(self, query):
        if "handle" in query:
            handle = query["handle"]
            page = self.pages.get(handle)
            if not page:
                return None
            if "workspace_id" in query and "$ne" in query["workspace_id"]:
                if page.get("workspace_id") == query["workspace_id"]["$ne"]:
                    return None
            return page
        if "$or" in query:
            for opt in query["$or"]:
                for p in self.pages.values():
                    if p.get("workspace_id") == opt.get("workspace_id") or p.get("user_id") == opt.get("user_id"):
                        return p
        return None

    async def update_one(self, query, update, upsert=False):
        handle = update.get("$set", {}).get("handle")
        if not handle and "handle" in query:
            handle = query["handle"]
        if handle:
            if "$set" in update:
                self.pages.setdefault(handle, {}).update(update["$set"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    if k.startswith("custom_links.$.clicks"):
                        for link in self.pages.get(handle, {}).get("custom_links", []):
                            if link.get("id") == query.get("custom_links.id"):
                                link["clicks"] = link.get("clicks", 0) + v
        from types import SimpleNamespace
        return SimpleNamespace(matched_count=1)


class _FakePostsCollection:
    def find(self, query):
        class _Cursor:
            def sort(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def __aiter__(self):
                self._iter = iter([])
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        return _Cursor()


class _FakeUsersCollection:
    async def find_one(self, query):
        return {"user_id": "u1", "name": "Jane Creator", "avatar_url": "https://avatar.png"}


class _FakeDB:
    def __init__(self):
        self.bio_pages = _FakeBioCollection()
        self.users = _FakeUsersCollection()
        self.posts = _FakePostsCollection()


@pytest.mark.asyncio
async def test_bio_page_save_and_public_view():
    db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}

    # 1. Save bio page
    config = BioPageConfig(
        handle="coolbrand",
        title="Cool Brand Co",
        bio="Official links",
        custom_links=[
            BioCustomLink(id="link_1", title="Our Shop", url="https://shop.coolbrand.com", icon="shopping-bag"),
        ],
        social_links={"twitter": "https://x.com/coolbrand"},
    )
    saved = await save_my_bio_page(config, current_user=user, db=db)
    assert saved["ok"] is True
    assert saved["handle"] == "coolbrand"

    # 2. Public view
    public_data = await get_public_bio_page("coolbrand", db=db)
    assert public_data["title"] == "Cool Brand Co"
    assert len(public_data["custom_links"]) == 1
    assert public_data["custom_links"][0]["title"] == "Our Shop"

    # 3. Track link click
    click_res = await track_bio_link_click("coolbrand", "link_1", request=None, db=db)
    assert click_res["ok"] is True
