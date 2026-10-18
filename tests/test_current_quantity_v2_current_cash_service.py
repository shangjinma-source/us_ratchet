from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_current_quantity_v2_current_cash_plan as base
from data.current_quantity_v2_current_cash_service import CurrentQuantityV2CurrentCashService
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from api.current_quantity_v2_difference import create_router as difference_router
from api.current_quantity_v2_paper import create_router as paper_router,PREFIX


def fixture(folder,args):
    supplied=deepcopy({k:v for k,v in args.items() if k!='now'});account=deepcopy(supplied['account_state'])
    clock=[datetime.fromisoformat(args['now'])]
    source=CurrentQuantityV2CurrentCashService(resolver=lambda _:deepcopy(supplied),
        account_reader=lambda _:deepcopy(account),clock=lambda:clock[0])
    paper=QuantityV2PaperService(store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3'),
        initial_resolver=source.initial_resolver,clock=lambda:clock[0])
    return source,paper,supplied,account,clock


def app_for(source,paper):
    app=FastAPI();app.include_router(difference_router(service=source));app.include_router(paper_router(service=paper));return app


class CurrentCashServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):base.CurrentCashTests.setUpClass();cls.args=deepcopy(base.CurrentCashTests.args)
    @classmethod
    def tearDownClass(cls):base.CurrentCashTests.tearDownClass()

    def test_prepare_only_on_preview_and_final_source_check(self):
        with TemporaryDirectory() as folder:
            source,paper,supplied,account,clock=fixture(folder,self.args)
            identifier=supplied['capital_decision']['decision_id'];calls=[]
            source.prepare=lambda decision_id:calls.append(decision_id)
            proposal=source.preview(identifier)
            self.assertEqual(proposal['status'],'READY')
            source.initial_resolver(account['account_id'],proposal['proposal_id'],clock[0])
            self.assertEqual(calls,[identifier])
            from data.current_quantity_v2_current_cash_ledger_adapter import freeze_current_cash_proposal
            def drift_after_freezing(plan,package):
                result=freeze_current_cash_proposal(plan,package)
                account['cash']='109'
                return result
            with patch('data.current_quantity_v2_current_cash_service.freeze_current_cash_proposal',
                       side_effect=drift_after_freezing):
                result=source.preview(identifier)
            self.assertEqual(result['status'],'UNAVAILABLE')
            self.assertEqual(result['orders'],[])

    def test_capture_failure_does_not_publish_previous_preview(self):
        with TemporaryDirectory() as folder:
            source,_,supplied,_,_=fixture(folder,self.args)
            identifier=supplied['capital_decision']['decision_id']
            self.assertEqual(source.preview(identifier)['status'],'READY')
            source.prepare=lambda _:(_ for _ in ()).throw(ValueError('CAPTURE_UNAVAILABLE'))
            result=source.preview(identifier)
            self.assertEqual(result['status'],'UNAVAILABLE')
            self.assertEqual(result['orders'],[])
            self.assertIsNone(result['proposal_id'])

    def test_real_asgi_delay_accept_fill_and_exact_retry_without_sources(self):
        with TemporaryDirectory() as folder:
            source,paper,supplied,account,clock=fixture(folder,self.args)
            with TestClient(app_for(source,paper)) as client:
                rid=supplied['capital_decision']['decision_id']
                r=client.post('/api/current_portfolio_research/difference',json={'decision_id':rid})
                self.assertEqual(r.status_code,200,r.text);p=r.json()
                self.assertEqual(p['historical_target_quantities'],{'A':1,'B':1});self.assertEqual(p['target_quantities'],{'A':6,'B':4})
                self.assertEqual(p['frozen_dollar_allocations_exact'],{'A':'60','B':'40'})
                self.assertFalse(p['source_bytes_verified']);self.assertTrue(p['current_execution_bytes_verified'])
                self.assertFalse(p['historical_source_bytes_reverified']);self.assertTrue(p['ledger_acceptance_supported'])
                for key in ('causal_inputs','files_base64','execution_package','frozen_execution_package','pinned_inputs'):
                    self.assertNotIn(key,r.text)
                clock[0]+=timedelta(seconds=1)
                request=dict(account_id=account['account_id'],proposal_id=p['proposal_id'],operation_id='accept')
                accepted=client.post(PREFIX+'/accept',json=request)
                self.assertEqual(accepted.status_code,200,accepted.text);accepted=accepted.json()
                self.assertEqual(accepted['execution_target_id'],p['execution_target_id'])
                self.assertEqual(accepted['cash'],'110');self.assertEqual(accepted['target_quantities'],{'A':6,'B':4})
                order=next(o for o in accepted['orders'] if o['security_id']=='A');clock[0]+=timedelta(seconds=1)
                event=dict(event_id='fill',type='FILL',order_id=order['order_id'],expected_revision=accepted['revision'],quantity=1,price='9',fees='1/5',executed_at=clock[0].isoformat())
                filled=client.post(PREFIX+'/event',json=dict(account_id=account['account_id'],event=event));self.assertEqual(filled.status_code,200,filled.text)
                source._proposals.clear();source.resolver=lambda _:(_ for _ in ()).throw(ValueError('source unavailable'))
                clock[0]+=timedelta(days=50)
                retry=client.post(PREFIX+'/accept',json=request);self.assertEqual(retry.status_code,200,retry.text)
                self.assertEqual(retry.json(),filled.json());self.assertEqual(retry.json()['cash'],'504/5')
                self.assertEqual(QuantityV2PaperStore(paper.store.path).read(account['account_id'])['ledger']['shares'],{'A':1})

    def test_drift_expiry_account_missing_and_request_fields_rejected(self):
        for mode in ('bytes','mapping','account','expiry','rollback','missing'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                source,paper,supplied,account,clock=fixture(folder,self.args)
                with TestClient(app_for(source,paper)) as client:
                    endpoint='/api/current_portfolio_research/difference';body=dict(decision_id=supplied['capital_decision']['decision_id'])
                    for key in ('cash','quotes','account_id','now'):
                        self.assertEqual(client.post(endpoint,json=dict(body,**{key:1})).status_code,400)
                    p=client.post(endpoint,json=body).json()
                    if mode=='bytes':supplied['execution_package']['files']['current/A.raw']+=b' '
                    elif mode=='mapping':supplied['execution_package']['documents']['quote_receipts']['A']='current/B.receipt'
                    elif mode=='account':account['cash']='109'
                    elif mode=='expiry':clock[0]+=timedelta(seconds=121)
                    elif mode=='rollback':clock[0]-=timedelta(seconds=1)
                    else:source._proposals.clear()
                    r=client.post(PREFIX+'/accept',json=dict(account_id=account['account_id'],proposal_id=p['proposal_id'],operation_id='new'))
                    self.assertNotEqual(r.status_code,200,r.text);self.assertEqual(r.json()['orders'],[])
                    with self.assertRaises(ValueError):paper.store.read(account['account_id'])

    def test_return_mutation_does_not_change_cached_proposal_and_final_clock_rollback(self):
        with TemporaryDirectory() as folder:
            source,paper,supplied,account,clock=fixture(folder,self.args);did=supplied['capital_decision']['decision_id']
            p=source.preview(did);identifier=p['proposal_id'];p['orders'][0]['quantity']=999
            original=source.initial_resolver(account['account_id'],identifier,clock[0])
            self.assertEqual(original['proposal']['orders'][0]['quantity'],6)
            original['proposal']['orders'][0]['quantity']=777
            self.assertEqual(source.initial_resolver(account['account_id'],identifier,clock[0])['proposal']['orders'][0]['quantity'],6)
            moments=iter((clock[0],clock[0]+timedelta(seconds=121)))
            paper.clock=lambda:next(moments)
            with self.assertRaises(ValueError):paper.accept(account_id=account['account_id'],proposal_id=identifier,operation_id='slow')
            with self.assertRaises(ValueError):paper.store.read(account['account_id'])
            paper.clock=lambda:clock[0]
            accepted=paper.accept(account_id=account['account_id'],proposal_id=identifier,operation_id='slow')
            self.assertEqual(accepted['cash'],'110')

if __name__=='__main__':unittest.main()
