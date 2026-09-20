"""AI Moment Selector for Video Clipping Engine.
Analyzes timestamped video transcripts to pick the highest engagement standalone clips.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
import httpx

from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)


def parse_youtube_timed_text(xml_text: str) -> List[Dict[str, Any]]:
    """
    Parse YouTube XML timedtext into a list of timestamped segments:
    [{'start': 12.3, 'dur': 4.1, 'end': 16.4, 'text': '...'}]
    """
    segments = []
    if not xml_text:
        return segments

    try:
        root = ET.fromstring(xml_text)
        for elem in root.iter("text"):
            start = float(elem.attrib.get("start", 0.0))
            dur = float(elem.attrib.get("dur", 3.0))
            text = (elem.text or "").strip()
            if text:
                segments.append({
                    "start": round(start, 2),
                    "dur": round(dur, 2),
                    "end": round(start + dur, 2),
                    "text": text,
                })
    except Exception as exc:
        logger.warning("Error parsing timed text XML: %s", exc)
        # Fallback to regex if XML parse fails
        matches = re.findall(r'<text start="([\d\.]+)" dur="([\d\.]+)">([^<]+)</text>', xml_text)
        for m in matches:
            s, d, t = float(m[0]), float(m[1]), m[2].strip()
            segments.append({
                "start": round(s, 2),
                "dur": round(d, 2),
                "end": round(s + d, 2),
                "text": t,
            })
    return segments


async def select_viral_clips(
    segments: List[Dict[str, Any]],
    video_title: str,
    num_clips: int = 3,
    min_clip_sec: int = 15,
    max_clip_sec: int = 60,
) -> List[Dict[str, Any]]:
    """
    Given timestamped transcript segments, use LLM to score and select viral standalone clips.
    """
    if not segments:
        # Generate synthetic fallback clips if no transcript available
        return _generate_heuristic_clips(video_title, num_clips, min_clip_sec, max_clip_sec)

    # Format transcript with timestamps for LLM prompt
    transcript_lines = []
    for s in segments[:150]:  # feed first ~20 mins of segments
        m = int(s["start"] // 60)
        sec = int(s["start"] % 60)
        time_str = f"[{m:02d}:{sec:02d}]"
        transcript_lines.append(f"{time_str} ({s['start']}s - {s['end']}s): {s['text']}")

    transcript_block = "\n".join(transcript_lines)

    system_prompt = (
        "You are an elite short-form video editor specialized in TikTok, Instagram Reels, and YouTube Shorts. "
        "Your task is to identify the most viral, hook-driven, standalone moments from this timestamped transcript. "
        f"Select exactly {num_clips} clips between {min_clip_sec} and {max_clip_sec} seconds in duration.\n\n"
        "Requirements for each clip:\n"
        "1. Strong opening hook (first 3 seconds grab attention).\n"
        "2. Standalone value (a complete idea, surprising fact, debate, or punchline).\n"
        "3. Precise start_time and end_time (in seconds) that match natural sentence boundaries in the transcript.\n"
        "4. Viral hook score between 75 and 99.\n"
        "5. Social caption and 3-5 relevant trending hashtags.\n\n"
        "Respond ONLY with a valid JSON array matching this exact schema:\n"
        "[\n"
        "  {\n"
        '    "title": "Short Catchy Clip Title",\n'
        '    "start_time": 45.5,\n'
        '    "end_time": 82.0,\n'
        '    "viral_score": 92,\n'
        '    "hook": "The opening sentence that stops the scroll",\n'
        '    "summary": "Brief 1-sentence summary of the clip",\n'
        '    "caption": "Compelling caption with CTA for viewers",\n'
        '    "hashtags": ["#shorts", "#tech", "#viral"]\n'
        "  }\n"
        "]"
    )

    user_prompt = f"Video Title: {video_title}\n\nTimestamped Transcript:\n{transcript_block}"

    try:
        response_text, _, _ = await free_llm.generate_text(system_prompt, user_prompt)
        # Extract JSON array from response
        match = re.search(r"\[\s*\{.*\}\s*\]", response_text, re.DOTALL)
        if match:
            clips = json.loads(match.group(0))
            validated_clips = []
            for c in clips[:num_clips]:
                start = float(c.get("start_time", 0))
                end = float(c.get("end_time", start + 30))
                dur = max(end - start, float(min_clip_sec))
                validated_clips.append({
                    "title": c.get("title") or f"Viral Clip #{len(validated_clips) + 1}",
                    "start_time": round(start, 2),
                    "end_time": round(start + min(dur, float(max_clip_sec)), 2),
                    "duration_sec": round(min(dur, float(max_clip_sec)), 2),
                    "viral_score": int(c.get("viral_score", 88)),
                    "hook": c.get("hook", ""),
                    "summary": c.get("summary", ""),
                    "caption": c.get("caption", f"{c.get('title')} 🔥 #shorts"),
                    "hashtags": c.get("hashtags", ["#shorts", "#viral"]),
                })
            if validated_clips:
                return validated_clips
    except Exception as exc:
        logger.warning("LLM viral clip selection failed, using heuristic: %s", exc)

    return _generate_heuristic_clips(video_title, num_clips, min_clip_sec, max_clip_sec, segments)


def _generate_heuristic_clips(
    video_title: str,
    num_clips: int,
    min_clip_sec: int,
    max_clip_sec: int,
    segments: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Fallback generator that extracts clips at regular intervals."""
    clips = []
    target_dur = min(max_clip_sec, max(min_clip_sec, 35))

    total_duration = segments[-1]["end"] if segments else 300.0
    step = max(total_duration / (num_clips + 1), target_dur + 5)

    for i in range(num_clips):
        start = round((i + 0.5) * step, 2)
        end = round(start + target_dur, 2)
        
        # Pull text if segments exist
        clip_text = ""
        if segments:
            matching = [s["text"] for s in segments if s["start"] >= start and s["end"] <= end]
            clip_text = " ".join(matching)[:100]

        clips.append({
            "title": f"Key Highlight #{i+1}: {video_title[:35]}",
            "start_time": start,
            "end_time": end,
            "duration_sec": target_dur,
            "viral_score": 85 + (i * 3) % 12,
            "hook": clip_text or f"Check out this viral moment from {video_title}",
            "summary": f"Key highlight excerpt from {video_title}",
            "caption": f"Must-watch moment from {video_title}! 🚀 Drop your thoughts below 👇 #viral #shorts",
            "hashtags": ["#shorts", "#reels", "#tiktok", "#trending"],
        })
    return clips
