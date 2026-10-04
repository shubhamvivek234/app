"""Bounded AWS KMS calls using an exact, frozen workload-role identity."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.credentials import InstanceMetadataProvider
from botocore.utils import InstanceMetadataFetcher
from botocore.httpsession import URLLib3Session

from outreach.core.credential_custody import CustodyUnavailable, KEY_ARN

METHODS = frozenset({"iam-role", "container-role", "assume-role-with-web-identity"})
_pool: ThreadPoolExecutor | None = None
_pool_pid: int | None = None
_slots = threading.BoundedSemaphore(2)
_lock = threading.Lock()


def _after_fork() -> None:
    global _pool, _pool_pid, _slots, _lock
    _pool, _pool_pid = None, None
    _slots = threading.BoundedSemaphore(2)
    _lock = threading.Lock()


os.register_at_fork(after_in_child=_after_fork)


@dataclass(frozen=True)
class WorkloadConfig:
    key_arn: str
    role_arn: str
    role_id: str
    region: str
    method: str

    def validate(self) -> None:
        if any(not isinstance(value, str) for value in (self.key_arn, self.role_arn, self.role_id, self.region, self.method)):
            raise CustodyUnavailable("Pinned workload configuration is required")
        key = KEY_ARN.fullmatch(self.key_arn)
        role = re.fullmatch(r"arn:aws:iam::([0-9]{12}):role/([A-Za-z0-9_+=,.@/-]{1,512})", self.role_arn)
        if (not key or not role or key[1] != self.region or key[2] != role[1]
                or not re.fullmatch(r"AROA[A-Z0-9]{12,32}", self.role_id) or self.method not in METHODS):
            raise CustodyUnavailable("Pinned workload configuration is required")

    @classmethod
    def from_environment(cls) -> WorkloadConfig:
        value = cls(*(os.getenv(name, "").strip() for name in (
            "OUTREACH_KMS_KEY_ARN", "OUTREACH_KMS_ROLE_ARN", "OUTREACH_KMS_ROLE_ID",
            "OUTREACH_KMS_REGION", "OUTREACH_KMS_CREDENTIAL_PROVIDER")))
        value.validate()
        return value


def _sdk_config() -> Config:
    return Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1},
        proxies={}, signature_version="v4", ignore_configured_endpoint_urls=True)


def _source_session(config: WorkloadConfig) -> boto3.Session:
    """Exclude static/profile/process providers before any credentials resolve."""
    config.validate()
    # Botocore DEBUG records request headers and decoded response bodies,
    # including temporary tokens and plaintext data keys. Reject that setup.
    names = {"botocore", "boto3"} | {name for name in logging.Logger.manager.loggerDict
        if name.startswith(("botocore.", "boto3."))}
    if any(logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in names):
        raise CustodyUnavailable("Verbose credential transport logging is unavailable")
    prohibited = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_EC2_METADATA_SERVICE_ENDPOINT", "AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_KMS", "AWS_ENDPOINT_URL_STS"}
    if any(os.getenv(name) for name in prohibited):
        raise CustodyUnavailable("Workload credential overrides are unavailable")
    if config.method == "container-role" and not re.fullmatch(r"/v2/credentials/[a-zA-Z0-9-]+", os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "")):
        raise CustodyUnavailable("An ECS relative credential endpoint is required")
    if config.method == "assume-role-with-web-identity" and (os.getenv("AWS_ROLE_ARN") != config.role_arn
            or not os.path.isabs(os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE", ""))):
        raise CustodyUnavailable("Configured web identity is required")
    session = boto3.Session(region_name=config.region)
    session._session.set_config_variable("ec2_metadata_v1_disabled", True)
    session._session.set_config_variable("metadata_service_timeout", 1)
    session._session.set_config_variable("metadata_service_num_attempts", 1)
    session._session.set_config_variable("sts_regional_endpoints", "regional")
    session._session.set_default_client_config(_sdk_config())
    resolver = session._session.get_component("credential_provider")
    if config.method == "iam-role":
        # The SDK's ordinary IMDS provider inherits shared config endpoints and
        # environment HTTP proxies separately from client Config. Replace it.
        fetcher = InstanceMetadataFetcher(timeout=1, num_attempts=1,
            base_url="http://169.254.169.254/", config={"ec2_metadata_v1_disabled": True},
            env={"AWS_EC2_METADATA_DISABLED": os.getenv("AWS_EC2_METADATA_DISABLED", "false")})
        fetcher._session.close()
        fetcher._session = URLLib3Session(timeout=1, proxies={})
        resolver.providers = [InstanceMetadataProvider(fetcher)]
    else:
        resolver.providers = [provider for provider in resolver.providers if provider.METHOD == config.method]
    if len(resolver.providers) != 1:
        raise CustodyUnavailable("Configured workload provider is unavailable")
    if config.method == "assume-role-with-web-identity":
        def source_sts(service_name, **kwargs):
            if service_name != "sts":
                raise CustodyUnavailable("Unexpected identity source service")
            return session.client("sts", region_name=config.region,
                endpoint_url=f"https://sts.{config.region}.amazonaws.com", verify=True,
                config=_sdk_config().merge(Config(signature_version=UNSIGNED)))
        resolver.providers[0]._client_creator = source_sts
    return session


class AWSKeyProvider:
    def __init__(self, config: WorkloadConfig) -> None:
        config.validate()
        self.config = config

    def _operate(self, operation: str, context: dict[str, str], wrapped: bytes | None) -> tuple[bytes, bytes] | bytes:
        sts = kms = None
        try:
            session = _source_session(self.config)
            credentials = session.get_credentials()
            if credentials is None or credentials.method != self.config.method:
                raise ValueError("Credential provider changed")
            frozen = credentials.get_frozen_credentials()
            if not frozen.access_key or not frozen.secret_key or not frozen.token:
                raise ValueError("Temporary credentials required")
            settings = {"region_name": self.config.region, "aws_access_key_id": frozen.access_key,
                "aws_secret_access_key": frozen.secret_key, "aws_session_token": frozen.token,
                "config": _sdk_config(), "verify": True}
            sts = session.client("sts", endpoint_url=f"https://sts.{self.config.region}.amazonaws.com", **settings)
            identity = sts.get_caller_identity()
            account = self.config.role_arn.split(":")[4]
            name = self.config.role_arn.rsplit("/", 1)[1]
            prefix = f"arn:aws:sts::{account}:assumed-role/{name}/"
            arn, user_id = identity.get("Arn", ""), identity.get("UserId", "")
            if (identity.get("Account") != account or not isinstance(arn, str) or not arn.startswith(prefix)
                    or not arn[len(prefix):] or not isinstance(user_id, str)
                    or user_id != self.config.role_id + ":" + arn[len(prefix):]):
                raise ValueError("Workload identity changed")
            kms = session.client("kms", endpoint_url=f"https://kms.{self.config.region}.amazonaws.com", **settings)
            response = (kms.generate_data_key(KeyId=self.config.key_arn, KeySpec="AES_256", EncryptionContext=context)
                if operation == "generate" else kms.decrypt(KeyId=self.config.key_arn, CiphertextBlob=wrapped,
                    EncryptionContext=context, EncryptionAlgorithm="SYMMETRIC_DEFAULT"))
            key = response.pop("Plaintext", None)
            if response.get("KeyId") != self.config.key_arn or not isinstance(key, bytes) or len(key) != 32:
                raise ValueError("Key response changed")
            if operation == "generate":
                encrypted = response.get("CiphertextBlob")
                if not isinstance(encrypted, bytes) or not 0 < len(encrypted) <= 6144:
                    raise ValueError("Wrapped key missing")
                return key, encrypted
            return key
        except Exception:
            raise CustodyUnavailable("Workload key operation is unavailable") from None
        finally:
            cleanup_failed = False
            for client in (sts, kms):
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        cleanup_failed = True
            if cleanup_failed:
                raise CustodyUnavailable("Workload key cleanup is unavailable") from None

    async def _invoke(self, operation: str, context: dict[str, str], wrapped: bytes | None = None):
        global _pool, _pool_pid, _slots
        pid = os.getpid()
        with _lock:
            if _pool is None or _pool_pid != pid:
                _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="outreach-kms")
                _pool_pid = pid
                _slots = threading.BoundedSemaphore(2)
            slots = _slots
            if not slots.acquire(blocking=False):
                raise CustodyUnavailable("Workload key capacity is unavailable")
            def run():
                try:
                    return self._operate(operation, context, wrapped)
                finally:
                    slots.release()
            try:
                future = _pool.submit(run)
            except Exception:
                slots.release()
                raise CustodyUnavailable("Workload key capacity is unavailable") from None
        try:
            # Timeout cannot terminate a started SDK thread. Its capacity remains
            # held until it finishes; no unbounded worker/DEK cache is created.
            wrapped_future = asyncio.wrap_future(future)
            def consume(completed):
                if not completed.cancelled(): completed.exception()
            wrapped_future.add_done_callback(consume)
            return await asyncio.wait_for(asyncio.shield(wrapped_future), timeout=20)
        except TimeoutError:
            raise CustodyUnavailable("Workload key deadline is unavailable") from None

    async def generate(self, context: dict[str, str]) -> tuple[bytes, bytes]:
        return await self._invoke("generate", context)

    async def unwrap(self, wrapped: bytes, context: dict[str, str]) -> bytes:
        return await self._invoke("unwrap", context, wrapped)
