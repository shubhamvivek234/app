"""Verified identity never adopts another UID's email-matched profile."""
from copy import deepcopy

from bson import Code
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
import pytest

from api.deps import _bootstrap_user_from_claims
from tests.outreach_memory import Collection, Database

CLAIMS = {'uid': 'verified-uid', 'email': 'same@example.invalid', 'email_verified': True, 'name': 'Current name'}
USER = {'_id': 'native-user', 'user_id': 'u', 'email': CLAIMS['email'], 'firebase_uid': 'prior-uid',
    'display_name': 'Original name', 'email_verified': False}


@pytest.fixture(autouse=True)
def majority_transport_adapter(monkeypatch):
    # Preserve erasure lookup semantics; this fake has no physical read concern.
    monkeypatch.setattr(Collection, 'with_options', lambda self, **options: self, raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('stored', ['prior-uid', ['verified-uid'], Code('verified-uid'), False, 0])
async def test_email_or_uid_alias_cannot_return_or_update_a_different_identity(stored):
    row = {**USER, 'firebase_uid': stored}; db = Database(users=[row]); before = deepcopy(db.users.docs)
    with pytest.raises(HTTPException):
        await _bootstrap_user_from_claims(db, CLAIMS)
    assert db.users.docs == before


@pytest.mark.asyncio
@pytest.mark.parametrize('uid', [None, '', ' ', ['verified-uid'], Code('verified-uid')])
async def test_unproven_verified_claim_uid_is_denied_before_any_profile_change(uid):
    db = Database(users=[USER]); before = deepcopy(db.users.docs)
    with pytest.raises(HTTPException):
        await _bootstrap_user_from_claims(db, {**CLAIMS, 'uid': uid})
    assert db.users.docs == before


@pytest.mark.asyncio
async def test_valid_existing_uid_updates_its_own_profile():
    db = Database(users=[{**USER, 'firebase_uid': CLAIMS['uid']}])
    result = await _bootstrap_user_from_claims(db, CLAIMS)
    assert result['firebase_uid'] == CLAIMS['uid'] and result['display_name'] == CLAIMS['name']


@pytest.mark.asyncio
@pytest.mark.parametrize('stored', ['missing', None, ''])
async def test_verified_email_can_link_an_explicitly_unlinked_legacy_record(stored):
    row = dict(USER)
    if stored == 'missing': row.pop('firebase_uid')
    else: row['firebase_uid'] = stored
    db = Database(users=[row])
    result = await _bootstrap_user_from_claims(db, CLAIMS)
    assert result['firebase_uid'] == CLAIMS['uid'] == db.users.docs[0]['firebase_uid']


@pytest.mark.asyncio
@pytest.mark.parametrize('verified', [False, None, 'true', 1])
async def test_unverified_or_untyped_email_cannot_link_a_legacy_profile(verified):
    row = dict(USER); row.pop('firebase_uid'); db = Database(users=[row]); before = deepcopy(db.users.docs)
    with pytest.raises(HTTPException):
        await _bootstrap_user_from_claims(db, {**CLAIMS, 'email_verified': verified})
    assert db.users.docs == before


@pytest.mark.asyncio
async def test_identity_change_before_profile_write_cannot_be_overwritten(monkeypatch):
    db = Database(users=[{**USER, 'firebase_uid': CLAIMS['uid']}]); original = db.users.update_one
    async def replace_uid(query, update, **options):
        db.users.docs[0]['firebase_uid'] = 'replacement-uid'
        return await original(query, update, **options)
    monkeypatch.setattr(db.users, 'update_one', replace_uid)
    with pytest.raises(HTTPException):
        await _bootstrap_user_from_claims(db, CLAIMS)
    assert db.users.docs[0]['firebase_uid'] == 'replacement-uid'
    assert db.users.docs[0]['display_name'] == USER['display_name']


class CollisionUsers(Collection):
    def __init__(self, recovered):
        super().__init__([recovered]); self.collided = False; self.writes = 0
    async def find_one(self, query=None, projection=None, **options):
        if not self.collided: return None
        return await super().find_one(query, projection, **options)
    async def insert_one(self, row):
        self.collided = True
        raise DuplicateKeyError('synthetic creation collision')
    async def update_one(self, *args, **kwargs):
        self.writes += 1
        return await super().update_one(*args, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('matching', [False, True])
async def test_creation_race_recovery_requires_the_same_verified_uid(matching):
    row = {**USER, 'firebase_uid': CLAIMS['uid'] if matching else 'prior-uid'}
    db = Database(); db.collections['users'] = CollisionUsers(row)
    if matching:
        result = await _bootstrap_user_from_claims(db, CLAIMS)
        assert result['firebase_uid'] == CLAIMS['uid']
    else:
        with pytest.raises(HTTPException): await _bootstrap_user_from_claims(db, CLAIMS)
        assert db.users.docs[0]['display_name'] == USER['display_name']
        assert db.users.writes == 0
