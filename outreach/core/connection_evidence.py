"""Bounded recorded person-membership evidence, never invitation causality."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import re
from typing import Any
from outreach.core.sequence_contract import bounded_json, DAGValidationError


def recipient_key(value: Any) -> tuple[str, str] | None:
    """Only known person URNs; vanity labels cannot stand in for identity."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'urn:li:(fsd_profile|fs_miniProfile):([A-Za-z0-9_-]{1,180})', value)
    if match:
        return ('profile', match.group(2))
    match = re.fullmatch(r'urn:li:member:([0-9]{1,20})', value)
    return ('member', match.group(1)) if match else None


def parse_connection_page(data: Any, recipient: str) -> bool | None:
    """Exact observed presence or complete-page absence; otherwise unknown.

    This supported schema is intentionally narrow. It is not verified provider
    API coverage, authenticated completeness, acceptance time or invite proof.
    """
    target = recipient_key(recipient)
    if target is None:
        return None
    try:
        bounded_json(data)
    except DAGValidationError:
        return None
    if not isinstance(data, dict) or set(data) - {'elements', 'paging'}:
        return None
    rows, paging = data.get('elements'), data.get('paging')
    if (not isinstance(rows, list) or len(rows) > 1000 or not isinstance(paging, dict)
            or set(paging) != {'start', 'total', 'count'}):
        return None
    start, total, count = (paging.get(key) for key in ('start', 'total', 'count'))
    if (type(start) is not int or start != 0 or type(total) is not int or total < len(rows)
            or type(count) is not int or not 1 <= count <= 1000 or len(rows) > count):
        return None
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'entityUrn', 'profileUrn', 'memberUrn', 'miniProfile', 'publicIdentifier'}:
            return None
        if 'publicIdentifier' in row and (not isinstance(row['publicIdentifier'], str) or len(row['publicIdentifier']) > 200):
            return None
        values = [row[key] for key in ('entityUrn', 'profileUrn', 'memberUrn') if key in row]
        if 'miniProfile' in row:
            mini = row['miniProfile']
            if not isinstance(mini, dict) or set(mini) - {'entityUrn', 'publicIdentifier'}:
                return None
            if 'publicIdentifier' in mini and (not isinstance(mini['publicIdentifier'], str) or len(mini['publicIdentifier']) > 200):
                return None
            if 'entityUrn' in mini:
                values.append(mini['entityUrn'])
        typed = [recipient_key(value) for value in values]
        if not typed or None in typed or len(set(typed)) != 1 or typed[0] in identities:
            return None
        identities.add(typed[0])
    if target in identities:
        return True
    return False if total == len(rows) else None
