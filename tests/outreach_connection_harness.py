"""Owned F6 Redis drill: real worker/guards, synthetic HTTP transport only."""
import asyncio
import os
from datetime import datetime,timezone
from urllib.parse import urlparse
import httpx
from celery import Celery
from motor.motor_asyncio import AsyncIOMotorClient

if os.getenv('UNRAVLER_CONNECTION_DRILL')!='1':raise RuntimeError('Explicit local drill required')
URI,DB,QUEUE,BROKER=(os.environ[key] for key in ('UNRAVLER_DRILL_URI','UNRAVLER_DRILL_DB','UNRAVLER_DRILL_QUEUE','UNRAVLER_DRILL_BROKER'))
if not DB.startswith('test_owned_ordering_') or not QUEUE.startswith('unravler_connection_'):raise RuntimeError('Owned names required')
if any(urlparse(value).hostname!='127.0.0.1' for value in (URI,BROKER)):raise RuntimeError('Loopback services only')
app=Celery('connection_drill',broker=BROKER)
app.conf.update(task_default_queue=QUEUE,task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,
    task_ignore_result=True,broker_transport_options={'visibility_timeout':3,'global_keyprefix':QUEUE+':'})
OriginalClient=httpx.AsyncClient

@app.task(bind=True,name='celery_workers.tasks.outreach.execute_sequence_job')
def execute(self,workspace,job_id):
    return asyncio.run(run(workspace,job_id,bool(self.request.delivery_info.get('redelivered'))))

async def run(workspace,job_id,redelivered):
    from outreach.tasks import sequence_dispatch,connection_recheck
    from outreach.tasks.sequence_executor import SequenceExecutor
    from outreach.core.execution_outbox import ExecutionOutbox
    client=AsyncIOMotorClient(URI,tz_aware=True);db=client[DB]
    try:
        await db.drill_controls.update_one({'_id':job_id},{'$inc':{'deliveries':1},'$set':{'redelivered':redelivered}})
        control=await db.drill_controls.find_one({'_id':job_id})
        async def checkpoint(stage):
            await db.drill_controls.update_one({'_id':job_id},{'$set':{'checkpoint':stage}})
            if control['stage']==stage and not control.get('resume'):await asyncio.Event().wait()
        async def response(request):
            if request.method!='GET' or request.url.path!='/voyager/api/relationships/connections':raise AssertionError('Unexpected HTTP request')
            await db.drill_controls.update_one({'_id':job_id},{'$inc':{'synthetic_reads':1}})
            return httpx.Response(200,json={'elements':[{'profileUrn':'urn:li:fsd_profile:original'}],
                'paging':{'start':0,'count':1000,'total':1}})
        class SyntheticClient(OriginalClient):
            def __init__(self,*args,**kwargs):
                kwargs.pop('proxy',None);kwargs['transport']=httpx.MockTransport(response)
                super().__init__(*args,**kwargs)
        httpx.AsyncClient=SyntheticClient
        original_apply=connection_recheck.apply_observation
        async def apply(*args,**kwargs):
            await checkpoint('received_fact')
            return await original_apply(*args,**kwargs)
        connection_recheck.apply_observation=apply
        async def executor(lead_id,current,**kwargs):
            if control['stage']=='possible' and not control.get('resume'):
                job=await current.outreach_sequence_jobs.find_one({'_id':job_id})
                outbox=ExecutionOutbox(current)
                assert await outbox.claim(workspace,job['intent_id'],job['owner'])
                assert await outbox.begin_submission(workspace,job['intent_id'],job['owner'])
                await checkpoint('possible')
            return await SequenceExecutor.execute_lead_step(lead_id,current,**kwargs)
        result=await sequence_dispatch.execute_job(db,workspace,job_id,executor=executor)
        if result.get('status')=='connection_redirected':await checkpoint('redirected')
        await db.drill_controls.update_one({'_id':job_id},{'$set':{'result':result['status'],'finished':True}})
        return result
    finally:client.close()
