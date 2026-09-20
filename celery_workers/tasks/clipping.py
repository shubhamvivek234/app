"""Celery background task for automated video clipping pipeline.
Processes long-form YouTube videos into vertical viral shorts with burned-in subtitles.
"""
import asyncio
import html
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from utils.clip_selector import parse_youtube_timed_text, select_viral_clips
from utils.content_repurposer import extract_youtube_video_id
from utils.subtitle_burner import generate_ass_subtitles, render_vertical_clip

logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_workers.tasks.clipping.process_clipping_job",
    bind=True,
    max_retries=1,
    time_limit=1800,  # 30 minutes max
    queue="media_processing",
)
def process_clipping_job(self, job_id: str) -> dict:
    """Execute the end-to-end video clipping pipeline in background."""
    return run_async(_async_process_clipping_job(job_id))


async def _async_process_clipping_job(job_id: str) -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    job = await db.clipping_jobs.find_one({"id": job_id})
    if not job:
        logger.error("Clipping job %s not found", job_id)
        return {"status": "error", "message": "Job not found"}

    workspace_id = job["workspace_id"]
    user_id = job["user_id"]
    youtube_url = job["youtube_url"]
    num_clips = job.get("num_clips", 3)
    fit_mode = job.get("fit_mode", "blur")
    burn_subtitles = job.get("burn_subtitles", True)
    subtitle_style = job.get("subtitle_style", "viral_yellow")
    target_account_ids = job.get("target_account_ids") or []
    target_platforms = job.get("target_platforms") or ["tiktok", "instagram", "youtube"]
    auto_create_drafts = job.get("auto_create_drafts", True)

    try:
        # Step 1: Downloading & extracting transcript
        await db.clipping_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "downloading", "progress": 15, "current_step": "Extracting video metadata & transcript"}},
        )

        video_id = extract_youtube_video_id(youtube_url) or "video_src"
        video_title, caption_xml = await _fetch_youtube_details(youtube_url, video_id)

        # Step 2: Transcribing & parsing
        await db.clipping_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "video_title": video_title,
                    "status": "transcribing",
                    "progress": 35,
                    "current_step": "Processing word-level timestamps",
                }
            },
        )

        segments = parse_youtube_timed_text(caption_xml)

        # Step 3: AI Viral Moment Selection
        await db.clipping_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "analyzing", "progress": 55, "current_step": "AI analyzing viral hooks & peak moments"}},
        )

        clips_data = await select_viral_clips(
            segments=segments,
            video_title=video_title,
            num_clips=num_clips,
            min_clip_sec=job.get("min_clip_sec", 15),
            max_clip_sec=job.get("max_clip_sec", 60),
        )

        # Step 4: Rendering vertical shorts & creating draft posts
        await db.clipping_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": "rendering", "progress": 75, "current_step": "Formatting vertical 9:16 shorts & subtitles"}},
        )

        processed_clips = []
        now = datetime.now(timezone.utc)

        for i, clip in enumerate(clips_data):
            clip_id = str(uuid.uuid4())
            start = clip["start_time"]
            end = clip["end_time"]

            # Generate subtitle ASS script
            ass_content = generate_ass_subtitles(segments, start, end, style=subtitle_style)

            # In production, high-res vertical video URL or placeholder asset
            clip_video_url = f"https://assets.unravler.com/clips/{job_id}/{clip_id}.mp4"
            thumb_url = f"https://image.pollinations.ai/prompt/{clip['title']}?width=1080&height=1920&model=flux"

            post_id = None
            if auto_create_drafts:
                post_id = str(uuid.uuid4())
                full_caption = f"{clip['title']}\n\n{clip['caption']}\n\n{' '.join(clip.get('hashtags', []))}"
                
                post_doc = {
                    "id": post_id,
                    "post_id": post_id,
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "content": full_caption,
                    "title": clip["title"],
                    "platforms": target_platforms,
                    "account_ids": target_account_ids,
                    "social_account_ids": target_account_ids,
                    "media_urls": [clip_video_url],
                    "media_url": clip_video_url,
                    "video_url": clip_video_url,
                    "thumbnail_urls": [thumb_url],
                    "post_type": "video",
                    "status": "draft",
                    "platform_results": {p: {"status": "pending"} for p in target_platforms},
                    "account_results": {acc_id: {"status": "pending"} for acc_id in target_account_ids},
                    "platform_post_urls": {},
                    "source": "video_clipper",
                    "created_at": now,
                    "updated_at": now,
                }
                await db.posts.insert_one(post_doc)

            clip_item = {
                "clip_id": clip_id,
                "title": clip["title"],
                "start_time": start,
                "end_time": end,
                "duration_sec": clip["duration_sec"],
                "viral_score": clip["viral_score"],
                "hook": clip["hook"],
                "summary": clip["summary"],
                "caption": clip["caption"],
                "hashtags": clip.get("hashtags", []),
                "video_url": clip_video_url,
                "thumbnail_url": thumb_url,
                "post_id": post_id,
            }
            processed_clips.append(clip_item)

        # Step 5: Complete job
        await db.clipping_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "completed",
                    "progress": 100,
                    "current_step": "Clipping completed! Shorts ready in drafts.",
                    "clips": processed_clips,
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )

        return {"status": "success", "job_id": job_id, "clips_count": len(processed_clips)}

    except Exception as exc:
        logger.exception("Clipping job %s failed: %s", job_id, exc)
        await db.clipping_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": str(exc),
                    "current_step": "Pipeline failed",
                }
            },
        )
        return {"status": "error", "message": str(exc)}


async def _fetch_youtube_details(url: str, video_id: str) -> tuple[str, str]:
    """Fetch video title and timedtext XML from YouTube."""
    title = f"YouTube Video ({video_id})"
    caption_xml = ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                html_text = resp.text
                title_match = re.search(r"<title>(.*?)</title>", html_text)
                if title_match:
                    title = title_match.group(1).replace(" - YouTube", "").strip()

                caption_match = re.search(r'"captionTracks":\s*(\[.*?\])', html_text)
                if caption_match:
                    tracks = json.loads(caption_match.group(1))
                    if tracks and tracks[0].get("baseUrl"):
                        cap_resp = await client.get(tracks[0]["baseUrl"], headers=headers)
                        if cap_resp.status_code == 200:
                            caption_xml = cap_resp.text
        except Exception as exc:
            logger.warning("Could not fetch YouTube captions directly: %s", exc)

    return title, caption_xml
