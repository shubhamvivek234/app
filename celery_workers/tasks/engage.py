"""Background profile enrichment and recent-post ingestion for Engage & Grow."""
import asyncio
import logging
import os
from datetime import datetime, timezone

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from celery_workers.shutdown_handler import is_shutting_down
from db.mongo import get_client
from outreach.api.engage import (
    CommentPostRequest, LikePostRequest, _build_voyager,
    comment_engage_post, like_engage_post,
)
from outreach.core.safety_shield import SafetyShield
from outreach.engine.voyager_client import VoyagerRestrictionError
from outreach.models import EngagePost

logger = logging.getLogger(__name__)


async def _db():
    client = await get_client()
    return client[os.environ["DB_NAME"]]


async def _enrich_one(contact: dict, db, voyager, workspace_id: str) -> dict:
    info = await voyager.fetch_profile_info(contact["vanity_name"])
    if info.get("status_code") and SafetyShield.should_trip_circuit_breaker(info["status_code"]):
        return {"status": "restricted", "status_code": info["status_code"]}
    verified = bool(info.get("verified") and info.get("profile_urn") and info.get("full_name"))
    await db.outreach_engage_contacts.update_one(
        {"id": contact["id"], "list_id": contact["list_id"], "workspace_id": workspace_id},
        {"$set": {
            "full_name": info.get("full_name", "") if verified else "",
            "headline": info.get("headline", "") if verified else "",
            "company": info.get("company", "") if verified else "",
            "job_title": info.get("job_title", "") if verified else "",
            "avatar_url": info.get("avatar_url", "") if verified else "",
            "profile_urn": info.get("profile_urn", "") if verified else "",
            "enrichment_status": "verified" if verified else "unverified",
        }},
    )
    await db.outreach_engage_posts.update_many(
        {"contact_id": contact["id"], "list_id": contact["list_id"], "workspace_id": workspace_id},
        {"$set": {"author_name": info.get("full_name") if verified else "LinkedIn Member",
                  "author_headline": info.get("headline", "") if verified else "",
                  "author_avatar": info.get("avatar_url", "") if verified else "",
                  "author_urn": info.get("profile_urn", "") if verified else ""}},
    )
    return {"status": "verified" if verified else "unverified", "profile_urn": info.get("profile_urn") if verified else "",
            "full_name": info.get("full_name", "") if verified else "", "headline": info.get("headline", "") if verified else "",
            "avatar_url": info.get("avatar_url", "") if verified else "",
            "company": info.get("company", "") if verified else "", "job_title": info.get("job_title", "") if verified else ""}


@celery_app.task(name="celery_workers.tasks.engage.enrich_contacts", queue="outreach", acks_late=True)
def enrich_contacts(list_id: str, workspace_id: str, account_id: str) -> dict:
    try:
        return run_async(_enrich_contacts(list_id, workspace_id, account_id))
    except Exception as exc:
        logger.exception("Engage enrichment failed for list %s", list_id)
        run_async(_mark_job_failed(list_id, workspace_id, "enrichment_status", exc))
        raise


async def _mark_job_failed(list_id: str, workspace_id: str, status_field: str, exc: Exception) -> None:
    db = await _db()
    await db.outreach_engage_lists.update_one(
        {"id": list_id, "workspace_id": workspace_id},
        {"$set": {status_field: "failed", "fetch_error": str(exc)[:200]}},
    )


