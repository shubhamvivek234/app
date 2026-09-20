"""Unit tests for the Video Clipping Engine."""
import pytest
from unittest.mock import AsyncMock, patch

from api.models.clipping import ClippingRequest
from utils.clip_selector import parse_youtube_timed_text, select_viral_clips
from utils.subtitle_burner import format_ass_timestamp, generate_ass_subtitles, render_vertical_clip


def test_clipping_request_defaults():
    req = ClippingRequest(youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert req.num_clips == 3
    assert req.fit_mode == "blur"
    assert req.burn_subtitles is True
    assert req.subtitle_style == "viral_yellow"
    assert req.min_clip_sec == 15
    assert req.max_clip_sec == 60


def test_parse_youtube_timed_text():
    sample_xml = """<?xml version="1.0" encoding="utf-8" ?>
    <transcript>
      <text start="0.5" dur="3.2">Welcome to the future of artificial intelligence</text>
      <text start="3.8" dur="4.0">Where autonomous coding agents solve real world software problems</text>
      <text start="8.1" dur="2.5">In mere minutes instead of days</text>
    </transcript>"""
    
    segments = parse_youtube_timed_text(sample_xml)
    assert len(segments) == 3
    assert segments[0]["start"] == 0.5
    assert segments[0]["dur"] == 3.2
    assert segments[0]["end"] == 3.7
    assert segments[0]["text"] == "Welcome to the future of artificial intelligence"
    assert segments[1]["start"] == 3.8


def test_format_ass_timestamp():
    assert format_ass_timestamp(0.0) == "0:00:00.00"
    assert format_ass_timestamp(65.42) == "0:01:05.42"
    assert format_ass_timestamp(3661.05) == "1:01:01.05"


def test_generate_ass_subtitles():
    segments = [
        {"start": 10.0, "end": 14.0, "dur": 4.0, "text": "This is a viral hook"},
        {"start": 14.5, "end": 18.0, "dur": 3.5, "text": "Pay attention to this"},
    ]
    ass_text = generate_ass_subtitles(segments, clip_start_sec=10.0, clip_end_sec=20.0, style="viral_yellow")
    assert "[Script Info]" in ass_text
    assert "PlayResX: 1080" in ass_text
    assert "PlayResY: 1920" in ass_text
    assert "ViralStyle" in ass_text
    assert "THIS IS A VIRAL HOOK" in ass_text
    assert "Dialogue: 0,0:00:00.00,0:00:04.00,ViralStyle,,0,0,0,,THIS IS A VIRAL HOOK" in ass_text


@pytest.mark.asyncio
async def test_select_viral_clips_heuristic():
    segments = [
        {"start": 0.0, "end": 20.0, "text": "Segment one intro"},
        {"start": 21.0, "end": 50.0, "text": "Segment two core insight"},
        {"start": 51.0, "end": 100.0, "text": "Segment three conclusion"},
    ]
    clips = await select_viral_clips(
        segments=segments,
        video_title="How to Build Autonomous AI Agents",
        num_clips=2,
        min_clip_sec=15,
        max_clip_sec=45,
    )
    assert len(clips) == 2
    assert clips[0]["duration_sec"] >= 15
    assert clips[0]["duration_sec"] <= 45
    assert "viral_score" in clips[0]
    assert clips[0]["viral_score"] >= 75
    assert len(clips[0]["hashtags"]) > 0


@pytest.mark.asyncio
async def test_render_vertical_clip_fallback_when_no_ffmpeg(tmp_path):
    input_file = tmp_path / "input.mp4"
    input_file.write_text("dummy video content")
    output_file = tmp_path / "output.mp4"

    with patch("shutil.which", return_value=None):
        out = await render_vertical_clip(
            str(input_file), str(output_file), start_sec=5.0, end_sec=15.0, fit_mode="blur"
        )
        assert out == str(output_file)
        assert output_file.exists()
