from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_difference_cash_service import fixture
from api.current_quantity_v2_difference import create_router as difference_router
from api.current_quantity_v2_paper import create_router as paper_router,PREFIX
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_store import QuantityV2PaperStore


class DelayedAcceptTests(unittest.TestCase):
    def test_http_day_expiry_keeps_partial_fill_and_releases_only_reserve(self):
        difference,identifier,_,account,clock=fixture()
        proposal=difference.preview(identifier)
        with TemporaryDirectory() as folder:
            store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3')
            service=QuantityV2PaperService(store=store,initial_resolver=difference.initial_resolver,clock=lambda:clock[0])
            app=FastAPI();app.include_router(paper_router(service=service))
            with TestClient(app) as client:
                state=client.post(PREFIX+'/accept',json=dict(account_id=account['account_id'],proposal_id=proposal['proposal_id'],operation_id='accept')).json()
                order=state['orders'][0];clock[0]+=timedelta(seconds=1)
                fill=dict(event_id='partial',type='FILL',order_id=order['order_id'],expected_revision=state['revision'],quantity=1,price='8',fees='0',executed_at=clock[0].isoformat())
                response=client.post(PREFIX+'/event',json=dict(account_id=account['account_id'],event=fill))
                self.assertEqual(response.status_code,200,response.text);filled=response.json()
                expiry=dict(event_id='expire',type='EXPIRE',order_id=order['order_id'],expected_revision=filled['revision'])
                request=dict(account_id=account['account_id'],event=expiry)
                early=client.post(PREFIX+'/event',json=request)
                self.assertEqual(early.status_code,409);self.assertEqual(early.json()['mutation_outcome'],'NOT_APPLIED')
                clock[0]=datetime.fromisoformat(order['session_close'])+timedelta(seconds=1)
                response=client.post(PREFIX+'/event',json=request)
                self.assertEqual(response.status_code,200,response.text);expired=response.json()
                self.assertEqual(expired['cash'],filled['cash']);self.assertEqual(expired['shares'],filled['shares'])
                self.assertEqual(expired['reserved_cash'],'0');self.assertEqual(expired['orders'][0]['closed'],'EXPIRED')
                self.assertEqual(expired['orders'][0]['filled_quantity'],1);self.assertEqual(expired['event_count'],2)
                self.assertEqual(client.post(PREFIX+'/event',json=request).json(),expired)

    def test_expired_proposal_http_is_definite_rejection(self):
        difference,identifier,_,account,clock=fixture()
        preview=difference.preview(identifier);clock[0]+=timedelta(minutes=3)
        with TemporaryDirectory() as folder:
            store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3')
            service=QuantityV2PaperService(store=store,initial_resolver=difference.initial_resolver,clock=lambda:clock[0])
            app=FastAPI();app.include_router(paper_router(service=service))
            with TestClient(app) as client:
                response=client.post(PREFIX+'/accept',json=dict(account_id=account['account_id'],proposal_id=preview['proposal_id'],operation_id='expired'))
                self.assertEqual(response.status_code,409,response.text)
                self.assertEqual(response.json()['mutation_outcome'],'NOT_APPLIED')
                self.assertEqual(response.json()['error_code'],'REFERENCE_NOT_ACCEPTABLE')
                with self.assertRaises(Exception):store.read(account['account_id'])

    def test_http_preview_later_accept_fill_exact_retry(self):
        difference,identifier,package,account,clock=fixture()
        with TemporaryDirectory() as folder:
            store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3')
            service=QuantityV2PaperService(store=store,initial_resolver=difference.initial_resolver,clock=lambda:clock[0])
            app=FastAPI();app.include_router(difference_router(service=difference));app.include_router(paper_router(service=service))
            with TestClient(app) as client:
                preview=client.post('/api/current_portfolio_research/difference',json={'decision_id':identifier}).json()
                self.assertEqual(preview['status'],'READY')
                request=dict(account_id=account['account_id'],proposal_id=preview['proposal_id'],operation_id='accept')
                preview['orders'].clear() # Client mutations never alter cached original.
                clock[0]+=timedelta(seconds=1)
                response=client.post(PREFIX+'/accept',json=request);self.assertEqual(response.status_code,200,response.text)
                state=response.json();self.assertEqual(len(state['orders']),1)
                self.assertEqual(state['capital_decision_id'],identifier)
                self.assertEqual(state['research_id'],identifier[:24])
                self.assertEqual(state['securities']['A']['ticker'],'AAA')
                self.assertEqual(store.read(account['account_id'])['genesis']['acceptance']['proposal']['proposal_id'],request['proposal_id'])
                clock[0]+=timedelta(minutes=1)
                e=dict(event_id='fill',type='FILL',order_id=state['orders'][0]['order_id'],expected_revision=state['revision'],
                       quantity=1,price='8',fees='0',executed_at=clock[0].isoformat())
                response=client.post(PREFIX+'/event',json=dict(account_id=account['account_id'],event=e))
                self.assertEqual(response.status_code,200,response.text);latest=response.json()
                self.assertEqual(latest['cash'],'92')
                difference._proposals.clear();package['files'].clear();clock[0]+=timedelta(days=1)
                retry=client.post(PREFIX+'/accept',json=request)
                self.assertEqual(retry.status_code,200);self.assertEqual(retry.json(),latest)

    def test_source_documents_account_and_expiry_fail_without_account(self):
        for mode in ('source','documents','account','expiry','unknown','clock_rollback','slow_source'):
            difference,identifier,package,account,clock=fixture();preview=difference.preview(identifier)
            if mode=='source':package['files']['source']+=b'changed'
            if mode=='documents':package['documents']['identities']=package['documents']['capital_decision']
            if mode=='account':account['cash']='99'
            if mode=='expiry':clock[0]+=timedelta(minutes=3)
            if mode=='unknown':preview['proposal_id']='missing'
            if mode=='clock_rollback':clock[0]-=timedelta(microseconds=1)
            if mode=='slow_source':
                original=difference.resolver
                def slow(identifier):
                    result=original(identifier);clock[0]+=timedelta(minutes=3)
                    return result
                difference.resolver=slow
            with TemporaryDirectory() as folder:
                store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3')
                service=QuantityV2PaperService(store=store,initial_resolver=difference.initial_resolver,clock=lambda:clock[0])
                with self.assertRaises(ValueError):service.accept(account_id=account['account_id'],proposal_id=preview['proposal_id'],operation_id='a')
                with self.assertRaises(Exception):store.read(account['account_id'])

    def test_cache_bound_eviction_account_binding_and_deepcopy(self):
        service,identifier,_,account,clock=fixture();first=service.preview(identifier)
        with self.assertRaisesRegex(ValueError,'ACCOUNT_MISMATCH'):
            service.initial_resolver('other',first['proposal_id'],clock[0])
        resolved=service.initial_resolver(account['account_id'],first['proposal_id'],clock[0]);resolved['proposal']['orders'].clear()
        self.assertTrue(service.initial_resolver(account['account_id'],first['proposal_id'],clock[0])['proposal']['orders'])
        for _ in range(32):
            clock[0]+=timedelta(microseconds=1);self.assertEqual(service.preview(identifier)['status'],'READY')
        self.assertEqual(len(service._proposals),32)
        with self.assertRaisesRegex(ValueError,'UNKNOWN_OR_EVICTED'):
            service.initial_resolver(account['account_id'],first['proposal_id'],clock[0])
        self.assertTrue(all('files' not in saved['package_identity'] for saved in service._proposals.values()))


if __name__=='__main__':unittest.main()