async def _enrich_contacts(list_id: str, workspace_id: str, account_id: str) -> dict:
    if is_shutting_down():
        await _mark_job_failed(list_id, workspace_id, "enrichment_status", RuntimeError("Worker is shutting down"))
        return {"status": "shutting_down"}
    db = await _db()
    account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": workspace_id, "status": "active"})
    if not account:
        await _mark_job_failed(list_id, workspace_id, "enrichment_status", RuntimeError("Sender account is unavailable"))
        return {"status": "account_unavailable"}
    voyager = _build_voyager(account)
    await db.outreach_engage_lists.update_one(
        {"id": list_id, "workspace_id": workspace_id}, {"$set": {"enrichment_status": "running"}},
    )
    contacts = await db.outreach_engage_contacts.find({
        "list_id": list_id, "workspace_id": workspace_id, "enrichment_status": {"$ne": "verified"},
    }).to_list(1000)
    verified = 0
    unverified = 0
    stopped = False
    for contact in contacts:
        if is_shutting_down():
            stopped = True
            break
        try:
            result = await _enrich_one(contact, db, voyager, workspace_id)
            if result["status"] == "restricted":
                await SafetyShield.trip_circuit_breaker(
                    account_id, f"Profile enrichment triggered HTTP {result['status_code']}", db, workspace_id,
                )
                stopped = True
                break
            verified += result["status"] == "verified"
            unverified += result["status"] == "unverified"
        except Exception:
            logger.exception("Could not enrich Engage contact %s", contact.get("id"))
            unverified += 1
    await db.outreach_engage_lists.update_one(
        {"id": list_id, "workspace_id": workspace_id},
        {"$set": {"enrichment_status": "failed" if stopped else "complete", "updated_at": datetime.now(timezone.utc)}},
    )
    return {"status": "failed" if stopped else "complete", "verified": verified, "unverified": unverified}


@celery_app.task(name="celery_workers.tasks.engage.fetch_posts", queue="outreach", acks_late=True)
def fetch_posts(list_id: str, workspace_id: str, account_id: str) -> dict:
    try:
        return run_async(_fetch_posts(list_id, workspace_id, account_id))
    except Exception as exc:
        logger.exception("Engage fetch failed for list %s", list_id)
        run_async(_mark_job_failed(list_id, workspace_id, "fetch_status", exc))
        raise


async def _fetch_posts(list_id: str, workspace_id: str, account_id: str) -> dict:
    if is_shutting_down():
        await _mark_job_failed(list_id, workspace_id, "fetch_status", RuntimeError("Worker is shutting down"))
        return {"status": "shutting_down"}
    db = await _db()
    query = {"id": list_id, "workspace_id": workspace_id}
    account = await db.outreach_accounts.find_one({"id": account_id, "workspace_id": workspace_id, "status": "active"})
    if not account:
        await db.outreach_engage_lists.update_one(query, {"$set": {"fetch_status": "failed", "fetch_error": "Sender account is unavailable."}})
        return {"status": "account_unavailable"}
    voyager = _build_voyager(account)
    await db.outreach_engage_lists.update_one(query, {"$set": {"fetch_status": "running"}})
    contacts = await db.outreach_engage_contacts.find({"list_id": list_id, "workspace_id": workspace_id}).to_list(1000)
    semaphore = asyncio.Semaphore(3)
    counts = {"fetched": 0, "unverified": 0, "failed": 0}
    restricted = False

    async def fetch_one(contact: dict) -> None:
        nonlocal restricted
        async with semaphore:
            if is_shutting_down() or restricted:
                return
            try:
                profile_urn = contact.get("profile_urn") if contact.get("enrichment_status") == "verified" else None
                if not profile_urn:
                    result = await _enrich_one(contact, db, voyager, workspace_id)
                    if result["status"] == "restricted":
                        restricted = True
                        await SafetyShield.trip_circuit_breaker(account_id, "Post fetch profile lookup restricted", db, workspace_id)
                        return
                    profile_urn = result.get("profile_urn")
                    contact = {**contact, **result}
                if not profile_urn:
                    counts["unverified"] += 1
                    return
                updates = await voyager.fetch_profile_recent_updates(profile_urn, count=3)
                for update in updates:
                    post_urn = update.get("post_urn")
                    if not post_urn:
                        continue
                    doc = EngagePost(
                        list_id=list_id, contact_id=contact["id"], workspace_id=workspace_id,
                        author_name=contact.get("full_name") or "LinkedIn Member",
                        author_headline=contact.get("headline", ""), author_avatar=contact.get("avatar_url", ""),
                        author_profile_url=contact.get("profile_url", ""), author_urn=profile_urn,
                        post_urn=post_urn, post_url=update.get("post_url", ""),
                        published_at=str(update.get("published_at") or ""),
                        content_text=update.get("content_text", ""),
                        reactions_count=update.get("reactions_count", 0), comments_count=update.get("comments_count", 0),
                        media_urls=update.get("media_urls", []),
                    ).model_dump()
                    inserted = await db.outreach_engage_posts.update_one(
                        {"list_id": list_id, "workspace_id": workspace_id, "post_urn": post_urn},
                        {"$setOnInsert": doc}, upsert=True,
                    )
                    counts["fetched"] += bool(inserted.upserted_id)
                await db.outreach_engage_contacts.update_one(
                    {"id": contact["id"], "list_id": list_id, "workspace_id": workspace_id},
                    {"$set": {"last_fetched_at": datetime.now(timezone.utc)}},
                )
            except Exception as exc:
                counts["failed"] += 1
                logger.exception("Could not fetch Engage posts for contact %s", contact.get("id"))
                if isinstance(exc, VoyagerRestrictionError):
                    restricted = True
                    await SafetyShield.trip_circuit_breaker(account_id, "Post fetch restricted by LinkedIn", db, workspace_id)

    for offset in range(0, len(contacts), 30):
        if is_shutting_down() or restricted:
            break
        await asyncio.gather(*(fetch_one(contact) for contact in contacts[offset:offset + 30]))

    pending = await db.outreach_engage_posts.count_documents({"list_id": list_id, "workspace_id": workspace_id, "status": "pending"})
    all_unusable = bool(contacts) and counts["fetched"] == 0 and counts["failed"] + counts["unverified"] == len(contacts)
    final_status = "failed" if restricted or is_shutting_down() or all_unusable else "complete"
    error = ("Sender restricted; account paused." if restricted else
             "All contacts failed or could not be verified. Check sender connection and profile URLs." if all_unusable else
             "Worker is shutting down." if is_shutting_down() else "")
    await db.outreach_engage_lists.update_one(query, {"$set": {
        "fetch_status": final_status, "fetch_error": error,
        "posts_fetched_last_run": counts["fetched"], "pending_posts_count": pending,
        "fetch_failed_contacts_last_run": counts["failed"], "fetch_unverified_contacts_last_run": counts["unverified"],
        "fetch_completed_at": datetime.now(timezone.utc),
    }})
    return {"status": final_status, **counts}


