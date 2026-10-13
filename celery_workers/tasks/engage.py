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
    _build_voyager,
)
from outreach.core.safety_shield import SafetyShield
from outreach.core.paid_access import sender_is_ready
from outreach.engine.voyager_client import VoyagerRestrictionError
from outreach.models import EngagePost
from outreach.core.engage_projection import (ProjectionStopped, start_run, project, check_contact, finish_run)
from outreach.core.workspace_scope import workspace_scope

logger = logging.getLogger(__name__)


async def _db():
    client = await get_client()
    return client[os.environ["DB_NAME"]]


async def _enrich_one(contact: dict, db, voyager, workspace_id: str, binding: dict) -> dict:
    try:
        await check_contact(db, binding, contact)
    except ProjectionStopped:
        return {"status": "stopped"}
    info = await voyager.fetch_profile_info(contact["vanity_name"])
    if info.get("status_code") and SafetyShield.should_trip_circuit_breaker(info["status_code"]):
        return {"status": "restricted", "status_code": info["status_code"]}
    verified = bool(info.get("verified") and info.get("profile_urn") and info.get("full_name"))
    async def save(current, contact_query):
        await current.outreach_engage_contacts.update_one(
            contact_query,
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
        await current.outreach_engage_posts.update_many(
            {"contact_id": contact["id"], "list_id": contact["list_id"], "workspace_id": workspace_id},
            {"$set": {"author_name": info.get("full_name") if verified else "LinkedIn Member",
                      "author_headline": info.get("headline", "") if verified else "",
                      "author_avatar": info.get("avatar_url", "") if verified else "",
                      "author_urn": info.get("profile_urn", "") if verified else ""}},
        )
    try:
        await project(db, binding, contact, save)
    except ProjectionStopped:
        return {"status": "stopped"}

    return {"status": "verified" if verified else "unverified", "profile_urn": info.get("profile_urn") if verified else "",
            "full_name": info.get("full_name", "") if verified else "", "headline": info.get("headline", "") if verified else "",
            "avatar_url": info.get("avatar_url", "") if verified else "",
            "company": info.get("company", "") if verified else "", "job_title": info.get("job_title", "") if verified else ""}


@celery_app.task(name="celery_workers.tasks.engage.enrich_contacts", queue="outreach", acks_late=True)
def enrich_contacts(list_id: str, workspace_id: str, account_id: str, run_id: str | None = None) -> dict:
    try:
        return run_async(_enrich_contacts(list_id, workspace_id, account_id, run_id))
    except Exception as exc:
        logger.error("Engage enrichment failed for list %s (%s)", list_id, type(exc).__name__)
        raise


async def _mark_job_failed(db, binding, message):
    return await finish_run(db, binding, {binding["kind"] + "_status": "failed", binding["kind"] + "_error": message})


async def _fail_captured_run(db, binding):
    try:
        await _mark_job_failed(db, binding, "Sender work could not be completed. Review the account and retry.")
    except Exception as exc:
        logger.error("Could not finalize Engage run (%s)", type(exc).__name__)


async def _prepare_run(list_id, workspace_id, account_id, kind, run_id):
    db = await _db()
    binding = await start_run(db, workspace_id, list_id, kind, run_id)
    if not binding:
        return db, None, None, None, "stopped"
    if is_shutting_down():
        await _mark_job_failed(db, binding, "Worker is shutting down.")
        return db, binding, None, None, "shutting_down"
    try:
        account = await db.outreach_accounts.find_one({"id": account_id, **workspace_scope(workspace_id), "status": "active"})
        if not account or not await sender_is_ready(db, workspace_id, account):
            await _mark_job_failed(db, binding, "Paid sender access or provider IP is unavailable.")
            return db, binding, None, None, "account_unavailable"
        voyager = await _build_voyager(account, db)
    except Exception:
        await _fail_captured_run(db, binding)
        raise

    return db, binding, account, voyager, None


async def _enrich_contacts(list_id: str, workspace_id: str, account_id: str, run_id: str | None = None) -> dict:
    db, binding, account, voyager, stop = await _prepare_run(list_id, workspace_id, account_id, "enrichment", run_id)
    if stop:
        return {"status": stop}
    try:
        return await _enrich_contacts_run(db, binding, account, voyager)
    except Exception:
        await _fail_captured_run(db, binding)
        raise


async def _enrich_contacts_run(db, binding, account, voyager):
    list_id, workspace_id, account_id = binding["id"], binding["workspace_id"], account["id"]
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
        if not await sender_is_ready(db, workspace_id, account):
            stopped = True
            break
        try:
            result = await _enrich_one(contact, db, voyager, workspace_id, binding)
            if result["status"] == "stopped":
                stopped = True
                break
            if result["status"] == "restricted":
                await SafetyShield.trip_circuit_breaker(
                    account_id, f"Profile enrichment triggered HTTP {result['status_code']}", db, workspace_id,
                )
                stopped = True
                break
            verified += result["status"] == "verified"
            unverified += result["status"] == "unverified"
        except Exception:
            logger.error("Could not enrich Engage contact %s", contact.get("id"))
            unverified += 1
    finished = await finish_run(db, binding,
        {"enrichment_status": "failed" if stopped else "complete", "updated_at": datetime.now(timezone.utc)})
    if not finished:
        return {"status": "stopped"}

    return {"status": "failed" if stopped else "complete", "verified": verified, "unverified": unverified}


@celery_app.task(name="celery_workers.tasks.engage.fetch_posts", queue="outreach", acks_late=True)
def fetch_posts(list_id: str, workspace_id: str, account_id: str, run_id: str | None = None) -> dict:
    try:
        return run_async(_fetch_posts(list_id, workspace_id, account_id, run_id))
    except Exception as exc:
        logger.error("Engage fetch failed for list %s (%s)", list_id, type(exc).__name__)
        raise


async def _fetch_posts(list_id: str, workspace_id: str, account_id: str, run_id: str | None = None) -> dict:
    db, binding, account, voyager, stop = await _prepare_run(list_id, workspace_id, account_id, "fetch", run_id)
    if stop:
        return {"status": stop}
    try:
        return await _fetch_posts_run(db, binding, account, voyager)
    except Exception:
        await _fail_captured_run(db, binding)
        raise


async def _fetch_posts_run(db, binding, account, voyager):
    list_id, workspace_id, account_id = binding["id"], binding["workspace_id"], account["id"]
    contacts = await db.outreach_engage_contacts.find({"list_id": list_id, "workspace_id": workspace_id}).to_list(1000)
    semaphore = asyncio.Semaphore(3)
    counts = {"fetched": 0, "unverified": 0, "failed": 0}
    restricted = False
    access_lost = False
    projection_stopped = False

    async def fetch_one(contact: dict) -> None:
        nonlocal restricted, access_lost, projection_stopped
        async with semaphore:
            if is_shutting_down() or restricted or access_lost or projection_stopped:
                return
            if not await sender_is_ready(db, workspace_id, account):
                access_lost = True
                return
            try:
                profile_urn = contact.get("profile_urn") if contact.get("enrichment_status") == "verified" else None
                if not profile_urn:
                    result = await _enrich_one(contact, db, voyager, workspace_id, binding)
                    if result["status"] == "stopped":
                        projection_stopped = True
                        return
                    if result["status"] == "restricted":
                        restricted = True
                        await SafetyShield.trip_circuit_breaker(account_id, "Post fetch profile lookup restricted", db, workspace_id)
                        return
                    profile_urn = result.get("profile_urn")
                    contact = {**contact, **result}
                if not profile_urn:
                    counts["unverified"] += 1
                    return
                if not await sender_is_ready(db, workspace_id, account):
                    access_lost = True
                    return
                await check_contact(db, binding, contact)
                updates = await voyager.fetch_profile_recent_updates(profile_urn, count=3)
                async def save_posts(current, contact_query):
                    inserted_count = 0
                    for update in updates[:3]:
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
                        inserted = await current.outreach_engage_posts.update_one(
                            {"list_id": list_id, "workspace_id": workspace_id, "post_urn": post_urn},
                            {"$setOnInsert": doc}, upsert=True,
                        )
                        inserted_count += bool(inserted.upserted_id)
                    await current.outreach_engage_contacts.update_one(
                        contact_query,
                        {"$set": {"last_fetched_at": datetime.now(timezone.utc)}},
                    )
                    return inserted_count
                counts["fetched"] += await project(db, binding, contact, save_posts)
            except ProjectionStopped:
                projection_stopped = True
            except Exception as exc:
                counts["failed"] += 1
                logger.error("Could not fetch Engage posts for contact %s (%s)", contact.get("id"), type(exc).__name__)
                if isinstance(exc, VoyagerRestrictionError):
                    restricted = True
                    await SafetyShield.trip_circuit_breaker(account_id, "Post fetch restricted by LinkedIn", db, workspace_id)

    for offset in range(0, len(contacts), 30):
        if is_shutting_down() or restricted or access_lost or projection_stopped:
            break
        if not await sender_is_ready(db, workspace_id, account):
            access_lost = True
            break
        await asyncio.gather(*(fetch_one(contact) for contact in contacts[offset:offset + 30]))

    all_unusable = bool(contacts) and counts["fetched"] == 0 and counts["failed"] + counts["unverified"] == len(contacts)
    final_status = "failed" if restricted or access_lost or projection_stopped or is_shutting_down() or all_unusable else "complete"
    error = ("Sender restricted; account paused." if restricted else
             "Paid sender access or provider IP is unavailable." if access_lost else
             "All contacts failed or could not be verified. Check sender connection and profile URLs." if all_unusable else
             "Worker is shutting down." if is_shutting_down() else "")
    finished = await finish_run(db, binding, {
        "fetch_status": final_status, "fetch_error": error,
        "posts_fetched_last_run": counts["fetched"],
        "fetch_failed_contacts_last_run": counts["failed"], "fetch_unverified_contacts_last_run": counts["unverified"],
        "fetch_completed_at": datetime.now(timezone.utc),
    })
    if not finished or projection_stopped:
        return {"status": "stopped"}
    return {"status": final_status, **counts}


@celery_app.task(name="celery_workers.tasks.engage.like_post", queue="outreach", acks_late=True)
def like_post(post_id: str, workspace_id: str, account_id: str, payload: str | None, action_id: str) -> dict:
    return run_async(_perform_action(post_id, workspace_id, account_id, "like", payload, action_id))


@celery_app.task(name="celery_workers.tasks.engage.comment_post", queue="outreach", acks_late=True)
def comment_post(post_id: str, workspace_id: str, account_id: str, payload: str | None, action_id: str) -> dict:
    return run_async(_perform_action(post_id, workspace_id, account_id, "comment", payload, action_id))


async def _perform_action(post_id: str, workspace_id: str, account_id: str,
                          action: str, payload: str | None, action_id: str) -> dict:
    from outreach.core.manual_actions import ManualActions

    db = await _db()
    job = await db.outreach_manual_actions.find_one({"_id": action_id, "workspace_id": workspace_id})
    if not job or job.get("source") != "engage" or job.get("account_id") != account_id or job.get("target_id") != post_id or job.get("action") != action:
        return {"status": "unapproved_legacy_job"}
    return await ManualActions(db).run(workspace_id, action_id)
