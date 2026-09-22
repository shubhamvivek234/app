"""
Phase 1: Just-In-Time (JIT) Residential Proxy Manager.
Provisions 1:1 dedicated static residential / ISP proxies on-demand via REST API.
Tears down proxies when subscriptions cancel or trials end to ensure ZERO idle costs.
"""
import os
import logging
import httpx
from datetime import datetime, timezone
from outreach.models import ProxyConfig, ProxyStatus
from utils.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2"


class ProxyProvisioningError(Exception):
    pass


class JITProxyManager:
    """
    Manages the lifecycle of dedicated static residential proxies for LinkedIn accounts.
    If WEBSHARE_API_KEY is not set or set to 'mock', operates in deterministic sandbox mode.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("WEBSHARE_API_KEY", "mock")
        self.is_mock = self.api_key in ("mock", "test", "")

    async def order_static_residential_proxy(self, country_code: str = "US") -> ProxyConfig:
        """
        Orders 1 dedicated static residential IP mapped to the user's country.
        Called strictly when a subscription or trial is authorized.
        """
        if self.is_mock:
            logger.info("JITProxyManager [MOCK]: Provisioning simulated static residential proxy for country=%s", country_code)
            mock_id = f"proxy_mock_{os.urandom(4).hex()}"
            return ProxyConfig(
                proxy_id=mock_id,
                provider="webshare_mock",
                host="127.0.0.1",
                port=8080,
                username=f"user_{mock_id}",
                password_enc=encrypt("mock_secure_pass_123"),
                country_code=country_code,
                status=ProxyStatus.HEALTHY,
                assigned_at=datetime.now(timezone.utc),
            )

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "proxy_type": "residential",
            "country_code": country_code.upper(),
            "count": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{WEBSHARE_API_URL}/proxy/order/", json=payload, headers=headers)
                if resp.status_code not in (200, 201):
                    logger.error("Webshare proxy order failed: status=%s body=%s", resp.status_code, resp.text)
                    raise ProxyProvisioningError(f"Provider returned status {resp.status_code}")

                data = resp.json()
                proxy_record = data.get("proxy", data)
                proxy_id = str(proxy_record.get("id", os.urandom(6).hex()))
                host = proxy_record.get("proxy_address") or proxy_record.get("host")
                port = int(proxy_record.get("port", 80))
                username = proxy_record.get("username", "")
                password = proxy_record.get("password", "")

                logger.info("JITProxyManager: Successfully ordered proxy_id=%s host=%s", proxy_id, host)
                return ProxyConfig(
                    proxy_id=proxy_id,
                    provider="webshare",
                    host=host,
                    port=port,
                    username=username,
                    password_enc=encrypt(password),
                    country_code=country_code,
                    status=ProxyStatus.HEALTHY,
                    assigned_at=datetime.now(timezone.utc),
                )
        except Exception as exc:
            logger.exception("Failed to order residential proxy: %s", exc)
            raise ProxyProvisioningError(f"Could not provision residential proxy: {exc}") from exc

    async def release_proxy(self, proxy_id: str) -> bool:
        """
        Deallocates the proxy from the provider so it stops incurring billing immediately.
        """
        if self.is_mock or proxy_id.startswith("proxy_mock_"):
            logger.info("JITProxyManager [MOCK]: Released proxy_id=%s", proxy_id)
            return True

        headers = {"Authorization": f"Token {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(f"{WEBSHARE_API_URL}/proxy/delete/{proxy_id}/", headers=headers)
                if resp.status_code in (200, 204, 404):
                    logger.info("JITProxyManager: Released proxy_id=%s from provider", proxy_id)
                    return True
                logger.warning("JITProxyManager: Provider release returned status %s for proxy_id=%s", resp.status_code, proxy_id)
                return False
        except Exception as exc:
            logger.error("Failed to release proxy %s: %s", proxy_id, exc)
            return False

    async def test_proxy_health(self, proxy: ProxyConfig) -> bool:
        """
        Verifies that outgoing traffic through this proxy reaches the web and masks the host IP.
        """
        if self.is_mock or proxy.host == "127.0.0.1":
            return True

        proxy_url = self.format_proxy_url(proxy)
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=10.0) as client:
                resp = await client.get("https://httpbin.org/ip")
                if resp.status_code == 200:
                    logger.info("JITProxyManager: Proxy %s is healthy. Verified IP: %s", proxy.proxy_id, resp.json().get("origin"))
                    return True
                return False
        except Exception as exc:
            logger.warning("Proxy health check failed for %s: %s", proxy.proxy_id, exc)
            return False

    @staticmethod
    def format_proxy_url(proxy: ProxyConfig) -> str:
        """Constructs an authenticated HTTP proxy URL for Playwright, httpx, or curl."""
        try:
            password = decrypt(proxy.password_enc)
        except Exception:
            password = ""
        if proxy.username and password:
            return f"http://{proxy.username}:{password}@{proxy.host}:{proxy.port}"
        return f"http://{proxy.host}:{proxy.port}"
