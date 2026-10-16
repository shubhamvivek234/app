"""Actual worker condition transitions preserve configured delays and holds."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest
from tests.test_outreach_sequence_capabilities import _runner_db
from outreach.tasks.sequence_executor import SequenceExecutor, _preflight_dispatch as REAL_PREFLIGHT
from outreach.core.sequence_preview import due_block_reason

pytestmark=pytest.mark.usefixtures('outreach_paid_gate_stub')


@pytest.fixture(autouse=True)
def open_schedule(monkeypatch):
    monkeypatch.setattr('outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours', lambda *args,**kwargs: True)


@pytest.mark.asyncio
@pytest.mark.parametrize('waiting,signal',[(False,True),(True,True),(True,False)])
async def test_connection_transition_applies_saved_successor_delay(waiting,signal):
    db=_runner_db('if_connected',waiting={'waiting_for_connection_at':datetime.now(timezone.utc)-timedelta(days=4)} if waiting else None)
    target='yes' if signal else 'no'
    db.outreach_sequences.find_one.return_value['compiled_dag']['nodes'][target]['delay_hours']=12
    before=datetime.now(timezone.utc)
    with patch('outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours',return_value=True),patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        voyager.return_value.check_connection_status_strict=AsyncMock(return_value=signal)
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status'] in {'success','branch_advanced'}
    fields=db.outreach_leads.update_one.await_args.args[1]['$set']
    assert fields['current_node_id']==target and fields['execution_state']=='waiting_delay'
    assert before+timedelta(hours=12)<=fields['next_action_due_at']<=datetime.now(timezone.utc)+timedelta(hours=12)


@pytest.mark.asyncio
async def test_one_sided_connection_yes_is_terminal_without_key_error():
    db=_runner_db('if_connected')
    compiled=db.outreach_sequences.find_one.return_value['compiled_dag']
    compiled['nodes']['step_a']['branches']={'negative':'no'};compiled['nodes'].pop('yes')
    with patch('outreach.tasks.sequence_executor.OutboundRateLimiter.is_within_working_hours',return_value=True),patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        voyager.return_value.check_connection_status_strict=AsyncMock(return_value=True)
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status']=='success' and result['next_node_id'] is None
    fields=db.outreach_leads.update_one.await_args.args[1]['$set']
    assert fields['execution_state']=='finished' and fields['next_action_due_at'] is None


@pytest.mark.asyncio
async def test_usable_email_without_durable_job_cannot_choose_branch_or_open_linkedin(monkeypatch):
    monkeypatch.setenv('OUTREACH_EMAIL_SEND_ENABLED','true');monkeypatch.setenv('OUTREACH_EMAIL_SYNC_ENABLED','true')
    db=_runner_db('if_email_available')
    nodes=db.outreach_sequences.find_one.return_value['compiled_dag']['nodes']
    nodes['step_a']['branches']={'positive':'yes','negative':'no'}
    nodes.update({key:{'id':key,'type':'find_email','delay_hours':6,'config':{},'branches':{},'next_default':None} for key in ('yes','no')})
    with patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status']=='dispatch_context_missing';voyager.assert_not_called()
    db.outreach_leads.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('due',[datetime.now(timezone.utc)+timedelta(days=1),'unproven'])
async def test_future_or_malformed_due_stops_before_preparation(due):
    db=_runner_db();db.outreach_leads.find_one.return_value['next_action_due_at']=due
    with patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status'] in {'not_due','sequence_timing_review_required'}
    assert result['not_submitted'] is True;voyager.assert_not_called();db.outreach_tasks.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_old_graph_is_held_before_opening_provider_or_changing_original_tasks():
    db=_runner_db();db.outreach_sequences.find_one.return_value['compiled_dag']['nodes']['step_a']['config']=[]
    with patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status']=='sequence_review_required';voyager.assert_not_called()
    db.outreach_tasks.update_one.assert_not_awaited();db.outreach_leads.update_one.assert_not_awaited()


def test_naive_native_due_is_utc_and_elapsed_due_is_allowed():
    now=datetime.now(timezone.utc)
    assert due_block_reason({'next_action_due_at':(now-timedelta(seconds=1)).replace(tzinfo=None)},now) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['due','pinned','variables'])
async def test_final_submission_preflight_rechecks_timing_graph_and_rendered_variables(monkeypatch,fault):
    db=_runner_db('send_message')
    current=db.outreach_leads.find_one.return_value
    sequence=db.outreach_sequences.find_one.return_value
    if fault=='due':current['next_action_due_at']=datetime.now(timezone.utc)+timedelta(hours=1)
    elif fault=='pinned':sequence['compiled_dag']['nodes']['step_a']['config']=[]
    else:sequence['compiled_dag']['nodes']['step_a']['config']={'body':'Hello {{missing_custom}}'}
    monkeypatch.setattr('outreach.tasks.sequence_executor.validate_dispatch_context',AsyncMock(return_value=None))
    monkeypatch.setattr('outreach.tasks.sequence_executor.dispatch_block_reason',lambda *args:None)
    reason=await REAL_PREFLIGHT(db,current,{'workspace_id':'workspace_a','campaign_id':'campaign_a','sender_id':'account_a'},'send_message')
    assert reason=={'due':'not_due','pinned':'sequence_review_required','variables':'sequence_variables_missing'}[fault]


@pytest.mark.asyncio
@pytest.mark.parametrize('value',[[],0,False,'','2026-10-14','garbage',datetime.now(timezone.utc)+timedelta(days=1)])
async def test_malformed_saved_wait_does_not_open_credentials_or_reset_start(value):
    db=_runner_db('if_connected',waiting={'waiting_for_connection_at':value})
    with patch('outreach.tasks.sequence_executor.account_session',new_callable=AsyncMock) as opening,patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status']=='sequence_review_required',result
    opening.assert_not_awaited();voyager.assert_not_called();db.outreach_leads.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('fresh',[True,False])
async def test_negative_reply_deadline_needs_complete_fresh_inbox(fresh):
    db=_runner_db('send_message',waiting={'waiting_for_reply_at':datetime.now(timezone.utc)-timedelta(days=8)})
    compiled=db.outreach_sequences.find_one.return_value['compiled_dag']
    compiled['nodes']['step_a']['branches']={'negative':'next'}
    compiled['nodes']['next']={'type':'visit_profile','delay_hours':6,'config':{},'branches':{},'next_default':None}
    with patch('outreach.tasks.sequence_executor.require_fresh_inbox',new_callable=AsyncMock,return_value=None if fresh else 'inbox_stale'),patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status']==('branch_advanced' if fresh else 'condition_needs_review'),result
    if fresh:assert db.outreach_leads.update_one.await_args.args[1]['$set']['execution_state']=='waiting_delay'
    else:assert db.outreach_leads.update_one.await_args.args[1]['$set']['execution_state']=='waiting_trigger'
    voyager.return_value.send_direct_message.assert_not_called()


@pytest.mark.asyncio
async def test_recorded_reply_stops_wait_without_requiring_freshness_or_preparation():
    db=_runner_db('send_message',waiting={'waiting_for_reply_at':datetime.now(timezone.utc),'has_replied':True})
    with patch('outreach.tasks.sequence_executor.require_fresh_inbox',new_callable=AsyncMock) as freshness,patch('outreach.tasks.sequence_executor.VoyagerClient') as voyager:
        result=await SequenceExecutor.execute_lead_step('lead_a',db)
    assert result['status']=='terminal_state' and result['state']=='replied'
    freshness.assert_not_awaited();voyager.assert_not_called()
