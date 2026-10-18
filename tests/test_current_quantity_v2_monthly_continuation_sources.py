"""Actual tiny worker/raw/archive fixed-target continuation fixtures."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_bounded_review import MonthlyBoundedUnitReview
from data.current_quantity_v2_monthly_continuation_sources import QuantityV2MonthlyContinuationSources
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge
from data.current_quantity_v2_monthly_factory import attach_monthly_services
from test_current_quantity_v2_monthly_research_service import fixture as research_fixture
from test_current_quantity_v2_bounded_unit_review import feed


def fixture(folder):
    research,state,_,old,paper,clock=research_fixture(folder)
    aid=state['ledger']['account_id'];selected=research.generate(account_id=aid,expected_revision=state['ledger']['revision'])
    requests=[];quotes=[]
    def account_review(snapshot):
        ledger=snapshot['state']['ledger'];path='explicit-account/'+ledger['revision']+'.json'
        raw=canonical(dict(account_id=aid,state_revision=ledger['revision'],pending_rights=[],reviewed_at=clock[0].isoformat(),source_references=[path]))
        return dict(files={path:raw},source_hashes={path:sha256(raw).hexdigest()},account_review_path=path)
    def fetch(ticker):
        quotes.append(ticker);value=json.loads(old.fetch(ticker));value['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp())
        return canonical(value)
    reader=MonthlyBoundedUnitReview(account_review_reader=account_review,fetch=lambda:(requests.append(1) or dict(status=200,body=feed())),clock=lambda:clock[0])
    paper.clock=lambda:clock[0]
    first=attach_monthly_services(paper,storage_root=Path(folder)/'monthly',decision_reader=research.decision_reader,review_reader=reader,fetch=fetch)
    preview=paper.monthly_preview(account_id=aid,decision_id=selected['decision_id'],expected_revision=state['ledger']['revision'])
    state=paper.accept_monthly_retarget(account_id=aid,proposal_id=preview['proposal_id'],operation_id='first-month',expected_revision=state['ledger']['revision'])
    state=paper.store.read(aid)
    # Real partial buy and fee, followed by cancellation: no rebinding of capital.
    buy=next(o for o in state['ledger']['orders'].values() if o['side']=='BUY')
    state=paper.store.record_event(account_id=aid,event=dict(type='FILL',event_id='partial-month',order_id=buy['order_id'],expected_revision=state['ledger']['revision'],quantity=1,price=buy['limit_price'],fees='1/10',executed_at=clock[0].isoformat()),clock=lambda:clock[0])
    for oid,order in list(state['ledger']['orders'].items()):
        if not order['closed']:
            state=paper.store.record_event(account_id=aid,event=dict(type='CANCEL',event_id='cancel-'+oid,order_id=oid,expected_revision=state['ledger']['revision'],cancelled_at=clock[0].isoformat()),clock=lambda:clock[0])
    clock[0]+=timedelta(seconds=1)
    continuation_reader=MonthlyBoundedUnitReview(account_review_reader=account_review,fetch=lambda:(requests.append(1) or dict(status=200,body=feed())),clock=lambda:clock[0])
    source=QuantityV2MonthlyContinuationSources(storage_root=Path(folder)/'continuations',monthly_blob_root=Path(folder)/'monthly'/'blobs',review_reader=continuation_reader,fetch=fetch,clock=lambda:clock[0])
    requests.clear();quotes.clear()
    return source,paper,state,clock,quotes,requests


class MonthlyContinuationSourceTests(unittest.TestCase):
    def test_fixed_targets_partial_fee_durable_and_retry(self):
        with TemporaryDirectory() as folder:
            source,paper,state,clock,quotes,rss=fixture(folder);aid=state['ledger']['account_id']
            original=deepcopy(state);source.capture(state)
            self.assertEqual(sorted(quotes),['AAA','BBB']);self.assertEqual(rss,[1])
            bridge=QuantityV2ContinuationSourceBridge(store=paper.store,resolver=source.resolve,clock=lambda:clock[0])
            preview=bridge.preview(account_id=aid,expected_revision=state['ledger']['revision'])
            self.assertEqual(preview['target_quantities'],state['ledger']['target_quantities'])
            self.assertEqual(preview['actual_cash'],state['ledger']['cash'])
            self.assertEqual(preview['recorded_fees'],state['ledger']['recorded_fees'])
            self.assertFalse(preview['unit_review']['coverage_complete'])
            from data.current_quantity_v2_paper_chain import build_continuation
            inputs,_=bridge._evidence(state,clock[0])
            for field,value in [('pending_rights',['unresolved']),('state_revision','old')]:
                bad=deepcopy(inputs);bad['account_review'][field]=value
                with self.assertRaisesRegex(ValueError,'EXPLICIT_ACCOUNT_REVIEW_REQUIRED'):build_continuation(state,execution_inputs=bad,now=clock[0])
            bad={k:v for k,v in inputs.items() if k not in ('account_review','held_unit_continuity')}
            with self.assertRaisesRegex(ValueError,'MONTHLY_CONTINUATION_REVIEW_REQUIRED'):build_continuation(state,execution_inputs=bad,now=clock[0])
            clock[0]+=timedelta(seconds=1)
            request=dict(account_id=aid,proposal_id=preview['proposal_id'],operation_id='continue-month',expected_revision=state['ledger']['revision'],factory=lambda s,n:bridge.continuation_resolver(s,preview['proposal_id'],n),clock=lambda:clock[0])
            accepted=paper.store.accept_continuation(**request)
            for key in ('cash','shares','recorded_fees','events','target_quantities'):self.assertEqual(accepted['ledger'][key],original['ledger'][key])
            self.assertEqual(accepted['genesis'],original['genesis']);self.assertEqual(rss,[1])
            self.assertEqual(sorted(quotes),['AAA','BBB'])
            source._current=None;bridge._proposals.clear();clock[0]+=timedelta(days=60)
            self.assertEqual(paper.store.accept_continuation(**request),accepted)
            self.assertEqual(paper.store.read(aid),accepted)

    def test_constructor_missing_archive_and_failed_publish(self):
        with TemporaryDirectory() as folder:
            def forbidden(*a):raise AssertionError('constructor callback')
            unused=Path(folder)/'absent'
            QuantityV2MonthlyContinuationSources(storage_root=unused,monthly_blob_root=unused/'blobs',review_reader=forbidden,fetch=forbidden,clock=forbidden)
            self.assertFalse(unused.exists())
            source,paper,state,clock,quotes,rss=fixture(folder)
            with patch('data.current_research_intraday_journal.os.fsync',side_effect=OSError('fail write')):
                with self.assertRaises(OSError):source.capture(state)
            self.assertIsNone(source._current)
            source.capture(state);path=source.monthly_blob_root/next(iter(state['ledger']['active_monthly_acceptance']['proposal']['causal_inputs']['source_hashes'].values()))
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):source.resolve(state['ledger']['account_id'],state['ledger']['active_monthly_acceptance']['proposal']['capital_decision_id'])
            with self.assertRaises(ValueError):source.capture(state)
            self.assertIsNone(source._current)


    def test_new_failed_attempt_supersedes_slow_and_restart_is_empty(self):
        from threading import Event
        from concurrent.futures import ThreadPoolExecutor
        with TemporaryDirectory() as folder:
            source,paper,state,clock,quotes,rss=fixture(folder)
            entered=Event();release=Event();fetch=source.fetch
            def slow(ticker):entered.set();release.wait(5);return fetch(ticker)
            source.fetch=slow
            with ThreadPoolExecutor(2) as pool:
                pending=pool.submit(source.capture,state);self.assertTrue(entered.wait(3))
                source.fetch=lambda _:(_ for _ in ()).throw(ValueError('new attempt failed'))
                with self.assertRaises(ValueError):source.capture(state)
                release.set()
                with self.assertRaises(ValueError):pending.result()
            self.assertIsNone(source._current)
            source.fetch=fetch;source.capture(state)
            restarted=QuantityV2MonthlyContinuationSources(storage_root=source.storage_root,monthly_blob_root=source.monthly_blob_root,
                review_reader=source.review_reader,fetch=fetch,clock=lambda:clock[0])
            with self.assertRaisesRegex(ValueError,'MONTHLY_CAPTURE_REQUIRED'):
                restarted.resolve(state['ledger']['account_id'],state['ledger']['active_monthly_acceptance']['proposal']['capital_decision_id'])


if __name__=='__main__':unittest.main()
