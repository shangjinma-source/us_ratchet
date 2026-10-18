import json
import unittest
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_difference_cash_service import fixture as initial_fixture
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from api.current_quantity_v2_paper import create_router, PREFIX


def fixture(folder):
    source,decision_id,package,account,clock=initial_fixture()
    store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3')
    paper=QuantityV2PaperService(store=store,initial_resolver=source.initial_resolver,clock=lambda:clock[0])
    p=source.preview(decision_id)
    accepted=paper.accept(account_id=account['account_id'],proposal_id=p['proposal_id'],operation_id='initial')
    clock[0]+=timedelta(seconds=1);o=accepted['orders'][0]
    filled=paper.event(account_id=account['account_id'],event=dict(event_id='fill',type='FILL',order_id=o['order_id'],
        expected_revision=accepted['revision'],quantity=2,price='8',fees='1/5',executed_at=clock[0].isoformat()))
    clock[0]+=timedelta(seconds=1)
    closed=paper.event(account_id=account['account_id'],event=dict(event_id='cancel',type='CANCEL',order_id=o['order_id'],
        expected_revision=filled['revision'],cancelled_at=clock[0].isoformat()))
    # Retain every original source byte. Add a new, explicitly reviewed raw receipt.
    files=package['files'];pins=package['source_hashes'];paths=package['documents']
    def put(name,value):
        files[name]=json.dumps(value,sort_keys=True).encode();pins[name]=sha256(files[name]).hexdigest();return name
    clock[0]+=timedelta(seconds=56);capture=clock[0];raw=json.loads(files['A.raw']);r=raw['chart']['result'][0]
    r['meta']['regularMarketTime']=int(capture.timestamp())-5;r['timestamp']=[int(capture.replace(second=0).timestamp())-60]
    rawpath=put('next.raw',raw)
    receiptpath=put('next.receipt',dict(security_id='A',ticker='AAA',raw_path=rawpath,
        raw_sha256=pins[rawpath],captured_at=capture.isoformat()))
    units=json.loads(files[paths['unit_continuity']]);units['A'].update(
        covered_through=capture.isoformat(),reviewed_at=(capture+timedelta(seconds=1)).isoformat(),
        reference_source_hashes={rawpath:pins[rawpath],receiptpath:pins[receiptpath]})
    paths['unit_continuity']=put('next.units',units);paths['quote_receipts']={'A':receiptpath}
    clock[0]+=timedelta(seconds=2)
    bridge=QuantityV2ContinuationSourceBridge(store=store,resolver=lambda aid,did:deepcopy(package),clock=lambda:clock[0])
    paper.continuation_previewer=bridge.preview;paper.continuation_resolver=bridge.continuation_resolver
    return paper,bridge,package,clock,closed


