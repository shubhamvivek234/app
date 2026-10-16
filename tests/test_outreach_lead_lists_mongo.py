"""Actual guarded list identity/membership/backfill; no duplicate enrollment authority."""
import asyncio
import os
import uuid

from fastapi import FastAPI, HTTPException
import httpx
from pymongo.errors import DuplicateKeyError
import pytest

from api.deps import get_current_user
from db.indexes import ensure_lead_list_indexes
from db.mongo import get_db
from outreach.api.lead_lists import router
from outreach.core import lead_lists as lists
from outreach.core.suppression import SuppressionCollection
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Owned native Mongo is opt-in")]


async def seed(db, count=2):
    await ensure_lead_list_indexes(db)
    await db.outreach_campaigns.insert_one({"id": "campaign", "workspace_id": "w", "status": "draft",
        "authorization_revision": 0, "leads_count": count})
    if count:
        await db.outreach_leads.insert_many([{"id": f"lead-{i:03d}", "workspace_id": "w", "campaign_id": "campaign",
            "first_name": "Person", "execution_state": "queued", "authorized_revision": 0} for i in range(count)])


async def create(db, name="Audience"):
    return await lists.create_list(db, "w", "actor", "campaign", name, str(uuid.uuid4()))


async def test_two_lists_share_one_native_enrollment_without_execution_changes(replica_db):
    await seed(replica_db)
    original = await replica_db.outreach_leads.find({}).to_list(10)
    one, two = await create(replica_db, "First"), await create(replica_db, "Second")
    for row in (one, two):
        assert (await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000"], "add"))["modified_count"] == 1
        page = await lists.members(replica_db, "w", row["id"])
        assert page["membership_count"] == 1 and page["members"][0]["status"] == "available"
        assert not page["membership_controls_execution"] and not page["complete_collection"]
    assert await replica_db.outreach_leads.find({}).to_list(10) == original
    assert await replica_db.outreach_tasks.count_documents({}) == 0
    assert await replica_db.outreach_sequence_jobs.count_documents({}) == 0
    assert (await replica_db.outreach_campaigns.find_one({"id": "campaign"}))["authorization_revision"] == 0


async def test_create_retry_preserves_original_identity_and_rejects_changed_body(replica_db):
    await seed(replica_db)
    request = str(uuid.uuid4())
    original = await lists.create_list(replica_db, "w", "actor", "campaign", "Audience", request)
    assert await lists.create_list(replica_db, "w", "actor", "campaign", "Audience", request) == original
    with pytest.raises(HTTPException) as failure:
        await lists.create_list(replica_db, "w", "actor", "campaign", "Different", request)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_lead_lists.count_documents({}) == 1


async def test_concurrent_normalized_names_have_one_winner(replica_db):
    await seed(replica_db)
    results = await asyncio.gather(create(replica_db, "  Hot   LEADS "), create(replica_db, "hot leads"), return_exceptions=True)
    assert sum(isinstance(row, dict) for row in results) == 1
    assert sum(isinstance(row, HTTPException) and row.status_code == 409 for row in results) == 1


async def test_archive_and_remove_do_not_delete_or_pause_enrollment(replica_db):
    await seed(replica_db)
    original = await replica_db.outreach_leads.find_one({"id": "lead-000"})
    row = await create(replica_db)
    await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000"], "add")
    await lists.change_members(replica_db, "w", "actor", row["id"], 2, ["lead-000"], "remove")
    archived = await lists.edit_list(replica_db, "w", row["id"], 3, archive=True)
    assert archived["archived"] and (await lists.inventory(replica_db, "w", "campaign"))["lists"] == []
    assert len((await lists.inventory(replica_db, "w", "campaign", True))["lists"]) == 1
    assert await replica_db.outreach_leads.find_one({"id": "lead-000"}) == original
    with pytest.raises(HTTPException): await lists.change_members(replica_db, "w", "actor", row["id"], 4, ["lead-000"], "add")


async def test_stale_revision_cannot_change_membership(replica_db):
    await seed(replica_db)
    row = await create(replica_db)
    await lists.edit_list(replica_db, "w", row["id"], 1, name="Renamed")
    with pytest.raises(HTTPException): await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000"], "add")
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 0


async def test_existing_membership_retry_is_metadata_only_and_idempotent(replica_db):
    await seed(replica_db)
    row = await create(replica_db)
    await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000"], "add")
    result = await lists.change_members(replica_db, "w", "actor", row["id"], 2, ["lead-000"], "add")
    assert result["modified_count"] == 0 and result["revision"] == 3
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 1


@pytest.mark.parametrize("bad", ["missing", "different_campaign", "foreign", "array_scope", "duplicate"])
async def test_invalid_membership_selection_rolls_back_entire_batch(replica_db, bad):
    await seed(replica_db)
    row = await create(replica_db)
    if bad != "missing":
        record = {"id": "bad", "workspace_id": "w", "campaign_id": "campaign"}
        if bad == "different_campaign": record["campaign_id"] = "other"
        elif bad == "foreign": record["workspace_id"] = "other"
        elif bad == "array_scope": record["workspace_id"] = ["w", "other"]
        await replica_db.outreach_leads.insert_one(record)
        if bad == "duplicate": await replica_db.outreach_leads.insert_one({"id": "bad", "workspace_id": "w", "campaign_id": "campaign"})
    with pytest.raises(HTTPException): await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000", "bad"], "add")
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 0
    assert (await replica_db.outreach_lead_lists.find_one({"id": row["id"]}))["revision"] == 1


async def test_late_write_failure_rolls_back_memberships_and_revision(replica_db, monkeypatch):
    await seed(replica_db)
    row = await create(replica_db)
    original = SuppressionCollection.insert_one
    async def fail(self, document, **kwargs):
        if self.collection.name == "outreach_lead_list_members" and document["lead_id"] == "lead-001":
            raise RuntimeError("Synthetic late membership failure")
        return await original(self, document, **kwargs)
    monkeypatch.setattr(SuppressionCollection, "insert_one", fail)
    with pytest.raises(RuntimeError): await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000", "lead-001"], "add")
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 0


async def test_deleted_and_recreated_public_lead_does_not_inherit_membership(replica_db):
    await seed(replica_db)
    row = await create(replica_db)
    await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000"], "add")
    await replica_db.outreach_leads.delete_one({"id": "lead-000"})
    await replica_db.outreach_leads.insert_one({"id": "lead-000", "workspace_id": "w", "campaign_id": "campaign", "first_name": "Replacement"})
    page = await lists.members(replica_db, "w", row["id"])
    assert page["members"][0]["status"] == "orphaned" and page["members"][0]["contact"] is None
    with pytest.raises(HTTPException): await lists.change_members(replica_db, "w", "actor", row["id"], 2, ["lead-000"], "add")


async def test_search_markers_survive_organizational_membership(replica_db):
    await seed(replica_db)
    await replica_db.outreach_leads.update_one({"id": "lead-000"}, {"$set": {"execution_state": "staged", "import_job_id": "old"}})
    original = await replica_db.outreach_leads.find_one({"id": "lead-000"})
    row = await create(replica_db)
    await lists.change_members(replica_db, "w", "actor", row["id"], 1, ["lead-000"], "add")
    assert (await lists.members(replica_db, "w", row["id"]))["members"][0]["status"] == "source_review"
    assert await replica_db.outreach_leads.find_one({"id": "lead-000"}) == original


async def test_member_pages_have_stable_scoped_positions(replica_db):
    await seed(replica_db, 4)
    row = await create(replica_db)
    await lists.change_members(replica_db, "w", "actor", row["id"], 1, [f"lead-{i:03d}" for i in range(4)], "add")
    first = await lists.members(replica_db, "w", row["id"], limit=2)
    second = await lists.members(replica_db, "w", row["id"], limit=2, after=first["next_cursor"])
    assert len({x["lead_id"] for x in first["members"] + second["members"]}) == 4
    assert second["next_cursor"] is None


async def test_index_conflicts_are_not_deleted_or_hidden(replica_db):
    await seed(replica_db)
    from outreach.core.workspace_scope import workspace_scope
    plan=await replica_db.outreach_leads.find({**workspace_scope('w'),'campaign_id':'campaign',
        'campaign_id.0':{'$exists':False},'id':{'$gt':'lead-000'}}).sort('id',1).limit(100).explain()
    def stages(node):
        if isinstance(node,dict):
            return [node.get('stage','')]+[stage for child in node.values() for stage in stages(child)]
        if isinstance(node,list):
            return [stage for child in node for stage in stages(child)]
        return []
    winning=stages(plan['queryPlanner']['winningPlan'])
    assert any(stage.endswith('IXSCAN') for stage in winning) and 'SORT' not in winning
    row = await create(replica_db)
    stored = await replica_db.outreach_lead_lists.find_one({"id": row["id"]})
    with pytest.raises(DuplicateKeyError): await replica_db.outreach_lead_lists.insert_one({**stored, "_id": "different"})
    await replica_db.outreach_lead_lists.drop_indexes()
    await replica_db.outreach_lead_lists.insert_one({**stored, "_id": "different"})
    with pytest.raises(DuplicateKeyError): await ensure_lead_list_indexes(replica_db)
    assert await replica_db.outreach_lead_lists.count_documents({}) == 2


@pytest.mark.parametrize("status", ["warming_up", "deleted"])
async def test_stopped_parent_boundaries_block_list_mutation(replica_db, status):
    await seed(replica_db)
    await replica_db.outreach_campaigns.update_one({}, {"$set": {"status": status, "is_deleted": status == "deleted"}})
    with pytest.raises(HTTPException): await create(replica_db)
    assert await replica_db.outreach_lead_lists.count_documents({}) == 0


async def test_bounded_deterministic_existing_audience_backfill(replica_db):
    await seed(replica_db, 205)
    original = await replica_db.outreach_leads.find({}).sort("id", 1).to_list(300)
    first = await lists.adopt_existing(replica_db, "w", "operator", "campaign", 0, True)
    assert first["legacy_adoption"] == {"status": "pending", "processed_count": 100}
    second = await lists.adopt_existing(replica_db, "w", "operator", "campaign", first["revision"], True)
    final = await lists.adopt_existing(replica_db, "w", "operator", "campaign", second["revision"], True)
    assert final["legacy_adoption"] == {"status": "selected_scope_complete", "processed_count": 205}
    assert final["source_kind"] == "legacy_unknown" and not final["collection_verified"]
    assert await lists.adopt_existing(replica_db, "w", "operator", "campaign", final["revision"], True) == final
    assert await replica_db.outreach_lead_lists.count_documents({}) == 1
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 205
    assert await replica_db.outreach_leads.find({}).sort("id", 1).to_list(300) == original


@pytest.mark.parametrize("bad", ["duplicate", "array_id", "missing_id", "no_drain"])
async def test_unknown_existing_identity_or_drain_is_not_adopted(replica_db, bad):
    await seed(replica_db)
    if bad == "duplicate": await replica_db.outreach_leads.insert_one({"id": "lead-000", "workspace_id": "w", "campaign_id": "campaign"})
    elif bad in {"array_id", "missing_id"}:
        await replica_db.outreach_leads.insert_one({"workspace_id": "w", "campaign_id": "campaign", **({"id": ["bad"]} if bad == "array_id" else {})})
    with pytest.raises(HTTPException): await lists.adopt_existing(replica_db, "w", "operator", "campaign", 0, bad != "no_drain")
    assert await replica_db.outreach_lead_lists.count_documents({}) == 0
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 0


@pytest.mark.parametrize("role", ["viewer", "editor", "admin"])
async def test_http_roles_and_operator_backfill_permission(replica_db, role):
    await seed(replica_db)
    await replica_db.workspace_members.insert_one({"workspace_id": "w", "user_id": "actor", "role": role})
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "actor", "default_workspace_id": "w"}
    app.dependency_overrides[get_db] = lambda: replica_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get('/lead-lists', params={"campaign_id": "campaign"})).status_code == 200
        response = await client.post('/lead-lists', json={"campaign_id": "campaign", "name": "List", "request_id": str(uuid.uuid4())})
        assert response.status_code == (403 if role == "viewer" else 200)
        result = await client.post('/lead-lists/adopt-existing', json={"campaign_id": "campaign", "revision": 0, "writers_drained": True})
        assert result.status_code == (200 if role == "admin" else 403)


