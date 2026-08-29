"""
RSS & Atom Feed Parser with SSRF Protection.
Supports RSS 2.0, Atom 1.0, and YouTube channel feeds.
"""
import email.utils
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from utils.ssrf_guard import assert_safe_url

logger = logging.getLogger(__name__)

# Common XML Namespaces for RSS / Atom / Media
NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def strip_html(text: str | None) -> str:
    """Strip HTML tags and unescape HTML entities."""
    if not text:
        return ""
    clean = _HTML_TAG_RE.sub(" ", text)
    clean = html.unescape(clean)
    return " ".join(clean.split()).strip()


def extract_images_from_html(html_text: str | None, base_url: str = "") -> list[str]:
    """Extract image URLs from raw HTML content."""
    if not html_text:
        return []
    matches = _IMG_SRC_RE.findall(html_text)
    images = []
    for src in matches:
        src = src.strip()
        if src.startswith("//"):
            src = f"https:{src}"
        elif base_url and not src.startswith("http"):
            src = urljoin(base_url, src)
        if src.startswith("http") and src not in images:
            images.append(src)
    return images


def parse_pub_date(date_str: str | None) -> datetime:
    """Parse RFC 822 or ISO 8601 date string to UTC datetime."""
    if not date_str:
        return datetime.now(timezone.utc)
    date_str = date_str.strip()

    # 1. Try RFC 822 / 2822 (standard in RSS 2.0)
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # 2. Try ISO 8601 (standard in Atom / YouTube)
    try:
        cleaned = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    return datetime.now(timezone.utc)


