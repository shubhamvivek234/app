"""HTTP regressions for tenant/role/erasure context agreement; no providers."""
from copy import deepcopy
import importlib
import re

from fastapi import FastAPI
import httpx
import pytest

from api.deps import ensure_active_workspace, get_current_user
from db.mongo import get_db
from outreach.api import campaigns, prompts
from outreach.api.router import router as outreach_router
from outreach.core.suppression import guard_scope
from tests.test_outreach_lead_workspace_scope import (
    FOREIGN, USER, USER_ID, WORKSPACE, StreamingCollection, tenant_db,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]


def app_for(db, router, auth=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = auth or (lambda: deepcopy(USER))
    app.dependency_overrides[get_db] = lambda: db
    return app


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def auth_then_revoke(db, *, initial_role="viewer"):
    await db.workspace_members.insert_one({"workspace_id": FOREIGN, "user_id": USER_ID, "role": initial_role})
    stale = {**USER, "default_workspace_id": FOREIGN, "workspace_ids": [FOREIGN, WORKSPACE]}
    captured = None

    async def authenticate():
        nonlocal captured
        if captured is None:
            captured = await ensure_active_workspace(db, stale)
            assert captured["default_workspace_id"] == FOREIGN
            await db.workspace_members.delete_one({"workspace_id": FOREIGN, "user_id": USER_ID})
        return deepcopy(captured)

    return authenticate


async def test_viewer_cannot_delete_foreign_campaign_using_fallback_admin_permission(synthetic_campaign_persistence):
    db = tenant_db(role="admin", campaign_scope={"workspace_id": FOREIGN})
    synthetic_campaign_persistence(db)
    auth = await auth_then_revoke(db)
    before = deepcopy(db.outreach_campaigns.docs)
    async with client_for(app_for(db, outreach_router, auth)) as client:
        response = await client.delete("/outreach/campaigns/campaign")
    assert response.status_code == 404
    assert db.outreach_campaigns.docs == before


async def test_permission_fallback_updates_only_current_campaign(synthetic_campaign_persistence):
    db = tenant_db(role="admin")
    synthetic_campaign_persistence(db)
    auth = await auth_then_revoke(db)
    await db.outreach_campaigns.insert_one({"id": "campaign", "workspace_id": FOREIGN, "name": "Foreign", "status": "draft"})
    async with client_for(app_for(db, outreach_router, auth)) as client:
        response = await client.delete("/outreach/campaigns/campaign")
    assert response.status_code == 200
    current, foreign = db.outreach_campaigns.docs
    assert current["is_deleted"] is True
    assert "is_deleted" not in foreign


async def test_closed_old_workspace_does_not_block_open_permission_fallback(synthetic_campaign_persistence):
    db = tenant_db(role="admin")
    synthetic_campaign_persistence(db)
    await db.outreach_suppression_guards.insert_one({**guard_scope(FOREIGN), "erasure_state": "stopped"})
    auth = await auth_then_revoke(db)
    async with client_for(app_for(db, outreach_router, auth)) as client:
        response = await client.delete("/outreach/campaigns/campaign")
    assert response.status_code == 200
    assert db.outreach_campaigns.docs[0]["is_deleted"] is True


async def test_role_downgrade_denies_without_resource_mutation():
    db = tenant_db(role="viewer")
    auth = await auth_then_revoke(db, initial_role="admin")
    before = deepcopy(db.outreach_campaigns.docs)
    async with client_for(app_for(db, outreach_router, auth)) as client:
        response = await client.delete("/outreach/campaigns/campaign")
    assert response.status_code == 403
    assert db.outreach_campaigns.docs == before


@pytest.mark.parametrize("scope", [FOREIGN, USER_ID, None, [WORKSPACE, FOREIGN], "MISSING"])
async def test_prompt_preview_library_and_delete_reject_non_current_creator_rows(scope):
    db = tenant_db(role="admin")
    row = {"id": "target", "user_id": USER_ID, "custom_variables": {"private": "synthetic-private"}}
    if scope != "MISSING":
        row["workspace_id"] = scope
    db.collections["outreach_leads"] = StreamingCollection([row])
    prompt = {**row, "id": "custom", "name": "Foreign", "prompt_text": "synthetic-private", "is_system": False}
    db.collections["outreach_ai_prompts"] = StreamingCollection([prompt])
    async with client_for(app_for(db, prompts.router)) as client:
        preview = await client.post("/prompts/preview", json={"lead_id": "target", "template": "{{private}}"})
        library = await client.get("/prompts")
        deleted = await client.delete("/prompts/custom")
    assert preview.status_code == deleted.status_code == 404
    assert library.status_code == 200 and "synthetic-private" not in library.text
    assert db.outreach_ai_prompts.docs == [prompt]


async def test_prompt_custom_collision_selects_current_workspace_and_reserved_catalog_is_stable():
    db = tenant_db(role="admin")
    db.collections["outreach_ai_prompts"] = StreamingCollection([
        {"id": "custom", "workspace_id": FOREIGN, "user_id": USER_ID, "is_system": False, "name": "Foreign", "prompt_text": "foreign-private"},
        {"id": "custom", "workspace_id": WORKSPACE, "user_id": "another", "is_system": False, "name": "Current", "prompt_text": "current-public"},
        {"id": "forged", "workspace_id": FOREIGN, "is_system": True, "name": "Forged", "prompt_text": "forged-private"},
    ])
    before = deepcopy(db.outreach_ai_prompts.docs)
    async with client_for(app_for(db, prompts.router)) as client:
        first = await client.get("/prompts")
        second = await client.get("/prompts")
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert "current-public" in first.text
        assert "foreign-private" not in first.text and "forged-private" not in first.text
        system = [p for p in first.json() if p["is_system"]]
        assert len(system) == 5 and len({p["id"] for p in system}) == 5
        assert all(not p.get("runs_count") for p in system)
        for item in system:
            assert (await client.delete("/prompts/" + item["id"])).status_code == 404
        assert db.outreach_ai_prompts.docs == before  # GET never seeds or deletes.
        deleted = await client.delete("/prompts/custom")
    assert deleted.status_code == 200
    assert len(db.outreach_ai_prompts.docs) == 2 and db.outreach_ai_prompts.docs[0]["workspace_id"] == FOREIGN


async def test_prompt_create_preview_delete_for_current_member_and_viewer_read_only():
    db = tenant_db(role="admin")
    db.collections["outreach_ai_prompts"] = StreamingCollection()
    db.outreach_leads.docs[0]["custom_variables"] = {"icebreaker": "Current sample"}
    async with client_for(app_for(db, prompts.router)) as client:
        created = await client.post("/prompts", json={"name": "Custom", "prompt_text": "Some instructions"})
        assert created.status_code == 200
        assert created.json()["workspace_id"] == WORKSPACE and not created.json()["is_system"]
        preview = await client.post("/prompts/preview", json={"lead_id": "target", "template": "{{icebreaker}}"})
        assert preview.status_code == 200 and preview.json()["evaluated_text"] == "Current sample"
        db.workspace_members.docs[0]["role"] = "viewer"
        assert (await client.get("/prompts")).status_code == 200
        assert (await client.post("/prompts", json={"name": "Custom", "prompt_text": "Some instructions"})).status_code == 403
        assert (await client.delete("/prompts/" + created.json()["id"])).status_code == 403
        db.workspace_members.docs[0]["role"] = "admin"
        assert (await client.delete("/prompts/" + created.json()["id"])).status_code == 200


async def test_prompt_catalog_is_available_without_database_seeding_or_shared_mutation():
    db = tenant_db(role="admin")
    db.collections["outreach_ai_prompts"] = StreamingCollection()
    async with client_for(app_for(db, prompts.router)) as client:
        first = await client.get("/prompts")
        assert first.status_code == 200 and len(first.json()) == 5
        assert db.outreach_ai_prompts.docs == []
        original = deepcopy(first.json())
        first.json()[0]["prompt_text"] = "Local changed response"
        second = await client.get("/prompts")
        assert second.json() == original and db.outreach_ai_prompts.docs == []


# Filled from the original authenticated route contract, not discovered from
# the new dependency. Removing a guard cannot silently remove its test case.
AUTHENTICATED_HANDLERS = (
    ('outreach.api.accounts', 'list_outreach_accounts'),
    ('outreach.api.accounts', 'get_connection_job'),
    ('outreach.api.accounts', 'connect_via_cookie'),
    ('outreach.api.accounts', 'login_start'),
    ('outreach.api.accounts', 'login_verify_2fa'),
    ('outreach.api.accounts', 'update_account_limits'),
    ('outreach.api.accounts', 'disconnect_account'),
    ('outreach.api.accounts', 'resume_sender_account'),
    ('outreach.api.action_reconciliation', 'list_action_reviews'),
    ('outreach.api.action_reconciliation', 'resolve_uncertain_action'),
    ('outreach.api.analytics', 'get_outreach_analytics'),
    ('outreach.api.analytics', 'export_outreach_analytics'),
    ('outreach.api.analytics', 'live_activity_feed'),
    ('outreach.api.billing', 'get_outreach_plans'),
    ('outreach.api.billing', 'request_pilot_access'),
    ('outreach.api.billing', 'update_billing_email'),
    ('outreach.api.billing', 'start_outreach_trial'),
    ('outreach.api.billing', 'update_seats'),
    ('outreach.api.billing', 'cancel_subscription'),
    ('outreach.api.campaigns', 'get_sequence_capabilities'),
    ('outreach.api.campaigns', 'get_conditional_launch_feature'),
    ('outreach.api.campaigns', 'arm_warmup_campaign'),
    ('outreach.api.campaigns', 'list_campaigns'),
    ('outreach.api.campaigns', 'auto_draft_campaign'),
    ('outreach.api.campaigns', 'create_campaign'),
    ('outreach.api.campaigns', 'get_campaign'),
    ('outreach.api.campaigns', 'update_campaign'),
    ('outreach.api.campaigns', 'delete_campaign'),
    ('outreach.api.campaigns', 'restore_campaign'),
    ('outreach.api.campaigns', 'duplicate_campaign'),
    ('outreach.api.campaigns', 'get_campaign_preflight'),
    ('outreach.api.campaigns', 'get_campaign_node_counts'),
    ('outreach.api.campaigns', 'launch_campaign'),
    ('outreach.api.campaigns', 'pause_campaign'),
    ('outreach.api.content_approvals', 'list_content_reviews'),
    ('outreach.api.content_approvals', 'prepare_content_reviews'),
    ('outreach.api.content_approvals', 'decide_content'),
    ('outreach.api.content_approvals', 'cancel_manual_content'),
    ('outreach.api.content_approvals', 'content_audio'),
    ('outreach.api.engage', 'create_engage_list'),
    ('outreach.api.engage', 'list_engage_lists'),
    ('outreach.api.engage', 'get_engage_list'),
    ('outreach.api.engage', 'list_engage_accounts'),
    ('outreach.api.engage', 'update_engage_list_settings'),
    ('outreach.api.engage', 'get_engage_list_stats'),
    ('outreach.api.engage', 'get_engage_report'),
    ('outreach.api.engage', 'list_engage_drafts'),
    ('outreach.api.engage', 'create_engage_draft'),
    ('outreach.api.engage', 'update_engage_draft'),
    ('outreach.api.engage', 'delete_engage_list'),
    ('outreach.api.engage', 'add_contacts_to_list'),
    ('outreach.api.engage', 'delete_engage_contact'),
    ('outreach.api.engage', 'get_engage_contact_history'),
    ('outreach.api.engage', 'export_engage_report'),
    ('outreach.api.engage', 'fetch_latest_posts_for_list'),
    ('outreach.api.engage', 'get_engage_posts_feed'),
    ('outreach.api.engage', 'queue_like_engage_post'),
    ('outreach.api.engage', 'queue_comment_engage_post'),
    ('outreach.api.engage', 'get_engage_post_action'),
    ('outreach.api.engage', 'discard_engage_post'),
    ('outreach.api.engage', 'generate_ai_comments'),
    ('outreach.api.inbox', 'list_inbox_threads'),
    ('outreach.api.inbox', 'get_thread'),
    ('outreach.api.inbox', 'send_thread_reply'),
    ('outreach.api.inbox', 'generate_ai_reply_options'),
    ('outreach.api.inbox', 'trigger_inbox_sync'),
    ('outreach.api.inbox', 'get_inbox_job'),
    ('outreach.api.inbox', 'seed_demo_threads'),
    ('outreach.api.inbox', 'update_thread_intent'),
    ('outreach.api.inbox', 'create_thread_reminder'),
    ('outreach.api.inbox', 'list_thread_reminders'),
    ('outreach.api.inbox', 'delete_thread_reminder'),
    ('outreach.api.inbox', 'list_snippets'),
    ('outreach.api.inbox', 'create_snippet'),
    ('outreach.api.inbox', 'delete_snippet'),
    ('outreach.api.inbox', 'list_tags'),
    ('outreach.api.inbox', 'create_tag'),
    ('outreach.api.inbox', 'delete_tag'),
    ('outreach.api.inbox', 'toggle_thread_tag'),
    ('outreach.api.integrations', 'list_webhooks'),
    ('outreach.api.integrations', 'create_webhook'),
    ('outreach.api.integrations', 'rotate_webhook_secret'),
    ('outreach.api.integrations', 'delete_webhook'),
    ('outreach.api.integrations', 'list_webhook_deliveries'),
    ('outreach.api.integrations', 'replay_failed_delivery'),
    ('outreach.api.integrations', 'test_webhook_ping'),
    ('outreach.api.integrations', 'get_integration_delivery_status'),
    ('outreach.api.integrations', 'list_api_keys'),
    ('outreach.api.integrations', 'create_api_key'),
    ('outreach.api.integrations', 'revoke_api_key'),
    ('outreach.api.integrations', 'get_slack_config'),
    ('outreach.api.integrations', 'update_slack_config'),
    ('outreach.api.integrations', 'test_slack_notification'),
    ('outreach.api.integrations', 'delete_slack_config'),
    ('outreach.api.integrations', 'get_hubspot_config'),
    ('outreach.api.integrations', 'update_hubspot_config'),
    ('outreach.api.integrations', 'delete_hubspot_config'),
    ('outreach.api.integrations', 'manual_sync_lead_hubspot'),
    ('outreach.api.integrations', 'preview_sheets_import'),
    ('outreach.api.integrations', 'import_sheets_leads'),
    ('outreach.api.leads', 'preview_leads_intake'),
    ('outreach.api.leads', 'import_leads_urls'),
    ('outreach.api.leads', 'import_leads_csv'),
    ('outreach.api.leads', 'import_leads_staged'),
    ('outreach.api.leads', 'import_search_url'),
    ('outreach.api.leads', 'get_import_job'),
    ('outreach.api.leads', 'cancel_import_job'),
    ('outreach.api.leads', 'get_staged_leads_for_job'),
    ('outreach.api.leads', 'commit_staged_leads'),
    ('outreach.api.leads', 'list_leads'),
    ('outreach.api.leads', 'export_leads'),
    ('outreach.api.leads', 'delete_lead'),
    ('outreach.api.leads', 'add_do_not_contact'),
    ('outreach.api.leads', 'list_do_not_contact'),
    ('outreach.api.leads', 'preview_lead_finder'),
    ('outreach.api.leads', 'enroll_finder_leads'),
    ('outreach.api.leads', 'import_post_engagers'),
    ('outreach.api.leads', 'update_lead_stage'),
    ('outreach.api.leads', 'get_lead_activity'),
    ('outreach.api.leads', 'add_lead_note'),
    ('outreach.api.leads', 'pause_lead'),
    ('outreach.api.leads', 'resume_lead'),
    ('outreach.api.mailboxes', 'list_mailboxes'),
    ('outreach.api.mailboxes', 'hunter_key_status'),
    ('outreach.api.mailboxes', 'put_hunter_key'),
    ('outreach.api.mailboxes', 'delete_hunter_key'),
    ('outreach.api.mailboxes', 'get_mailbox_connection_job'),
    ('outreach.api.mailboxes', 'authorize_mailbox'),
    ('outreach.api.mailboxes', 'disconnect_mailbox'),
    ('outreach.api.prompts', 'list_prompts'),
    ('outreach.api.prompts', 'create_prompt'),
    ('outreach.api.prompts', 'delete_prompt'),
    ('outreach.api.prompts', 'preview_evaluated_message'),
    ('outreach.api.sequences', 'get_sequence_templates'),
    ('outreach.api.sequences', 'save_custom_template'),
    ('outreach.api.sequences', 'delete_custom_template'),
    ('outreach.api.sequences', 'get_campaign_sequence'),
    ('outreach.api.sequences', 'save_campaign_sequence'),
    ('outreach.api.styles', 'create_writing_style'),
    ('outreach.api.styles', 'list_writing_styles'),
    ('outreach.api.styles', 'get_writing_style'),
    ('outreach.api.styles', 'delete_writing_style'),
    ('outreach.api.swipe', 'create_swipe_item'),
    ('outreach.api.swipe', 'list_swipe_items'),
    ('outreach.api.swipe', 'delete_swipe_item'),
    ('outreach.api.swipe', 'repurpose_swipe_item'),
    ('outreach.api.voice', 'list_voices'),
    ('outreach.api.voice', 'clone_voice'),
    ('outreach.api.voice', 'preview_voice_note'),
    ('outreach.api.voice', 'job_status'),
    ('outreach.api.voice', 'cancel_job'),
    ('outreach.api.voice', 'saved_audio'),
    ('outreach.api.voice', 'assign_voice'),
    ('outreach.api.voice', 'update_consent'),
    ('outreach.api.voice', 'delete_voice'),
)


@pytest.mark.parametrize("module_name,handler_name", AUTHENTICATED_HANDLERS)
async def test_every_authenticated_outreach_handler_checks_final_tenant_erasure(module_name, handler_name):
    module = importlib.import_module(module_name)
    route = next(r for r in module.router.routes if r.endpoint.__name__ == handler_name)
    db = tenant_db(role="owner")
    await db.outreach_suppression_guards.insert_one({**guard_scope(WORKSPACE), "erasure_state": "stopped"})
    stale = {**USER, "default_workspace_id": FOREIGN, "workspace_ids": [FOREIGN, WORKSPACE]}
    app = app_for(db, module.router, lambda: deepcopy(stale))
    path = re.sub(r"\{[^}]+\}", "target", route.path)
    before = deepcopy(db.outreach_campaigns.docs)
    async with client_for(app) as client:
        response = await client.request(next(iter(route.methods)), path, json={})
    assert response.status_code == 409, (handler_name, response.status_code, response.text[:200])
    assert "closed for data deletion" in response.json()["detail"]
    assert db.outreach_campaigns.docs == before


@pytest.mark.parametrize('role,expected', [('owner', 200), ('admin', 200), ('editor', 403), ('viewer', 403)])
async def test_team_approval_policy_uses_defined_admin_permission(role, expected):
    from api.routes.team import router
    db = tenant_db(role=role)
    async with client_for(app_for(db, router)) as client:
        response = await client.put('/workspace/approval-policy', json={'enabled': True})
    assert response.status_code == expected
    assert bool(db.workspaces.docs[0].get('approval_policy')) == (expected == 200)


async def test_team_approval_policy_writes_permission_resolved_workspace_only():
    from api.routes.team import router
    db = tenant_db(role='admin')
    await db.workspaces.insert_one({'workspace_id': FOREIGN, 'owner_id': 'someone-else'})
    auth = await auth_then_revoke(db)
    async with client_for(app_for(db, router, auth)) as client:
        response = await client.put('/workspace/approval-policy', json={'enabled': True})
    assert response.status_code == 200
    assert db.workspaces.docs[0]['approval_policy']['enabled'] is True
    assert 'approval_policy' not in db.workspaces.docs[1]


async def test_team_invitation_still_requires_verified_email():
    from api.routes.team import router
    db = tenant_db(role='admin')
    async with client_for(app_for(db, router, lambda: {**USER, 'email_verified': False})) as client:
        response = await client.post('/workspace/members/invite', json={'email': 'invitee@example.com'})
    assert response.status_code == 403
    assert 'verification required' in response.json()['detail']
    assert db.workspace_invites.docs == []


def dependency_calls(dependant):
    yield dependant.call
    for child in dependant.dependencies:
        yield from dependency_calls(child)


def concrete_routes(router):
    # FastAPI 0.143 keeps include_router nodes lazy; inspect each leaf contract.
    for route in router.routes:
        if hasattr(route, 'dependant'):
            yield route
        elif hasattr(route, 'original_router'):
            yield from concrete_routes(route.original_router)
        else:
            raise AssertionError(f'Uninspected route type: {type(route).__name__}')


async def test_route_graph_covers_every_ordinary_route_and_preserves_auth_exceptions():
    from outreach.api import integrations, mailboxes
    from outreach.api import sequences
    from outreach.api.dependencies import get_outreach_user
    from outreach.api.sequences import router as sequence_router

    # The optional integration routers are checked even when disabled at import.
    routes = {id(r): r for source in (outreach_router, integrations.router, integrations.public_router)
              for r in concrete_routes(source)}.values()
    exempt = {'outreach_health', 'mailbox_oauth_callback'} | {
        r.endpoint.__name__ for r in integrations.public_router.routes
    }
    assert len(exempt) == 9
    # These exact readers own their permission/UID/erasure transaction rather
    # than taking an ordinary sequential outreach-context snapshot first.
    snapshot_readers = {
        sequences.get_template_history: '/outreach/sequences/templates/{template_id}/revision-checkpoints',
        sequences.get_template_snapshot_content: '/outreach/sequences/templates/{template_id}/revision-checkpoints/{checkpoint_id}/content',
    }
    for route in routes:
        calls = list(dependency_calls(route.dependant))
        guarded = any(call and call.__module__ == 'outreach.api.dependencies' for call in calls)
        if route.endpoint.__name__ in exempt:
            assert not guarded, route.path  # OAuth/state and API-key auth stay independent.
            assert get_current_user not in calls, route.path
        elif route.endpoint in snapshot_readers:
            assert route.path == snapshot_readers[route.endpoint] and route.methods == {'GET'}
            assert not guarded and get_current_user in calls, route.path
        else:
            assert guarded and get_current_user in calls, route.path
    callback = next(r for r in mailboxes.router.routes if r.endpoint.__name__ == 'mailbox_oauth_callback')
    assert get_outreach_user not in list(dependency_calls(callback.dependant))
    validator = next(r for r in sequence_router.routes if r.endpoint.__name__ == 'validate_sequence')
    assert any(c and c.__module__ == 'outreach.api.dependencies' for c in dependency_calls(validator.dependant))


@pytest.mark.parametrize('kind', ['history', 'content'])
@pytest.mark.parametrize('signed_in', [False, True])
async def test_snapshot_readers_keep_auth_and_delegate_to_current_guard(monkeypatch, kind, signed_in):
    from unittest.mock import AsyncMock, MagicMock
    from fastapi import HTTPException
    from outreach.api import sequences

    db = MagicMock()
    reader = AsyncMock(side_effect=HTTPException(409, 'Synthetic owning-authority hold'))
    service = sequences.template_history if kind == 'history' else sequences.template_snapshot_reads
    monkeypatch.setattr(service, 'read_history' if kind == 'history' else 'read_content', reader)
    current_user = {**deepcopy(USER), 'firebase_uid': 'synthetic-snapshot-reader-uid'}

    async def authenticate():
        if not signed_in:
            raise HTTPException(401, 'Synthetic authentication required')
        return current_user

    suffix = '/checkpoint/content' if kind == 'content' else ''
    query = {'identity_digest': 'a' * 64}
    if kind == 'content':
        query['history_digest'] = 'b' * 64
    async with client_for(app_for(db, sequences.router, authenticate)) as client:
        response = await client.get('/sequences/templates/template/revision-checkpoints' + suffix, params=query)
    assert response.status_code == (409 if signed_in else 401)
    if signed_in:
        reader.assert_awaited_once()
        assert reader.await_args.args[:5] == (db, WORKSPACE, USER_ID, current_user['firebase_uid'], 'template')
        assert response.json()['detail'] == 'Synthetic owning-authority hold'
    else:
        reader.assert_not_awaited()


@pytest.mark.parametrize('method,path', [('GET', '/outreach/overview'), ('POST', '/outreach/sequences/validate')])
async def test_parent_overview_and_pure_validator_check_resolved_tenant_erasure(method, path):
    db = tenant_db(role='owner')
    await db.outreach_suppression_guards.insert_one({**guard_scope(WORKSPACE), 'erasure_state': 'stopped'})
    async with client_for(app_for(db, outreach_router)) as client:
        response = await client.request(method, path, json={})
    assert response.status_code == 409


@pytest.mark.parametrize('bad', [None, '', ' ', ['a'], 42, {'id': 'a'}])
async def test_workspace_context_never_coerces_uid_or_ambiguous_values(bad):
    from fastapi import HTTPException
    from outreach.api.dependencies import workspace_id
    with pytest.raises(HTTPException) as error:
        workspace_id({'user_id': USER_ID, 'default_workspace_id': bad})
    assert error.value.status_code == 403
