"""
Phase 0.1 — MongoDB Index Definitions
Run once on DB setup. Never rely on auto-indexing.
"""
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from db.mongo import get_client

logger = logging.getLogger(__name__)


async def ensure_mailbox_job_indexes(db) -> None:
    """Drained cutover: remove destructive TTLs before building the expanded slot.

    Conflicts and duplicates must fail this migration; ignoring them would let
    retention/reconnect protections silently disappear.
    """
    from outreach.core.mailbox_jobs import ACTIVE_JOB_STATES, REVIEW_ERROR
    jobs = db.outreach_mailbox_connection_jobs
    indexes = await jobs.index_information()
    migration_needed = "mailbox_active_connection_v2" not in indexes or any(
        "expireAfterSeconds" in definition for definition in indexes.values())
    for name, definition in indexes.items():
        if "expireAfterSeconds" in definition:
            await jobs.drop_index(name)
    # TTL is gone even if uniqueness validation fails. Old unmarked running
    # workers cannot prove a non-call and must remain available for review.
    if migration_needed:
        await jobs.update_many({"$or": [{"exchange_state": {"$in": ["possible", "unknown"]}},
            {"status": "running", "protocol_version": {"$ne": 2}}]}, {
            "$set": {"status": "review_required", "error": REVIEW_ERROR}, "$unset": {"expires_at": "", "authorization_code_enc": "", "code_verifier_enc": ""}})
    await jobs.create_index([("workspace_id", 1), ("sender_account_id", 1)],
        name="mailbox_active_connection_v2", unique=True,
        partialFilterExpression={"status": {"$in": list(ACTIVE_JOB_STATES)}})
    await jobs.create_index([("status", 1), ("next_publish_at", 1)])
    await jobs.create_index([("status", 1), ("next_recovery_at", 1)])
    await db.outreach_mailbox_exchange_budgets.create_index([("workspace_id", 1), ("sender_account_id", 1), ("day", 1)], unique=True)


async def _safe_create_index(collection, keys, **kwargs) -> None:
    """Create index, ignoring conflicts with pre-existing indexes of different names."""
    try:
        await collection.create_index(keys, **kwargs)
    except Exception as exc:
        # IndexOptionsConflict (85/86) — index exists with different name, safe to ignore
        # DuplicateKeyError (11000) - unique index creation failed due to existing duplicates, ignore for local/dev
        if "already exists" in str(exc) or getattr(exc, "code", None) in (85, 86, 11000):
            logger.warning("Index creation skipped on %s (code %s): %s", collection.name, getattr(exc, "code", None), exc)
        else:
            raise


async def ensure_mailbox_sync_indexes(db) -> None:
    """Strict durable read identities; evidence has no TTL or ignored conflicts."""
    await db.outreach_mailboxes.create_index([('workspace_id', 1), ('sender_account_id', 1)], unique=True)
    await db.outreach_mailbox_sync_jobs.create_index([('workspace_id', 1), ('sender_account_id', 1)],
        name='mailbox_active_sync_v1', unique=True, partialFilterExpression={'status': {'$in': ['queued', 'running']}})
    await db.outreach_mailbox_sync_jobs.create_index([('status', 1), ('next_publish_at', 1)])
    await db.outreach_mailbox_sync_jobs.create_index([('status', 1), ('next_recovery_at', 1)])
    await db.outreach_mailbox_sync_reads.create_index([('workspace_id', 1), ('job_id', 1), ('request_index', 1)],
        name='mailbox_received_read_v1', unique=True, partialFilterExpression={'status': 'received'})
    await db.outreach_mailbox_sync_reads.create_index([('workspace_id', 1), ('job_id', 1), ('owner', 1), ('status', 1)])
    await db.outreach_mailbox_read_budgets.create_index([('workspace_id', 1), ('sender_account_id', 1), ('day', 1)], unique=True)
    await db.outreach_mailboxes.create_index([('status', 1), ('next_sync_at', 1)])


