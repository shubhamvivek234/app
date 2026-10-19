"""Terminal deletion digests bind the original without advancing its revision."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from bson import Code, Int64
from fastapi import HTTPException
import pytest

from outreach.core import template_revision_checkpoints as checkpoints
from outreach.core.authorization import canonical_hash
from outreach.core.suppression import SuppressionDatabase
from outreach.core.template_governance import MAX_REVISION
from tests.test_outreach_template_revision_checkpoints import record

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


@pytest.mark.parametrize('revision',[0,1,MAX_REVISION])
def test_terminal_keeps_original_revision_and_exact_parent_without_content(revision):
    row = record(revision); baseline = checkpoints.checkpoint_for(row,'actor',NOW)
    terminal = checkpoints.deletion_checkpoint_for(row,'actor',NOW)
    assert terminal['event'] == 'deleted' and terminal['revision'] == terminal['predecessor_revision'] == revision
    assert terminal['predecessor_review_digest'] == baseline['review_digest']
    assert terminal['review_digest'] != baseline['review_digest'] and terminal['_id'] != baseline['_id']
    expected = canonical_hash(['template-deletion-result-v1','workspace',row['id'],baseline['identity_digest'],revision,baseline['review_digest']])
    assert terminal['review_digest'] == expected and len(terminal) == 12
    assert not {'name','description','nodes','edges','firebase_uid','content_json'} & terminal.keys()
    assert checkpoints.validate_checkpoint(terminal,'workspace',row['id'],baseline['identity_digest'],revision) == terminal


@pytest.mark.parametrize('change',[{'_id':'a'*64},{'review_digest':'b'*64},
    {'predecessor_review_digest':'c'*64},{'predecessor_revision':0},{'predecessor_revision':True},
    {'revision':True},{'revision':1.0},{'event':Code('deleted')},{'recorded_by':Code('actor')},
    {'recorded_at':NOW.replace(microsecond=1)},{'workspace_id':'other'},{'extra':'field'}])
def test_terminal_schema_id_and_result_digest_cannot_be_reinterpreted(change):
    row = record(1); terminal = checkpoints.deletion_checkpoint_for(row,'actor',NOW)
    with pytest.raises(HTTPException):
        checkpoints.validate_checkpoint({**terminal,**change},'workspace',row['id'],terminal['identity_digest'],1)


def test_native_int64_revision_is_preserved_in_original_record_digest():
    row = record(1)
    ordinary = checkpoints.deletion_checkpoint_for(row,'actor',NOW)
    native = checkpoints.deletion_checkpoint_for({**row,'template_revision':Int64(1)},'actor',NOW)
    assert native['revision'] == ordinary['revision'] == 1 and native['identity_digest'] == ordinary['identity_digest']
    assert native['predecessor_review_digest'] != ordinary['predecessor_review_digest']
    assert native['review_digest'] != ordinary['review_digest']


def test_terminal_builder_cannot_hide_a_different_native_identity():
    from bson import ObjectId
    row = record(0)
    first = checkpoints.deletion_checkpoint_for(row,'actor',NOW)
    second = checkpoints.deletion_checkpoint_for({**row,'_id':ObjectId()},'actor',NOW)
    assert first['_id'] != second['_id'] and first['identity_digest'] != second['identity_digest']


@pytest.mark.asyncio
async def test_deletion_append_requires_active_guard_before_database_access():
    db = MagicMock(); current = SuppressionDatabase(db,'workspace',SimpleNamespace(in_transaction=False))
    with pytest.raises(HTTPException):
        await checkpoints.append_deletion_checkpoints(current,record(1),'actor',NOW)
    assert db.mock_calls == []
