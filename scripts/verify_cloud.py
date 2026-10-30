"""Verify PostgreSQL in a newly allocated schema; never reset application data."""
import csv
import asyncio
import io
import json
import os
from pathlib import Path
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url

root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
runtime=json.loads((root/'work/cloud-runtime.json').read_text())
url=make_url(runtime['DATABASE_URL']).set(drivername='postgresql+psycopg')
url=url.set(host=url.host.replace('-pooler.', '.'))  # Schema-scoped verification uses the documented direct connection.
schema='verify_'+uuid.uuid4().hex
admin=create_engine(url,connect_args={'connect_timeout':10,'prepare_threshold':None})
with admin.begin() as connection:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
admin.dispose()
url=url.update_query_dict({'options':'-csearch_path='+schema})
os.environ.update(runtime)
os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
os.environ['WORKER_POLL_SECONDS']='2'
from backend.main import app
from backend.db import transaction, now, stamp
from backend.models import Order, Setting, Incident, Job, ModelArtifact
from backend.services import core, worker
from fastapi.testclient import TestClient

async def paused_background_loop():
    await asyncio.Event().wait()
worker.run = paused_background_loop  # This script drives ticks explicitly; avoid WAN lock contention from test-only polling.

def post(c,path,body,key=None):
    return c.post(path,json=body,headers={'Idempotency-Key':key or str(uuid.uuid4())})

checks={}
with TestClient(app) as c:
    print('Cloud schema initialized; checking APIs',flush=True)
    login=c.post('/api/console/login',json={'password':runtime['OPERATOR_PASSWORD']})
    assert login.status_code==200
    c.headers.update({'Authorization':'Bearer '+login.json()['token'],'X-Customer-Session':uuid.uuid4().hex+uuid.uuid4().hex})
    assert c.get('/api/health').status_code==200
    assert len(c.get('/api/products').json())==20
    booking={'user_name':'Cloud Verification Fixture','phone':'DEMO_CONTACT','address':'DEMO_LOCATION','contact_mode':'demo','pincode':'560038','items':[{'product_id':'PROD-109','qty':1}],'payment_method':'UPI'}
    rows=[]
    for index in range(20):
        response=post(c,'/api/orders',booking)
        assert response.status_code==201
        rows.append(response.json())
        if (index+1)%5==0: print('Verified booking count:',index+1,flush=True)
    assert sum(r['initial_failed'] for r in rows)==12
    checks['postgres_default_pattern_20_bookings_12_failures']=True
    with ThreadPoolExecutor(max_workers=4) as pool:
        concurrent=list(pool.map(lambda _:post(c,'/api/orders',booking).json(),range(8)))
    assert len({r['booking_seq'] for r in concurrent})==8
    checks['postgres_concurrent_unique_bookings']=True
    first=post(c,'/api/orders',booking,'cloud-idempotency-once').json()
    assert post(c,'/api/orders',booking,'cloud-idempotency-once').json()==first
    checks['postgres_idempotency']=True
    config=c.get('/api/console/settings').json()
    c.post('/api/console/settings',json={**config,'force_error':'OUT_OF_STOCK'})
    order=post(c,'/api/orders',booking).json()
    incidents=c.get('/api/console/incidents?limit=100').json()['items']
    inc=next(i for i in incidents if i['order_id']==order['id'])
    result=post(c,f'/api/console/incidents/{inc["id"]}/approve',{'action':'REASSIGN_STORE','expected_version':inc['version'],'note':'Cloud verification fixture','confirmed':False})
    assert result.status_code==200 and result.json()['ok']
    history=c.get('/api/console/history?q=OUT_OF_STOCK&actor=OPERATOR').json()['items']
    exported=c.get('/api/console/history?q=OUT_OF_STOCK&actor=OPERATOR&format=csv')
    assert len(history)==len(list(csv.DictReader(io.StringIO(exported.text)))) and history
    assert c.get('/api/console/history?since='+stamp(now()-timedelta(days=1)).replace('+','%2B')).status_code==200
    checks['postgres_approval_history_csv_and_date_filters']=True
    c.post('/api/console/settings',json={**config,'force_error':'UNMATCHED_DEBIT'})
    order=post(c,'/api/orders',{**booking,'items':[{'product_id':'PROD-101','qty':1}]}).json()
    incidents=c.get('/api/console/incidents?limit=100').json()['items']
    inc=next(i for i in incidents if i['order_id']==order['id'])
    def action(inc,name,confirmed=False):
        response=post(c,f'/api/console/incidents/{inc["id"]}/action',{'action':name,'expected_version':inc['version'],'note':'Cloud verification fixture','confirmed':confirmed})
        assert response.status_code==200 and response.json()['ok']
        return response.json()['incident']
    inc=action(inc,'CHECK_PAYMENT')
    assert inc['order']['payment']['attempt_count']==1
    inc=action(inc,'REFUND',True)
    assert inc['order']['refund']['status']=='PENDING'
    with transaction() as s:
        for j in s.scalars(select(Job).where(Job.order_id==order['id'],Job.kind=='REFUND_SETTLE')):
            j.due_at=stamp(now()-timedelta(seconds=1))
    worker.tick()
    updated=c.get('/api/orders/'+order['id']).json()
    assert updated['refund']['status']=='COMPLETED'
    checks['postgres_reconciliation_and_asynchronous_refund']=True
    with transaction() as s:
        sequence=s.get(Setting,'sequence').value['next']
    core.initialize()
    with transaction() as s:
        assert s.get(Setting,'sequence').value['next']==sequence
    checks['postgres_restart_preserves_sequence']=True

result={'passed':True,'timestamp':stamp(),'isolated_schema':schema,'checks':checks,'note':'Only a newly generated verification schema was used; application public schema was not modified.'}
(root/'work/cloud-postgres-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
