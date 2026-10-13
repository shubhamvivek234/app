"""Synthetic admission resources for legacy campaign unit tests; no gate mocks."""
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from outreach.core.crypto import encrypt_secret
from outreach.models import WorkingSchedule
from tests.outreach_memory import Database


def admission_database(monkeypatch, workspace='w', campaign='c', sender='a', leads=1, nodes=None):
    from utils import encryption
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr(encryption, '_fernet', None)
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false')
    monkeypatch.delenv('OUTREACH_EXECUTION_EPOCH', raising=False)
    now = datetime.now(timezone.utc)
    proxy = {'proxy_id': 'asset', 'provider': 'iproyal_static', 'host': '8.8.4.4', 'port': 1234,
             'username': 'synthetic', 'password_enc': encrypt_secret('synthetic-password'), 'country_code': 'US'}
    return Database(
        outreach_campaigns=[{'id': campaign, 'workspace_id': workspace, 'status': 'draft', 'authorization_revision': 0,
            'sender_account_ids': [sender], 'schedule': WorkingSchedule().model_dump()}],
        outreach_accounts=[{'id': sender, 'workspace_id': workspace, 'status': 'active', 'country_code': 'US',
            'credential_generation': 'original', 'session_cookie_enc': encrypt_secret('synthetic-session'), 'jsession_id': 'ajax:synthetic', 'proxy': proxy}],
        outreach_entitlements=[{'workspace_id': workspace, 'status': 'active', 'seats': 1,
            'payment_source': 'manual_verified_invoice', 'paid_through': now + timedelta(days=1)}],
        outreach_proxy_inventory=[{**proxy, '_id': 'asset', 'workspace_id': workspace, 'last_workspace_id': workspace,
            'status': 'available', 'expires_at': now + timedelta(days=2)}],
        outreach_proxy_leases=[{'_id': 'asset', 'workspace_id': workspace, 'sender_id': sender, 'provider': 'iproyal_static', 'country_code': 'US'}],
        outreach_sender_slots=[{'workspace_id': workspace, 'sender_id': sender}],
        outreach_sequences=[{'workspace_id': workspace, 'campaign_id': campaign,
            'nodes': nodes or [{'id': 'n', 'type': 'visit_profile', 'config': {}}], 'edges': []}],
        outreach_leads=[{'id': f'lead_{index}', 'workspace_id': workspace, 'campaign_id': campaign,
            'linkedin_url': f'https://linkedin.com/in/synthetic-{index}', 'execution_state': 'queued'} for index in range(leads)])
