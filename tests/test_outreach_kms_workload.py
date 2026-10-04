"""AWS SDK calls use one frozen, attested workload identity and fixed endpoints."""
from unittest.mock import MagicMock

import pytest

from outreach.core.kms_workload import AWSKeyProvider, WorkloadConfig
from outreach.core.credential_custody import CustodyUnavailable
from tests.test_outreach_credential_custody import ARN, scope

ROLE = "arn:aws:iam::123456789012:role/outreach-test"
ROLE_ID = "AROA12345678901234567"


@pytest.fixture
def aws(monkeypatch):
    from outreach.core import kms_workload
    config = WorkloadConfig(ARN, ROLE, ROLE_ID, "eu-north-1", "iam-role")
    session = MagicMock()
    session.get_credentials.return_value.method = "iam-role"
    frozen = session.get_credentials.return_value.get_frozen_credentials.return_value
    frozen.access_key, frozen.secret_key, frozen.token = "fake-key", "fake-secret", "fake-token"
    sts, kms = MagicMock(), MagicMock()
    sts.get_caller_identity.return_value = {"Account": "123456789012", "Arn": "arn:aws:sts::123456789012:assumed-role/outreach-test/session", "UserId": ROLE_ID + ":session"}
    kms.generate_data_key.return_value = {"KeyId": ARN, "Plaintext": bytes(32), "CiphertextBlob": bytes(64)}
    kms.decrypt.return_value = {"KeyId": ARN, "Plaintext": bytes(32)}
    session.client.side_effect = lambda service, **kwargs: sts if service == "sts" else kms
    monkeypatch.setattr(kms_workload, "_source_session", lambda conf: session)
    return AWSKeyProvider(config), session, sts, kms


@pytest.mark.asyncio
async def test_attested_key_operations_have_exact_context_key_and_bounded_sdk(aws):
    provider, session, sts, kms = aws
    context = scope().kms_context()
    assert await provider.generate(context) == (bytes(32), bytes(64))
    assert await provider.unwrap(bytes(64), context) == bytes(32)
    kms.generate_data_key.assert_called_once_with(KeyId=ARN, KeySpec="AES_256", EncryptionContext=context)
    kms.decrypt.assert_called_once_with(KeyId=ARN, CiphertextBlob=bytes(64), EncryptionContext=context, EncryptionAlgorithm="SYMMETRIC_DEFAULT")
    assert sts.get_caller_identity.call_count == 2
    for call in session.client.call_args_list:
        settings = call.kwargs
        assert settings["aws_access_key_id"] == "fake-key" and settings["aws_session_token"] == "fake-token"
        assert settings["endpoint_url"].startswith("https://") and settings["verify"] is True
        assert settings["config"].proxies == {} and settings["config"].ignore_configured_endpoint_urls
        assert settings["config"].retries["total_max_attempts"] == 1
    assert sts.close.call_count == 2 and kms.close.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["static", "role", "role_id", "account", "missing_token", "wrong_key", "short_key", "error"])
async def test_wrong_workload_or_key_response_denies_without_secret_error(aws, change):
    provider, session, sts, kms = aws
    if change == "static": session.get_credentials.return_value.method = "env"
    if change == "role": sts.get_caller_identity.return_value["Arn"] = "arn:aws:sts::123456789012:assumed-role/other/session"
    if change == "role_id": sts.get_caller_identity.return_value["UserId"] = "AROAOTHER:session"
    if change == "account": sts.get_caller_identity.return_value["Account"] = "000000000000"
    if change == "missing_token": session.get_credentials.return_value.get_frozen_credentials.return_value.token = ""
    if change == "wrong_key": kms.generate_data_key.return_value["KeyId"] = ARN.replace("11111111", "99999999")
    if change == "short_key": kms.generate_data_key.return_value["Plaintext"] = bytes(16)
    if change == "error": kms.generate_data_key.side_effect = RuntimeError("fake-secret-provider-error")
    with pytest.raises(CustodyUnavailable) as error:
        await provider.generate(scope().kms_context())
    assert "fake-secret" not in str(error.value)
    if change in {"static", "role", "role_id", "account", "missing_token"}:
        kms.generate_data_key.assert_not_called()


@pytest.mark.parametrize("variable,value", [("AWS_ACCESS_KEY_ID", "static"), ("AWS_CONTAINER_CREDENTIALS_FULL_URI", "http://evil.test"), ("AWS_ENDPOINT_URL", "http://evil.test"), ("AWS_EC2_METADATA_SERVICE_ENDPOINT", "http://evil.test")])
def test_environment_endpoint_and_static_overrides_are_rejected_before_sdk(monkeypatch, variable, value):
    from outreach.core.kms_workload import _source_session
    monkeypatch.setenv(variable, value)
    with pytest.raises(CustodyUnavailable):
        _source_session(WorkloadConfig(ARN, ROLE, ROLE_ID, "eu-north-1", "iam-role"))


