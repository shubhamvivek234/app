"""
Unit tests for Cluster B (Monetization Engine) features:
- Broadcasts API: CRUD, stats, templates, sending, test-send
- WhatsApp Outreach: personalized click-to-chat link generation
- AI Broadcast Copywriting: /ai/broadcast-draft
- Smart Bio Payment Link: /bio-pages/payment-link
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from starlette.requests import Request

from api.routes.broadcasts import (
    BroadcastCreate,
    BroadcastUpdate,
    EmailPreviewRequest,
    WhatsAppLinksRequest,
    list_broadcasts,
    get_broadcast_stats,
    list_templates,
    get_broadcast,
    create_broadcast,
    update_broadcast,
    send_broadcast,
    send_test_email,
    delete_broadcast,
    generate_whatsapp_outreach_links,
)
from api.routes.ai import (
    BroadcastDraftRequest,
    generate_broadcast_draft,
)
from api.routes.bio_pages import (
    PaymentLinkRequest,
    create_or_format_payment_link,
)


class FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, length):
        self.items = self.items[:length]
        return self

    def skip(self, offset):
        self.items = self.items[offset:]
        return self

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self, initial=None):
        self.items = list(initial or [])

    def find(self, query=None, *args, **kwargs):
        matched = []
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(item)
        return FakeCursor(matched)

    async def find_one(self, query, *args, **kwargs):
        for item in self.items:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                return item
        return None

    async def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.items.append(doc)
        return doc

    async def update_one(self, query, update, *args, **kwargs):
        target = await self.find_one(query)
        if target:
            if "$set" in update:
                target.update(update["$set"])
            return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def delete_one(self, query):
        target = await self.find_one(query)
        if target:
            self.items.remove(target)
            return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()

    async def count_documents(self, query=None):
        if not query:
            return len(self.items)
        matched = 0
        for item in self.items:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                matched += 1
        return matched

    def aggregate(self, pipeline):
        match_stage = pipeline[0].get("$match", {})
        matched_items = [
            item for item in self.items
            if all(item.get(k) == v for k, v in match_stage.items())
        ]
        total_delivered = sum(i.get("delivered_count", 0) for i in matched_items)
        total_recipients = sum(i.get("recipients_count", 0) for i in matched_items)
        total_opens = sum(i.get("open_count", 0) for i in matched_items)
        result = [{
            "_id": None,
            "total_delivered": total_delivered,
            "total_recipients": total_recipients,
            "total_opens": total_opens,
        }]
        return FakeCursor(result)


class FakeDB:
    def __init__(self):
        self.broadcasts = FakeCollection()
        self.workspace_leads = FakeCollection()
        self.bio_pages = FakeCollection()


@pytest.fixture
def fake_db():
    db = FakeDB()
    now = datetime.now(timezone.utc)
    # Seed 3 sample leads
    db.workspace_leads.items = [
        {
            "_id": ObjectId(),
            "workspace_id": "ws_123",
            "email": "sarah@example.com",
            "name": "Sarah Connor",
            "phone": "+14155552671",
            "tag": "subscriber",
            "created_at": now,
        },
        {
            "_id": ObjectId(),
            "workspace_id": "ws_123",
            "email": "john@example.com",
            "name": "John Doe",
            "phone": "+14155559876",
            "tag": "vip",
            "created_at": now,
        },
        {
            "_id": ObjectId(),
            "workspace_id": "ws_123",
            "email": "nophone@example.com",
            "name": "Alex Smith",
            "phone": "",
            "tag": "lead",
            "created_at": now,
        },
    ]
    return db


@pytest.fixture
def user():
    return {
        "user_id": "usr_456",
        "default_workspace_id": "ws_123",
        "email": "creator@unravler.com",
        "display_name": "Test Creator",
        "name": "Test Creator",
    }


# ── Broadcasts Tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_templates_list():
    res = await list_templates()
    assert res["ok"] is True
    assert len(res["templates"]) >= 5
    ids = [t["id"] for t in res["templates"]]
    assert "tpl_announcement" in ids
    assert "tpl_flash_sale" in ids


@pytest.mark.asyncio
async def test_broadcast_crud(fake_db, user):
    # 1. Create Broadcast
    create_body = BroadcastCreate(
        name="Summer Launch",
        subject="🚀 Big News: Summer Collection Live!",
        preview_text="Get 30% off before midnight",
        target_tag="all",
        body_markdown="Hey {{name}}, check out our summer launch!",
        body_html="<p>Hey {{name}}, summer is here!</p>",
        is_draft=True,
    )
    create_res = await create_broadcast(create_body, current_user=user, db=fake_db)
    assert create_res["ok"] is True
    b_id = create_res["broadcast"]["id"]
    assert create_res["broadcast"]["status"] == "draft"
    assert create_res["broadcast"]["recipients_count"] == 3

    # 2. Get Single Broadcast
    get_res = await get_broadcast(b_id, current_user=user, db=fake_db)
    assert get_res["ok"] is True
    assert get_res["broadcast"]["subject"] == "🚀 Big News: Summer Collection Live!"

    # 3. List Broadcasts
    list_res = await list_broadcasts(current_user=user, db=fake_db)
    assert list_res["ok"] is True
    assert len(list_res["broadcasts"]) == 1

    # 4. Update Broadcast
    update_body = BroadcastUpdate(
        subject="🚀 Updated: Summer Collection Live Now!",
        target_tag="vip",
    )
    update_res = await update_broadcast(b_id, update_body, current_user=user, db=fake_db)
    assert update_res["ok"] is True
    assert update_res["broadcast"]["subject"] == "🚀 Updated: Summer Collection Live Now!"
    assert update_res["broadcast"]["recipients_count"] == 1  # 1 VIP lead

    # 5. Delete Broadcast
    del_res = await delete_broadcast(b_id, current_user=user, db=fake_db)
    assert del_res["ok"] is True
    assert await fake_db.broadcasts.count_documents() == 0


@pytest.mark.asyncio
async def test_broadcast_send_execution(fake_db, user):
    create_body = BroadcastCreate(
        subject="Exclusive Note for VIPs",
        target_tag="vip",
        body_markdown="Hey {{name}}, as a VIP from {{creator_name}}, you get early access.",
        body_html="<p>Hey {{name}}, as a VIP from {{creator_name}}, you get early access.</p>",
        is_draft=False,
    )
    create_res = await create_broadcast(create_body, current_user=user, db=fake_db)
    b_id = create_res["broadcast"]["id"]

    # Send broadcast (mocking email send)
    with patch("api.routes.broadcasts.send_email_async", new=AsyncMock(return_value=True)) as mock_send:
        send_res = await send_broadcast(b_id, current_user=user, db=fake_db)
        assert send_res["ok"] is True
        assert "dispatched to 1 recipients" in send_res["message"]
        assert mock_send.call_count == 1
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["to"] == "john@example.com"
        assert "John Doe" in call_kwargs["html"]
        assert "Test Creator" in call_kwargs["html"]

    # Check updated broadcast doc
    updated_doc = await fake_db.broadcasts.find_one({"_id": ObjectId(b_id)})
    assert updated_doc["status"] == "sent"
    assert updated_doc["delivered_count"] == 1
    assert updated_doc["failed_count"] == 0

    # Test Stats aggregation
    stats_res = await get_broadcast_stats(current_user=user, db=fake_db)
    assert stats_res["ok"] is True
    assert stats_res["sent_campaigns"] == 1
    assert stats_res["total_delivered"] == 1
    assert stats_res["delivery_rate"] == 100.0


@pytest.mark.asyncio
async def test_broadcast_test_send(user):
    test_req = EmailPreviewRequest(
        subject="Previewing our summer drop",
        body_html="<p>Hello Preview</p>",
    )
    with patch("api.routes.broadcasts.send_email_async", new=AsyncMock(return_value=True)):
        res = await send_test_email(test_req, current_user=user)
        assert res["ok"] is True
        assert res["recipient"] == "creator@unravler.com"


@pytest.mark.asyncio
async def test_whatsapp_outreach_links(fake_db, user):
    req = WhatsAppLinksRequest(
        template_message="Hey {{name}}, here is your access link from {{creator_name}}!",
        target_tag="all",
    )
    res = await generate_whatsapp_outreach_links(req, current_user=user, db=fake_db)
    assert res["ok"] is True
    assert res["total_leads"] == 3
    assert res["leads_with_phone"] == 2

    # Verify personalized wa.me links
    sarah = next(item for item in res["outreach_items"] if item["name"] == "Sarah Connor")
    assert sarah["has_phone"] is True
    assert "https://wa.me/14155552671?text=" in sarah["wa_link"]
    assert "Sarah%20Connor" in sarah["wa_link"]

    alex = next(item for item in res["outreach_items"] if item["name"] == "Alex Smith")
    assert alex["has_phone"] is False
    assert alex["wa_link"] is None


# ── AI Broadcast Draft Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_broadcast_draft(user):
    fake_req = Request({"type": "http", "method": "POST", "path": "/ai/broadcast-draft", "headers": []})
    body = BroadcastDraftRequest(
        topic="Announce 40% discount on all video editing packs ending Sunday",
        tone="urgent",
        audience_type="subscribers",
    )

    with patch("api.routes.ai.free_llm.generate_text", new=AsyncMock(return_value=(
        '{"subject_lines": ["⚡ 40% Flash Sale!", "Urgent discount inside", "Save 40% now"],'
        ' "preview_text": "Disappears Sunday midnight...",'
        ' "suggested_cta": "Claim 40% Off Now →",'
        ' "body_markdown": "Hey {{name}}, don\'t miss out!",'
        ' "body_html": "<p>Hey {{name}}</p>"}',
        "mock-provider",
        "mock-model"
    ))):
        res = await generate_broadcast_draft(fake_req, body, current_user=user)
        assert res["ok"] is True
        assert len(res["subject_lines"]) == 3
        assert res["subject_lines"][0] == "⚡ 40% Flash Sale!"
        assert res["suggested_cta"] == "Claim 40% Off Now →"


# ── Smart Bio Payment Link Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bio_payment_link_formatting(user):
    # 1. Custom URL
    custom_req = PaymentLinkRequest(
        title="1-on-1 Consultation",
        amount=499.0,
        currency="INR",
        provider="custom",
        custom_url="buy.stripe.com/abc123",
    )
    res1 = await create_or_format_payment_link(custom_req, current_user=user)
    assert res1["ok"] is True
    assert res1["payment_url"] == "https://buy.stripe.com/abc123"

    # 2. UPI Handle
    upi_req = PaymentLinkRequest(
        title="Coffee Tip",
        amount=50.0,
        currency="INR",
        provider="upi",
        custom_url="creator@okaxis",
    )
    res2 = await create_or_format_payment_link(upi_req, current_user=user)
    assert res2["ok"] is True
    assert res2["payment_url"].startswith("upi://pay?pa=creator@okaxis")
    assert "am=50.00" in res2["payment_url"]

    # 3. PayPal.me
    pp_req = PaymentLinkRequest(
        title="Exclusive Bundle",
        amount=19.99,
        currency="USD",
        provider="paypal",
        custom_url="paypal.me/topcreator",
    )
    res3 = await create_or_format_payment_link(pp_req, current_user=user)
    assert res3["ok"] is True
    assert res3["payment_url"] == "https://paypal.me/topcreator/19.99USD"
