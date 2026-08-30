"""
Content Repurposer Utility for Unravler.

Extracts text from:
1. YouTube Videos (via transcript / timedtext / metadata)
2. Web articles / Blog posts (clean HTML parsing)
3. Raw text or PDF transcripts

And repurposes them into multi-network social packages (LinkedIn, X Thread, Instagram, Carousel slides)
using the 6-Tier Free LLM Waterfall.
"""

import html
import json
import logging
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self.skip = False
        self.skip_tags = {"script", "style", "nav", "footer", "header", "noscript", "svg"}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.skip = True

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags:
            self.skip = False
        if tag.lower() in {"p", "h1", "h2", "h3", "h4", "li", "div", "br"}:
            self.fed.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.fed.append(data)

    def get_text(self) -> str:
        raw = "".join(self.fed)
        # Normalize whitespace
        cleaned = re.sub(r"[ \t]+", " ", raw)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return html.unescape(cleaned).strip()


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract YouTube Video ID from various URL formats."""
    parsed = urlparse(url)
    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.startswith(("/embed/", "/v/", "/shorts/")):
            return parsed.path.split("/")[2]
    elif parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/")
    return None


async def fetch_youtube_content(video_id: str) -> Dict[str, Any]:
    """Fetches video metadata and subtitles/transcript for a YouTube video."""
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    title = f"YouTube Video ({video_id})"
    description = ""
    transcript_text = ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            # 1. Fetch video page HTML to extract title & caption track
            resp = await client.get(video_url, headers=headers)
            if resp.status_code == 200:
                html_text = resp.text
                title_match = re.search(r"<title>(.*?)</title>", html_text)
                if title_match:
                    title = title_match.group(1).replace(" - YouTube", "").strip()

                # Extract description
                desc_match = re.search(r'"shortDescription":"(.*?)"', html_text)
                if desc_match:
                    description = desc_match.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")

                # Look for timedtext caption tracks in ytInitialPlayerResponse
                caption_match = re.search(r'"captionTracks":\s*(\[.*?\])', html_text)
                if caption_match:
                    tracks = json.loads(caption_match.group(1))
                    if tracks:
                        # Prefer English or first track
                        track_url = tracks[0].get("baseUrl")
                        if track_url:
                            caption_resp = await client.get(track_url, headers=headers)
                            if caption_resp.status_code == 200:
                                # Strip XML tags from caption track
                                raw_xml = caption_resp.text
                                transcript_text = re.sub(r"<[^>]+>", " ", raw_xml)
                                transcript_text = html.unescape(transcript_text).strip()
        except Exception as exc:
            logger.warning("Failed to extract full YouTube transcript: %s", exc)

    combined_text = f"Title: {title}\n\nDescription:\n{description}\n\nTranscript / Content:\n{transcript_text or description or title}"
    return {
        "title": title,
        "type": "youtube",
        "video_id": video_id,
        "text": combined_text[:12000],
    }


async def fetch_web_article_content(url: str) -> Dict[str, Any]:
    """Fetches and cleans article text from any public URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise ValueError(f"Failed to fetch webpage (HTTP {resp.status_code})")

        parser = _HTMLTextExtractor()
        parser.feed(resp.text)
        cleaned_text = parser.get_text()

        title_match = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else url

        return {
            "title": html.unescape(title),
            "type": "article",
            "url": url,
            "text": cleaned_text[:12000],
        }


async def extract_content_from_source(url_or_text: str) -> Dict[str, Any]:
    """Universal extractor for URLs (YouTube, Web articles) or raw text."""
    trimmed = url_or_text.strip()
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        yt_id = extract_youtube_video_id(trimmed)
        if yt_id:
            return await fetch_youtube_content(yt_id)
        return await fetch_web_article_content(trimmed)

    # It's raw text or notes
    return {
        "title": "Notes / Source Material",
        "type": "text",
        "text": trimmed[:12000],
    }


async def repurpose_content_to_social(
    source_text: str,
    source_title: str = "",
    tone: str = "engaging",
    brand_voice: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Transforms source material into high-performing social post packages for LinkedIn, X, and Instagram.
    """
    voice_guidelines = ""
    if brand_voice:
        tone_str = brand_voice.get("tone") or tone
        formatting = brand_voice.get("formatting_rules") or ""
        banned = brand_voice.get("banned_words") or []
        voice_guidelines = f"Tone: {tone_str}. Formatting: {formatting}. Banned words to avoid: {', '.join(banned)}."

    system_prompt = (
        "You are an elite social media ghostwriter and content repurposer for founders and creators. "
        "Transform the provided source material into a complete, high-converting social media distribution package.\n\n"
        f"{voice_guidelines}\n\n"
        "Return ONLY a valid JSON object matching this EXACT schema with NO markdown wrapping:\n"
        "{\n"
        '  "linkedin_post": "A long-form post with a 2-line hook, spaced paragraphs, 3-5 bullet insights, and 1 closing CTA question.",\n'
        '  "twitter_thread": [\n'
        '    "Tweet 1 (Hook + Thread indicator 1/5)",\n'
        '    "Tweet 2 (Core insight)",\n'
        '    "Tweet 3 (Framework)",\n'
        '    "Tweet 4 (Takeaway)",\n'
        '    "Tweet 5 (Conclusion / RT CTA)"\n'
        "  ],\n"
        '  "instagram_caption": "Visual caption with story hook, bullet takeaways, and 4-6 hashtags.",\n'
        '  "carousel_slides": [\n'
        '    {"slide_num": 1, "type": "hook", "title": "Punchy Hook Title", "body": "Subtitle / context"},\n'
        '    {"slide_num": 2, "type": "content", "title": "Point 1 Title", "body": "Key takeaway"},\n'
        '    {"slide_num": 3, "type": "content", "title": "Point 2 Title", "body": "Key takeaway"},\n'
        '    {"slide_num": 4, "type": "content", "title": "Point 3 Title", "body": "Key takeaway"},\n'
        '    {"slide_num": 5, "type": "cta", "title": "Conclusion", "body": "Save & Share"}\n'
        "  ],\n"
        '  "key_takeaways": ["Insight 1", "Insight 2", "Insight 3"]\n'
        "}"
    )

    user_prompt = f"Source Title: {source_title}\n\nSource Content:\n{source_text[:8000]}"

    raw_response, provider, model = await free_llm.generate_text(
        system_message=system_prompt,
        user_prompt=user_prompt,
        response_json=True,
    )

    # Clean JSON
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        data["provider"] = provider
        data["model"] = model
        return data
    except Exception as e:
        logger.error("JSON parsing error on repurposed content: %s. Raw: %s", e, cleaned[:400])
        # Fallback dictionary
        return {
            "linkedin_post": raw_response,
            "twitter_thread": [raw_response[:270]],
            "instagram_caption": raw_response[:500],
            "carousel_slides": [
                {"slide_num": 1, "type": "hook", "title": source_title or "Key Insight", "body": raw_response[:150]},
                {"slide_num": 2, "type": "cta", "title": "Summary", "body": "Save this post for later"},
            ],
            "key_takeaways": [source_title or "Core Insight"],
            "provider": provider,
            "model": model,
        }