async def test_standalone_cannot_partially_create_lists(real_db):
    await seed(real_db)
    with pytest.raises(HTTPException) as failure: await create(real_db)
    assert failure.value.status_code == 503
    assert await real_db.outreach_lead_lists.count_documents({}) == 0


async def test_http_edit_member_archive_routes_keep_execution_separate(replica_db):
    await seed(replica_db)
    await replica_db.workspace_members.insert_one({"workspace_id": "w", "user_id": "actor", "role": "admin"})
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "actor", "default_workspace_id": "w"}
    app.dependency_overrides[get_db] = lambda: replica_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        row = (await client.post('/lead-lists', json={"campaign_id": "campaign", "name": "Audience", "request_id": str(uuid.uuid4())})).json()
        path = '/lead-lists/' + row['id']
        renamed = await client.patch(path, json={"name": "Renamed", "revision": 1, "review_digest": row["review_digest"]})
        assert renamed.status_code == 200
        assert (await client.post(path+'/members', json={"lead_ids": ["lead-000"], "operation": "add", "revision": 2, "review_digest": renamed.json()["review_digest"]})).status_code == 200
        page = (await client.get(path+'/members')).json()
        assert page['membership_count'] == 1
        assert (await client.post(path+'/archive', json={"revision": 3, "review_digest": page["list"]["review_digest"]})).status_code == 200
    assert (await replica_db.outreach_leads.find_one({"id": "lead-000"}))['execution_state'] == 'queued'


