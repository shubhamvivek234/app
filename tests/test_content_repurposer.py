import pytest
from unittest.mock import AsyncMock, patch
from utils.content_repurposer import (
    extract_youtube_video_id,
    _HTMLTextExtractor,
    repurpose_content_to_social,
)


def test_youtube_video_id_extraction():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://google.com") is None


def test_html_text_extractor():
    html_sample = """
    <html>
      <head><title>Test Article</title></head>
      <body>
        <nav><a href="/">Home</a></nav>
        <h1>How to Grow on Social Media</h1>
        <p>This is paragraph 1 with actionable insights.</p>
        <p>This is paragraph 2.</p>
        <script>console.log("ignore me");</script>
      </body>
    </html>
    """
    parser = _HTMLTextExtractor()
    parser.feed(html_sample)
    cleaned = parser.get_text()
    assert "How to Grow on Social Media" in cleaned
    assert "paragraph 1" in cleaned
    assert "console.log" not in cleaned


@pytest.mark.asyncio
async def test_repurpose_content_to_social():
    mock_json_response = """
    {
      "linkedin_post": "Here is a viral LinkedIn post.\\n\\n1. Consistency\\n2. Quality",
      "twitter_thread": ["1/3 Hook tweet", "2/3 Core point", "3/3 CTA tweet"],
      "instagram_caption": "Story caption #growth #marketing",
      "carousel_slides": [
        {"slide_num": 1, "type": "hook", "title": "Hook", "body": "Context"},
        {"slide_num": 2, "type": "cta", "title": "Conclusion", "body": "Follow me"}
      ],
      "key_takeaways": ["Point 1", "Point 2"]
    }
    """
    with patch("utils.content_repurposer.free_llm.generate_text", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = (mock_json_response, "google", "gemini-2.5-flash")
        res = await repurpose_content_to_social(
            source_text="Some source material about social growth",
            source_title="Growth Guide",
        )

        assert "viral LinkedIn post" in res["linkedin_post"]
        assert len(res["twitter_thread"]) == 3
        assert len(res["carousel_slides"]) == 2
        assert res["provider"] == "google"
