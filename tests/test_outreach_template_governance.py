"""Native template review is a precondition, never deletion authority itself."""
from copy import deepcopy
from datetime import datetime, timezone

from bson import Int64, ObjectId
from fastapi import HTTPException
import pytest

from outreach.core.template_governance import deletion_precondition, template_review


def record():
    return {"_id": ObjectId(), "workspace_id": "workspace", "user_id": "creator",
            "id": "tpl_custom_012345abcd", "is_custom": True, "name": "Starter",
            "nodes": [{"id": "a", "type": "send_email"}], "edges": [],
            "created_at": datetime(2026, 10, 16, tzinfo=timezone.utc)}


def test_review_does_not_mutate_source_or_authorize_any_operation():
    row=record();before=deepcopy(row)
    review=template_review(row,"workspace")
    assert review["reviewable"] is True and review["revision"]==0
    assert review["execution_authorized"] is False and review["deletion_authorized"] is False
    assert len(review["review_digest"])==64 and row==before


@pytest.mark.parametrize("changes", [
    {"_id":None},{"_id":[]},{"_id":" "},{"workspace_id":["workspace"]},{"workspace_id":"other"},
    {"id":["tpl_custom_012345abcd"]},{"id":"tpl_connect_and_follow_up"},
    {"is_custom":1},{"user_id":[]},{"user_id":" "*200+"actor"},{"template_revision":True},
    {"template_revision":-1},{"template_revision":2**53},{"template_revision":1.0},
])
def test_ambiguous_or_unsupported_native_records_are_review_only(changes):
    row={**record(),**changes};result=template_review(row,"workspace")
    assert result["reviewable"] is False and result["review_digest"] is None
    assert result["deletion_authorized"] is False


@pytest.mark.parametrize("change", ["native","name","graph","creator","revision","new_field"])
def test_review_cannot_be_reused_for_replaced_or_changed_records(change):
    row=record();review=template_review(row,"workspace");changed=deepcopy(row)
    if change=="native":changed["_id"]=ObjectId()
    elif change=="graph":changed["nodes"][0]["type"]="visit_profile"
    elif change=="creator":changed["user_id"]="replacement"
    elif change=="revision":changed["template_revision"]=1
    elif change=="new_field":changed["future_metadata"]="changed"
    else:changed["name"]="Renamed"
    with pytest.raises(HTTPException) as caught:
        deletion_precondition(changed,"workspace",review["revision"],review["review_digest"])
    assert caught.value.status_code==409


def test_native_integer_representation_and_revision_presence_are_not_conflated():
    row=record();row["template_revision"]=1
    reviewed=template_review(row,"workspace")
    changed={**row,"template_revision":Int64(1)}
    assert template_review(changed,"workspace")["review_digest"]!=reviewed["review_digest"]
    assert template_review(changed,"workspace")["revision"]==1


def test_precondition_uses_literal_full_record_and_native_scope():
    row=record();row['future_metadata']={'$ne':'literal data'}
    review=template_review(row,"workspace")
    query=deletion_precondition(row,"workspace",0,review["review_digest"])
    assert query["_id"]==row["_id"] and query["workspace_id"]=="workspace"
    assert query["$expr"]=={"$eq":["$$ROOT",{"$literal":row}]}


@pytest.mark.parametrize("revision,digest", [(True,"a"*64),(1.0,"a"*64),(-1,"a"*64),(0,"bad"),(0,None)])
def test_client_review_fields_are_strict(revision,digest):
    with pytest.raises(HTTPException) as caught:deletion_precondition(record(),"workspace",revision,digest)
    assert caught.value.status_code==422


@pytest.mark.parametrize('payload',[{'bad':object()},{1:'invalid key'},{'nul\x00key':'invalid'}])
def test_malformed_bson_is_unavailable(payload):
    row=record();row['metadata']=payload
    assert template_review(row,'workspace')['reviewable'] is False


def test_cas_literal_is_a_capture_not_a_mutable_source_alias():
    row=record();review=template_review(row,'workspace')
    query=deletion_precondition(row,'workspace',0,review['review_digest'])
    before=deepcopy(query)
    row['nodes'][0]['type']='visit_profile';row['name']='changed'
    assert query==before


def test_oversized_full_bson_record_never_becomes_reviewable():
    from outreach.core.template_governance import MAX_RECORD_BYTES
    row=record();row['metadata']='x'*(MAX_RECORD_BYTES+1)
    assert template_review(row,'workspace')['reviewable'] is False


@pytest.mark.asyncio
async def test_reviewed_url_cannot_invoke_the_older_unreviewed_handler():
    import httpx
    from fastapi import FastAPI
    app=FastAPI();calls=[]
    @app.delete('/sequences/templates/{identifier}')
    async def older_handler(identifier:str):
        calls.append(identifier);return {'status':'success'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as api:
        result=await api.request('DELETE','/sequences/templates/tpl_custom_012345abcd/reviewed',json={'contract_version':1})
    assert result.status_code==404 and calls==[]
