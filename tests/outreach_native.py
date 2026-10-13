"""Owned random-port replica set for mandatory native ordering checks."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

@pytest.fixture(scope='module')
def replica_server():
    executable = shutil.which('mongod')
    assert executable, 'Native ordering checks require mongod'
    with tempfile.TemporaryDirectory(prefix='unravler-native-ordering-') as directory:
        storage = Path(directory) / 'data'; storage.mkdir(mode=0o700)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        name = 'owned_' + uuid.uuid4().hex
        uri = f'mongodb://127.0.0.1:{port}/?directConnection=true'
        process = subprocess.Popen([executable, '--dbpath', str(storage), '--bind_ip', '127.0.0.1',
            '--port', str(port), '--replSet', name, '--nounixsocket', '--logpath', str(Path(directory) / 'mongo.log'),
            '--setParameter', 'diagnosticDataCollectionEnabled=false'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = MongoClient(uri, serverSelectionTimeoutMS=200, connectTimeoutMS=200)
        try:
            deadline = time.monotonic() + 20
            initialized = False
            while time.monotonic() < deadline:
                assert process.poll() is None, 'Owned Mongo failed to start'
                try:
                    if not initialized:
                        client.admin.command('replSetInitiate', {'_id': name, 'members': [{'_id': 0, 'host': f'127.0.0.1:{port}'}]})
                        initialized = True
                    if client.admin.command('hello').get('isWritablePrimary'): break
                except PyMongoError: pass
                time.sleep(0.05)
            else: raise AssertionError('Owned replica set did not become ready')
            yield uri
            assert not [value for value in client.list_database_names() if value.startswith('test_owned_ordering_')]
        finally:
            client.close()
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

@pytest_asyncio.fixture
async def replica_db(replica_server):
    client = AsyncIOMotorClient(replica_server, tz_aware=True, serverSelectionTimeoutMS=2000)
    name = 'test_owned_ordering_' + uuid.uuid4().hex
    try: yield client[name]
    finally: await client.drop_database(name); client.close()
