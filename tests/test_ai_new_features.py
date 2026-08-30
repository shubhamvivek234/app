import base64
import pytest
from unittest.mock import AsyncMock, patch
from starlette.requests import Request
from api.routes.ai import (
    repurpose_content,
    voice_to_post,
    scan_content_dna,
    suggest_comment,
    RepurposeRequest,
    VoiceToPostRequest,
    SuggestCommentRequest,
)


class _FakeCollection:
    def __init__(self, items=None):
        self.items = items or []
        self.doc = None

    async def find_one(self, query):
        return self.doc

    async def update_one(self, query, update, upsert=False):
        if "$set" in update:
            self.doc = update["$set"]
        return None

    def find(self, query):
        return self

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length=20):
        return self.items


class _FakeDB:
    def __init__(self):
        self.brand_voices = _FakeCollection()
        self.posts = _FakeCollection([
            {"content": "First great post about engineering scale", "status": "published"},
            {"content": "Second post on system design and resilience", "status": "published"},
            {"content": "Third post on async workflows and low cost LLM routers", "status": "published"},
        ])


def _make_request():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/ai/test",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_ai_repurpose_route():
    db = _FakeDB()
    user = {"user_id": "test_user", "default_workspace_id": "ws_1"}
    req = _make_request()

    mock_repurpose_data = {
        "linkedin_post": "Sample LinkedIn Post",
        "twitter_thread": ["1/2 Tweet", "2/2 Tweet"],
        "instagram_caption": "Insta caption #test",
        "carousel_slides": [{"slide_num": 1, "type": "hook", "title": "Hook", "body": "Context"}],
        "key_takeaways": ["Takeaway 1"],
        "provider": "google",
        "model": "gemini-2.5-flash",
    }

    with patch("api.routes.ai.extract_content_from_source", new_callable=AsyncMock) as mock_extract, \
         patch("api.routes.ai.repurpose_content_to_social", new_callable=AsyncMock) as mock_repurpose:
        mock_extract.return_value = {"title": "Test YouTube", "text": "Transcript text content"}
        mock_repurpose.return_value = mock_repurpose_data

        body = RepurposeRequest(url_or_text="https://www.youtube.com/watch?v=12345", tone="engaging")
        resp = await repurpose_content(req, body, current_user=user, db=db)
        assert resp.linkedin_post == "Sample LinkedIn Post"
        assert len(resp.twitter_thread) == 2
        assert len(resp.carousel_slides) == 1


@pytest.mark.asyncio
async def test_ai_voice_to_post_route():
    db = _FakeDB()
    user = {"user_id": "test_user", "default_workspace_id": "ws_1"}
    req = _make_request()

    mock_audio_base64 = base64.b64encode(b"fake-audio-bytes").decode()
    mock_json = '{"linkedin_post": "Voice to LinkedIn", "twitter_thread": ["Tweet 1", "Tweet 2"], "instagram_caption": "Voice Insta"}'

    with patch("api.routes.ai.free_llm.transcribe_and_structure_audio", new_callable=AsyncMock) as mock_transcribe:
        mock_transcribe.return_value = (mock_json, "google-gemini-audio")

        body = VoiceToPostRequest(audio_base64=mock_audio_base64, mime_type="audio/webm")
        resp = await voice_to_post(req, body, current_user=user, db=db)
        assert resp.linkedin_post == "Voice to LinkedIn"
        assert resp.provider == "google-gemini-audio"


@pytest.mark.asyncio
async def test_ai_suggest_comment_route():
    db = _FakeDB()
    user = {"user_id": "test_user", "default_workspace_id": "ws_1"}
    req = _make_request()

    mock_suggestions = '["Great point on timing!", "How do you handle team pushback?", "Execution is everything."]'

    with patch("api.routes.ai.free_llm.generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = (mock_suggestions, "groq", "openai/gpt-oss-120b")

        body = SuggestCommentRequest(post_content="Sharing our roadmap for Q3", author_name="Satya")
        resp = await suggest_comment(req, body, current_user=user, db=db)
        assert len(resp.suggestions) == 3
        assert resp.provider == "groq"


@pytest.mark.asyncio
async def test_ai_content_dna_scan_route():
    db = _FakeDB()
    user = {"user_id": "test_user", "default_workspace_id": "ws_1"}
    req = _make_request()

    mock_dna_json = """
    {
      "tone": "Bold & Direct",
      "sentence_cadence": "1-2 punchy lines",
      "hook_style": "Contrarian truth",
      "emoji_density": "Minimal",
      "vocabulary_tier": "B2B Executive",
      "sample_hooks": ["Stop doing this:", "Here is the truth:"]
    }
    """
    with patch("api.routes.ai.free_llm.generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = (mock_dna_json, "google", "gemini-2.5-flash")

        resp = await scan_content_dna(req, current_user=user, db=db)
        assert resp.tone == "Bold & Direct"
        assert resp.hook_style == "Contrarian truth"
        assert resp.posts_analyzed == 3
