# MongoDB Migration Checklist

Copy this checklist every time you change the MongoDB schema.
Post it in the engineering Slack channel before deploying.

---

## Pre-Migration Checklist

Answer YES to both questions before writing any migration code:

- [ ] **Does OLD application code work with the NEW schema?**
  - Add the new field as Optional with a default value
  - Old code that doesn't write this field should not crash
  - Old code that reads this field should handle None gracefully

- [ ] **Does NEW application code work with the OLD schema?**
  - New code reading the new field gets None/default on old documents
  - New code must handle the absence of the new field gracefully

If BOTH are YES: safe to deploy simultaneously.
If EITHER is NO: use the expand-contract pattern below.

---

## Expand-Contract Pattern (3 phases)

### Phase 1 — Expand (add the field, keep old code working)
```python
# Deploy this first. Old and new documents coexist safely.
# New writes: include the new field
# Old writes: field is missing (None when read)
# Reading: always use .get('new_field', default)
```
Duration: 1 deployment cycle

### Phase 2 — Backfill (migrate old documents in batches)
```python
# Run via Celery Beat task, off-peak hours
# See: celery_tasks/migrations.py
# Track progress: CLAUDE.md "Schema Changes In Progress" section
# Always test on production-sized Atlas snapshot first
```
Batch size: 10,000 documents
Sleep between batches: 100ms
Monitor: migration:{name}:progress in Redis

### Phase 3 — Contract (make field required, remove fallback)
```python
# Only after Phase 2 is 100% complete and verified
# Remove the Optional[] type hint
# Remove .get() fallback code
# Add the index if needed
```

---

## Current Migrations

| Name | Status | Started | Completed |
|------|--------|---------|-----------|
| add_schema_version_v1 | pending | — | — |
| add_workspace_id | not started | — | — |

---

## Migration Script Template

```python
# celery_tasks/migrations.py
from celery_app.celery_instance import celery_app
import redis.asyncio as aioredis
import asyncio

@celery_app.task
def run_migration(migration_name: str, batch_size: int = 10000):
    """
    Expand-contract batch migration.
    Always test on Atlas snapshot before running on production.
    """
    asyncio.run(_run_migration_async(migration_name, batch_size))

async def _run_migration_async(migration_name: str, batch_size: int):
    from db.motor_client import get_db
    from db.redis_client import get_redis

    db = await get_db()
    redis = await get_redis()
    progress_key = f"migration:{migration_name}:progress"

    # Count before
    total = await db.posts.count_documents({})
    processed = 0

    async for batch_start in range(0, total, batch_size):
        # Fetch batch of documents missing the new field
        cursor = db.posts.find(
            {"new_field": {"$exists": False}},
            projection={"_id": 1}
        ).skip(batch_start).limit(batch_size)

        ids = [doc["_id"] async for doc in cursor]
        if not ids:
            break

        # Update batch
        result = await db.posts.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"new_field": None, "schema_version": 2}}
        )
        processed += result.modified_count

        # Track progress
        await redis.set(progress_key, str(processed), ex=86400)

        # Breathe — don't hammer Atlas
        await asyncio.sleep(0.1)

    print(f"Migration {migration_name}: {processed}/{total} documents updated")
```

---

## Zero-Downtime Verification

After every migration phase, verify:

```bash
# Count documents with and without the new field
mongo "mongodb+srv://..." --eval "
  db.posts.aggregate([
    { \$group: {
      _id: { has_field: { \$cond: [{ \$ifNull: ['\$new_field', false] }, 'yes', 'no'] } },
      count: { \$sum: 1 }
    }}
  ])
"
```

Expected after Phase 2: all documents should show `has_field: yes`.