async def ensure_voice_studio_indexes(db) -> None:
    """Strict identities and unfinished profile ownership; no evidence TTL."""
    from outreach.core.voice_studio import ACTIVE
    from outreach.core.voice_vendor_evidence import READ_ACTIVE
    jobs = db.outreach_voice_studio_jobs
    migrations = db.outreach_voice_source_migrations
    reads = db.outreach_voice_vendor_reads
    for collection in (jobs, migrations, reads):
        for name, definition in (await collection.index_information()).items():
            if 'expireAfterSeconds' in definition:
                await collection.drop_index(name)
    await jobs.create_index([('workspace_id', 1), ('voice_id', 1)], unique=True,
        name='studio_active_profile_v1', partialFilterExpression={'status': {'$in': ACTIVE}})
    await jobs.create_index([('status', 1), ('next_publish_at', 1)])
    await jobs.create_index([('status', 1), ('next_recovery_at', 1)])
    await jobs.create_index([('result_expires_at', 1)])
    await db.outreach_voices.create_index([('workspace_id', 1), ('id', 1)], unique=True)
    await db.outreach_voice_studio_budgets.create_index([('workspace_id', 1), ('operation', 1), ('day', 1)], unique=True)
    await migrations.create_index([('workspace_id', 1), ('voice_id', 1), ('review_digest', 1)],
        unique=True, name='voice_source_review_v1')
    await migrations.create_index([('workspace_id', 1), ('voice_id', 1), ('_id', 1)])
    await reads.create_index([('workspace_id', 1), ('voice_id', 1), ('inspection_digest', 1)],
        unique=True, name='voice_vendor_inspection_v1')
    await reads.create_index([('workspace_id', 1), ('voice_id', 1)], unique=True,
        name='voice_vendor_active_v1', partialFilterExpression={'status': {'$in': READ_ACTIVE}})


async def remove_other_evidence_ttls(db) -> None:
    """Remove all other touched evidence TTLs before even the first strict build.

    Mailbox jobs keep their own retention-first inspection because its TTL
    presence also determines whether legacy-running work needs quarantine.
    """
    for name in ("outreach_webhook_deliveries", "outreach_voice_studio_jobs",
                 "outreach_voice_source_migrations", "outreach_voice_vendor_reads",
                 "outreach_integration_reviews", "outreach_integration_controls", "outreach_credential_migrations", "outreach_proxy_lifecycle_reviews",
                 "account_proxy_ip_guards", "outreach_proxy_adoptions", "outreach_health_controls", "outreach_execution_epochs",
                 "outreach_restore_proxy_exclusions", "account_proxy_ip_restore_fences", "outreach_restore_invoices", "account_invoice_guards", "outreach_restore_exclusions", "outreach_restore_suppressions", "outreach_restore_reply_stops", "outreach_reply_stops", "outreach_do_not_contact",
                 "outreach_email_suppressions", "account_erasure_tombstones", "outreach_suppression_guards"):
        collection = db[name]
        for index, definition in (await collection.index_information()).items():
            if "expireAfterSeconds" in definition:
                await collection.drop_index(index)


