"""
Migration 004: Create workspace collection with indexes.
Stage 5.9 — Workspace Model.
"""
from pymongo import ASCENDING


async def up(db):
    # Create workspace indexes
    await db.workspaces.create_index(
        [("owner_id", ASCENDING)],
        name="workspaces_owner",
        background=True,
    )
    await db.workspaces.create_index(
        [("slug", ASCENDING)],
        name="workspaces_slug",
        unique=True,
        sparse=True,
        background=True,
    )
    await db.workspaces.create_index(
        [("members.user_id", ASCENDING)],
        name="workspaces_member_user",
        background=True,
    )
    # Workspace invites indexes
    await db.workspace_invites.create_index(
        [("token", ASCENDING)],
        name="invites_token",
        unique=True,
        background=True,
    )
    await db.workspace_invites.create_index(
        [("invited_email", ASCENDING)],
        name="invites_email",
        background=True,
    )
    # Create a personal workspace for each existing user
    users = await db.users.find({}, {"user_id": 1, "name": 1, "email": 1}).to_list(None)
    created = 0
    for user in users:
        uid = user["user_id"]
        # Check if workspace already exists for this user
        existing = await db.workspaces.find_one({"owner_id": uid})
        if not existing:
            import uuid, re
            from datetime import datetime, timezone
            slug_base = re.sub(r"[^a-z0-9]", "-", (user.get("name") or "workspace").lower())[:20]
            slug = f"{slug_base}-{uid[:8]}"
            workspace = {
                "id": str(uuid.uuid4()),
                "name": f"{user.get('name', 'My')} Workspace",
                "slug": slug,
                "owner_id": uid,
                "members": [{"user_id": uid, "email": user.get("email",""), "name": user.get("name",""), "role": "owner", "joined_at": datetime.now(timezone.utc).isoformat()}],
                "plan": "starter",
                "subscription_status": "free",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "settings": {},
                "max_members": 1,
                "max_accounts": 5,
                "max_scheduled_posts": 30,
            }
            await db.workspaces.insert_one(workspace)
            created += 1
    print(f"  Created {created} personal workspaces")
    print("  ✅ Workspace collection + indexes ready")


async def down(db):
    await db.workspaces.drop()
    await db.workspace_invites.drop()
    print("  Dropped workspaces and workspace_invites collections")
