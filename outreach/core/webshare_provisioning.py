"""Private import of manually verified, already purchased dedicated Webshare IPs.

No HTTP, purchase, renewal, vendor ownership proof or legacy adoption occurs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import re
from typing import Any
from urllib.parse import unquote, urlsplit

from outreach.core.authorization import canonical_hash
from outreach.core.paid_access import _utc
from outreach.core.proxy_custody import policy, seal_proxy_password
from outreach.core.proxy_identity import require_ip_binding, raw_options
from outreach.core import suppression
from outreach.core import session_custody
from outreach.core.credential_custody import PREFIX
from utils.ssrf_guard import is_safe_url

BASIS_FIELDS = ('_id', 'workspace_id', 'last_workspace_id', 'provider', 'host', 'port', 'username',
    'country_code', 'provider_plan_id', 'provider_resource_id', 'provider_order_id', 'expires_at',
    'credential_generation', 'custody_workspace_id', 'verified_by', 'evidence_digest', 'verified_at',
    'dedicated_isp_confirmed', 'request_digest', 'managed_webshare_version')


def _time(value: datetime) -> datetime:
    if not isinstance(value, (datetime, str)):
        raise ValueError('A verified provider term is required')
    value = _utc(value)
    if value is None:
        raise ValueError('A verified provider term is required')
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 128 or any(ord(c) < 32 for c in value):
        raise ValueError(f'A bounded {label} is required')
    return value.strip()


def _basis(row: dict) -> str:
    values = {key: row.get(key) for key in BASIS_FIELDS}
    for key in ('expires_at', 'verified_at'):
        values[key] = _time(values[key])
    return canonical_hash(values)


def webshare_basis_valid(row: dict, workspace: str) -> bool:
    """Validate metadata only; this never proves decryptability or vendor facts."""
    try:
        return bool(row.get('provider') == 'webshare_plan' and row.get('managed_webshare_version') == 1
            and row.get('workspace_id') == row.get('last_workspace_id') == row.get('custody_workspace_id') == workspace
            and row.get('dedicated_isp_confirmed') is True and row.get('credential_generation')
            and row.get('_id') == f"webshare:{row['provider_plan_id']}:{row['provider_resource_id']}"
            and row.get('import_basis_digest') == _basis(row))
    except (KeyError, TypeError, ValueError):
        return False


async def managed_webshare_valid(db: Any, row: dict, workspace: str, *, now: datetime | None = None) -> bool:
    """Require exact local import, physical exclusion and current provider term."""
    if not webshare_basis_valid(row, workspace):
        return False
    from outreach.core.proxy_lifecycle_proof import valid_history
    if not await valid_history(db, row, workspace):
        return False
    try:
        encrypted = row.get('password_enc')
        if (not isinstance(encrypted, str) or not encrypted or len(encrypted) > 16384
                or encrypted.startswith(PREFIX) != (session_custody.custody_mode() == 'kms_v1')):
            return False
        return bool(row.get('status') == 'available' and _time(row['expires_at']) > (now or datetime.now(timezone.utc))
                    and await require_ip_binding(db, row, workspace))
    except (TypeError, ValueError):
        return False


async def import_webshare_proxy(db: Any, *, proxy_url: str, country_code: str, plan_id: str,
    resource_id: str, provider_order_id: str, workspace_id: str, expires_at: datetime,
    verified_by: str, evidence_digest: str, dedicated_isp_confirmed: bool,
    now: datetime | None = None) -> dict:
    """Commit an immutable manual verification basis; retries never rotate secrets."""
    now = _time(now or datetime.now(timezone.utc)); expires_at = _time(expires_at)
    workspace_id = _text(workspace_id, 'workspace'); plan_id = _text(plan_id, 'plan ID')
    resource_id = _text(resource_id, 'resource ID'); provider_order_id = _text(provider_order_id, 'order ID')
    verified_by = _text(verified_by, 'operator')
    if ':' in plan_id or ':' in resource_id:
        raise ValueError('Plan and resource identifiers must be unambiguous')
    country_code = _text(country_code, 'country').upper()
    if not re.fullmatch('[A-Z]{2}', country_code) or not isinstance(evidence_digest, str) or not re.fullmatch('[a-f0-9]{64}', evidence_digest):
        raise ValueError('Country and original manual evidence digest are required')
    if dedicated_isp_confirmed is not True or expires_at <= now:
        raise ValueError('Verified dedicated static ISP capacity and a future term are required')
    try:
        if not isinstance(proxy_url, str) or len(proxy_url) > 2048 or any(ord(c) < 32 for c in proxy_url):
            raise ValueError('url')
        parsed = urlsplit(proxy_url); host = parsed.hostname or ''; port = parsed.port
        username = unquote(parsed.username or ''); password = unquote(parsed.password or '')
        address = ipaddress.IPv4Address(host)
        if (parsed.scheme != 'http' or not address.is_global or str(address) != host or not port
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or not 1 <= len(username) <= 256 or not 1 <= len(password) <= 256
                or any(ord(c) < 32 for c in username + password) or not is_safe_url(f'http://{host}:{port}')):
            raise ValueError('url')
    except (TypeError, ValueError):
        raise ValueError('A bounded authenticated public static IPv4 URL is required') from None
    row = {'_id': f'webshare:{plan_id}:{resource_id}', 'workspace_id': workspace_id,
        'last_workspace_id': workspace_id, 'provider': 'webshare_plan', 'provider_plan_id': plan_id,
        'provider_resource_id': resource_id, 'provider_order_id': provider_order_id, 'country_code': country_code,
        'host': host, 'port': port, 'username': username, 'expires_at': expires_at, 'status': 'available',
        'verified_by': verified_by, 'evidence_digest': evidence_digest, 'dedicated_isp_confirmed': True,
        'managed_webshare_version': 1, 'verified_at': now, 'created_at': now,
        'provider_auto_renew_confirmed': False}
    row['request_digest'] = canonical_hash({key: value for key, value in row.items()
        if key not in ('verified_at', 'created_at', 'status', 'provider_auto_renew_confirmed')})
    captured_policy = policy()

    async def inspect(current):
        raw, options = raw_options(current)
        existing = await raw.outreach_proxy_inventory.find_one({'_id': row['_id']}, **options)
        if existing:
            if (existing.get('request_digest') != row['request_digest']
                    or not await managed_webshare_valid(current, existing, workspace_id, now=now)):
                raise ValueError('Existing proxy needs drained review; import cannot replace it')
            return existing
        if not await require_ip_binding(current, row, workspace_id, claim=True):
            raise ValueError('Physical IP is already assigned to another managed resource')
        return None

    # Prove transaction/tenant availability before any key call. Claim and insert
    # are repeated together below; this preflight retains exclusion on seal failure.
    existing = await suppression.mutate_suppression(db, workspace_id, inspect)
    if existing:
        return _result(existing, 'already_imported')
    row.update(await seal_proxy_password(password, row, workspace_id))
    if captured_policy != policy():
        raise ValueError('Proxy custody configuration changed')
    row['import_basis_digest'] = _basis(row)

    async def insert(current):
        if captured_policy != policy():
            raise ValueError('Proxy custody configuration changed')
        saved = await inspect(current)
        if saved:
            return _result(saved, 'already_imported')
        await current.outreach_proxy_inventory.insert_one(row)
        return _result(row, 'imported')
    return await suppression.mutate_suppression(db, workspace_id, insert)


def _result(row: dict, status: str) -> dict:
    return {'proxy_id': row['_id'], 'provider': row['provider'], 'country_code': row['country_code'],
            'expires_at': row['expires_at'], 'status': status, 'provenance': 'manual_operator_verified'}