async def ensure_integration_indexes(db) -> None:
    """Drained cutover preserves possible/received integration evidence first."""
    await db.outreach_restore_proxy_exclusions.create_index([('workspace_id', 1), ('execution_epoch', 1), ('source_digest', 1)],
        unique=True, name='restore_proxy_exclusion_source_v1')
    await db.outreach_restore_invoices.create_index([('workspace_id', 1), ('execution_epoch', 1), ('source_digest', 1)],
        unique=True, name='restore_invoice_source_v1')
    await db.outreach_restore_reply_stops.create_index([('workspace_id', 1), ('execution_epoch', 1), ('source_digest', 1)],
        unique=True, name='restore_reply_stop_source_v1')
    await db.outreach_reply_stops.create_index([('workspace_id', 1), ('sender_id', 1), ('field', 1), ('value', 1)],
        unique=True, name='reply_stop_identity_v1')
    await db.outreach_restore_suppressions.create_index([('workspace_id', 1), ('execution_epoch', 1), ('source_digest', 1)],
        unique=True, name='restore_suppression_source_v1')
    # Duplicate recipient rows must fail the cutover instead of weakening lookup.
    await db.outreach_email_suppressions.create_index([('workspace_id', 1), ('email', 1)], unique=True)
    from outreach.core.integration_delivery import ACTIVE
    await db.outreach_restore_exclusions.create_index([('workspace_id', 1), ('execution_epoch', 1), ('source_digest', 1)],
        unique=True, name='restore_exclusion_source_v1')
    await db.outreach_execution_epochs.create_index([('workspace_id', 1), ('kind', 1), ('execution_epoch', 1)],
        unique=True, name='execution_epoch_journal_v1', partialFilterExpression={'kind': 'journal'})
    await db.outreach_execution_epochs.create_index([('workspace_id', 1), ('kind', 1)],
        unique=True, name='execution_epoch_root_v1', partialFilterExpression={'kind': 'root'})
    await db.outreach_health_controls.create_index([('workspace_id', 1), ('sender_id', 1)], unique=True,
        name='health_sender_active_v1', partialFilterExpression={'status': 'armed'})
    await db.outreach_health_controls.create_index([('status', 1), ('next_check_at', 1), ('_id', 1)],
        name='health_control_due_v1')
    # Every evidence TTL is removed before uniqueness can fail elsewhere.
    for collection in (db.outreach_integration_reviews, db.outreach_integration_controls, db.outreach_credential_migrations):
        for name, definition in (await collection.index_information()).items():
            if 'expireAfterSeconds' in definition:
                await collection.drop_index(name)
    deliveries = db.outreach_webhook_deliveries
    indexes = await deliveries.index_information()
    first_cutover = "integration_active_slot_v2" not in indexes
    for name, definition in indexes.items():
        if "expireAfterSeconds" in definition:
            await deliveries.drop_index(name)
    if first_cutover:
        await deliveries.update_many({"custody_protocol_version": {"$ne": 2}, "status": {"$in": ["pending", "retry", "leased"]}},
            {"$set": {"status": "review_required", "error_sanitized": "Legacy delivery requires drained review"}})
    await db.outreach_webhooks.create_index([("workspace_id", 1), ("id", 1)], unique=True)
    await db.outreach_integrations.create_index([("workspace_id", 1), ("provider", 1)], unique=True)
    await db.outreach_external_mappings.create_index([("workspace_id", 1), ("provider", 1),
        ("external_account_id", 1), ("object_type", 1), ("internal_id", 1)], unique=True)
    await deliveries.create_index([("workspace_id", 1), ("id", 1)], unique=True)
    if "event_id_1_destination_id_1" in indexes:
        await deliveries.drop_index("event_id_1_destination_id_1")
    await deliveries.create_index([("workspace_id", 1), ("event_id", 1),
        ("destination_type", 1), ("destination_id", 1)], unique=True)
    await deliveries.create_index([("workspace_id", 1), ("active_slot", 1)], unique=True,
        name="integration_active_slot_v2", partialFilterExpression={"custody_protocol_version": 2,
        "active_slot": {"$type": "string"}, "status": {"$in": ACTIVE}})
    await deliveries.create_index([("custody_protocol_version", 1), ("status", 1), ("next_attempt_at", 1)])
    await db.outreach_integration_reviews.create_index([('workspace_id', 1), ('id', 1)], unique=True,
        name='integration_review_original_v1')
    await db.outreach_integration_controls.create_index([('workspace_id', 1), ('_id', 1)], unique=True,
        name='integration_resource_stop_v1')
    await db.outreach_credential_migrations.create_index([('workspace_id', 1), ('resource_kind', 1),
        ('resource_id', 1), ('before_digest', 1)], unique=True, name='integration_migration_inspection_v1',
        partialFilterExpression={'kind': 'integration'})


async def ensure_managed_proxy_indexes(db) -> None:
    """Require sender uniqueness; a conflicting legacy lease stops startup."""
    for name, definition in (await db.account_proxy_ip_guards.index_information()).items():
        if 'expireAfterSeconds' in definition:
            await db.account_proxy_ip_guards.drop_index(name)
    await db.outreach_proxy_leases.create_index([('workspace_id', 1), ('sender_id', 1)],
        unique=True, partialFilterExpression={'sender_id': {'$type': 'string'}})
    await db.outreach_proxy_inventory.create_index([('host', 1)])
    await db.outreach_proxy_lifecycle_reviews.create_index([('workspace_id', 1), ('proxy_id', 1), ('revision', 1)],
        unique=True, name='proxy_lifecycle_revision_v1')
    await db.outreach_proxy_adoptions.create_index([('workspace_id', 1), ('proxy_id', 1)],
        unique=True, name='proxy_adoption_asset_v1')
    for name in ('proxy', 'proxy_config'):
        await db.outreach_accounts.create_index([(name + '.host', 1)])
        await db.outreach_accounts.create_index([(name + '.proxy_id', 1)])


async def ensure_voice_artifact_migration_indexes(db) -> None:
    """Permanent per-generation conversion proof; conflicts require drained repair."""
    await db.outreach_credential_migrations.create_index(
        [('workspace_id', 1), ('artifact_id', 1), ('generation_digest', 1)], unique=True,
        name='voice_artifact_migration_generation_v1', partialFilterExpression={'kind': 'voice_artifact'})
    await db.outreach_content_approvals.create_index([('workspace_id', 1), ('binding.context.voice_artifact_id', 1)])
    await db.outreach_credential_migrations.create_index([('workspace_id', 1), ('job_id', 1)],
        unique=True, name='voice_studio_result_migration_original_v1',
        partialFilterExpression={'kind': 'voice_studio_result'})
    await db.outreach_credential_migrations.create_index([('workspace_id', 1), ('job_id', 1)],
        unique=True, name='voice_studio_input_stop_original_v1',
        partialFilterExpression={'kind': 'voice_studio_input_stop'})


