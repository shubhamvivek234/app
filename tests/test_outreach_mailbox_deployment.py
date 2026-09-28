"""Production services must receive the same fail-closed mailbox configuration."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MAILBOX_SETTINGS = {
    "OUTREACH_MAILBOX_CONNECTION_ENABLED",
    "OUTREACH_EMAIL_SEND_ENABLED",
    "OUTREACH_EMAIL_SYNC_ENABLED",
    "OUTREACH_HUNTER_ENABLED",
    "OUTREACH_GMAIL_CLIENT_ID",
    "OUTREACH_GMAIL_CLIENT_SECRET",
    "OUTREACH_GMAIL_REDIRECT_URI",
    "OUTREACH_MICROSOFT_CLIENT_ID",
    "OUTREACH_MICROSOFT_CLIENT_SECRET",
    "OUTREACH_MICROSOFT_REDIRECT_URI",
    "OUTREACH_MICROSOFT_TENANT",
}


def test_mailbox_settings_reach_api_and_workers_without_enabling_live_actions():
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())
    common = compose["x-common-env"]
    assert MAILBOX_SETTINGS <= common.keys()
    for service in ("api", "worker", "beat"):
        assert MAILBOX_SETTINGS <= compose["services"][service]["environment"].keys()
    for setting in (
        "OUTREACH_MAILBOX_CONNECTION_ENABLED",
        "OUTREACH_EMAIL_SEND_ENABLED",
        "OUTREACH_EMAIL_SYNC_ENABLED",
        "OUTREACH_HUNTER_ENABLED",
    ):
        assert common[setting].endswith(":-false}")


def test_mailbox_settings_are_documented_in_env_template():
    example = (ROOT / "backend/.env.example").read_text()
    assert all(f"{setting}=" in example for setting in MAILBOX_SETTINGS)
