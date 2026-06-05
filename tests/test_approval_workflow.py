from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from api.models.post import PostStatus
from api.routes import posts as posts_route


def _matches_value(value, expected):
    if isinstance(expected, dict):
        if "$exists" in expected and (value is not None) != bool(expected["$exists"]):
            return False
        if "$ne" in expected and value == expected["$ne"]:
            return False
        if "$gt" in expected and not (value is not None and value > expected["$gt"]):
            return False
        if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
            return False
        if "$lte" in expected and not (value is not None and value <= expected["$lte"]):
            return False
        if "$in" in expected and value not in expected["$in"]:
            return False
        return True
    return value == expected


def _matches_query(doc, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_matches_query(doc, branch) for branch in expected):
                return False
            continue
        if not _matches_value(doc.get(key), expected):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]

    def sort(self, spec, direction=None):
        docs = list(self._docs)
        if isinstance(spec, list):
            for key, sort_direction in reversed(spec):
                docs.sort(
                    key=lambda doc: doc.get(key) or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=sort_direction < 0,
                )
        else:
            docs.sort(
                key=lambda doc: doc.get(spec) or datetime.min.replace(tzinfo=timezone.utc),
                reverse=(direction or -1) < 0,
            )
        self._docs = docs
        return self

    def limit(self, count):
        self._docs = self._docs[:count]
        return self

    async def to_list(self, length=None):
        if length is None:
            return list(self._docs)
        return list(self._docs[:length])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query=None, _projection=None):
        filtered = [dict(doc) for doc in self.docs if _matches_query(doc, query or {})]
        return FakeCursor(filtered)

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches_query(doc, query):
                result = dict(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None

    async def find_one_and_update(self, query, update, return_document=True, projection=None):
        for doc in self.docs:
            if _matches_query(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                for key in update.get("$unset", {}):
                    doc.pop(key, None)
                for key, value in update.get("$push", {}).items():
                    current = list(doc.get(key) or [])
                    current.append(value)
                    doc[key] = current
                result = dict(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None


class FakeDB:
    def __init__(self, *, posts=None, users=None):
        self.posts = FakeCollection(posts or [])
        self.users = FakeCollection(users or [])


def _post(
    post_id,
    *,
    user_id,
    workspace_id,
    status,
    content="Post body",
    scheduled_time=None,
    rejection_reason=None,
    rejected_at=None,
    created_at=None,
    updated_at=None,
):
    created_at = created_at or datetime.now(timezone.utc) - timedelta(days=1)
    updated_at = updated_at or created_at
    doc = {
        "id": post_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "status": status,
        "content": content,
        "platforms": ["instagram"],
        "post_type": "text",
        "media_ids": [],
        "media_urls": [],
        "thumbnail_urls": [],
        "created_at": created_at,
        "updated_at": updated_at,
        "scheduled_time": scheduled_time,
        "status_history": [],
    }
    if rejection_reason is not None:
        doc["rejection_reason"] = rejection_reason
    if rejected_at is not None:
        doc["rejected_at"] = rejected_at
    return doc


async def _identity_hydrate(_db, docs):
    return [dict(doc) for doc in docs]


@pytest.mark.asyncio
async def test_list_approval_queue_buckets_workspace_posts_and_preserves_rejection_metadata(monkeypatch):
    now = datetime.now(timezone.utc)
    db = FakeDB(
        posts=[
            _post(
                "awaiting-1",
                user_id="author-1",
                workspace_id="ws-1",
                status=PostStatus.PENDING_APPROVAL,
                scheduled_time=now + timedelta(hours=3),
                updated_at=now - timedelta(minutes=10),
            ),
            _post(
                "changes-1",
                user_id="author-2",
                workspace_id="ws-1",
                status=PostStatus.DRAFT,
                rejection_reason="Needs a clearer CTA",
                rejected_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=2),
            ),
            _post(
                "expired-1",
                user_id="author-3",
                workspace_id="ws-1",
                status=PostStatus.PENDING_APPROVAL,
                scheduled_time=now - timedelta(minutes=30),
                updated_at=now - timedelta(minutes=45),
            ),
            _post(
                "blank-reason",
                user_id="author-4",
                workspace_id="ws-1",
                status=PostStatus.DRAFT,
                rejection_reason="   ",
                rejected_at=now - timedelta(hours=1),
            ),
            _post(
                "other-workspace",
                user_id="author-5",
                workspace_id="ws-2",
                status=PostStatus.PENDING_APPROVAL,
                scheduled_time=now + timedelta(hours=1),
            ),
        ],
        users=[
            {"user_id": "author-1", "display_name": "Author One", "email": "one@example.com"},
            {"user_id": "author-2", "display_name": "Author Two", "email": "two@example.com"},
            {"user_id": "author-3", "display_name": "Author Three", "email": "three@example.com"},
        ],
    )
    monkeypatch.setattr(posts_route, "_hydrate_post_card_fields_for_docs", _identity_hydrate)

    result = await posts_route.list_approval_queue(
        current_user={"user_id": "reviewer-1", "default_workspace_id": "ws-1"},
        db=db,
        limit=10,
    )

    assert result["summary"] == {
        "awaiting": 1,
        "changes_requested": 1,
        "expired": 1,
    }
    assert result["awaiting"][0]["id"] == "awaiting-1"
    assert result["awaiting"][0]["creator_display_name"] == "Author One"
    assert result["changes_requested"][0]["id"] == "changes-1"
    assert result["changes_requested"][0]["rejection_reason"] == "Needs a clearer CTA"
    assert result["changes_requested"][0]["rejection_note"] == "Needs a clearer CTA"
    assert result["expired"][0]["id"] == "expired-1"


@pytest.mark.asyncio
async def test_reject_resubmit_submit_review_and_return_to_draft_update_post_statuses():
    now = datetime.now(timezone.utc)
    db = FakeDB(
        posts=[
            _post(
                "pending-1",
                user_id="author-1",
                workspace_id="ws-1",
                status=PostStatus.PENDING_APPROVAL,
                scheduled_time=now + timedelta(hours=2),
            ),
            _post(
                "draft-1",
                user_id="author-1",
                workspace_id="ws-1",
                status=PostStatus.DRAFT,
            ),
            _post(
                "expired-1",
                user_id="author-2",
                workspace_id="ws-1",
                status=PostStatus.PENDING_APPROVAL,
                scheduled_time=now - timedelta(minutes=15),
            ),
        ]
    )

    rejected = await posts_route.reject_post(
        "pending-1",
        posts_route.ApprovalDecisionBody(reason="Tighten the caption and CTA."),
        {"user_id": "reviewer-1", "default_workspace_id": "ws-1"},
        db,
    )
    assert rejected["status"] == PostStatus.DRAFT
    rejected_doc = await db.posts.find_one({"id": "pending-1"})
    assert rejected_doc["status"] == PostStatus.DRAFT
    assert rejected_doc["rejection_reason"] == "Tighten the caption and CTA."

    resubmitted = await posts_route.resubmit_post(
        "pending-1",
        posts_route.ApprovalResubmitBody(content="Updated copy with stronger CTA."),
        {"user_id": "author-1", "default_workspace_id": "ws-1"},
        db,
    )
    assert resubmitted["status"] == PostStatus.PENDING_APPROVAL
    resubmitted_doc = await db.posts.find_one({"id": "pending-1"})
    assert resubmitted_doc["status"] == PostStatus.PENDING_APPROVAL
    assert resubmitted_doc["content"] == "Updated copy with stronger CTA."
    assert "rejection_reason" not in resubmitted_doc
    assert resubmitted_doc["status_history"][-1]["status"] == PostStatus.PENDING_APPROVAL

    submitted = await posts_route.submit_post_for_review(
        "draft-1",
        posts_route.ApprovalResubmitBody(),
        {"user_id": "author-1", "default_workspace_id": "ws-1"},
        db,
    )
    assert submitted["status"] == PostStatus.PENDING_APPROVAL
    submitted_doc = await db.posts.find_one({"id": "draft-1"})
    assert submitted_doc["status"] == PostStatus.PENDING_APPROVAL

    returned = await posts_route.return_post_to_draft(
        "expired-1",
        {"user_id": "reviewer-1", "default_workspace_id": "ws-1"},
        db,
    )
    assert returned["status"] == PostStatus.DRAFT
    returned_doc = await db.posts.find_one({"id": "expired-1"})
    assert returned_doc["status"] == PostStatus.DRAFT
    assert returned_doc["status_history"][-1]["reason"] == "Returned to draft after approval window expired"


@pytest.mark.asyncio
async def test_approve_post_blocks_expired_pending_items_and_schedules_future_items():
    now = datetime.now(timezone.utc)
    db = FakeDB(
        posts=[
            _post(
                "future-1",
                user_id="author-1",
                workspace_id="ws-1",
                status=PostStatus.PENDING_APPROVAL,
                scheduled_time=now + timedelta(hours=4),
            ),
            _post(
                "expired-1",
                user_id="author-1",
                workspace_id="ws-1",
                status=PostStatus.PENDING_APPROVAL,
                scheduled_time=now - timedelta(minutes=10),
            ),
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await posts_route.approve_post(
            "expired-1",
            {"user_id": "reviewer-1", "default_workspace_id": "ws-1", "email_verified": True},
            db,
        )
    assert exc.value.status_code == 409

    approved = await posts_route.approve_post(
        "future-1",
        {"user_id": "reviewer-1", "default_workspace_id": "ws-1", "email_verified": True},
        db,
    )
    assert approved == {
        "approved": True,
        "post_id": "future-1",
        "status": PostStatus.SCHEDULED,
    }
    approved_doc = await db.posts.find_one({"id": "future-1"})
    assert approved_doc["status"] == PostStatus.SCHEDULED
    assert approved_doc["approved_by"] == "reviewer-1"
    assert approved_doc["status_history"][-1]["status"] == PostStatus.SCHEDULED