async def ensure_lead_list_indexes(db) -> None:
    """Required audience identities; conflicts need drained repair, never deletion."""
    await db.outreach_lead_lists.create_index([("workspace_id", 1), ("id", 1)], unique=True)
    await db.outreach_lead_lists.create_index([("workspace_id", 1), ("campaign_id", 1), ("name_normalized", 1)], unique=True)
    await db.outreach_lead_list_imports.create_index([("workspace_id", 1), ("actor_id", 1), ("request_id", 1)], unique=True)
    await db.outreach_lead_list_members.create_index([("workspace_id", 1), ("list_id", 1), ("lead_id", 1)], unique=True)
    await db.outreach_lead_list_members.create_index([("workspace_id", 1), ("campaign_id", 1), ("list_id", 1), ("id", 1)])
    await db.outreach_leads.create_index([("workspace_id", 1), ("id", 1)])
    await db.outreach_leads.create_index([("workspace_id", 1), ("campaign_id", 1), ("id", 1)])


async def ensure_connection_wait_indexes(db) -> None:
    """Original invite scope identities retain conflicts; no TTL or adoption."""
    await db.outreach_connection_waits.create_index([('workspace_id', 1), ('invite_intent_id', 1), ('invite_attempt_id', 1)], unique=True)
    await db.outreach_connection_waits.create_index([('workspace_id', 1), ('lead_id', 1), ('status', 1)])
    await db.outreach_sequence_jobs.create_index([('workspace_id', 1), ('stamp.connection_wait_id', 1), ('status', 1)])
    await db.outreach_physical_requests.create_index([('workspace_id', 1), ('connection_wait_context.scope_id', 1),
        ('connection_wait_context.scope_revision', 1), ('connection_wait_context.node_id', 1), ('connection_fact.connected', 1)])


async def ensure_lead_tag_indexes(db) -> None:
    """Required identities must fail startup if the tag cutover is inconsistent."""
    await db.outreach_lead_tags.create_index([("workspace_id", 1), ("id", 1)], unique=True)
    await db.outreach_lead_tags.create_index([("workspace_id", 1), ("name_normalized", 1)], unique=True)
    await db.outreach_leads.create_index([("workspace_id", 1), ("tag_ids", 1), ("created_at", -1)])
    await db.outreach_inbox_threads.create_index([("workspace_id", 1), ("lead_id", 1)])


