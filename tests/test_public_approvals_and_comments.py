from datetime import datetime, timezone
import pytest
from bson import ObjectId
from fastapi import HTTPException
from api.routes.posts import (
    AddCommentBody,
    PublicDecisionBody,
    ShareReviewLinkBody,
    add_post_comment,
    generate_shareable_review_link,
    get_public_approval_feed,
    submit_public_client_decision,
    toggle_post_comment_resolve,
)


class _FakePostsCollection:
    def __init__(self, posts=None):
        self.posts = {p["id"]: p for p in (posts or [])}

    async def find_one(self, query):
        post_id = query.get("id")
        return self.posts.get(post_id)

    async def update_one(self, query, update):
        post_id = query.get("id")
        if post_id in self.posts:
            post = self.posts[post_id]
            if "$set" in update:
                post.update(update["$set"])
            if "$push" in update:
                for k, v in update["$push"].items():
                    post.setdefault(k, []).append(v)
        return None

    def find(self, query):
        class _Cursor:
            def __init__(self, items):
                self.items = list(items)

            def sort(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def __aiter__(self):
                self._iter = iter(self.items)
                return self

            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration

        return _Cursor(self.posts.values())


class _FakeApprovalLinksCollection:
    def __init__(self):
        self.links = {}

    async def insert_one(self, doc):
        self.links[doc["token"]] = doc
        return doc

    async def find_one(self, query):
        return self.links.get(query.get("token"))


class _FakeUsersCollection:
    async def find_one(self, query):
        return {"user_id": "u1", "name": "Alice Agent"}


class _FakeDB:
    def __init__(self, posts=None):
        self.posts = _FakePostsCollection(posts or [])
        self.approval_links = _FakeApprovalLinksCollection()
        self.users = _FakeUsersCollection()
        self.approval_activity = _FakeApprovalLinksCollection()


@pytest.mark.asyncio
async def test_comments_add_and_resolve():
    post_id = "post_123"
    post_doc = {
        "id": post_id,
        "workspace_id": "ws_1",
        "user_id": "u1",
        "content": "Draft post",
        "comments": [],
    }
    db = _FakeDB([post_doc])
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}

    # Add comment
    req = AddCommentBody(text="Please swap the first image")
    comment = await add_post_comment(post_id, req, current_user=user, db=db)
    assert comment["text"] == "Please swap the first image"
    assert comment["author_name"] == "Alice Agent"
    assert comment["resolved"] is False

    # Resolve comment
    toggle_res = await toggle_post_comment_resolve(post_id, comment["id"], current_user=user, db=db)
    assert toggle_res["resolved"] is True


@pytest.mark.asyncio
async def test_magic_review_link_flow():
    post_id = "post_999"
    post_doc = {
        "id": post_id,
        "workspace_id": "ws_1",
        "user_id": "u1",
        "status": "pending_approval",
        "content": "Exciting product launch!",
        "platforms": ["twitter", "linkedin"],
        "media_urls": [],
        "comments": [],
    }
    db = _FakeDB([post_doc])
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}

    # 1. Generate magic link
    link_info = await generate_shareable_review_link(ShareReviewLinkBody(expires_in_days=3), current_user=user, db=db)
    token = link_info["token"]
    assert token.startswith("rev_")

    # 2. Public client views feed
    feed = await get_public_approval_feed(token, db=db)
    assert len(feed["posts"]) == 1
    assert feed["posts"][0]["id"] == post_id

    # 3. Public client submits approval decision
    decision_req = PublicDecisionBody(
        post_id=post_id,
        decision="approve",
        reviewer_name="Sarah CEO",
    )
    dec_res = await submit_public_client_decision(token, decision_req, db=db)
    assert dec_res["ok"] is True
    assert dec_res["status"] == "scheduled"
    assert db.posts.posts[post_id]["status"] == "scheduled"
