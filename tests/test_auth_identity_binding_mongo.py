"""Shared identity recovery against an owned replica; no auth/provider requests."""
import asyncio
import os

import pytest
from fastapi import HTTPException

from api.deps import _bootstrap_user_from_claims
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_auth_identity_binding import CLAIMS, USER

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]


async def test_email_mismatch_cannot_change_or_return_an_existing_profile(replica_db):
    await replica_db.users.insert_one(dict(USER)); before = await replica_db.users.find_one({})
    with pytest.raises(HTTPException): await _bootstrap_user_from_claims(replica_db, CLAIMS)
    assert await replica_db.users.find_one({}) == before


@pytest.mark.parametrize('stored', ['missing', None, ''])
async def test_verified_legacy_link_is_native_fenced_and_returns_no_native_id(replica_db, stored):
    row = dict(USER)
    if stored == 'missing': row.pop('firebase_uid')
    else: row['firebase_uid'] = stored
    await replica_db.users.insert_one(row)
    result = await _bootstrap_user_from_claims(replica_db, CLAIMS)
    assert result['firebase_uid'] == CLAIMS['uid'] and '_id' not in result
    saved = await replica_db.users.find_one({})
    assert saved['_id'] == USER['_id'] and saved['display_name'] == CLAIMS['name']


async def test_two_verified_identities_cannot_relink_the_same_legacy_record(replica_db):
    row = dict(USER); row.pop('firebase_uid'); await replica_db.users.insert_one(row)
    results = await asyncio.gather(*(_bootstrap_user_from_claims(replica_db, {**CLAIMS, 'uid': uid})
        for uid in ['uid-one', 'uid-two']), return_exceptions=True)
    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum(isinstance(value, HTTPException) for value in results) == 1
    winner = next(value for value in results if isinstance(value, dict))
    assert (await replica_db.users.find_one({}))['firebase_uid'] == winner['firebase_uid']
    assert await replica_db.users.count_documents({}) == 1


async def test_current_uid_change_between_read_and_profile_write_is_not_overwritten(replica_db, monkeypatch):
    row = {**USER, 'firebase_uid': CLAIMS['uid']}; await replica_db.users.insert_one(row)
    collection_type = type(replica_db.users); original = collection_type.update_one
    async def race(collection, query, update, **options):
        if collection.database.name == replica_db.name and collection.name == 'users':
            await original(collection, {'_id': USER['_id']}, {'$set': {'firebase_uid': 'other-uid'}})
        return await original(collection, query, update, **options)
    monkeypatch.setattr(collection_type, 'update_one', race)
    with pytest.raises(HTTPException) as failure: await _bootstrap_user_from_claims(replica_db, CLAIMS)
    assert failure.value.status_code == 409
    saved = await replica_db.users.find_one({})
    assert saved['firebase_uid'] == 'other-uid' and saved['display_name'] == USER['display_name']


async def test_actual_duplicate_email_insert_recovery_cannot_adopt_another_uid(replica_db, monkeypatch):
    await replica_db.users.create_index('email', unique=True)
    await replica_db.users.insert_one(dict(USER)); before = await replica_db.users.find_one({})
    collection_type = type(replica_db.users); original = collection_type.find_one; reads = []
    async def miss_initial(collection, query, *args, **options):
        if collection.database.name == replica_db.name and collection.name == 'users' and len(reads) < 2:
            reads.append(query); return None
        return await original(collection, query, *args, **options)
    monkeypatch.setattr(collection_type, 'find_one', miss_initial)
    with pytest.raises(HTTPException): await _bootstrap_user_from_claims(replica_db, CLAIMS)
    assert await replica_db.users.find_one({}) == before
    assert await replica_db.users.count_documents({}) == 1
