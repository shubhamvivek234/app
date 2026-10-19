"""Rollout defaults and strict caller-owned snapshot admission."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from bson import ObjectId
import pytest
from fastapi import HTTPException

from outreach.core import template_mutation_snapshots as snapshots
from tests.test_outreach_template_revision_checkpoints import record

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


@pytest.mark.parametrize('value,expected', [(None, False), ('false', False), ('true', True)])
def test_server_capture_setting_has_explicit_default(monkeypatch, value, expected):
    monkeypatch.delenv(snapshots.SETTING, raising=False)
    if value is not None:
        monkeypatch.setenv(snapshots.SETTING, value)
    assert snapshots.capture_enabled() is expected


@pytest.mark.parametrize('value', ['', '1', '0', 'TRUE', 'false ', 'enabled'])
def test_invalid_setting_holds_instead_of_silently_disabling_capture(monkeypatch, value):
    monkeypatch.setenv(snapshots.SETTING, value)
    with pytest.raises(HTTPException) as caught:
        snapshots.capture_enabled()
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_disabled_hook_never_observes_storage_keys_or_transaction(monkeypatch):
    monkeypatch.delenv(snapshots.SETTING, raising=False)
    assert await snapshots.capture_mutation(object(), (), 'actor', 'uid', None, event='created') is None


@pytest.mark.asyncio
async def test_enabled_hook_rejects_an_unowned_transaction(monkeypatch):
    monkeypatch.setenv(snapshots.SETTING, 'true')
    with pytest.raises(HTTPException) as caught:
        await snapshots.capture_mutation(object(), (), 'actor', 'uid', None, event='created')
    assert caught.value.status_code == 409


@pytest.mark.parametrize('fault', ['list', 'empty', 'extra_image', 'event_type', 'unknown_event',
    'timestamp_type', 'timestamp_precision', 'timestamp_zone', 'nondict', 'native_type',
    'workspace_type', 'workspace_mismatch', 'public_type', 'creator_type', 'revision_type',
    'new_creation_revision', 'replacement_native', 'replacement_public', 'skipped_revision'])
def test_internal_transition_contract_rejects_ambiguous_images(fault):
    first = record(1)
    sources = (first,)
    event, timestamp = 'created', NOW
    if fault == 'list': sources = [first]
    elif fault == 'empty': sources = ()
    elif fault == 'extra_image': sources = (first, first)
    elif fault == 'event_type': event = None
    elif fault == 'unknown_event': event = 'restored'
    elif fault == 'timestamp_type': timestamp = NOW.isoformat()
    elif fault == 'timestamp_precision': timestamp = NOW.replace(microsecond=1)
    elif fault == 'timestamp_zone': timestamp = NOW.astimezone(timezone(timedelta(hours=1)))
    elif fault == 'nondict': sources = (None,)
    elif fault == 'native_type': first['_id'] = ['alias']
    elif fault == 'workspace_type': first['workspace_id'] = ['workspace']
    elif fault == 'workspace_mismatch': first['workspace_id'] = 'foreign'
    elif fault == 'public_type': first['id'] = ['tpl_custom_012345abcd']
    elif fault == 'creator_type': first['user_id'] = ['creator']
    elif fault == 'revision_type': first['template_revision'] = True
    elif fault == 'new_creation_revision': first['template_revision'] = 2
    else:
        second = deepcopy(first); second['template_revision'] = 2
        sources, event = (first, second), 'metadata'
        if fault == 'replacement_native': second['_id'] = ObjectId()
        elif fault == 'replacement_public': second['id'] = 'tpl_custom_ffffffffff'
        else: second['template_revision'] = 3
    with pytest.raises(HTTPException) as caught:
        snapshots._reviews(SimpleNamespace(workspace_id='workspace'), sources, timestamp, event)
    assert caught.value.status_code == 409
