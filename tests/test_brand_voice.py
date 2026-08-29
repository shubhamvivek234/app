import pytest
from api.routes.ai import (
    BrandVoiceConfig,
    _build_system_message,
    get_brand_voice,
    save_brand_voice,
)


class _FakeBrandVoiceCollection:
    def __init__(self):
        self.doc = None

    async def find_one(self, query):
        return self.doc

    async def update_one(self, query, update, upsert=False):
        if "$set" in update:
            self.doc = update["$set"]
        return None


class _FakeDB:
    def __init__(self):
        self.brand_voices = _FakeBrandVoiceCollection()


def test_build_system_message_with_brand_voice():
    bv = {
        "brand_name": "Acme Software",
        "target_audience": "Senior engineers",
        "formatting_rules": "Use bullet points, max 1 emoji",
        "banned_words": ["synergy", "paradigm shift"],
    }
    sys_msg = _build_system_message("twitter", "witty", None, brand_voice=bv)
    assert "Acme Software" in sys_msg
    assert "Senior engineers" in sys_msg
    assert "synergy, paradigm shift" in sys_msg


@pytest.mark.asyncio
async def test_brand_voice_crud():
    db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}

    config = BrandVoiceConfig(
        brand_name="TechWave",
        tone="Inspirational",
        target_audience="Founders",
        banned_words=["cheap", "guarantee"],
    )
    saved = await save_brand_voice(config, current_user=user, db=db)
    assert saved.brand_name == "TechWave"
    assert "cheap" in saved.banned_words

    fetched = await get_brand_voice(current_user=user, db=db)
    assert fetched.brand_name == "TechWave"
    assert fetched.tone == "Inspirational"
