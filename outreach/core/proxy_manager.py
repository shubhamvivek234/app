"""Assign pre-purchased dedicated ISP proxies to outreach senders.

Webshare exposes plan and proxy lists; it has no per-proxy order or delete API.
Each sender gets a distinct local assignment while the Webshare plan remains
active until its owner changes or cancels it in Webshare.
For small pilots, IPRoyal supports a manually purchased static ISP IP configured
server-side; this module never orders, renews, or cancels provider subscriptions.
"""
import hashlib
import ipaddress
import os
import logging
import httpx
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, unquote, urlsplit
from outreach.models import ProxyConfig, ProxyStatus
from utils.encryption import encrypt, decrypt_strict

logger = logging.getLogger(__name__)

WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2"


class ProxyProvisioningError(Exception):
    pass


class ProxyPlanRequiredError(ProxyProvisioningError):
    pass


class ProxyInventoryExhaustedError(ProxyProvisioningError):
    pass


class JITProxyManager:
    """Select an unused dedicated ISP proxy from the configured provider."""

    def __init__(self, api_key: str | None = None):
        self.provider = os.getenv("OUTREACH_PROXY_PROVIDER", "webshare").strip().lower()
        self.api_key = api_key or os.getenv("WEBSHARE_API_KEY", "mock")
        self.is_mock = self.provider == "webshare" and self.api_key in ("mock", "test", "")

    def _select_iproyal_proxy(self, country_code: str, excluded: set[str]) -> ProxyConfig:
        """Use one operator-configured public IP from a purchased IPRoyal ISP order."""
        raw_url = os.getenv("IPROYAL_PROXY_URL", "").strip()
        if not raw_url:
            raise ProxyPlanRequiredError(
                "IPRoyal proxy is not configured. Purchase one dedicated ISP IP and set "
                "IPROYAL_PROXY_URL and IPROYAL_PROXY_COUNTRY on the server."
            )
        configured_country = os.getenv("IPROYAL_PROXY_COUNTRY", "").strip().upper()
        if len(configured_country) != 2 or not configured_country.isascii() or not configured_country.isalpha():
            raise ProxyProvisioningError("IPRoyal proxy country is not configured correctly")
        if country_code != configured_country:
            raise ProxyInventoryExhaustedError(
                f"The configured IPRoyal proxy is in {configured_country}, not {country_code}. "
                "Choose the purchased proxy's country."
            )

        try:
            parsed = urlsplit(raw_url)
            host = parsed.hostname or ""
            port = parsed.port
            address = ipaddress.IPv4Address(host)
            username = unquote(parsed.username or "")
            password = unquote(parsed.password or "")
        except (ValueError, TypeError) as exc:
            raise ProxyProvisioningError("IPRoyal proxy URL is invalid") from exc
        if (
            parsed.scheme != "http" or not address.is_global
            or not port or not 1 <= port <= 65535
            or not username or not password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        ):
            raise ProxyProvisioningError(
                "IPRoyal proxy URL must be an authenticated HTTP URL for one public static ISP IP"
            )

        identity = hashlib.sha256(f"{host}:{port}".encode()).hexdigest()[:24]
        proxy_id = f"iproyal:{identity}"
        if proxy_id in excluded:
            raise ProxyInventoryExhaustedError(
                "The configured IPRoyal proxy is already assigned to a sender. "
                "Add another dedicated ISP IP or disconnect the existing sender."
            )
        return ProxyConfig(
            proxy_id=proxy_id,
            provider="iproyal_static",
            host=host,
            port=port,
            username=username,
            password_enc=encrypt(password),
            country_code=configured_country,
            status=ProxyStatus.HEALTHY,
            assigned_at=datetime.now(timezone.utc),
        )

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
        """Select a dedicated static ISP proxy already owned by the operator.

        The caller atomically reserves the returned proxy ID before using it.
        ``excluded_proxy_ids`` lets a caller retry after another request wins
        the reservation race.
        """
        country_code = country_code.upper()
        if self.provider == "iproyal":
            return self._select_iproyal_proxy(country_code, excluded_proxy_ids or set())
        if self.provider != "webshare":
            raise ProxyProvisioningError("Unknown outreach proxy provider configured")
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
        """Clear a local assignment; the provider retains the purchased proxy."""
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
            password = decrypt_strict(password_enc) if username else ""
        except (ValueError, EnvironmentError) as exc:
            raise ProxyProvisioningError("Stored proxy credentials cannot be decrypted") from exc
        if username and password:
            return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
        return f"http://{host}:{port}"
