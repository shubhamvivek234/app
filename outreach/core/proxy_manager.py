"""Assign pre-purchased dedicated ISP proxies to outreach senders.

Webshare exposes plan and proxy lists; it has no per-proxy order or delete API.
Each sender gets a distinct local assignment while the Webshare plan remains
active until its owner changes or cancels it in Webshare.
For small pilots, IPRoyal supports a manually purchased static ISP IP configured
server-side; this module never orders, renews, or cancels provider subscriptions.
"""
import asyncio
import hashlib
import ipaddress
import os
import logging
import time
import httpx
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, unquote, urlsplit
from outreach.models import ProxyConfig, ProxyStatus
from utils.encryption import encrypt, decrypt_strict
from outreach.core import session_custody, webshare_key_custody

logger = logging.getLogger(__name__)

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
        self._key_override = api_key

    @property
    def configuration_state(self) -> str:
        """Configuration metadata; no key opening or provider health request."""
        if self.provider == "iproyal":
            return "live"
        if self.provider != "webshare":
            return "unavailable"
        return webshare_key_custody.configuration_state(self._key_override)

    @property
    def is_mock(self) -> bool:
        return self.provider == "webshare" and self.configuration_state == "mock"

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

    @staticmethod
    def _webshare_proxy(record: dict, plan_id: int, country: str, excluded: set[str]) -> ProxyConfig | None:
        """Accept bounded credentials for one public static IPv4, never a hostname."""
        resource = record.get("id")
        if not isinstance(resource, str) or not 1 <= len(resource) <= 128:
            return None
        if resource != resource.strip() or any(ord(char) < 32 or ord(char) == 127 for char in resource):
            return None
        proxy_id = f"webshare:{plan_id}:{resource}"
        if proxy_id in excluded or record.get("valid") is not True or record.get("country_code") != country:
            return None
        host, username, password = (record.get(field) for field in ("proxy_address", "username", "password"))
        if any(not isinstance(value, str) or not 1 <= len(value) <= bound
               or any(ord(char) < 32 or ord(char) == 127 for char in value)
               for value, bound in ((host, 256), (username, 256), (password, 4096))):
            return None
        try:
            address = ipaddress.IPv4Address(host)
            raw_port = record.get("port")
            if type(raw_port) not in (int, str):
                return None
            port = int(raw_port)
        except (TypeError, ValueError):
            return None
        if not address.is_global or not 1 <= port <= 65535:
            return None
        return ProxyConfig(
            proxy_id=proxy_id, provider="webshare_plan", host=str(address), port=port,
            username=username, password_enc="", country_code=country,
            status=ProxyStatus.HEALTHY, assigned_at=datetime.now(timezone.utc),
        )

    async def order_static_residential_proxy(
        self, country_code: str = "US", excluded_proxy_ids: set[str] | None = None,
        *, workspace_id: str | None = None,
    ) -> ProxyConfig:
        """Select an existing proxy; callers still must prove and reserve ownership.

        This helper performs only bounded inventory GETs, never orders or renews.
        Scoped selections require a workspace for sealing the returned password.
        It is not the paid pilot's managed-inventory/import/assignment path.
        """
        from outreach.core.webshare_inventory import InventoryRead, TOTAL_TIMEOUT
        from outreach.core.proxy_custody import seal_proxy_password
        try:
            mode = session_custody.custody_mode()
            if not isinstance(country_code, str):
                raise ProxyProvisioningError("A two-letter proxy country is required")
            country_code = country_code.upper()
            if len(country_code) != 2 or not country_code.isascii() or not country_code.isalpha():
                raise ProxyProvisioningError("A two-letter proxy country is required")
            if self.provider == "iproyal":
                if mode == "kms_v1":
                    raise ProxyProvisioningError("Scoped custody requires the managed IPRoyal inventory path")
                return self._select_iproyal_proxy(country_code, excluded_proxy_ids or set())
            if self.provider != "webshare":
                raise ProxyProvisioningError("Unknown outreach proxy provider configured")
            if self.is_mock:
                if mode != "legacy_fernet":
                    raise ProxyProvisioningError("Webshare custody changed before mock selection")
                mock_id = f"proxy_mock_{os.urandom(4).hex()}"
                proxy = ProxyConfig(
                    proxy_id=mock_id, provider="webshare_mock", host="127.0.0.1", port=8080,
                    username=f"user_{mock_id}", password_enc=encrypt("mock_secure_pass_123"),
                    country_code=country_code, status=ProxyStatus.HEALTHY,
                    assigned_at=datetime.now(timezone.utc),
                )
                if session_custody.custody_mode() != mode or not self.is_mock:
                    raise ProxyProvisioningError("Webshare custody changed during mock selection")
                return proxy
            # Validate storage and tenant before KMS, DNS or HTTP. Scoped values
            # never fall through to mock, constructor plaintext or old Fernet.
            config = webshare_key_custody.capture_configuration(self._key_override)
            if config.policy[0] != mode:
                raise ProxyProvisioningError("Webshare custody changed before inventory selection")
            mode = config.policy[0]
            if mode == "kms_v1":
                session_custody.context(workspace_id, "webshare-selection", "preflight", "proxy_password")
            excluded = excluded_proxy_ids or set()
            deadline = time.monotonic() + TOTAL_TIMEOUT
            async with asyncio.timeout(TOTAL_TIMEOUT):
                key = await webshare_key_custody.prepare_key(
                    expected_digest=config.digest, override=self._key_override,
                )
                async with InventoryRead(key, deadline=deadline) as inventory:
                    plans = await inventory.pages("/subscription/plan/", {})
                    eligible = [
                        plan for plan in plans
                        if plan.get("status") == "active" and plan.get("proxy_type") == "dedicated"
                        and plan.get("proxy_subtype") == "isp" and not plan.get("automatic_refresh_frequency")
                    ]
                    if not eligible:
                        raise ProxyPlanRequiredError(
                            "Webshare has no active Dedicated Static Residential (ISP) plan. "
                            "Add one in Webshare before connecting a LinkedIn sender."
                        )
                    for plan in eligible:
                        plan_id = plan.get("id")
                        if type(plan_id) is not int or not 0 < plan_id <= 2**63 - 1:
                            continue
                        records = await inventory.pages("/proxy/list/", {
                            "mode": "direct", "country_code__in": country_code, "plan_id": plan_id,
                        })
                        for record in records:
                            proxy = self._webshare_proxy(record, plan_id, country_code, excluded)
                            if proxy is None:
                                continue
                            if mode == "kms_v1":
                                encrypted = await seal_proxy_password(record["password"], proxy, workspace_id)
                                proxy = proxy.model_copy(update=encrypted)
                            else:
                                proxy = proxy.model_copy(update={"password_enc": encrypt(record["password"])})
                            inventory.require_current()
                            return proxy
                    raise ProxyInventoryExhaustedError(
                        f"No unassigned Dedicated Static Residential (ISP) proxy is available in {country_code}. "
                        "Add a proxy for that country in Webshare."
                    )
        except ProxyProvisioningError:
            raise
        except (httpx.HTTPError, httpx.StreamError, ValueError, TimeoutError, OSError):
            # Do not preserve an exception cause that could retain headers,
            # response bodies, private key-service details or proxy passwords.
            raise ProxyProvisioningError("Webshare inventory or credential preparation is unavailable") from None

    async def release_proxy(self, proxy_id: str) -> bool:
        """Clear a local assignment; the provider retains the purchased proxy."""
        return bool(proxy_id)

    async def test_proxy_health(self, proxy: ProxyConfig, *, prepared_proxy=None, allowed=None) -> bool:
        """
        Verifies that outgoing traffic through this proxy reaches the web and masks the host IP.
        """
        from outreach.core.session_custody import custody_mode
        if custody_mode() == "kms_v1" and (prepared_proxy is None or not prepared_proxy.scoped
                or not prepared_proxy.matches(proxy, proxy.custody_workspace_id)):
            return False
        if self.is_mock and proxy.provider == "webshare_mock" and proxy.host == "127.0.0.1":
            return True

        proxy_url = prepared_proxy.url if prepared_proxy else self.format_proxy_url(proxy)
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=10.0) as client:
                if allowed is not None and not allowed():
                    return False
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

        if password_enc.startswith("uc1:"):
            raise ProxyProvisioningError("Scoped proxy preparation is required")
        try:
            password = decrypt_strict(password_enc) if username else ""
        except (ValueError, EnvironmentError) as exc:
            raise ProxyProvisioningError("Stored proxy credentials cannot be decrypted") from exc
        if username and password:
            return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
        return f"http://{host}:{port}"