@pytest.mark.parametrize('scope', ['foreign', ['w', 'foreign'], None])
async def test_foreign_or_ambiguous_list_scope_never_grants_access(replica_db, scope):
    await seed(replica_db)
    row = await create(replica_db)
    await replica_db.outreach_lead_lists.update_one({'id':row['id']},{'$set':{'workspace_id':scope}})
    with pytest.raises(HTTPException) as failure: await lists.members(replica_db,'w',row['id'])
    assert failure.value.status_code == 404
    with pytest.raises(HTTPException): await lists.change_members(replica_db,'w','actor',row['id'],1,['lead-000'],'add')
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 0


async def test_membership_records_store_scalar_references_without_query_operators(replica_db):
    await seed(replica_db)
    row=await create(replica_db)
    await lists.change_members(replica_db,'w','actor',row['id'],1,['lead-000'],'add')
    stored=await replica_db.outreach_lead_list_members.find_one({})
    assert all('.' not in key and not key.startswith('$') for key in stored)
    assert all(isinstance(stored[key],str) for key in ('workspace_id','campaign_id','list_id','lead_id','lead_native_digest'))


async def test_deleted_campaign_hides_retained_list_metadata(replica_db):
    await seed(replica_db)
    row=await create(replica_db)
    await replica_db.outreach_campaigns.update_one({},{'$set':{'is_deleted':True}})
    with pytest.raises(HTTPException): await lists.members(replica_db,'w',row['id'])
    with pytest.raises(HTTPException): await lists.inventory(replica_db,'w','campaign')
    assert await replica_db.outreach_lead_lists.count_documents({}) == 1


