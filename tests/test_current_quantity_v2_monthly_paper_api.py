from copy import deepcopy
from contextlib import contextmanager,closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_current_quantity_v2_monthly_store as monthly_store
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from api.current_quantity_v2_paper import create_router,PREFIX

class MonthlyApiTests(unittest.TestCase):
    def setup(self,folder):
        store,state,args,p,r,calls=monthly_store.MonthlyStoreTests().setup(folder);guard=[]
        @contextmanager
        def source_guard():
            guard.append('held')
            try:yield
            finally:guard.remove('held')
        def resolver(current,pid,now):
            self.assertEqual(guard,['held']);calls.append(now);return deepcopy(p)
        def previewer(**kw):
            return dict(status='READY',scope='MONTHLY_RETARGET',target_scope=p['target_scope'],account_id=r['account_id'],
                capital_decision_id=p['capital_decision_id'],prior_revision=r['expected_revision'],source_bytes_verified=True,
                orders_created=False,account_mutated=False,research_only=True,execution_blocked=True,real_account=False,
                proposal_id=p['proposal_id'],orders=p['orders'])
        service=QuantityV2PaperService(store=store,monthly_previewer=previewer,monthly_resolver=resolver,
            monthly_source_guard=source_guard,clock=r['clock'])
        app=FastAPI();app.include_router(create_router(service=service))
        req={k:r[k] for k in ('account_id','proposal_id','operation_id','expected_revision')}
        return service,TestClient(app),state,p,req,guard,calls
    def test_http_preview_accept_retry_and_strict_fields(self):
        with TemporaryDirectory() as folder:
            s,c,state,p,req,guard,calls=self.setup(folder)
            body=dict(account_id=req['account_id'],decision_id=p['capital_decision_id'],expected_revision=req['expected_revision'])
            with c:
                self.assertEqual(c.post(PREFIX+'/monthly/preview',json=body).status_code,200)
                with patch.object(s,'monthly_previewer',side_effect=AssertionError('invalid ID callback')):
                    for invalid in ('x','A'*64,'a'*63):
                        self.assertEqual(c.post(PREFIX+'/monthly/preview',json=dict(body,decision_id=invalid)).status_code,400)
                for extra in ('cash','targets','prices','source_hashes','now'):
                    self.assertEqual(c.post(PREFIX+'/monthly/preview',json=dict(body,**{extra:{}})).status_code,400)
                self.assertEqual(c.post(PREFIX+'/monthly/accept?x=1',json=req).status_code,400)
                original=s.store.save
                def checked(*args):self.assertEqual(guard,['held']);return original(*args)
                with patch.object(s.store,'save',side_effect=checked):response=c.post(PREFIX+'/monthly/accept',json=req)
                self.assertEqual(response.status_code,200,response.text);self.assertEqual(guard,[])
                value=response.json();self.assertEqual(value['cash'],state['ledger']['cash']);self.assertTrue(value['capabilities']['monthly']['configured'])
                s.monthly_resolver=None;s.monthly_source_guard=None;s.clock=lambda:self.fail('retry clock')
                replay=c.post(PREFIX+'/monthly/accept',json=req);self.assertEqual(replay.status_code,200,replay.text)
                self.assertEqual(replay.json()['revision'],value['revision']);self.assertFalse(replay.json()['capabilities']['monthly']['configured']);self.assertEqual(len(calls),1)
    def test_real_raw_bridge_http_delayed_accept_response_loss_exact_retry(self):
        from test_current_quantity_v2_monthly_service import fixture
        from datetime import timedelta
        from threading import RLock
        with TemporaryDirectory() as folder:
            paper,bridge,package,clock,state,did=fixture(folder)
            lock=RLock();paper.monthly_previewer=bridge.preview;paper.monthly_resolver=bridge.monthly_resolver
            paper.monthly_source_guard=lambda:lock;paper.clock=lambda:clock[0]
            app=FastAPI();app.include_router(create_router(service=paper))
            aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            with TestClient(app) as client:
                response=client.post(PREFIX+'/monthly/preview',json=dict(account_id=aid,decision_id=did,expected_revision=rev))
                self.assertEqual(response.status_code,200,response.text)
                preview=response.json();self.assertNotIn('causal_inputs',preview);self.assertNotIn('binding',preview)
                clock[0]+=timedelta(seconds=1)
                request=dict(account_id=aid,proposal_id=preview['proposal_id'],operation_id='raw-http',expected_revision=rev)
                with patch.object(paper,'_response',side_effect=OSError('lost after commit')):
                    response=client.post(PREFIX+'/monthly/accept',json=request)
                self.assertEqual(response.status_code,503);self.assertEqual(response.json()['mutation_outcome'],'UNKNOWN_RETRY_SAME_REQUEST')
                saved=paper.store.read(aid);self.assertNotEqual(saved['ledger']['revision'],rev)
                bridge._proposals.clear();bridge.resolver=lambda *_:self.fail('retry source');clock[0]+=timedelta(days=90)
                response=client.post(PREFIX+'/monthly/accept',json=request)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['revision'],saved['ledger']['revision'])
                for key in ('cash','shares','recorded_fees','events'):self.assertEqual(saved['ledger'][key],state['ledger'][key])
                self.assertEqual(response.json()['capital_decision_id'],did)

    def test_guard_through_commit_and_rollback_missing_capability(self):
        with TemporaryDirectory() as folder:
            s,c,state,p,req,guard,calls=self.setup(folder)
            transaction=s.store.transaction
            @contextmanager
            def observed_transaction(**kw):
                with transaction(**kw) as db:
                    yield db
                    self.assertEqual(guard,['held']) # immediately before outer commit
                self.assertEqual(guard,['held']) # immediately after commit, before return
            with c,patch.object(s.store,'transaction',observed_transaction):
                result=c.post(PREFIX+'/monthly/accept',json=req);self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(guard,[])
        with TemporaryDirectory() as folder:
            s,c,state,p,req,guard,calls=self.setup(folder)
            with closing(sqlite3.connect(s.store.path,isolation_level=None)) as db:db.execute("CREATE TRIGGER fail BEFORE INSERT ON v2_accept_operations BEGIN SELECT RAISE(ABORT,'failed'); END")
            with c:
                result=c.post(PREFIX+'/monthly/accept',json=req);self.assertEqual(result.status_code,503)
                self.assertEqual(result.json()['mutation_outcome'],'UNKNOWN_RETRY_SAME_REQUEST');self.assertEqual(guard,[]);self.assertEqual(s.store.read(req['account_id']),state)
                s.monthly_source_guard=None
                result=c.post(PREFIX+'/monthly/preview',json=dict(account_id=req['account_id'],decision_id=p['capital_decision_id'],expected_revision=req['expected_revision']))
                self.assertEqual(result.json()['error_code'],'MONTHLY_SOURCE_UNAVAILABLE')

if __name__=='__main__':unittest.main()
