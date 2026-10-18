from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_paper_ledger import initial
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_chain import build_continuation
from test_current_quantity_v2_paper_chain import inputs
from api.current_quantity_v2_paper import create_router,PREFIX


class ApiTests(unittest.TestCase):
    def setup_service(self,folder):
        _,p,args=initial();calls=[];now=[datetime.fromisoformat(args['now'])]
        def resolver(account_id,proposal_id,at):
            calls.append(at);return dict(proposal=deepcopy(p),account_state=deepcopy(args['account_state']))
        service=QuantityV2PaperService(store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3'),
            initial_resolver=resolver,clock=lambda:now[0])
        app=FastAPI();app.include_router(create_router(service=service))
        return service,TestClient(app),dict(account_id=args['account_state']['account_id'],proposal_id=p['proposal_id'],operation_id='accept'),calls,now

    def test_capability_retry_and_controlled_read_errors(self):
        with TemporaryDirectory() as folder:
            service,client,request,calls,now=self.setup_service(folder)
            with client:
                first=client.post(PREFIX+'/accept',json=request).json()
                self.assertIs(first['capabilities']['continuation']['configured'],False)
                self.assertEqual(first['capabilities']['continuation']['policy'],'EXPLICIT_UNIT_REVIEW')
                service.continuation_review_policy='BOUNDED_PUBLIC_KNOWN_ACTIONS_V1'
                service.continuation_previewer=lambda **kw: None
                service.continuation_resolver=lambda *args: None
                replay=client.post(PREFIX+'/accept',json=request).json()
                self.assertIs(replay['capabilities']['continuation']['configured'],True)
                self.assertEqual(replay['capabilities']['continuation']['policy'],'BOUNDED_PUBLIC_KNOWN_ACTIONS_V1')
                self.assertEqual(len(calls),1)
                self.assertEqual(replay['revision'],first['revision'])
                for code in ['UNIT_REVIEW_SOURCE_UNAVAILABLE','RESELECT_REQUIRED','REFERENCE_EXPIRED','BOUNDED_PUBLIC_REVIEW_UNAVAILABLE','BOUNDED_UNIT_CHANGE_CANDIDATE','private/path']:
                    def fail(**kwargs):raise ValueError(code)
                    service.continuation_previewer=fail
                    response=client.post(PREFIX+'/continuation/preview',json=dict(account_id=first['account_id'],expected_revision=first['revision']))
                    self.assertEqual(response.status_code,503)
                    self.assertEqual(response.json()['error_code'],code if code!='private/path' else 'PAPER_SOURCE_OR_STATE_UNAVAILABLE')

    def test_review_policy_constructor_and_unknown_mutation(self):
        for policy in ('UNKNOWN',True,None):
            with self.assertRaisesRegex(ValueError,'INVALID_CONTINUATION_REVIEW_POLICY'):
                QuantityV2PaperService(store=None,continuation_review_policy=policy)
        with TemporaryDirectory() as folder:
            service,client,request,*_=self.setup_service(folder)
            def fail(**kwargs):raise ValueError('BOUNDED_UNIT_CHANGE_CANDIDATE')
            service.accept=fail
            with client:
                response=client.post(PREFIX+'/accept',json=request)
                self.assertEqual(response.status_code,503)
                self.assertEqual(response.json()['mutation_outcome'],'UNKNOWN_RETRY_SAME_REQUEST')

    def test_http_double_accept_fill_cancel_read_retry_compact(self):
        with TemporaryDirectory() as folder:
            service,client,request,calls,now=self.setup_service(folder)
            with client:
                with ThreadPoolExecutor(2) as pool:
                    responses=list(pool.map(lambda _:client.post(PREFIX+'/accept',json=request),range(2)))
                self.assertTrue(all(r.status_code==200 for r in responses));self.assertEqual(len(calls),1)
                state=responses[0].json();buy=next(o for o in state['orders'] if o['side']=='BUY')
                now[0]=datetime.fromisoformat('2026-10-15T13:01:00-04:00')
                e=dict(event_id='fill',type='FILL',order_id=buy['order_id'],expected_revision=state['revision'],
                    quantity=2,price='0.9',fees='0.1',executed_at='2026-10-15T13:00:00-04:00')
                r=client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=e));self.assertEqual(r.status_code,200,r.text)
                state=r.json();self.assertEqual(state['cash'],'181/10');self.assertEqual(state['recorded_fees'],'1/10')
                cancel=dict(event_id='cancel',type='CANCEL',order_id=buy['order_id'],expected_revision=state['revision'],cancelled_at=now[0].isoformat())
                latest=client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=cancel)).json()
                self.assertEqual(latest['reserved_cash'],'0')
                service.initial_resolver=None
                self.assertEqual(client.post(PREFIX+'/accept',json=request).json(),latest)
                self.assertEqual(client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=e)).json(),latest)
                self.assertEqual(client.get(PREFIX+'/account',params={'account_id':request['account_id']}).json(),latest)
                self.assertFalse(latest['real_account']);self.assertNotIn('acceptance',latest);self.assertNotIn('causal_inputs',latest)

    def test_strict_requests_and_conflict_do_not_mutate(self):
        with TemporaryDirectory() as folder:
            service,client,request,_,_=self.setup_service(folder)
            with client:
                state=client.post(PREFIX+'/accept',json=request).json();before=service.store.read(request['account_id'])
                for field in ('now','cash','quotes','accepted_at','sourcepaths'):
                    self.assertEqual(client.post(PREFIX+'/accept',json=dict(request,**{field:'bad'})).status_code,400)
                e=dict(event_id='e',type='EXPIRE',order_id=state['orders'][0]['order_id'],expected_revision=state['revision'],recorded_at='bad')
                self.assertEqual(client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=e)).status_code,400)
                self.assertEqual(client.get(PREFIX+'/account?account_id=a&account_id=b').status_code,400)
                self.assertEqual(client.post(PREFIX+'/accept',json=dict(request,proposal_id='other')).status_code,409)
                self.assertEqual(service.store.read(request['account_id']),before)

    def test_missing_source_unavailable_and_no_account(self):
        with TemporaryDirectory() as folder:
            service,client,request,_,_=self.setup_service(folder);service.initial_resolver=None
            with client:
                r=client.post(PREFIX+'/accept',json=request);self.assertEqual(r.status_code,503);self.assertEqual(r.json()['orders'],[])
            with self.assertRaises(Exception):service.store.read(request['account_id'])

    def test_withdrawn_source_rejects_accept_before_account_creation(self):
        with TemporaryDirectory() as folder:
            service,client,request,_,_=self.setup_service(folder)
            def withdrawn(*args): raise ValueError('RESEARCH_SOURCE_WITHDRAWN')
            service.initial_resolver=withdrawn
            response=client.post(PREFIX+'/accept',json=request)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['error_code'],'RESEARCH_SOURCE_WITHDRAWN')
            self.assertEqual(response.json()['mutation_outcome'],'NOT_APPLIED')
            with self.assertRaises(Exception): service.store.read(request['account_id'])

    def test_bad_fill_is_400_and_sql_error_is_unknown(self):
        with TemporaryDirectory() as folder:
            service,client,request,_,_=self.setup_service(folder)
            with client:
                state=client.post(PREFIX+'/accept',json=request).json()
                e=dict(event_id='x',type='FILL',order_id=state['orders'][0]['order_id'],expected_revision=state['revision'],
                       quantity=1,price='1',fees='0',executed_at='2026-10-15T13:00:00-04:00')
                for change in ({'price':'NaN'},{'price':'0'},{'fees':'-1'},{'executed_at':'2026-10-15T13:00:00'}):
                    self.assertEqual(client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=dict(e,**change))).status_code,400)
                service.clock=lambda:datetime.fromisoformat('2026-10-15T13:01:00-04:00')
                rejected=client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=dict(e,quantity=999)))
                self.assertEqual(rejected.status_code,409);self.assertEqual(rejected.json()['mutation_outcome'],'NOT_APPLIED')
                unknown=client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=dict(e,order_id='missing-order')))
                self.assertEqual(unknown.status_code,409)
                self.assertEqual(unknown.json()['error_code'],'UNKNOWN_ORDER')
                self.assertEqual(unknown.json()['mutation_outcome'],'NOT_APPLIED')
                def fail(**kwargs):raise sqlite3.OperationalError('synthetic lock error')
                service.event=fail
                r=client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=e))
                self.assertEqual(r.status_code,503);self.assertEqual(r.json()['mutation_outcome'],'UNKNOWN_RETRY_SAME_REQUEST')

    def test_continuation_callback_and_source_free_retry(self):
        with TemporaryDirectory() as folder:
            service,client,request,_,now=self.setup_service(folder)
            with client:
                state=client.post(PREFIX+'/accept',json=request).json()
                now[0]=datetime.fromisoformat('2026-10-15T13:01:00-04:00')
                for order in state['orders']:
                    e=dict(event_id=order['side'],order_id=order['order_id'],expected_revision=state['revision'])
                    if order['side']=='BUY':e.update(type='CANCEL',cancelled_at=now[0].isoformat())
                    else:e.update(type='FILL',quantity=2,price='51',fees='0',executed_at=now[0].isoformat())
                    response=client.post(PREFIX+'/event',json=dict(account_id=request['account_id'],event=e))
                    self.assertEqual(response.status_code,200,response.text);state=response.json()
                now[0]=datetime.fromisoformat('2026-10-15T13:03:30-04:00')
                _,_,args=initial();chain=service.store.read(request['account_id'])
                proposal=build_continuation(chain,execution_inputs=inputs(args),now=now[0])
                service.continuation_resolver=lambda current,proposal_id,at:deepcopy(proposal)
                body=dict(account_id=request['account_id'],proposal_id=proposal['proposal_id'],operation_id='continue',expected_revision=state['revision'])
                accepted=client.post(PREFIX+'/continuation/accept',json=body)
                self.assertEqual(accepted.status_code,200,accepted.text)
                self.assertEqual(accepted.json()['cash'],'122')
                service.continuation_resolver=None
                self.assertEqual(client.post(PREFIX+'/continuation/accept',json=body).json(),accepted.json())


if __name__=='__main__':unittest.main()
