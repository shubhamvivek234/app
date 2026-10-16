"""Versioned literal stored-field checks shared by authoring, preview and workers."""
from __future__ import annotations

import math
import re
from bson.int64 import Int64
from typing import Any

from outreach.core.sequence_contract import DAGValidationError

FIELDS = frozenset({'first_name', 'last_name', 'company_name', 'job_title', 'location', 'country_code', 'email', 'phone'})
KEY = re.compile(r'custom_variables\.[A-Za-z_][A-Za-z0-9_]{0,99}\Z')
SAFE_NUMBER = 2**53 - 1
# Explicit Unicode White_Space set, identical in preview and stored evaluation.
WHITESPACE = '\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
MISSING = object()


def field_allowed(field: Any) -> bool:
    return isinstance(field, str) and (field in FIELDS or bool(KEY.fullmatch(field)))


def scalar_type(value: Any) -> str | None:
    if type(value) is str and len(value) <= 1000:
        try:
            value.encode('utf-8')
        except UnicodeError:
            return None
        return 'text'
    if type(value) is bool:
        return 'boolean'
    if type(value) in (int, float, Int64) and abs(value) <= SAFE_NUMBER and math.isfinite(value):
        return 'number'
    return None


def validate_config(config: Any) -> dict:
    if (not isinstance(config, dict) or type(config.get('condition_contract_version')) is not int
            or config['condition_contract_version'] != 1 or not field_allowed(config.get('field'))
            or config.get('operator') not in ('has_value', 'equals', 'not_equals')):
        raise DAGValidationError('Stored-field conditions require an explicit version, allowed field and operator.')
    keys = {'condition_contract_version', 'field', 'operator'}
    if config['operator'] != 'has_value':
        keys |= {'value_type', 'value'}
        kind = config.get('value_type')
        if (kind not in ('text', 'number', 'boolean') or scalar_type(config.get('value')) != kind
                or config['field'] in FIELDS and kind != 'text'):
            raise DAGValidationError('Condition comparisons require a bounded value of the declared type; standard fields use text.')
    if set(config) != keys:
        raise DAGValidationError('Condition configuration contains missing or unsupported settings.')
    return config


def evaluate(config: dict, lead: dict) -> dict:
    """No normalization, rendering fallback, provider verification or truthiness."""
    validate_config(config)
    field = config['field']
    if field in FIELDS:
        value = lead.get(field, MISSING)
    else:
        custom = lead.get('custom_variables', MISSING)
        if custom is MISSING:
            value = MISSING
        elif not isinstance(custom, dict):
            return {'condition_met': None, 'reason': 'malformed_custom_fields'}
        else:
            value = custom.get(field.split('.', 1)[1], MISSING)
    absent = 'missing' if value is MISSING else 'null' if value is None else None
    if absent:
        return {'condition_met': False if config['operator'] == 'has_value' else None, 'reason': absent}
    kind = scalar_type(value)
    if kind is None or field in FIELDS and kind != 'text':
        return {'condition_met': None, 'reason': 'unsupported_value'}
    if config['operator'] == 'has_value':
        reason = 'empty' if value == '' else 'blank' if kind == 'text' and not value.strip(WHITESPACE) else 'present'
        return {'condition_met': reason == 'present', 'reason': reason}
    if kind != config['value_type']:
        return {'condition_met': None, 'reason': 'type_mismatch'}
    equal = value == config['value']
    return {'condition_met': equal if config['operator'] == 'equals' else not equal, 'reason': 'compared'}


def validate_samples(values: Any) -> None:
    if not isinstance(values, dict) or len(values) > 9 or set(values) - FIELDS - {'custom_variables'}:
        raise DAGValidationError('Condition samples require supported stored fields.')
    for key, value in values.items():
        if key == 'custom_variables':
            if (not isinstance(value, dict) or len(value) > 50
                    or any(not field_allowed('custom_variables.' + k) or v is not None and scalar_type(v) is None for k, v in value.items())):
                raise DAGValidationError('Custom condition samples require up to 50 bounded scalar values.')
        elif value is not None and scalar_type(value) != 'text':
            raise DAGValidationError('Standard condition samples require bounded text or null.')
