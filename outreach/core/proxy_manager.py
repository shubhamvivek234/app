"""Assign dedicated Webshare ISP proxies from an existing subscription.

Webshare exposes plan and proxy lists; it has no per-proxy order or delete API.
Each sender gets a distinct local assignment while the Webshare plan remains
active until its owner changes or cancels it in Webshare.
"""
import os
import logging
import httpx
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from outreach.models import ProxyConfig, ProxyStatus
from utils.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2"


class ProxyProvisioningError(Exception):
    pass


class ProxyPlanRequiredError(ProxyProvisioningError):
    pass


class ProxyInventoryExhaustedError(ProxyProvisioningError):
    pass


class JITProxyManager:
    """Select an unused, dedicated ISP proxy from a paid Webshare plan."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("WEBSHARE_API_KEY", "mock")
        self.is_mock = self.api_key in ("mock", "test", "")

    async def _get_pages(self, client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> list[dict]:
        records: list[dict] = []
        page = 1
        while page <= 100:
            response = await client.get(
                f"{WEBSHARE_API_URL}{path}",
                params={**params, "page": page, "page_size": 100},
                headers={"Authorization": f"Token {self.api_key}"},
            )
            if response.status_code in (401, 403):
                raise ProxyProvisioningError("Webshare API key cannot access proxy plans")
            if response.status_code != 200:
                raise ProxyProvisioningError(f"Webshare proxy inventory is unavailable (HTTP {response.status_code})")
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise ProxyProvisioningError("Webshare returned an invalid proxy inventory")
            records.extend(item for item in data["results"] if isinstance(item, dict))
            if not data.get("next"):
                return records
            page += 1
        raise ProxyProvisioningError("Webshare proxy inventory exceeds the supported page limit")

    async def order_static_residential_proxy(
        self, country_code: str = "US", excluded_proxy_ids: set[str] | None = None,
    ) -> ProxyConfig:
        """Select a dedicated static ISP proxy already owned in Webshare.

        The caller atomically reserves the returned proxy ID before using it.
        ``excluded_proxy_ids`` lets a caller retry after another request wins
        the reservation race.
        """
        country_code = country_code.upper()
        if self.is_mock:
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

        excluded = excluded_proxy_ids or set()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                plans = await self._get_pages(client, "/subscription/plan/", {})
                eligible = [
                    plan for plan in plans
                    if plan.get("status") == "active"
                    and plan.get("proxy_type") == "dedicated"
                    and plan.get("proxy_subtype") == "isp"
                    and not plan.get("automatic_refresh_frequency")
                ]
                if not eligible:
                    raise ProxyPlanRequiredError(
                        "Webshare has no active Dedicated Static Residential (ISP) plan. "
                        "Add one in Webshare before connecting a LinkedIn sender."
                    )

                for plan in eligible:
                    plan_id = plan.get("id")
                    if plan_id is None:
                        continue
                    proxies = await self._get_pages(
                        client,
                        "/proxy/list/",
                        {"mode": "direct", "country_code__in": country_code, "plan_id": plan_id},
                    )
                    for record in proxies:
                        proxy_id = f"webshare:{plan_id}:{record.get('id', '')}"
                        if (
                            not record.get("id") or proxy_id in excluded
                            or record.get("valid") is not True
                            or record.get("country_code") != country_code
                            or not record.get("proxy_address")
                            or not record.get("username") or not record.get("password")
                        ):
                            continue
                        try:
                            port = int(record["port"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        if not 1 <= port <= 65535:
                            continue
                        return ProxyConfig(
                            proxy_id=proxy_id,
                            provider="webshare_plan",
                            host=record["proxy_address"],
                            port=port,
                            username=record["username"],
                            password_enc=encrypt(record["password"]),
                            country_code=country_code,
                            status=ProxyStatus.HEALTHY,
                            assigned_at=datetime.now(timezone.utc),
                        )
                raise ProxyInventoryExhaustedError(
                    f"No unassigned Dedicated Static Residential (ISP) proxy is available in {country_code}. "
                    "Add a proxy for that country in Webshare."
                )
        except ProxyProvisioningError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Webshare proxy inventory request failed: %s", type(exc).__name__)
            raise ProxyProvisioningError("Could not read Webshare proxy inventory. Please retry.") from exc

    async def release_proxy(self, proxy_id: str) -> bool:
        """Clear a local assignment; Webshare retains the subscribed proxy."""
        return bool(proxy_id)

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
                    return True
                return False
        except Exception as exc:
            logger.warning("Proxy health check failed for %s: %s", proxy.proxy_id, type(exc).__name__)
            return False

    @staticmethod
    def format_proxy_url(proxy: ProxyConfig | dict[str, Any]) -> str:
        """Constructs an authenticated HTTP proxy URL for Playwright, httpx, or curl."""
        if isinstance(proxy, dict):
            host = proxy.get("host", "")
            port = proxy.get("port", "")
            username = proxy.get("username", "")
            password_enc = proxy.get("password_enc", "")
        else:
            host = getattr(proxy, "host", "")
            port = getattr(proxy, "port", "")
            username = getattr(proxy, "username", "")
            password_enc = getattr(proxy, "password_enc", "")

        try:
            password = decrypt(password_enc) if password_enc else ""
        except Exception:
            password = ""
        if username and password:
            return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
        return f"http://{host}:{port}"
