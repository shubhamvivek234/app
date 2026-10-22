"""Async custody for LinkedIn cookies; KMS never runs inside Mongo callbacks."""
import logging
logger = logging.getLogger(__name__)
import os

from outreach.core.credential_custody import CredentialContext, CredentialCustody, CustodyUnavailable, PREFIX
from outreach.core.crypto import encrypt_secret, decrypt_secret
from outreach.core.inbox_freshness import credential_generation
from outreach.core.kms_workload import AWSKeyProvider, WorkloadConfig
from utils.encryption import decrypt_strict


def custody_mode() -> str:
    mode = os.getenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet").strip()
    if mode not in {"legacy_fernet", "kms_v1"}:
        raise CustodyUnavailable("Credential custody mode is unavailable")
    return mode


def configured_custody() -> CredentialCustody:
    config = WorkloadConfig.from_environment()
    return CredentialCustody(config.key_arn, AWSKeyProvider(config))


def context(workspace: str, sender: str, generation: str, purpose: str) -> CredentialContext:
    value = CredentialContext(workspace, sender, generation, purpose, os.getenv("OUTREACH_CUSTODY_ENVIRONMENT_ID", "").strip())
    value.kms_context()
    return value


async def _seal(material: dict, workspace: str, sender: str, generation: str, pending: bool) -> dict:
    mapping = {"li_at": "li_at_enc" if pending else "session_cookie_enc",
        "jsession_id": "jsession_id_enc" if pending else "jsession_id", "li_a": "li_a_enc"}
    mode = custody_mode()
    if not material.get("li_at") or not material.get("jsession_id"):
        raise CustodyUnavailable("Complete session material is required")
    result = {}
    for name, field in mapping.items():
        value = material.get(name) or ""
        purpose = ("pending_" if pending else "session_") + ("jsession" if name == "jsession_id" else name)
        result[field] = (await configured_custody().seal(value, context(workspace, sender, generation, purpose))
            if mode == "kms_v1" and value else encrypt_secret(value))
    return result


async def seal_pending(material: dict, workspace: str, sender: str, job_id: str) -> dict:
    return await _seal(material, workspace, sender, job_id, True)


async def seal_installed(material: dict, workspace: str, sender: str, generation: str) -> dict:
    return await _seal(material, workspace, sender, generation, False)


async def _open(record: dict, pending: bool) -> dict:
    mode = custody_mode()
    mapping = {"li_at": "li_at_enc" if pending else "session_cookie_enc",
        "jsession_id": "jsession_id_enc" if pending else "jsession_id", "li_a": "li_a_enc"}
    if pending:
        workspace, sender, generation = record.get("workspace_id"), record.get("sender_id"), record.get("id")
    else:
        workspace, sender, generation = record.get("workspace_id"), record.get("id"), credential_generation(record)
    result = {}
    for name, field in mapping.items():
        value = record.get(field) or (record.get("encrypted_session_cookie") or record.get("li_at_enc")
            if name == "li_at" and not pending else record.get("jsession_id_enc") if name == "jsession_id" and not pending else "") or ""
        purpose = ("pending_" if pending else "session_") + ("jsession" if name == "jsession_id" else name)
        if mode == "kms_v1":
            if not value and name == "li_a":
                result[name] = ""
            else:
                result[name] = await configured_custody().open(value, context(workspace, sender, generation, purpose))
        else:
            if value.startswith(PREFIX):
                raise CustodyUnavailable("Scoped credentials cannot use legacy custody")
            # Preserve historical installed-session compatibility in the default
            # mode. Pending writes are already encrypted and always strict.
            result[name] = (decrypt_strict(value) if pending and value else
                decrypt_secret(value) if name != "jsession_id" or value.startswith("gAAAAA") else value)
    return result


async def pending_session(job: dict) -> dict:
    return await _open(job, True)


async def account_session(account: dict) -> dict:
    return await _open(account, False)
