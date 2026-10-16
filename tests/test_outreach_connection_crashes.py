"""SIGKILL and Redis redelivery: original positive facts survive worker loss."""
import asyncio
from datetime import datetime,timedelta,timezone
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import uuid
import pytest
from celery import Celery
from redis import Redis
from tests.outreach_native import replica_server,replica_db  # noqa:F401
from tests.test_outreach_sender_resume_mongo import local_custody  # noqa:F401
from tests.test_outreach_connection_waits_mongo import seed,negative,WS
from outreach.tasks import sequence_dispatch

pytestmark=[pytest.mark.asyncio,pytest.mark.atomic_dispatch,pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO')!='1' or os.getenv('OUTREACH_TEST_CONNECTION_BROKER')!='1',reason='Owned F6 services opt-in')]

async def wait_for(read,predicate,timeout=35):
    async with asyncio.timeout(timeout):
        while True:
            value=await read()
            if value and predicate(value):return value
            await asyncio.sleep(.1)

@pytest.mark.parametrize('stage',['received_fact','redirected','possible'])
async def test_real_redelivery_keeps_original_observation_or_possible_hold(replica_db,replica_server,tmp_path,stage):
    assert shutil.which('redis-server'),'Owned Redis runtime required'
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    redis_process=subprocess.Popen(['redis-server','--bind','127.0.0.1','--port',str(port),'--save','','--appendonly','no',
        '--dir',str(tmp_path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    redis=Redis(host='127.0.0.1',port=port,socket_connect_timeout=.2)
    processes=[];handles=[];queue='unravler_connection_'+uuid.uuid4().hex
    broker=f'redis://127.0.0.1:{port}/0';publisher=Celery('f6_publisher',broker=broker)
    publisher.conf.broker_transport_options={'visibility_timeout':3,'global_keyprefix':queue+':'}
    def start_worker():
        env={key:os.environ[key] for key in ('PATH','ENCRYPTION_KEY')}
        env.update({'UNRAVLER_CONNECTION_DRILL':'1','UNRAVLER_DRILL_URI':replica_server,'UNRAVLER_DRILL_DB':replica_db.name,
            'UNRAVLER_DRILL_QUEUE':queue,'UNRAVLER_DRILL_BROKER':broker,'OUTREACH_LIVE_ACTIONS_ENABLED':'true',
            'OUTREACH_RESTORE_FENCING_ENABLED':'false','OUTREACH_CREDENTIAL_CUSTODY_MODE':'legacy_fernet','PYTHONUNBUFFERED':'1'})
        log=(tmp_path/f'worker-{len(processes)}.log').open('w');handles.append(log)
        processes.append(subprocess.Popen([sys.executable,'-m','celery','-A','tests.outreach_connection_harness:app','worker',
            '--pool=solo','--loglevel=WARNING','--without-heartbeat','--without-gossip','--without-mingle','-Q',queue],
            cwd=Path(__file__).resolve().parents[1],env=env,stdout=log,stderr=subprocess.STDOUT))
    try:
        async def ready():
            try:return await asyncio.to_thread(redis.ping)
            except Exception:return False
        await wait_for(ready,bool,10)
        await seed(replica_db);scope=await negative(replica_db)
        now=datetime.now(timezone.utc)
        await replica_db.outreach_accounts.update_one({}, {'$set':{'inbox_sync':{'status':'complete','credential_generation':'original',
            'coverage_started_at':now,'completed_at':now,'parser_version':__import__('outreach.core.inbox_freshness',fromlist=['PARSER_VERSION']).PARSER_VERSION}}})
        assert (await sequence_dispatch.prepare_due(replica_db))['prepared']==1
        job=await replica_db.outreach_sequence_jobs.find_one({});key=job['_id']
        await replica_db.drill_controls.insert_one({'_id':key,'stage':stage,'deliveries':0,'synthetic_reads':0})
        read=lambda:replica_db.drill_controls.find_one({'_id':key})
        start_worker()
        def publish(task,**kwargs):kwargs['queue']=queue;return publisher.send_task(task,**kwargs)
        assert (await sequence_dispatch.publish_due(replica_db,publish))['published']==1
        await wait_for(read,lambda value:value.get('checkpoint')==stage)
        processes[0].kill();await asyncio.to_thread(processes[0].wait,5)
        first=await read();saved=await replica_db.outreach_connection_waits.find_one({'_id':scope['_id']})
        past=datetime.now(timezone.utc)-timedelta(minutes=5)
        await replica_db.drill_controls.update_one({'_id':key},{'$set':{'resume':True}})
        await replica_db.outreach_sequence_jobs.update_one({'_id':key},{'$set':{'claim_expires_at':past}})
        await replica_db.outreach_leads.update_one({'id':'lead'},{'$set':{'execution_claimed_at':past}})
        await asyncio.sleep(4);start_worker()
        result=await wait_for(read,lambda value:value.get('deliveries',0)>=2 and value.get('redelivered') and value.get('finished'))
        final=await replica_db.outreach_connection_waits.find_one({'_id':scope['_id']})
        if stage=='possible':
            assert final['status']=='held' and result['synthetic_reads']==1
            assert (await replica_db.outreach_intents.find_one({'_id':job['intent_id']}))['status']=='in_flight'
        else:
            assert final['status']=='redirected' and result['synthetic_reads']==first['synthetic_reads']==1
            assert (await replica_db.outreach_leads.find_one({'id':'lead'}))['current_node_id']=='yes'
            assert (await replica_db.outreach_sequence_jobs.find_one({'_id':key}))['status']=='superseded'
            if stage=='redirected':assert final['redirect_receipt']==saved['redirect_receipt']
    finally:
        for process in processes:
            if process.poll() is None:process.kill()
            await asyncio.to_thread(process.wait,5)
        for handle in handles:handle.close()
        redis.close();publisher.close()
        if redis_process.poll() is None:redis_process.terminate()
        await asyncio.to_thread(redis_process.wait,5)
