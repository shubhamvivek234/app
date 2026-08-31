import pytest
from api.routes.ai import (
    get_viral_hooks,
    generate_short_form_script,
    auto_fill_viral_hook,
    GenerateScriptRequest,
    AutoFillHookRequest,
)

class _FakeCollection:
    def __init__(self):
        self.items = []

    async def find_one(self, query):
        for item in self.items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    if not any(item.get(subk) == subv for cond in v for subk, subv in cond.items()):
                        match = False
                elif item.get(k) != v:
                    match = False
            if match:
                return item
        return None

    async def insert_one(self, doc):
        self.items.append(doc)
        return doc

    async def delete_one(self, query):
        for i, item in enumerate(self.items):
            if all(item.get(k) == v for k, v in query.items() if k != "_id"):
                self.items.pop(i)
                return True
        return False


class _FakeDB:
    def __init__(self):
        self.brand_voices = _FakeCollection()
        self.workspace_bookmarks = _FakeCollection()


@pytest.mark.asyncio
async def test_get_viral_hooks_catalog():
    # 1. Fetch all
    res = await get_viral_hooks()
    assert res["total"] >= 20
    assert len(res["categories"]) >= 8
    assert len(res["niches"]) >= 8

    # 2. Filter by category
    contrarian_res = await get_viral_hooks(category="contrarian")
    assert contrarian_res["total"] >= 4
    for h in contrarian_res["hooks"]:
        assert h["category"] == "contrarian"

    # 3. Filter by niche
    saas_res = await get_viral_hooks(niche="saas_tech")
    assert saas_res["total"] >= 5
    for h in saas_res["hooks"]:
        assert "saas_tech" in h["niche"]

    # 4. Search query
    search_res = await get_viral_hooks(search="mistake")
    assert search_res["total"] >= 1


@pytest.mark.asyncio
async def test_generate_short_form_script():
    db = _FakeDB()
    user = {"user_id": "usr_tester1", "default_workspace_id": "ws_tester1"}

    req = GenerateScriptRequest(
        topic="3 reasons your social posts are getting 0 views",
        niche="creator",
        platform="tiktok",
        target_duration="30s",
        hook_style="contrarian",
        use_brand_voice=False,
    )

    res = await generate_short_form_script(body=req, current_user=user, db=db)
    assert len(res.hooks) >= 1
    assert len(res.storyboard) >= 3
    assert len(res.full_script) > 20
    assert res.call_to_action is not None


@pytest.mark.asyncio
async def test_auto_fill_viral_hook():
    user = {"user_id": "usr_tester1"}
    req = AutoFillHookRequest(
        hook_template="Stop doing [Activity] if you want to grow in [Industry]:",
        topic_or_brand="manual scheduling",
        niche="social media marketing",
    )
    res = await auto_fill_viral_hook(body=req, current_user=user)
    assert len(res.variations) >= 1
    assert len(res.variations[0]) > 10