class ContinuationServiceTests(unittest.TestCase):
    def test_http_partial_close_delay_accept_and_exact_retry(self):
        with TemporaryDirectory() as folder:
            paper,bridge,package,clock,closed=fixture(folder);app=FastAPI();app.include_router(create_router(service=paper))
            account_id=closed['account_id'];before=paper.store.read(account_id)
            with TestClient(app) as client:
                r=client.post(PREFIX+'/continuation/preview',json=dict(account_id=account_id,expected_revision=closed['revision']))
                self.assertEqual(r.status_code,200,r.text);p=r.json()
                self.assertEqual(p['scope'],'FIXED_MONTH_CONTINUATION');self.assertEqual(p['target_quantities'],{'A':50})
                self.assertEqual(p['shares'],{'A':2});self.assertEqual(p['actual_cash'],'419/5')
                self.assertEqual(p['orders'][0]['quantity'],10);self.assertNotIn('binding',p)
                self.assertNotIn('execution_inputs',p);self.assertEqual(p['prior_revision'],closed['revision'])
                clock[0]+=timedelta(seconds=1)
                request=dict(account_id=account_id,proposal_id=p['proposal_id'],operation_id='continue',expected_revision=closed['revision'])
                r=client.post(PREFIX+'/continuation/accept',json=request);self.assertEqual(r.status_code,200,r.text)
                accepted=r.json();self.assertEqual(accepted['cash'],closed['cash']);self.assertEqual(accepted['recorded_fees'],'1/5')
                self.assertEqual(accepted['shares'],closed['shares']);self.assertNotEqual(accepted['revision'],closed['revision'])
                o=accepted['orders'][0];clock[0]+=timedelta(seconds=1)
                e=dict(event_id='second-fill',type='FILL',order_id=o['order_id'],expected_revision=accepted['revision'],
                    quantity=1,price='8',fees='0',executed_at=clock[0].isoformat())
                latest=client.post(PREFIX+'/event',json=dict(account_id=account_id,event=e)).json()
                bridge._proposals.clear();bridge.resolver=lambda *a:(_ for _ in ()).throw(ValueError('gone'))
                clock[0]+=timedelta(days=40)
                retry=client.post(PREFIX+'/continuation/accept',json=request);self.assertEqual(retry.status_code,200,retry.text)
                self.assertEqual(retry.json(),latest);self.assertEqual(latest['cash'],'379/5');self.assertEqual(latest['shares'],{'A':3})
                self.assertEqual(paper.store.read(account_id)['genesis'],before['genesis'])

    def test_strict_requests_source_account_and_deadline_refuse_without_write(self):
        for mode in ('source','expired','revision','clockback','mapping'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                paper,bridge,package,clock,closed=fixture(folder);app=FastAPI();app.include_router(create_router(service=paper))
                with TestClient(app) as client:
                    path=PREFIX+'/continuation/preview';body=dict(account_id=closed['account_id'],expected_revision=closed['revision'])
                    for k in ('quotes','now','cash','source_paths'):
                        self.assertEqual(client.post(path,json=dict(body,**{k:1})).status_code,400)
                    self.assertEqual(client.post(path+'?x=1',json=body).status_code,400)
                    p=client.post(path,json=body).json();before=paper.store.read(closed['account_id'])
                    req=dict(body,proposal_id=p['proposal_id'],operation_id='next')
                    if mode=='source':package['files']['next.raw']+=b' '
                    elif mode=='mapping':package['documents']['quote_receipts']['A']='A.receipt'
                    elif mode=='expired':clock[0]+=timedelta(seconds=121)
                    elif mode=='clockback':clock[0]-=timedelta(seconds=1)
                    else:req['expected_revision']='wrong'
                    r=client.post(PREFIX+'/continuation/accept',json=req)
                    self.assertNotEqual(r.status_code,200,r.text);self.assertEqual(r.json()['orders'],[])
                    self.assertEqual(paper.store.read(closed['account_id']),before)

    def test_malformed_raw_is_controlled_and_empty_cash_not_acceptable(self):
        with TemporaryDirectory() as folder:
            paper,bridge,package,clock,closed=fixture(folder);app=FastAPI();app.include_router(create_router(service=paper))
            package['files']['next.raw']=b'{"chart":{"result":[]}}'
            package['source_hashes']['next.raw']=sha256(package['files']['next.raw']).hexdigest()
            receipt=json.loads(package['files']['next.receipt']);receipt['raw_sha256']=package['source_hashes']['next.raw']
            package['files']['next.receipt']=json.dumps(receipt).encode()
            package['source_hashes']['next.receipt']=sha256(package['files']['next.receipt']).hexdigest()
            with TestClient(app) as client:
                response=client.post(PREFIX+'/continuation/preview',json=dict(account_id=closed['account_id'],expected_revision=closed['revision']))
                self.assertEqual(response.status_code,503,response.text)
                self.assertEqual(response.json()['mutation_outcome'],'READ_ONLY');self.assertEqual(response.json()['orders'],[])
        with TemporaryDirectory() as folder:
            paper,bridge,package,clock,closed=fixture(folder)
            p=bridge.preview(account_id=closed['account_id'],expected_revision=closed['revision'])
            a=paper.accept_continuation(account_id=closed['account_id'],proposal_id=p['proposal_id'],operation_id='lastcash',expected_revision=closed['revision'])
            o=a['orders'][0]
            a=paper.event(account_id=closed['account_id'],event=dict(event_id='allcash',type='FILL',order_id=o['order_id'],expected_revision=a['revision'],quantity=10,price='8',fees='19/5',executed_at=clock[0].isoformat()))
            clock[0]+=timedelta(seconds=10)
            files=package['files'];pins=package['source_hashes'];capture=clock[0]
            raw=json.loads(files['next.raw']);raw['chart']['result'][0]['meta']['regularMarketTime']=int(capture.timestamp())
            files['next.raw']=json.dumps(raw).encode();pins['next.raw']=sha256(files['next.raw']).hexdigest()
            receipt=json.loads(files['next.receipt']);receipt.update(captured_at=capture.isoformat(),raw_sha256=pins['next.raw'])
            files['next.receipt']=json.dumps(receipt).encode();pins['next.receipt']=sha256(files['next.receipt']).hexdigest()
            units=json.loads(files['next.units']);units['A'].update(covered_through=capture.isoformat(),reviewed_at=capture.isoformat(),reference_source_hashes={k:pins[k] for k in ('next.raw','next.receipt')})
            files['next.units']=json.dumps(units).encode();pins['next.units']=sha256(files['next.units']).hexdigest()
            p=bridge.preview(account_id=a['account_id'],expected_revision=a['revision'])
            self.assertEqual(p['action'],'WAIT_CASH');self.assertEqual(p['orders'],[]);self.assertIsNone(p['proposal_id'])

    def test_preview_open_orders_and_missing_source_fail_closed(self):
        with TemporaryDirectory() as folder:
            paper,bridge,p,clock,closed=fixture(folder)
            proposal=bridge.preview(account_id=closed['account_id'],expected_revision=closed['revision'])
            accepted=paper.accept_continuation(account_id=closed['account_id'],proposal_id=proposal['proposal_id'],operation_id='open',expected_revision=closed['revision'])
            with self.assertRaisesRegex(ValueError,'PRIOR_ORDERS_OPEN'):
                bridge.preview(account_id=closed['account_id'],expected_revision=accepted['revision'])
            p['files'][p['documents']['unit_continuity']]=b'{}'
            with self.assertRaises(ValueError):bridge.preview(account_id=closed['account_id'],expected_revision=accepted['revision'])

if __name__=='__main__':unittest.main()
