from tempfile import TemporaryDirectory
from unittest.mock import patch
from threading import Event
from concurrent.futures import ThreadPoolExecutor
"""Temporary tiny sources only; explicit synthetic reviews are not real admission."""
from copy import deepcopy
from datetime import datetime,timedelta
from hashlib import sha256
import json
from pathlib import Path
import unittest
from data.current_quantity_v2_current_cash_continuation_sources import CurrentCashContinuationSources
from data.current_quantity_v2_current_cash_plan import canonical,BASIS
from data.current_quantity_v2_difference_service import decode_execution_package
from data.current_quantity_v2_paper_chain import build_continuation
from test_current_quantity_v2_current_cash_continuation import fixture
import test_current_quantity_v2_current_cash_plan as base
from test_current_quantity_v2_intraday_reference import raw


class SourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):base.CurrentCashTests.setUpClass()
    @classmethod
    def tearDownClass(cls):base.CurrentCashTests.tearDownClass()

    def fixture(self,mode=None):
        state,_,now=fixture(base.CurrentCashTests.args);clock=[datetime.fromisoformat(now)];calls=[]
        def fetch(ticker):
            calls.append(ticker);d=json.loads(raw(ticker,10));d['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp())
            return canonical(d)
        def review(snapshot):
            evidence='external/synthetic-review.json';units={}
            for sid,origin in snapshot['origins'].items():
                sec=snapshot['securities'][sid];current=snapshot['current_receipts'][sid]
                units[sid]=dict(security_id=sid,ticker=sec['ticker'],security_class=sec['security_class'],
                    price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',initial_price_basis=BASIS,
                    status='NO_UNPROCESSED_ACTIONS',initial_execution_target_id=snapshot['execution_target_id'],
                    initial_reference_source_hashes=origin['source_hashes'],reference_source_hashes=current['source_hashes'],
                    covered_from=origin['captured_at'],covered_through=current['captured_at'],
                    reviewed_at=clock[0].isoformat(),source_references=[evidence])
            if mode=='origin':units['A']['initial_execution_target_id']='wrong'
            if mode=='coverage':units['A']['covered_from']=clock[0].isoformat()
            if mode=='expired':clock[0]+=timedelta(minutes=3)
            if mode=='missing':return None
            files={evidence:canonical({'synthetic':True}), 'external/units.json':canonical(units)}
            return dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},unit_continuity_path='external/units.json')
        service=CurrentCashContinuationSources(root=base.CurrentCashTests.temp.name,unit_review_reader=review,fetch=fetch,clock=lambda:clock[0])
        return state,service,clock,calls

    def test_capture_then_resolve_no_fetch_full_pins_and_fixed_target(self):
        state,service,clock,calls=self.fixture();before=deepcopy(state)
        result=service.capture(state);self.assertEqual(len(calls),2)
        p=service.resolve(result['account_id'],result['decision_id']);service.resolve(result['account_id'],result['decision_id'])
        self.assertEqual(len(calls),2);self.assertEqual(state,before)
        self.assertEqual(set(p['files']),set(p['source_hashes']))
        old=state['ledger']['acceptance']['proposal']['causal_inputs']['frozen_execution_package']['source_hashes']
        self.assertTrue(all(p['source_hashes'][k]==v for k,v in old.items()))
        inputs=decode_execution_package(p,needed={'A','B'},now=clock[0]);proposal=build_continuation(state,execution_inputs=inputs,now=clock[0])
        self.assertEqual(proposal['binding']['target_quantities'],{'A':6,'B':4})
        self.assertEqual(proposal['binding']['cash'],'459/5')
        self.assertEqual({o['security_id']:o['quantity'] for o in proposal['orders']},{'A':4,'B':4})
        p['files'].clear();self.assertTrue(service.resolve(result['account_id'],result['decision_id'])['files'])

    def test_audit_partial_review_failure_and_restart_without_authority(self):
        for mode in ('partial','review','success'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                state,service,_,_=self.fixture();service.audit_storage_root=Path(folder)/'audit'
                self.assertFalse(service.audit_storage_root.exists());fetch=service.fetch
                if mode=='partial':
                    def fail_second(ticker):
                        if ticker=='BBB':raise ValueError('PRIVATE endpoint')
                        return fetch(ticker)
                    service.fetch=fail_second
                elif mode=='review':service.unit_review_reader=lambda _:None
                if mode=='success':capture_id=service.capture(state)['capture_id']
                else:
                    with self.assertRaises(ValueError) as error:service.capture(state)
                    capture_id=error.exception.capture_id
                def forbidden(*a,**k):raise AssertionError('audit side effect')
                reopened=CurrentCashContinuationSources(root=service.root,unit_review_reader=forbidden,
                    fetch=forbidden,clock=forbidden,audit_storage_root=service.audit_storage_root)
                audit=reopened.audit(capture_id,state['ledger']['account_id'])
                self.assertEqual(audit['status'],'CAPTURED' if mode=='success' else 'FAILED')
                self.assertEqual(audit['binding_scope']['chain_sha256'],sha256(canonical(state)).hexdigest())
                self.assertEqual(len([e for e in audit['events'] if e['kind']=='RAW']),1 if mode=='partial' else 2)
                self.assertNotIn('PRIVATE',json.dumps(audit['events']))
                with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):reopened.resolve('any','any')
                if mode=='success':
                    (service.audit_storage_root/'blobs'/sha256(canonical(state)).hexdigest()).write_bytes(b'tamper')
                    with self.assertRaisesRegex(ValueError,'CHAIN_AUDIT_CONTEXT_MISMATCH'):
                        reopened.audit(capture_id,state['ledger']['account_id'])

    def test_archive_latency_and_late_old_failure(self):
        from data.current_quantity_v2_monthly_capture_audit import CaptureAudit
        with TemporaryDirectory() as folder:
            state,service,clock,_=self.fixture();service.audit_storage_root=Path(folder)/'audit'
            actual=CaptureAudit.package
            def slow(audit,*a,**k):
                result=actual(audit,*a,**k);clock[0]+=timedelta(minutes=5);return result
            with patch.object(CaptureAudit,'package',slow):
                with self.assertRaises(ValueError) as error:service.capture(state)
            self.assertIsNone(service._current)
            self.assertEqual(service.audit(error.exception.capture_id,state['ledger']['account_id'])['status'],'FAILED')
        with TemporaryDirectory() as folder:
            state,service,_,_=self.fixture();service.audit_storage_root=Path(folder)/'audit'
            entered=Event();release=Event();original=service.fetch
            def old(ticker):
                entered.set();self.assertTrue(release.wait(5));raise TimeoutError('private old failure')
            service.fetch=old
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(service.capture,state);self.assertTrue(entered.wait(3))
                service.fetch=original;new=service.capture(state);saved=deepcopy(service._current);release.set()
                with self.assertRaises(TimeoutError):future.result()
            self.assertEqual(service._current,saved)
            self.assertEqual(service.audit(new['capture_id'],state['ledger']['account_id'])['status'],'CAPTURED')

    def test_missing_bad_origin_coverage_and_review_latency_fail(self):
        for mode in ('missing','origin','coverage','expired'):
            state,service,clock,calls=self.fixture(mode)
            with self.subTest(mode=mode),self.assertRaises(ValueError):service.capture(state)
            with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):service.resolve('x','x')
        state,service,_,calls=self.fixture();service.unit_review_reader=None
        with self.assertRaisesRegex(ValueError,'UNIT_REVIEW_SOURCE_UNAVAILABLE'):service.capture(state)
        self.assertEqual(calls,[])

    def test_scope_mismatch_expiry_and_failed_new_attempt_remove_old(self):
        state,service,clock,calls=self.fixture();r=service.capture(state)
        with self.assertRaisesRegex(ValueError,'MISMATCH'):service.resolve('wrong',r['decision_id'])
        clock[0]+=timedelta(minutes=3)
        with self.assertRaises(ValueError):service.resolve(r['account_id'],r['decision_id'])
        self.assertEqual(len(calls),2)
        service.unit_review_reader=None
        with self.assertRaises(ValueError):service.capture(state)
        with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):service.resolve(r['account_id'],r['decision_id'])

    def test_old_attempt_cannot_publish_after_new_attempt(self):
        state,service,_,_=self.fixture();reader=service.unit_review_reader
        def supersede(snapshot):
            reviewed=reader(snapshot)
            with service.lock:service._attempt+=1;service._current=None
            return reviewed
        service.unit_review_reader=supersede
        with self.assertRaisesRegex(ValueError,'CAPTURE_SUPERSEDED'):service.capture(state)
        with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):service.resolve('x','x')


if __name__=='__main__':unittest.main()
