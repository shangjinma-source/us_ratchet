"""Real ASGI requests to an injected service; no production registration."""
import unittest
import subprocess
from copy import deepcopy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_monthly_research import create_router,PREFIX


class Service:
    def __init__(self):
        self.calls=[];self.failure=None
        self.result=dict(status='READY',account_id='pool',expected_revision='rev',state_revision='rev',
            target_month='2026-11',registration_id='a'*64,decision_id='b'*64,research_id='b'*24,
            selected_for_current_account=True,research_only=True,execution_blocked=True,real_account=False,
            account_mutated=False,orders_created=False,automatic_retry=False,worker_liveness='UNKNOWN')
    def generate(self,**values):
        self.calls.append(('generate',values))
        if self.failure:raise ValueError(self.failure)
        return deepcopy(self.result)
    def current(self,**values):
        self.calls.append(('current',values));return deepcopy(self.result)
    def read(self,**values):
        self.calls.append(('read',values))
        if self.failure:raise ValueError(self.failure)
        return deepcopy(self.result)


class RouterTests(unittest.TestCase):
    def setup(self):
        service=Service();app=FastAPI();app.include_router(create_router(service=service))
        return service,TestClient(app)
    def test_generate_and_read_are_distinct_and_compact(self):
        service,client=self.setup()
        with client:
            request=dict(account_id='pool',expected_revision='rev',retry_failed=False)
            response=client.post(PREFIX+'/generate',json=request)
            self.assertEqual(response.status_code,200);self.assertFalse(response.json()['account_mutated'])
            for status in ('READY','FAILED','ATTEMPT_STARTED','INCOMPLETE'):
                service.result.update(status=status,decision_id='b'*64 if status=='READY' else None,research_id='b'*24 if status=='READY' else None,selected_for_current_account=status=='READY')
                response=client.get(PREFIX,params=dict(account_id='pool',registration_id='a'*64))
                self.assertEqual(response.status_code,200,response.text)
            self.assertEqual([c[0] for c in service.calls],['generate','read','read','read','read'])
    def test_current_recovers_without_registration_and_never_generates(self):
        service,client=self.setup()
        with client:
            for status in ('UNAVAILABLE','PENDING','FAILED'):
                service.result.update(status=status,registration_id=None,decision_id=None,research_id=None,selected_for_current_account=False)
                response=client.get(PREFIX,params={'account_id':'pool'})
                self.assertEqual(response.status_code,200,response.text)
                self.assertFalse(response.json()['automatic_retry'])
            service.result.update(status='PENDING',worker_liveness='RUNNING')
            self.assertEqual(client.get(PREFIX,params={'account_id':'pool'}).status_code,503)
            self.assertEqual(client.get(PREFIX,params={'account_id':'pool','registration_id':''}).status_code,400)
        self.assertEqual([c[0] for c in service.calls],['current']*4)

    def test_invalid_requests_never_call_service(self):
        service,client=self.setup();base=dict(account_id='pool',expected_revision='rev',retry_failed=False)
        with client:
            for change in ({'retry_failed':1},{'retry_failed':'false'},{'cash':20000},{'source_path':'secret'},{'expected_revision':None}):
                self.assertEqual(client.post(PREFIX+'/generate',json={**base,**change}).status_code,400)
            for raw in ('{"account_id":"pool","account_id":"other","expected_revision":"rev","retry_failed":false}', '[]', 'x'*4097):
                self.assertEqual(client.post(PREFIX+'/generate',content=raw).status_code,400)
            self.assertEqual(client.post(PREFIX+'/generate?x=1',json=base).status_code,400)
            for query in ('account_id=pool&registration_id=bad','account_id=pool&account_id=other&registration_id='+'a'*64,'account_id=pool&registration_id='+'A'*64,'account_id=pool&registration_id='+'a'*64+'&path=x'):
                self.assertEqual(client.get(PREFIX+'?'+query).status_code,400)
            self.assertEqual(client.request('GET',PREFIX+'?account_id=pool&registration_id='+'a'*64,content='x').status_code,400)
        self.assertEqual(service.calls,[])
    def test_conflicts_sources_and_corrupt_results_fail_closed(self):
        service,client=self.setup();request=dict(account_id='pool',expected_revision='rev',retry_failed=True)
        with client:
            for code,status in (('STALE_REVISION',409),('MONTHLY_RESEARCH_EXPIRED',409),('MONTHLY_RESEARCH_ACCOUNT_CHANGED',409),('MONTHLY_RESEARCH_SELECTION_UNAVAILABLE',503),('private/source/path',503)):
                service.failure=code;r=client.post(PREFIX+'/generate',json=request)
                self.assertEqual(r.status_code,status);self.assertFalse(r.json()['automatic_retry'])
                self.assertNotIn('private/source/path',r.text)
            service.failure=None
            def timeout(**kwargs):raise subprocess.TimeoutExpired('private-worker-path',300)
            original_generate=service.generate;service.generate=timeout
            r=client.post(PREFIX+'/generate',json=request)
            self.assertEqual(r.status_code,503);self.assertNotIn('private-worker-path',r.text)
            service.generate=original_generate
            original=deepcopy(service.result)
            for change in ({'account_id':'other'},{'state_revision':'old'},{'account_mutated':True},{'capital_decision':{}},{'research_id':'c'*24},{'selected_for_current_account':'true'}):
                service.result={**original,**change}
                self.assertEqual(client.post(PREFIX+'/generate',json=request).status_code,503)

if __name__=='__main__':unittest.main()
