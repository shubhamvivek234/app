from pydantic import BaseModel
from typing import Optional, Dict, Any

class CheckoutSessionResponse(BaseModel):
    url: str
    session_id: str

class CheckoutStatusResponse(BaseModel):
    status: str
    payment_status: str
    amount_total: int
    currency: str
    metadata: Dict[str, Any]

class CheckoutSessionRequest(BaseModel):
    amount: float
    currency: str
    success_url: str
    cancel_url: str
    metadata: Dict[str, Any]

class WebhookResponse:
    def __init__(self, event_type, session_id):
        self.event_type = event_type
        self.session_id = session_id

class StripeCheckout:
    def __init__(self, api_key, webhook_url):
        self.api_key = api_key
        self.webhook_url = webhook_url

    async def create_checkout_session(self, request: CheckoutSessionRequest):
        return CheckoutSessionResponse(
            url="http://mock-payment-gateway",
            session_id="mock_session_id"
        )

    async def get_checkout_status(self, session_id):
        return CheckoutStatusResponse(
            status="complete",
            payment_status="paid",
            amount_total=1000,
            currency="usd",
            metadata={}
        )

    async def handle_webhook(self, body, signature):
        return WebhookResponse(
            event_type="checkout.session.completed",
            session_id="mock_session_id"
        )