async def test_list_collections_join_existing_workspace_erasure_inventory(replica_db):
    from outreach.core.erasure import DATA_COLLECTIONS
    assert 'outreach_lead_lists' in DATA_COLLECTIONS and 'outreach_lead_list_members' in DATA_COLLECTIONS
    await seed(replica_db)
    row=await create(replica_db)
    await lists.change_members(replica_db,'w','actor',row['id'],1,['lead-000'],'add')
    from outreach.core.erasure import OutreachErasure, _control
    for name in ('outreach_lead_lists','outreach_lead_list_members'):
        await replica_db[name].insert_one({'workspace_id':'other','id':'foreign'})
        async def erase(current):
            return await OutreachErasure(replica_db)._erase_batch(current, 'w', name)
        assert await _control(replica_db, 'w', erase)
        assert await replica_db[name].count_documents({'workspace_id':'w'}) == 0
        assert await replica_db[name].count_documents({'workspace_id':'other'}) == 1


async def test_corrupt_checkpoint_does_not_advance_or_adopt(replica_db):
    await seed(replica_db,101)
    row=await lists.adopt_existing(replica_db,'w','operator','campaign',0,True)
    await replica_db.outreach_lead_lists.update_one({'id':row['id']},{'$set':{'migration.cursor':['wrong']}})
    with pytest.raises(HTTPException): await lists.adopt_existing(replica_db,'w','operator','campaign',row['revision'],True)
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 100


@pytest.mark.parametrize('field,value', [('id','f'*64),('lead_native_digest','bad')])
async def test_corrupt_membership_identity_denies_read_and_reuse(replica_db,field,value):
    await seed(replica_db)
    row=await create(replica_db)
    await lists.change_members(replica_db,'w','actor',row['id'],1,['lead-000'],'add')
    await replica_db.outreach_lead_list_members.update_one({},{'$set':{field:value}})
    with pytest.raises(HTTPException): await lists.members(replica_db,'w',row['id'])
    with pytest.raises(HTTPException): await lists.change_members(replica_db,'w','actor',row['id'],2,['lead-000'],'add')
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 1


