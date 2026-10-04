"""Asset-scoped proxy preparation before database-only physical authorization."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from outreach.models import ProxyConfig

from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, PREFIX
from outreach.core import session_custody
from outreach.core.crypto import encrypt_secret

TRANSPORT_FIELDS = ('proxy_id', 'provider', 'host', 'port', 'username', 'country_code')
BINDING_FIELDS = (*TRANSPORT_FIELDS, 'password_enc', 'credential_generation', 'custody_workspace_id')


def proxy_record(proxy: dict[str, Any] | ProxyConfig) -> dict[str, Any]:
    """Normalize inventory and embedded account representations without opening secrets."""
    if not isinstance(proxy, dict) and not hasattr(proxy, 'model_dump'):
        raise CustodyUnavailable('Proxy asset record is unavailable')
    row = proxy if isinstance(proxy, dict) else proxy.model_dump()
    if row.get('_id') and row.get('proxy_id') and row['_id'] != row['proxy_id']:
        raise CustodyUnavailable('Proxy asset identifiers disagree')
    value = {name: row.get(name) for name in BINDING_FIELDS}
    value['proxy_id'] = row.get('proxy_id') or row.get('_id')
    return value


def proxy_digest(proxy: dict[str, Any] | ProxyConfig) -> str:
    return canonical_hash(proxy_record(proxy))


def _context(row: dict[str, Any], workspace: str) -> session_custody.CredentialContext:
    if (not row.get('credential_generation') or row.get('custody_workspace_id') != workspace
            or not row.get('proxy_id') or not row.get('host') or not row.get('username')
            or type(row.get('port')) is not int or not 1 <= row['port'] <= 65535):
        raise CustodyUnavailable('Scoped proxy asset identity is unavailable')
    if any(not isinstance(row.get(name), str) or not 1 <= len(row[name]) <= 256
            for name in ('proxy_id', 'credential_generation', 'username', 'host', 'country_code', 'provider')):
        raise CustodyUnavailable('Scoped proxy transport metadata is invalid')
    try:
        address = ipaddress.IPv4Address(row['host'])
        if not address.is_global: raise ValueError('nonpublic')
    except ValueError:
        raise CustodyUnavailable('Scoped proxy requires a public static IPv4 asset') from None
    generation = canonical_hash({'credential_generation': row['credential_generation'],
        **{name: row.get(name) for name in TRANSPORT_FIELDS}})
    return session_custody.context(workspace, row['proxy_id'], generation, 'proxy_password')


@dataclass(frozen=True)
class PreparedProxy:
    workspace_id: str
    binding_digest: str
    scoped: bool
    url: str = field(repr=False)
    _url_digest: str = field(repr=False)

    def matches(self, proxy: dict[str, Any] | ProxyConfig, workspace: str) -> bool:
        """Compare exact captured material without unwrapping inside a transaction."""
        return bool(workspace == self.workspace_id
            and self.scoped == (session_custody.custody_mode() == 'kms_v1')
            and hmac.compare_digest(self._url_digest, hashlib.sha256(self.url.encode()).hexdigest())
            and hmac.compare_digest(self.binding_digest, proxy_digest(proxy)))


async def seal_proxy_password(password: str, proxy: dict[str, Any] | ProxyConfig, workspace: str, *, generation: str | None = None) -> dict[str, str]:
    if not isinstance(password, str) or not password:
        raise CustodyUnavailable('Complete proxy credentials are required')
    row = proxy_record(proxy)
    row.update(credential_generation=generation or str(uuid.uuid4()), custody_workspace_id=workspace)
    mode = session_custody.custody_mode()
    encrypted = (await session_custody.configured_custody().seal(password, _context(row, workspace))
        if mode == 'kms_v1' else encrypt_secret(password))
    return {name: row[name] for name in ('credential_generation', 'custody_workspace_id')} | {'password_enc': encrypted}


async def prepare_proxy(proxy: dict[str, Any] | ProxyConfig, workspace: str) -> PreparedProxy:
    """Open one asset for this caller's tenant, then capture exact transport data."""
    row = proxy_record(proxy)
    captured_digest = proxy_digest(row)
    mode = session_custody.custody_mode()
    if mode == 'kms_v1':
        password = await session_custody.configured_custody().open(row.get('password_enc'), _context(row, workspace))
        url = f"http://{quote(row['username'], safe='')}:{quote(password, safe='')}@{row['host']}:{row['port']}"
    else:
        if str(row.get('password_enc') or '').startswith(PREFIX):
            raise CustodyUnavailable('Scoped proxy credentials cannot use legacy custody')
        from outreach.core.proxy_manager import JITProxyManager
        url = JITProxyManager.format_proxy_url(proxy)
    return PreparedProxy(workspace, captured_digest, mode == 'kms_v1', url, hashlib.sha256(url.encode()).hexdigest())