@celery_app.task(name="celery_workers.tasks.engage.like_post", queue="outreach", acks_late=True)
def like_post(post_id: str, workspace_id: str, account_id: str, payload: str | None, action_id: str) -> dict:
    return run_async(_perform_action(post_id, workspace_id, account_id, "like", payload, action_id))


@celery_app.task(name="celery_workers.tasks.engage.comment_post", queue="outreach", acks_late=True)
def comment_post(post_id: str, workspace_id: str, account_id: str, payload: str | None, action_id: str) -> dict:
    return run_async(_perform_action(post_id, workspace_id, account_id, "comment", payload, action_id))


async def _perform_action(post_id: str, workspace_id: str, account_id: str,
                          action: str, payload: str | None, action_id: str) -> dict:
    import json
    from fastapi import HTTPException

    db = await _db()
    query = {"id": post_id, "workspace_id": workspace_id}
    claim_query = {**query, "action_id": action_id}
    try:
        if is_shutting_down():
            raise RuntimeError("Outreach worker is shutting down")
        post = await db.outreach_engage_posts.find_one(query)
        if not post:
            return {"status": "post_deleted"}
        if post.get("action_id") != action_id:
            return {"status": "stale_job"}
        if (action == "like" and post.get("status") in {"liked", "commented"}) or \
           (action == "comment" and post.get("status") == "commented"):
            return {"status": "already_completed"}
        user = {"default_workspace_id": workspace_id}
        if action == "like":
            return await like_engage_post(post_id, LikePostRequest(sender_account_id=account_id),
                                          current_user=user, db=db)
        data = json.loads(payload or "{}")
        req = CommentPostRequest(**data, sender_account_id=account_id)
        return await comment_engage_post(post_id, req, current_user=user, db=db)
    except Exception as exc:
        message = exc.detail if isinstance(exc, HTTPException) else "LinkedIn action failed. Please retry after checking the sender."
        await db.outreach_engage_posts.update_one(claim_query, {"$set": {"action_error": str(message)[:200]}})
        logger.exception("Engage %s failed for post %s", action, post_id)
        return {"status": "failed", "error": str(message)[:200]}
    finally:
        await db.outreach_engage_posts.update_one(claim_query, {"$unset": {"action_queued_at": "", "action_id": ""}})