async def create_all_indexes(client: AsyncIOMotorClient | None = None) -> None:
    if client is None:
        client = await get_client()

    import os
    db = client[os.environ["DB_NAME"]]
    # Retention comes first: Mongo's TTL monitor keeps running while unrelated
    # collection indexes build, even when application writers are drained.
    await remove_other_evidence_ttls(db)
    await ensure_mailbox_job_indexes(db)
    await ensure_managed_proxy_indexes(db)
    await ensure_mailbox_sync_indexes(db)
    await ensure_voice_studio_indexes(db)
    await ensure_integration_indexes(db)
    await ensure_voice_artifact_migration_indexes(db)

    # posts
    await _safe_create_index(db.posts, [("id", 1)], unique=True)
    await _safe_create_index(db.posts, [("status", 1), ("scheduled_time", 1)])
    await _safe_create_index(db.posts, [("user_id", 1), ("status", 1), ("created_at", -1)])
    await _safe_create_index(db.posts, [("workspace_id", 1), ("status", 1), ("scheduled_time", 1)])
    await _safe_create_index(db.posts, [("workspace_id", 1), ("user_id", 1), ("status", 1), ("created_at", -1)])
    await _safe_create_index(db.posts, [("workspace_id", 1), ("status", 1), ("updated_at", -1)])
    await _safe_create_index(db.posts, [("deleted_at", 1)], expireAfterSeconds=2592000)  # 30-day TTL
    # Subscription grace period: paused post queries (user_id + status + paused_reason)
    await _safe_create_index(db.posts, [("user_id", 1), ("status", 1), ("paused_reason", 1)])
    await _safe_create_index(db.posts, [("user_id", 1), ("status", 1), ("paused_reason", 1), ("scheduled_time", 1)])

    # users — subscription lifecycle queries (full table scans without these)
    await _safe_create_index(db.users, [("subscription_expires_at", 1), ("subscription_status", 1)])
    await _safe_create_index(db.users, [("subscription_cleanup_date", 1), ("subscription_status", 1)])
    await _safe_create_index(db.users, [("subscription_status", 1), ("subscription_expires_at", 1)])
    await _safe_create_index(db.users, [("status", 1), ("deletion_next_publish_at", 1)])
    # Webhook lookup indexes (Stripe + Razorpay match by customer ID and email)
    await _safe_create_index(db.users, [("user_id", 1)], unique=True)
    await _safe_create_index(db.users, [("firebase_uid", 1)], unique=True, sparse=True)
    await _safe_create_index(db.users, [("email", 1)], unique=True)
    await _safe_create_index(db.users, [("stripe_customer_id", 1)])
    await _safe_create_index(db.users, [("razorpay_customer_id", 1)])

    # notifications
    await _safe_create_index(db.notifications, [("user_id", 1), ("is_read", 1), ("created_at", -1)])
    await _safe_create_index(db.notifications, [("created_at", 1)], expireAfterSeconds=7776000)  # 90-day TTL
    await _safe_create_index(db.notifications, [("dedup_key", 1)], unique=True, sparse=True)

    # social_accounts
    await _safe_create_index(db.social_accounts, [("account_id", 1)], unique=True, sparse=True)
    await _safe_create_index(db.social_accounts, [("id", 1)], unique=True, sparse=True)
    await _safe_create_index(db.social_accounts, [("user_id", 1), ("account_id", 1)], sparse=True)
    await _safe_create_index(db.social_accounts, [("user_id", 1), ("platform", 1), ("is_active", 1)])
    await _safe_create_index(db.social_accounts, [("user_id", 1), ("platform_user_id", 1), ("platform", 1)])

    # payment_transactions
    await _safe_create_index(db.payment_transactions, [("user_id", 1), ("created_at", -1)])

    # user_sessions — TTL 30 days
    await _safe_create_index(db.user_sessions, [("created_at", 1)], expireAfterSeconds=2592000)

    # audit_events indexes are managed exclusively by db/audit_events.py:ensure_indexes()
    # which is called separately from api/main.py lifespan. Do not add audit_events
    # indexes here — the authoritative field is created_at/expires_at, not timestamp.

    # media_assets
    await _safe_create_index(db.media_assets, [("media_id", 1)], unique=True, sparse=True)
    await _safe_create_index(db.media_assets, [("asset_id", 1)], unique=True, sparse=True)
    await _safe_create_index(db.media_assets, [("user_id", 1), ("status", 1)])
    await _safe_create_index(db.media_assets, [("workspace_id", 1), ("status", 1), ("created_at", -1)])
    await _safe_create_index(db.media_assets, [("user_id", 1), ("media_id", 1)])
    await _safe_create_index(db.media_assets, [("post_id", 1)])

    # inbox_messages
    await _safe_create_index(db.inbox_messages, [("id", 1)], unique=True)
    await _safe_create_index(
        db.inbox_messages,
        [("user_id", 1), ("platform", 1), ("account_id", 1), ("type", 1), ("platform_message_id", 1)],
        unique=True,
        sparse=True,
    )
    await _safe_create_index(db.inbox_messages, [("workspace_id", 1), ("user_id", 1), ("received_at", -1)])
    await _safe_create_index(db.inbox_messages, [("workspace_id", 1), ("user_id", 1), ("status", 1), ("received_at", -1)])
    await _safe_create_index(db.inbox_messages, [("workspace_id", 1), ("user_id", 1), ("platform", 1), ("type", 1), ("received_at", -1)])

    # api_keys
    await _safe_create_index(db.api_keys, [("key_hash", 1)], unique=True)
    await _safe_create_index(db.api_keys, [("workspace_id", 1), ("revoked", 1), ("created_at", -1)])

    # youtube_analytics_snapshots
    await _safe_create_index(
        db.youtube_analytics_snapshots,
        [("account_id", 1), ("platform", 1), ("report_type", 1), ("metric", 1), ("window_days", 1), ("as_of_date", -1)],
        unique=True,
    )
    await _safe_create_index(
        db.youtube_analytics_snapshots,
        [("platform", 1), ("report_type", 1), ("window_days", 1), ("last_refreshed_at", -1)],
    )

    # tiktok_analytics_snapshots
    await _safe_create_index(
        db.tiktok_analytics_snapshots,
        [("account_id", 1), ("platform", 1), ("report_type", 1), ("snapshot_date", -1)],
        unique=True,
    )
    await _safe_create_index(
        db.tiktok_analytics_snapshots,
        [("platform", 1), ("report_type", 1), ("captured_at", -1)],
    )
    await _safe_create_index(
        db.tiktok_analytics_snapshots,
        [("user_id", 1), ("platform", 1), ("snapshot_date", -1)],
    )

    # workspace_invites
    await _safe_create_index(db.workspace_invites, [("token", 1)], unique=True)
    await _safe_create_index(db.workspace_invites, [("workspace_id", 1), ("status", 1), ("created_at", -1)])

    # webhook_events (dedup) — compound index on (platform, event_id) because different
    # platforms can share the same event_id value. sparse=True skips docs with null event_id.
    await _safe_create_index(db.webhook_events, [("platform", 1), ("event_id", 1)], unique=True, sparse=True)
    await _safe_create_index(db.webhook_events, [("created_at", 1)], expireAfterSeconds=604800)  # 7-day TTL

    # workspaces / workspace_members
    await _safe_create_index(db.workspaces, [("workspace_id", 1)], unique=True)
    await _safe_create_index(db.workspaces, [("owner_id", 1)])
    await _safe_create_index(
        db.workspaces,
        [("owner_id", 1), ("workspace_type", 1)],
        unique=True,
        partialFilterExpression={"workspace_type": "personal"},
    )
    await _safe_create_index(db.workspace_members, [("workspace_id", 1), ("user_id", 1)], unique=True)

    # posting_sets
    await _safe_create_index(db.posting_sets, [("id", 1)], unique=True)
    await _safe_create_index(db.posting_sets, [("workspace_id", 1), ("created_at", 1)])
    await _safe_create_index(db.posting_sets, [("user_id", 1), ("created_at", 1)])

    # LinkedIn outreach analytics, swipe files, and unified inbox
    await _safe_create_index(db.outreach_entitlements, [("workspace_id", 1)], unique=True)
    await _safe_create_index(db.outreach_entitlements, [("status", 1), ("paid_through", 1)])
    await _safe_create_index(db.outreach_access_requests, [("workspace_id", 1)], unique=True)
    await _safe_create_index(db.outreach_sender_slots, [("workspace_id", 1), ("sender_id", 1)], unique=True)
    await _safe_create_index(db.outreach_proxy_leases, [("workspace_id", 1), ("sender_id", 1)],
                             unique=True, partialFilterExpression={"sender_id": {"$type": "string"}})
    await _safe_create_index(db.outreach_proxy_inventory, [("provider", 1), ("country_code", 1), ("status", 1), ("expires_at", 1)])
    await _safe_create_index(db.outreach_connection_jobs, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_connection_jobs, [("status", 1), ("created_at", 1)])
    await _safe_create_index(db.outreach_connection_jobs, [("status", 1), ("next_verification_due_at", 1)])
    await _safe_create_index(db.outreach_connection_jobs, [("status", 1), ("custody_expires_at", 1), ("next_custody_check_at", 1)])
    await _safe_create_index(db.outreach_connection_jobs, [("created_at", 1)], expireAfterSeconds=86400)
    await _safe_create_index(db.outreach_mailboxes, [("workspace_id", 1), ("sender_account_id", 1)], unique=True)
    await _safe_create_index(db.outreach_mailboxes, [("status", 1), ("last_sync_at", 1)])
    await _safe_create_index(db.outreach_mailbox_connection_jobs, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_mailbox_oauth_states, [("expires_at", 1)], expireAfterSeconds=0)
    await _safe_create_index(db.outreach_hunter_credentials, [("workspace_id", 1)], unique=True)
    await _safe_create_index(db.outreach_email_operations, [("workspace_id", 1), ("sender_account_id", 1), ("recipient", 1), ("accepted_at", -1)])
    await _safe_create_index(db.outreach_email_inbound_events, [("workspace_id", 1), ("sender_account_id", 1), ("provider_message_id", 1)], unique=True)
    await _safe_create_index(db.outreach_email_suppressions, [("workspace_id", 1), ("email", 1)], unique=True)
    # Persistent workspace ordering guard: no TTL or periodic reset.
    await _safe_create_index(db.outreach_suppression_guards, [("workspace_id", 1)], unique=True)
    await _safe_create_index(db.outreach_erasure_requests, [("workspace_id", 1)], unique=True)
    await _safe_create_index(db.outreach_erasure_holds, [("workspace_id", 1), ("kind", 1)])
    await _safe_create_index(db.outreach_accounts, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_accounts, [("status", 1), ("priority_sync_due_at", 1)])
    await _safe_create_index(db.outreach_tasks, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_tasks, [("workspace_id", 1), ("status", 1), ("updated_at", 1), ("id", 1)])
    await _safe_create_index(db.outreach_sequence_jobs, [("status", 1), ("next_due_at", 1), ("next_publish_at", 1)])
    await _safe_create_index(db.outreach_sequence_jobs, [("status", 1), ("claim_expires_at", 1)])
    await _safe_create_index(db.outreach_campaigns, [("status", 1), ("next_sequence_scan_at", 1), ("id", 1)])
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("campaign_id", 1), ("execution_state", 1), ("next_sequence_scan_at", 1)])
    await _safe_create_index(db.outreach_email_discoveries, [("workspace_id", 1), ("lead_id", 1), ("completed_at", -1)])
    await _safe_create_index(db.outreach_email_discoveries, [("status", 1), ("created_at", 1)])
    await _safe_create_index(db.outreach_provider_budgets, [("workspace_id", 1), ("source", 1), ("day", 1)], unique=True)
    await _safe_create_index(db.outreach_intents, [("workspace_id", 1), ("legacy_operation_id", 1)])
    await _safe_create_index(db.outreach_intents, [("status", 1), ("next_action_due_at", 1)])
    await _safe_create_index(db.outreach_intents, [("status", 1), ("claim_expires_at", 1)])
    await _safe_create_index(db.outreach_intents, [("status", 1), ("projection_reconciled", 1)])
    await _safe_create_index(db.outreach_intents, [("next_recovery_due_at", 1), ("_id", 1)])
    await _safe_create_index(db.outreach_execution_permissions, [("workspace_id", 1), ("sender_id", 1)])
    await _safe_create_index(db.outreach_physical_requests, [("workspace_id", 1), ("sender_id", 1), ("status", 1)])
    await _safe_create_index(db.outreach_physical_requests, [("status", 1), ("started_at", 1)])
    await _safe_create_index(db.outreach_content_approvals, [("workspace_id", 1), ("status", 1), ("updated_at", -1)])
    await _safe_create_index(db.outreach_manual_actions, [("status", 1), ("next_due_at", 1)])
    await _safe_create_index(db.outreach_manual_actions, [("status", 1), ("claim_expires_at", 1)])
    await _safe_create_index(db.outreach_manual_actions, [("next_publish_at", 1), ("created_at", 1)])
    await _safe_create_index(db.outreach_manual_actions, [("next_recovery_due_at", 1), ("_id", 1)])
    await _safe_create_index(db.outreach_manual_actions, [("workspace_id", 1), ("source", 1), ("target_id", 1)], unique=True,
        name="manual_active_target_v2", partialFilterExpression={"status": {"$in": ["awaiting_approval", "queued", "preparing", "in_flight", "unknown_outcome", "projection_pending", "resolving"]}})
    await _safe_create_index(db.outreach_credential_migrations, [("workspace_id", 1), ("sender_id", 1), ("at", -1)])
    await _safe_create_index(db.outreach_credential_migrations, [("workspace_id", 1), ("proxy_id", 1), ("at", -1)])
    await _safe_create_index(db.outreach_credential_migrations, [("workspace_id", 1), ("kind", 1), ("at", -1)])
    await _safe_create_index(db.outreach_voice_artifacts, [("expires_at", 1)], expireAfterSeconds=0)
    await _safe_create_index(db.outreach_voice_preparation_jobs, [("status", 1), ("next_publish_at", 1)])
    await _safe_create_index(db.outreach_voice_preparation_jobs, [("status", 1), ("claim_expires_at", 1)])
    await _safe_create_index(db.outreach_voice_preparation_jobs, [("next_recovery_due_at", 1), ("_id", 1)])
    await _safe_create_index(db.outreach_voice_preparation_jobs, [("workspace_id", 1), ("status", 1), ("updated_at", -1)])
    await _safe_create_index(db.outreach_import_jobs, [("status", 1), ("next_page_due_at", 1)])
    await _safe_create_index(db.outreach_sequence_versions, [("workspace_id", 1), ("campaign_id", 1), ("version", -1)])
    await _safe_create_index(db.outreach_tasks, [("workspace_id", 1), ("campaign_id", 1), ("task_type", 1), ("status", 1), ("updated_at", -1)])
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("campaign_id", 1), ("pipeline_stage", 1)])
    await ensure_lead_tag_indexes(db)
    await ensure_lead_list_indexes(db)
    await ensure_connection_wait_indexes(db)
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("campaign_id", 1), ("accepted_at", -1)])
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("campaign_id", 1), ("replied_at", -1)])
    await _safe_create_index(db.outreach_leads, [("campaign_id", 1), ("current_node_id", 1)])
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("identifiers.normalized_url", 1)], sparse=True)
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("identifiers.vanity_name", 1)], sparse=True)
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("identifiers.member_urn", 1)], sparse=True)
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("identifiers.sales_lead_urn", 1)], sparse=True)
    await _safe_create_index(db.outreach_leads, [("workspace_id", 1), ("identifiers.email", 1)], sparse=True)
    await _safe_create_index(db.outreach_do_not_contact, [("workspace_id", 1), ("linkedin_url", 1)])
    await _safe_create_index(db.outreach_do_not_contact, [("workspace_id", 1), ("identifiers.normalized_url", 1)], sparse=True)
    await _safe_create_index(db.outreach_do_not_contact, [("workspace_id", 1), ("identifiers.vanity_name", 1)], sparse=True)
    await _safe_create_index(db.outreach_do_not_contact, [("workspace_id", 1), ("identifiers.member_urn", 1)], sparse=True)
    await _safe_create_index(db.outreach_do_not_contact, [("workspace_id", 1), ("identifiers.sales_lead_urn", 1)], sparse=True)
    await _safe_create_index(db.outreach_do_not_contact, [("workspace_id", 1), ("identifiers.email", 1)], sparse=True)
    await _safe_create_index(db.outreach_withdrawn_invites, [("workspace_id", 1), ("account_id", 1), ("withdrawn_at", -1)])
    await _safe_create_index(db.outreach_withdrawn_invites, [("workspace_id", 1), ("member_urn", 1)], sparse=True)
    await _safe_create_index(db.outreach_inbox_threads, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_inbox_threads, [("workspace_id", 1), ("account_id", 1), ("lead_urn", 1)])
    await _safe_create_index(db.outreach_inbox_threads, [("workspace_id", 1), ("last_message_at", -1)])
    await _safe_create_index(db.outreach_inbox_jobs, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_inbox_jobs, [("workspace_id", 1), ("thread_id", 1), ("kind", 1), ("status", 1)])
    await _safe_create_index(db.outreach_inbox_reminders, [("workspace_id", 1), ("thread_id", 1), ("remind_at", 1)])
    await _safe_create_index(db.outreach_swipe_files, [("workspace_id", 1), ("created_at", -1)])
    await _safe_create_index(db.outreach_engage_posts, [("workspace_id", 1), ("list_id", 1), ("liked_at", -1)])
    await _safe_create_index(db.outreach_engage_posts, [("workspace_id", 1), ("list_id", 1), ("commented_at", -1)])
    await _safe_create_index(db.outreach_engage_drafts, [("workspace_id", 1), ("list_id", 1), ("status", 1), ("created_at", -1)])
    await _safe_create_index(db.outreach_event_outbox, [("workspace_id", 1), ("dedupe_key", 1)], unique=True)
    await _safe_create_index(db.outreach_event_outbox, [("status", 1), ("occurred_at", 1)])
    await _safe_create_index(db.outreach_event_outbox, [("lease_id", 1), ("leased_until", 1)])
    await _safe_create_index(db.outreach_webhooks, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_webhooks, [("workspace_id", 1), ("status", 1)])
    await _safe_create_index(db.outreach_webhook_deliveries, [("workspace_id", 1), ("event_id", 1), ("destination_type", 1), ("destination_id", 1)], unique=True)
    await _safe_create_index(db.outreach_webhook_deliveries, [("status", 1), ("next_attempt_at", 1)])
    await _safe_create_index(db.outreach_webhook_deliveries, [("workspace_id", 1), ("status", 1), ("created_at", -1)])
    await _safe_create_index(db.outreach_webhook_deliveries, [("destination_id", 1), ("status", 1), ("created_at", -1)])
    await _safe_create_index(db.outreach_webhook_deliveries, [("created_at", 1)])
    await _safe_create_index(db.outreach_api_keys, [("workspace_id", 1), ("id", 1)], unique=True)
    await _safe_create_index(db.outreach_api_keys, [("key_hash", 1)], unique=True)
    await _safe_create_index(db.outreach_api_keys, [("workspace_id", 1), ("revoked_at", 1)])
    await _safe_create_index(db.outreach_integrations, [("workspace_id", 1), ("provider", 1)], unique=True)
    await _safe_create_index(db.outreach_external_mappings,
                             [("workspace_id", 1), ("provider", 1), ("external_account_id", 1), ("object_type", 1), ("internal_id", 1)],
                             unique=True)

    # Search Import Jobs & Staged Leads
    await _safe_create_index(
        db.outreach_import_jobs,
        [("sender_account_id", 1)],
        unique=True,
        partialFilterExpression={"status": {"$in": ["queued", "crawling"]}},
    )
    await _safe_create_index(db.outreach_import_jobs, [("workspace_id", 1), ("campaign_id", 1)])
    await _safe_create_index(db.outreach_import_jobs, [("status", 1), ("heartbeat_at", 1)])
    await _safe_create_index(db.outreach_leads, [("import_job_id", 1), ("execution_state", 1)])
    await _safe_create_index(db.outreach_leads, [("staged_at", 1)], expireAfterSeconds=30 * 86400)

    logger.info("All MongoDB indexes created successfully")


if __name__ == "__main__":
    asyncio.run(create_all_indexes())
