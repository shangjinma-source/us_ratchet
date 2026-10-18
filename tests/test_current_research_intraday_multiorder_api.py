import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_research_intraday_multiorder import create_router,BASE
import test_current_research_intraday_multiorder_service as fixtures

class MultiorderRouteTests(unittest.TestCase):
    def client(self,service):
        app=FastAPI();app.include_router(create_router(service=service));return TestClient(app)
    def test_http_preview_accept_fill_restart_retry_compact(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=fixtures.MultiorderServiceTests().fixture(root);aid=before['account_id']
            with self.client(service) as client:
                request=dict(account_id=aid,expected_revision=before['revision'])
                response=client.post(BASE+'/preview',json=request);self.assertEqual(response.status_code,200,response.text)
                proposal=response.json()['proposal'];accept=dict(request,proposal_id=proposal['proposal_id'],operation_id='http-accept')
                response=client.post(BASE+'/accept',json=accept);self.assertEqual(response.status_code,200,response.text)
                account=response.json()['account'];order=account['orders'][0]
                clock[0]+=timedelta(minutes=3)
                fill=dict(event_id='http-fill',kind='FILL',expected_revision=account['revision'],order_id=order['order_id'],quantity=100,price='37',fees='1',executed_at=clock[0].isoformat())
                response=client.post(BASE+'/event',json=dict(account_id=aid,event=fill));self.assertEqual(response.status_code,200,response.text)
                account=response.json()['account'];self.assertEqual(account['cash'],'16499');self.assertEqual(account['recorded_sell_notional'],'3000')
                self.assertEqual(client.post(BASE+'/event',json=dict(account_id=aid,event=fill)).json()['account'],account)
                service.proposals.clear();service.evidence_provider=lambda **_:self.fail('successful retry must not call provider')
                self.assertEqual(client.post(BASE+'/accept',json=accept).json()['account'],account)
                self.assertEqual(client.get(BASE+'/account',params={'account_id':aid}).json()['account'],account)
                for forbidden in ('causal_inputs','execution_evidence','base64','source_hashes','"genesis"'):
                    self.assertNotIn(forbidden,response.text)
    def test_invalid_fields_types_duplicate_queries_and_json_never_write(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=fixtures.MultiorderServiceTests().fixture(root);aid=before['account_id']
            with self.client(service) as client:
                original=service.store.path.read_bytes()
                good=dict(account_id=aid,expected_revision=before['revision'])
                bodies=[dict(good,evidence={}),dict(good,provider='evil'),dict(good,account_id=True),dict(good,expected_revision=3),[],dict(good,price='1')]
                for body in bodies:self.assertEqual(client.post(BASE+'/preview',json=body).status_code,400)
                for query in [('account_id='+aid+'&account_id='+aid),('account_id='+aid+'&source=x'),('account_id='+aid+'&expected_revision='+before['revision'])]:
                    self.assertEqual(client.get(BASE+'/account?'+query).status_code,400)
                self.assertEqual(client.post(BASE+'/preview?unexpected=1',json=good).status_code,400)
                self.assertEqual(client.request('GET',BASE+'/account',params={'account_id':aid},json={'evidence':{}}).status_code,400)
                duplicate='{"account_id":'+json.dumps(aid)+',"account_id":'+json.dumps(aid)+',"expected_revision":'+json.dumps(before['revision'])+'}'
                self.assertEqual(client.post(BASE+'/preview',content=duplicate,headers={'content-type':'application/json'}).status_code,400)
                fill=dict(event_id='bad',kind='FILL',expected_revision=before['revision'],order_id='some-order',quantity=1,price='37',fees='0',executed_at=clock[0].isoformat())
                for change in [dict(recorded_at=clock[0].isoformat()),dict(quantity=True),dict(quantity='1'),dict(price=37.0),dict(fees=False),dict(source_hashes={}),dict(kind=[]),dict(executed_at=1)]:
                    r=client.post(BASE+'/event',json=dict(account_id=aid,event=dict(fill,**change)))
                    self.assertEqual(r.status_code,400,r.text)
                self.assertEqual(service.store.read(aid),before);self.assertEqual(service.store.path.read_bytes(),original);self.assertEqual(calls,[])
    def test_commit_then_response_failure_keeps_exact_retry(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=fixtures.MultiorderServiceTests().fixture(root);aid=before['account_id']
            with self.client(service) as client:
                p=client.post(BASE+'/preview',json=dict(account_id=aid,expected_revision=before['revision'])).json()['proposal']
                body=dict(account_id=aid,proposal_id=p['proposal_id'],operation_id='response-lost',expected_revision=before['revision'])
                with patch.object(service,'_response',side_effect=ValueError('ACCOUNT_CHANGED_AFTER_OPERATION_RETRY_WITH_SAME_ID')):
                    failed=client.post(BASE+'/accept',json=body)
                self.assertEqual(failed.status_code,400)
                self.assertEqual(failed.json()['mutation_outcome'],'UNKNOWN_RETRY_SAME_REQUEST')
                self.assertTrue(failed.json()['retry_same_request'])
                self.assertEqual(failed.json()['error_code'],'ACCOUNT_CHANGED_AFTER_OPERATION_RETRY_WITH_SAME_ID')
                committed=service.store.read(aid);self.assertNotEqual(committed['revision'],before['revision'])
                service.proposals.clear();service.evidence_provider=lambda **_:self.fail('retry revalidated quote')
                retry=client.post(BASE+'/accept',json=body)
                self.assertEqual(retry.status_code,200,retry.text)
                self.assertEqual(retry.json()['mutation_outcome'],'APPLIED_OR_IDEMPOTENT')
                self.assertEqual(retry.json()['account']['revision'],committed['revision'])
                with patch.object(service,'accept',side_effect=ValueError('STALE_ACCOUNT_REVISION:unclassified-detail')):
                    unclassified=client.post(BASE+'/accept',json=body)
                self.assertEqual(unclassified.json()['mutation_outcome'],'UNKNOWN_RETRY_SAME_REQUEST')
                malformed=client.post(BASE+'/accept',json=dict(body,price='1'))
                self.assertEqual(malformed.json()['mutation_outcome'],'NOT_APPLIED')
                self.assertFalse(malformed.json()['retry_same_request'])
                missing=client.get(BASE+'/account',params={'account_id':'not-found'})
                self.assertEqual(missing.json()['mutation_outcome'],'NOT_A_MUTATION')

    def test_expired_accept_and_legacy_account_event_no_write(self):
        from pathlib import Path
        from data.current_research_intraday_paper_store import IntradayPaperStore
        from data.current_research_intraday_paper_ledger import _initial
        from data.current_research_intraday_multiorder_service import IntradayMultiorderService
        with tempfile.TemporaryDirectory() as root:
            service,before,clock,current,calls=fixtures.MultiorderServiceTests().fixture(root);aid=before['account_id']
            with self.client(service) as client:
                p=client.post(BASE+'/preview',json=dict(account_id=aid,expected_revision=before['revision'])).json()['proposal']
                clock[0]+=timedelta(seconds=120)
                r=client.post(BASE+'/accept',json=dict(account_id=aid,proposal_id=p['proposal_id'],operation_id='expired-http',expected_revision=before['revision']))
                self.assertEqual(r.status_code,400);self.assertEqual(r.json()['mutation_outcome'],'NOT_APPLIED');self.assertEqual(service.store.read(aid),before)
            initial=_initial(before['acceptance']);store=IntradayPaperStore(Path(root)/'legacy');store.accept(aid,initial['acceptance']['proposal']['proposal_id'],'initial',lambda:initial)
            isolated=IntradayMultiorderService(store=store,clock=lambda:clock[0]);bytes_before=store.path.read_bytes()
            with self.client(isolated) as client:
                event=dict(event_id='legacy',kind='CANCEL',expected_revision=initial['revision'],order_id=initial['order']['order_id'],cancelled_at=initial['order']['accepted_at'])
                r=client.post(BASE+'/event',json=dict(account_id=aid,event=event))
                self.assertEqual(r.status_code,400);self.assertIn('RETARGET_ACCEPTANCE_REQUIRED',r.json()['message'])
            self.assertEqual(store.path.read_bytes(),bytes_before);self.assertEqual(store.read(aid),initial)

if __name__=='__main__':unittest.main()