def parse_feed_xml(xml_content: str, source_url: str = "") -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Parse XML string into feed metadata and item list.
    Supports both RSS 2.0 (<rss><channel>) and Atom (<feed>).
    """
    try:
        # Strip potential XML declarations or byte order marks
        xml_content = xml_content.strip()
        root = ET.fromstring(xml_content)
    except Exception as exc:
        raise ValueError(f"Invalid XML feed structure: {exc}") from exc

    tag = root.tag.lower()

    if "feed" in tag:
        return _parse_atom_feed(root, source_url)
    return _parse_rss2_feed(root, source_url)


def _parse_rss2_feed(root: ET.Element, source_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    channel = root.find("channel")
    if channel is None:
        channel = root

    title = channel.findtext("title", "").strip() or "Untitled Feed"
    description = channel.findtext("description", "").strip()
    link = channel.findtext("link", "").strip() or source_url
    icon_url = None

    image_elem = channel.find("image")
    if image_elem is not None:
        icon_url = image_elem.findtext("url")

    feed_meta = {
        "title": strip_html(title),
        "description": strip_html(description),
        "site_url": link,
        "feed_url": source_url,
        "icon_url": icon_url,
        "feed_type": "rss2",
    }

    items = []
    for item_node in channel.findall("item"):
        item_title = item_node.findtext("title", "").strip()
        item_link = item_node.findtext("link", "").strip()
        item_guid = item_node.findtext("guid", "").strip() or item_link
        raw_desc = item_node.findtext("description", "") or ""
        
        # Check content:encoded
        content_encoded = None
        content_elem = item_node.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        if content_elem is not None and content_elem.text:
            content_encoded = content_elem.text

        pub_date_str = item_node.findtext("pubDate")
        author = item_node.findtext("author") or item_node.findtext("{http://purl.org/dc/elements/1.1/}creator")

        # Media enclosures
        media_urls = []
        enclosure = item_node.find("enclosure")
        if enclosure is not None:
            enc_url = enclosure.get("url")
            enc_type = enclosure.get("type", "")
            if enc_url and (not enc_type or enc_type.startswith("image/") or enc_type.startswith("video/")):
                media_urls.append(enc_url)

        # Media:content and Media:thumbnail
        for media_tag in item_node.findall("{http://search.yahoo.com/mrss/}content"):
            m_url = media_tag.get("url")
            if m_url and m_url not in media_urls:
                media_urls.append(m_url)

        for thumb_tag in item_node.findall("{http://search.yahoo.com/mrss/}thumbnail"):
            t_url = thumb_tag.get("url")
            if t_url and t_url not in media_urls:
                media_urls.append(t_url)

        # Fallback to images in description/content
        if not media_urls:
            html_content = content_encoded or raw_desc
            media_urls.extend(extract_images_from_html(html_content, base_url=item_link))

        clean_summary = strip_html(raw_desc)[:500]

        items.append({
            "guid": item_guid or item_link or f"rss_{hash(item_title)}",
            "url": item_link,
            "title": strip_html(item_title) or "Untitled",
            "summary": clean_summary,
            "author": strip_html(author) if author else None,
            "media_urls": media_urls[:4],
            "pub_date": parse_pub_date(pub_date_str),
        })

    return feed_meta, items


def _find_elem(parent: ET.Element, tag_names: list[str], ns: dict[str, str]) -> ET.Element | None:
    for tag in tag_names:
        try:
            el = parent.find(tag, ns)
            if el is not None:
                return el
        except Exception:
            pass
        if ":" not in tag:
            try:
                el = parent.find(tag)
                if el is not None:
                    return el
            except Exception:
                pass
        # Fallback by matching local name
        target_name = tag.split(":")[-1].split("[")[0]
        for child in parent:
            child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_local == target_name:
                return child
    return None


def _find_text(parent: ET.Element, tag_names: list[str], ns: dict[str, str], default: str = "") -> str:
    el = _find_elem(parent, tag_names, ns)
    if el is not None and el.text:
        return el.text.strip()
    return default


def _parse_atom_feed(root: ET.Element, source_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ns = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/", "yt": "http://www.youtube.com/xml/schemas/2015"}
    
    title = _find_text(root, ["atom:title", "title"], ns, "Untitled Feed")
    subtitle = _find_text(root, ["atom:subtitle", "subtitle"], ns, "")
    
    site_url = source_url
    link_elem = _find_elem(root, ["atom:link[@rel='alternate']", "atom:link", "link"], ns)
    if link_elem is not None:
        site_url = link_elem.get("href") or site_url

    icon_url = _find_text(root, ["atom:icon", "atom:logo", "icon", "logo"], ns, "") or None

    feed_meta = {
        "title": strip_html(title) or "Untitled Feed",
        "description": strip_html(subtitle),
        "site_url": site_url,
        "feed_url": source_url,
        "icon_url": icon_url,
        "feed_type": "atom",
    }

    items = []
    # Find all entry elements
    entries = root.findall("atom:entry", ns)
    if not entries:
        entries = root.findall("entry")
    if not entries:
        entries = [c for c in root if c.tag.split("}")[-1] == "entry"]

    for entry in entries:
        item_title = _find_text(entry, ["atom:title", "title"], ns, "Untitled")
        item_guid = _find_text(entry, ["atom:id", "id"], ns, "")
        
        item_link = ""
        link_el = _find_elem(entry, ["atom:link[@rel='alternate']", "atom:link", "link"], ns)
        if link_el is not None:
            item_link = link_el.get("href", "")

        raw_summary = _find_text(entry, ["atom:summary", "summary", "atom:content", "content"], ns, "")
        pub_date_str = _find_text(entry, ["atom:published", "published", "atom:updated", "updated"], ns, "")

        author = _find_text(entry, ["atom:author/atom:name", "author/name", "atom:author", "author"], ns, "")

        media_urls = []
        for media_group in entry.findall("media:group", ns):
            for thumb in media_group.findall("media:thumbnail", ns):
                t_url = thumb.get("url")
                if t_url and t_url not in media_urls:
                    media_urls.append(t_url)

        for thumb in entry.findall("media:thumbnail", ns):
            t_url = thumb.get("url")
            if t_url and t_url not in media_urls:
                media_urls.append(t_url)

        if not media_urls:
            media_urls.extend(extract_images_from_html(raw_summary, base_url=item_link))

        items.append({
            "guid": item_guid or item_link or f"atom_{hash(item_title)}",
            "url": item_link,
            "title": strip_html(item_title) or "Untitled",
            "summary": strip_html(raw_summary)[:500],
            "author": strip_html(author) if author else None,
            "media_urls": media_urls[:4],
            "pub_date": parse_pub_date(pub_date_str),
        })

    return feed_meta, items


async def fetch_feed(
    feed_url: str,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout: float = 10.0,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, str | None, str | None, bool]:
    """
    Fetch and parse a remote RSS/Atom feed with SSRF guard and HTTP cache headers.
    Returns: (feed_meta, items, new_etag, new_last_modified, not_modified)
    """
    assert_safe_url(feed_url)

    headers = {
        "User-Agent": "Unravler-Bot/1.0 (+https://unravler.com; RSS Reader)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(feed_url, headers=headers)

        if response.status_code == 304:
            return None, None, etag, last_modified, True

        if response.status_code >= 400:
            raise ValueError(f"HTTP {response.status_code} error fetching feed: {response.text[:200]}")

        new_etag = response.headers.get("etag")
        new_last_modified = response.headers.get("last-modified")

        feed_meta, items = parse_feed_xml(response.text, source_url=feed_url)
        return feed_meta, items, new_etag, new_last_modified, False
