"""Fixed, bounded, source-fenced Webshare GETs; no provisioning mutations."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import asyncio
import json
import time
from typing import Any

import httpx

from outreach.core.proxy_manager import ProxyProvisioningError
from outreach.core.safe_transport import create_safe_client
from outreach.core.webshare_key_custody import PreparedKey

API_URL = 'https://proxy.webshare.io/api/v2'
TOTAL_TIMEOUT = 30.0
MAX_REQUESTS = 40
MAX_PAGES = 20
MAX_RESPONSE_BYTES = 1024 * 1024


class InventoryRead:
    """One operation-wide request allowance and deadline, including all plans."""

    def __init__(self, key: PreparedKey, *, deadline: float) -> None:
        self.key = key
        self.deadline = deadline
        self.requests = 0
        self.client: httpx.AsyncClient | None = None

    def matches(self) -> bool:
        return time.monotonic() < self.deadline and self.key.matches()

    def require_current(self) -> None:
        if not self.matches():
            raise ProxyProvisioningError('Webshare inventory authority expired or changed')

    async def __aenter__(self) -> InventoryRead:
        self.require_current()
        self.client = create_safe_client(timeout=10.0, preflight=self.matches)
        try:
            await self.client.__aenter__()
            self.require_current()
        except BaseException:
            await self.client.aclose()
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self.client is not None:
            await self.client.__aexit__(*args)
        if args[0] is None:
            self.require_current()

    @staticmethod
    def _validate(path: str, params: dict[str, Any]) -> None:
        if path == '/subscription/plan/' and params == {}:
            return
        if path == '/proxy/list/' and set(params) == {'mode', 'country_code__in', 'plan_id'}:
            country, plan = params['country_code__in'], params['plan_id']
            if (
                params['mode'] == 'direct' and type(plan) is int and plan > 0
                and isinstance(country, str) and len(country) == 2
                and country.isascii() and country.isalpha() and country == country.upper()
            ):
                return
        raise ProxyProvisioningError('Webshare inventory request identity is unavailable')

    async def pages(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._validate(path, params)
        params = dict(params)
        records: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            self.require_current()
            if self.client is None or self.requests >= MAX_REQUESTS:
                raise ProxyProvisioningError('Webshare inventory request allowance exhausted')
            self.requests += 1
            async with asyncio.timeout(max(0.001, self.deadline - time.monotonic())):
                async with self.client.stream(
                    'GET', API_URL + path,
                    params={**params, 'page': page, 'page_size': 100},
                    headers={'Authorization': 'Token ' + self.key.value, 'Accept-Encoding': 'identity'},
                ) as response:
                    self.require_current()
                    if response.status_code in (401, 403):
                        raise ProxyProvisioningError('Webshare key cannot access proxy inventory')
                    if response.status_code != 200:
                        raise ProxyProvisioningError('Webshare proxy inventory is unavailable')
                    if response.headers.get('Content-Encoding', '').lower() not in {'', 'identity'}:
                        raise ProxyProvisioningError('Encoded Webshare inventory is unavailable')
                    length = response.headers.get('Content-Length')
                    if length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE_BYTES):
                        raise ProxyProvisioningError('Webshare inventory response exceeds its bound')
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        self.require_current()
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ProxyProvisioningError('Webshare inventory response exceeds its bound')
                        body.extend(chunk)
                    self.require_current()
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError):
                raise ProxyProvisioningError('Webshare returned invalid inventory') from None
            if (
                not isinstance(data, dict) or data.get('error') or not isinstance(data.get('results'), list)
                or len(data['results']) > 100 or any(not isinstance(row, dict) for row in data['results'])
                or data.get('next') is not None and (
                    not isinstance(data['next'], str) or len(data['next']) > 2048
                )
            ):
                raise ProxyProvisioningError('Webshare returned invalid inventory')
            records.extend(data['results'])
            if not data.get('next'):
                return records
            # Only advance the fixed endpoint's page. Never follow provider URLs.
        raise ProxyProvisioningError('Webshare inventory page allowance exhausted')
