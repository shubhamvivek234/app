"""
Zero-downtime MongoDB migration runner.
Tracks applied migrations in the `migrations_log` collection.
Usage:
    python -m migrations.runner up      # Apply all pending migrations
    python -m migrations.runner down    # Rollback last migration
    python -m migrations.runner status  # Show migration status
"""
import asyncio
import importlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent.parent.resolve()
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

MIGRATIONS_DIR = Path(__file__).parent


async def get_db():
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]


async def get_applied_migrations(db) -> list[str]:
    docs = await db.migrations_log.find(
        {"status": "success"}, {"migration_name": 1}
    ).sort("applied_at", 1).to_list(None)
    return [d["migration_name"] for d in docs]


async def get_all_migration_files() -> list[str]:
    files = sorted(
        f.stem for f in MIGRATIONS_DIR.glob("*.py")
        if f.stem not in ("__init__", "runner") and f.stem[0].isdigit()
    )
    return files


async def run_migration(db, name: str, direction: str = "up"):
    module = importlib.import_module(f"migrations.{name}")
    fn = getattr(module, direction, None)
    if not fn:
        print(f"  ⚠️  No {direction}() function in {name}, skipping")
        return

    start = time.time()
    try:
        await fn(db)
        duration_ms = int((time.time() - start) * 1000)
        await db.migrations_log.insert_one({
            "migration_name": name,
            "direction": direction,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "status": "success",
        })
        print(f"  ✅ {name} ({direction}) — {duration_ms}ms")
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        await db.migrations_log.insert_one({
            "migration_name": name,
            "direction": direction,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "status": "failed",
            "error": str(e),
        })
        print(f"  ❌ {name} ({direction}) — FAILED: {e}")
        raise


async def cmd_up(db):
    all_migrations = await get_all_migration_files()
    applied = await get_applied_migrations(db)
    pending = [m for m in all_migrations if m not in applied]

    if not pending:
        print("✅ All migrations are up to date.")
        return

    print(f"Applying {len(pending)} migration(s)...")
    for name in pending:
        await run_migration(db, name, "up")
    print("Done.")


async def cmd_down(db):
    applied = await get_applied_migrations(db)
    if not applied:
        print("No migrations to roll back.")
        return
    last = applied[-1]
    print(f"Rolling back: {last}")
    await run_migration(db, last, "down")
    # Mark as rolled back
    await db.migrations_log.update_one(
        {"migration_name": last, "direction": "up", "status": "success"},
        {"$set": {"status": "rolled_back"}}
    )
    print("Done.")


async def cmd_status(db):
    all_migrations = await get_all_migration_files()
    applied = await get_applied_migrations(db)
    print(f"\n{'Migration':<50} {'Status':<15}")
    print("-" * 65)
    for m in all_migrations:
        status = "✅ applied" if m in applied else "⏳ pending"
        print(f"{m:<50} {status:<15}")
    print()


async def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    db = await get_db()

    if command == "up":
        await cmd_up(db)
    elif command == "down":
        await cmd_down(db)
    elif command == "status":
        await cmd_status(db)
    else:
        print(f"Unknown command: {command}. Use: up | down | status")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