@pytest.mark.parametrize("field,value", [("key_arn", "alias/key"), ("role_arn", "arn:aws:iam::000000000000:role/other"), ("role_id", "bad"), ("region", "us-east-1"), ("method", "env")])
def test_workload_configuration_is_pinned(field, value):
    from dataclasses import replace
    with pytest.raises(CustodyUnavailable):
        replace(WorkloadConfig(ARN, ROLE, ROLE_ID, "eu-north-1", "iam-role"), **{field: value}).validate()


def test_imds_ignores_shared_endpoint_and_environment_proxy(monkeypatch, tmp_path):
    from outreach.core.kms_workload import _source_session
    shared = tmp_path / 'aws-config'
    shared.write_text('[default]\nec2_metadata_service_endpoint = http://untrusted.invalid\n')
    monkeypatch.setenv('AWS_CONFIG_FILE', str(shared))
    monkeypatch.setenv('HTTPS_PROXY', 'http://untrusted.invalid:1')
    monkeypatch.setenv('HTTP_PROXY', 'http://untrusted.invalid:1')
    session = _source_session(WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', 'iam-role'))
    providers = session._session.get_component('credential_provider').providers
    assert len(providers) == 1 and providers[0].METHOD == 'iam-role'
    fetcher = providers[0]._role_fetcher
    assert fetcher._base_url == 'http://169.254.169.254/'
    assert fetcher._imds_v1_disabled
    assert fetcher._session._proxy_config._proxies == {}
    fetcher._session.close()


def test_web_identity_source_sts_pins_ca_endpoint_and_unsigned_client(monkeypatch):
    from outreach.core import kms_workload
    from botocore import UNSIGNED
    monkeypatch.setenv('AWS_ROLE_ARN', ROLE)
    monkeypatch.setenv('AWS_WEB_IDENTITY_TOKEN_FILE', '/tmp/nonexistent-offline-test-token')
    monkeypatch.setenv('AWS_CA_BUNDLE', '/tmp/untrusted-offline-ca')
    config = WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', 'assume-role-with-web-identity')
    session = kms_workload._source_session(config)
    client = MagicMock()
    monkeypatch.setattr(session, 'client', client)
    provider = session._session.get_component('credential_provider').providers[0]
    provider._client_creator('sts', region_name='other', verify=False, endpoint_url='http://untrusted.invalid')
    kwargs = client.call_args.kwargs
    assert kwargs['verify'] is True and kwargs['endpoint_url'] == 'https://sts.eu-north-1.amazonaws.com'
    assert kwargs['config'].signature_version == UNSIGNED and kwargs['config'].proxies == {}
    with pytest.raises(CustodyUnavailable): provider._client_creator('kms')


@pytest.mark.parametrize('method', ['container-role', 'assume-role-with-web-identity'])
def test_incomplete_source_configuration_denies(monkeypatch, method):
    from outreach.core.kms_workload import _source_session
    monkeypatch.delenv('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI', raising=False)
    monkeypatch.delenv('AWS_ROLE_ARN', raising=False)
    with pytest.raises(CustodyUnavailable):
        _source_session(WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', method))


def test_ecs_uses_only_relative_container_provider(monkeypatch):
    from outreach.core.kms_workload import _source_session
    monkeypatch.setenv('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI', '/v2/credentials/local-test')
    session = _source_session(WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', 'container-role'))
    assert [p.METHOD for p in session._session.get_component('credential_provider').providers] == ['container-role']


def test_sdk_debug_logging_denies_before_credential_resolution(monkeypatch):
    import logging
    from outreach.core import kms_workload
    logger = logging.getLogger('botocore.endpoint')
    original = logger.level
    logger.setLevel(logging.DEBUG)
    sdk = MagicMock()
    monkeypatch.setattr(kms_workload.boto3, 'Session', sdk)
    try:
        with pytest.raises(CustodyUnavailable):
            kms_workload._source_session(WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', 'iam-role'))
    finally:
        logger.setLevel(original)
    sdk.assert_not_called()


@pytest.mark.asyncio
async def test_both_clients_close_and_cleanup_errors_are_sanitized(aws):
    provider, _, sts, kms = aws
    sts.close.side_effect = RuntimeError('private-token')
    kms.close.side_effect = RuntimeError('private-key')
    with pytest.raises(CustodyUnavailable) as error:
        await provider.generate(scope().kms_context())
    assert 'private' not in str(error.value)
    sts.close.assert_called_once()
    kms.close.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_sdk_threads_retain_bounded_capacity_and_consume_late_errors(monkeypatch):
    import asyncio
    import threading
    from outreach.core import kms_workload
    provider = AWSKeyProvider(WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', 'iam-role'))
    release = threading.Event()
    started = [threading.Event(), threading.Event()]
    counter, lock = [0], threading.Lock()
    def blocked(*_):
        with lock:
            index = counter[0]
            counter[0] += 1
        started[index].set()
        assert release.wait(5)
        raise CustodyUnavailable('sanitized late failure')
    monkeypatch.setattr(provider, '_operate', blocked)
    tasks = [asyncio.create_task(provider.generate({})) for _ in range(2)]
    errors = []
    loop = asyncio.get_running_loop()
    original = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    try:
        assert await asyncio.to_thread(lambda: all(event.wait(3) for event in started))
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with pytest.raises(CustodyUnavailable, match='capacity'):
            await provider.generate({})
        release.set()
        for _ in range(100):
            if kms_workload._slots._value == 2: break
            await asyncio.sleep(.01)
        assert kms_workload._slots._value == 2
        await asyncio.sleep(.02)
        assert not errors
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.set_exception_handler(original)


def test_fork_child_resets_inherited_locked_pool(monkeypatch):
    import asyncio
    import os
    import signal
    from outreach.core import kms_workload
    provider = AWSKeyProvider(WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', 'iam-role'))
    monkeypatch.setattr(provider, '_operate', lambda *_: (bytes(32), bytes(64)))
    read_fd, write_fd = os.pipe()
    kms_workload._lock.acquire()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        signal.alarm(5)
        try:
            result = asyncio.run(provider.generate({}))
            os.write(write_fd, b'pass' if result == (bytes(32), bytes(64)) else b'fail')
        finally:
            os._exit(0)
    kms_workload._lock.release()
    os.close(write_fd)
    try:
        _, status = os.waitpid(pid, 0)
        assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
        assert os.read(read_fd, 8) == b'pass'
    finally:
        os.close(read_fd)


@pytest.mark.asyncio
async def test_key_timeout_does_not_release_started_call_capacity(monkeypatch):
    import asyncio
    import threading
    from outreach.core import kms_workload
    provider = AWSKeyProvider(WorkloadConfig(ARN, ROLE, ROLE_ID, 'eu-north-1', 'iam-role'))
    release = threading.Event()
    monkeypatch.setattr(provider, '_operate', lambda *_: release.wait(3) and (bytes(32), bytes(64)))
    wait_for = asyncio.wait_for
    monkeypatch.setattr(kms_workload.asyncio, 'wait_for', lambda value, timeout: wait_for(value, .01))
    try:
        with pytest.raises(CustodyUnavailable, match='deadline'):
            await provider.generate({})
        assert kms_workload._slots._value == 1
    finally:
        release.set()
        for _ in range(100):
            if kms_workload._slots._value == 2: break
            await asyncio.sleep(.01)
    assert kms_workload._slots._value == 2


def test_environment_config_factory_and_invalid_types(monkeypatch):
    values = {'KEY_ARN': ARN, 'ROLE_ARN': ROLE, 'ROLE_ID': ROLE_ID, 'REGION': 'eu-north-1', 'CREDENTIAL_PROVIDER': 'iam-role'}
    for suffix, value in values.items(): monkeypatch.setenv('OUTREACH_KMS_' + suffix, value)
    assert WorkloadConfig.from_environment().role_id == ROLE_ID
    with pytest.raises(CustodyUnavailable): WorkloadConfig(ARN, ROLE, [], 'eu-north-1', 'iam-role').validate()


@pytest.mark.asyncio
async def test_bad_wrapped_key_and_submit_failure_are_sanitized_and_release_capacity(aws, monkeypatch):
    from outreach.core import kms_workload
    provider, _, _, kms = aws
    kms.generate_data_key.return_value['CiphertextBlob'] = b''
    with pytest.raises(CustodyUnavailable): await provider.generate({})
    monkeypatch.setattr(kms_workload._pool, 'submit', MagicMock(side_effect=RuntimeError('private-key')))
    with pytest.raises(CustodyUnavailable) as error: await provider.generate({})
    assert 'private-key' not in str(error.value) and kms_workload._slots._value == 2