@pytest.mark.parametrize('change',[{'source_kind':[]},{'collection_state':'verified'},{'campaign_id':['campaign']},
    {'requested_limit':2500},{'source_fingerprint':'https://example.invalid/secret'}])
async def test_malformed_list_catalog_cannot_be_called_a_supported_source(replica_db,change):
    await seed(replica_db)
    row=await create(replica_db)
    await replica_db.outreach_lead_lists.update_one({'id':row['id']},{'$set':change})
    with pytest.raises(HTTPException): await lists.members(replica_db,'w',row['id'])


@pytest.mark.parametrize('checkpoint',[{'processed_count':-1},{'upper_bound':None},{'cursor':'z'*200},
    {'cursor':None},{'status':[]}])
async def test_checkpoint_contradictions_cannot_fabricate_completion(replica_db,checkpoint):
    await seed(replica_db,101)
    row=await lists.adopt_existing(replica_db,'w','operator','campaign',0,True)
    await replica_db.outreach_lead_lists.update_one({'id':row['id']},{'$set':{'migration.'+key:value for key,value in checkpoint.items()}})
    with pytest.raises(HTTPException): await lists.adopt_existing(replica_db,'w','operator','campaign',row['revision'],True)
    assert await replica_db.outreach_lead_list_members.count_documents({}) == 100


async def test_parent_warmup_race_revalidates_before_list_commit(replica_db,monkeypatch):
    await seed(replica_db)
    entered,release=asyncio.Event(),asyncio.Event()
    original=SuppressionCollection.update_one
    intercepted=False
    async def pause(self,query,update,**kwargs):
        nonlocal intercepted
        if self.collection.name=='outreach_campaigns' and not intercepted:
            intercepted=True; entered.set(); await release.wait()
        return await original(self,query,update,**kwargs)
    monkeypatch.setattr(SuppressionCollection,'update_one',pause)
    work=asyncio.create_task(create(replica_db))
    await asyncio.wait_for(entered.wait(),5)
    await replica_db.outreach_campaigns.update_one({},{'$set':{'status':'warming_up'}})
    release.set()
    with pytest.raises(HTTPException) as failure: await work
    assert failure.value.status_code==409
    assert await replica_db.outreach_lead_lists.count_documents({})==0


async def test_campaign_native_replacement_cannot_inherit_audience_lists(replica_db):
    await seed(replica_db)
    request=str(uuid.uuid4())
    row=await lists.create_list(replica_db,'w','actor','campaign','Original',request)
    await replica_db.outreach_campaigns.delete_one({'id':'campaign'})
    await replica_db.outreach_campaigns.insert_one({'id':'campaign','workspace_id':'w','status':'draft'})
    with pytest.raises(HTTPException): await lists.inventory(replica_db,'w','campaign')
    with pytest.raises(HTTPException): await lists.members(replica_db,'w',row['id'])
    with pytest.raises(HTTPException): await lists.change_members(replica_db,'w','actor',row['id'],1,['lead-000'],'add')
    with pytest.raises(HTTPException): await lists.create_list(replica_db,'w','actor','campaign','Original',request)
    assert await replica_db.outreach_lead_lists.count_documents({})==1


async def test_backfill_acknowledgement_retry_cannot_advance_next_page(replica_db):
    await seed(replica_db,101)
    row=await lists.adopt_existing(replica_db,'w','operator','campaign',0,True)
    with pytest.raises(HTTPException): await lists.adopt_existing(replica_db,'w','operator','campaign',0,True)
    assert await replica_db.outreach_lead_list_members.count_documents({})==100
    assert (await replica_db.outreach_lead_lists.find_one({'id':row['id']}))['revision']==row['revision']


async def test_recreated_list_parent_cannot_inherit_membership(replica_db):
    await seed(replica_db)
    row=await create(replica_db)
    await lists.change_members(replica_db,'w','actor',row['id'],1,['lead-000'],'add')
    stored=await replica_db.outreach_lead_lists.find_one({'id':row['id']})
    await replica_db.outreach_lead_lists.delete_one({'_id':stored.pop('_id')})
    await replica_db.outreach_lead_lists.insert_one(stored)
    with pytest.raises(HTTPException): await lists.members(replica_db,'w',row['id'])
    with pytest.raises(HTTPException): await lists.change_members(replica_db,'w','actor',row['id'],2,['lead-000'],'add')
    assert await replica_db.outreach_lead_list_members.count_documents({})==1
