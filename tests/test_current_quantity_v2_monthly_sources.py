from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from concurrent.futures import ThreadPoolExecutor
import json,unittest
from test_current_quantity_v2_monthly_service import fixture as bridge_fixture
from data.current_quantity_v2_monthly_sources import QuantityV2MonthlySources
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge


def fixture(folder):
    paper,_,package,clock,state,did=bridge_fixture(folder)
    base=deepcopy(package);base['documents']={k:v for k,v in base['documents'].items() if k in ('capital_decision','target_mandate','identities')}
    calls=[]
    def fetch(ticker):
        calls.append(ticker);return package['files'][('A' if ticker=='AAA' else 'B')+'-new.raw']
    def review(snapshot):
        files={};pins={};docs={}
        for key in ('unit_continuity','held_unit_continuity','account_review'):
            value=json.loads(package['files'][package['documents'][key]])
            if key!='account_review':
                for sid,row in value.items():
                    row.update(reference_source_hashes=snapshot['current_receipts'][sid]['source_hashes'],
                        covered_through=snapshot['current_receipts'][sid]['captured_at'],reviewed_at=snapshot['current_receipts'][sid]['captured_at'])
            path='review/'+key+'.json';files[path]=json.dumps(value,sort_keys=True).encode();pins[path]=sha256(files[path]).hexdigest();docs[key]=path
        return dict(files=files,source_hashes=pins,documents=docs)
    provider=QuantityV2MonthlySources(storage_root=Path(folder)/'saved',decision_reader=lambda _:deepcopy(base),review_reader=review,fetch=fetch,clock=lambda:clock[0])
    return provider,paper,state,did,clock,calls,base


class SourceTests(unittest.TestCase):
    def test_durable_raw_bridge_accept_and_read_no_fetch(self):
        with TemporaryDirectory() as folder:
            p,paper,state,did,clock,calls,base=fixture(folder);self.assertFalse(p.storage_root.exists())
            p.capture(state);self.assertEqual(calls,['AAA','BBB'])
            bridge=QuantityV2MonthlySourceBridge(store=paper.store,resolver=p.resolve,clock=lambda:clock[0])
            aid=state['ledger']['account_id'];v=bridge.preview(account_id=aid,decision_id=did,expected_revision=state['ledger']['revision'])
            clock[0]+=timedelta(seconds=1)
            accepted=paper.store.accept_monthly_retarget(account_id=aid,proposal_id=v['proposal_id'],operation_id='monthly',expected_revision=state['ledger']['revision'],
                factory=lambda c,n:bridge.monthly_resolver(c,v['proposal_id'],n),clock=lambda:clock[0])
            self.assertEqual(calls,['AAA','BBB']);self.assertEqual(accepted['ledger']['cash'],state['ledger']['cash'])
            self.assertEqual(paper.store.read(aid),accepted)
            saved=p._current['receipt'];path=Path(saved['root'])/'blobs'/next(iter(p.resolve(aid,did)['source_hashes'].values()))
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):p.resolve(aid,did)

    def test_failure_clear_and_constructor_no_callbacks(self):
        with TemporaryDirectory() as folder:
            def forbidden(*a):raise AssertionError('constructor IO')
            untouched=Path(folder)/'absent'
            QuantityV2MonthlySources(storage_root=untouched,decision_reader=forbidden,review_reader=forbidden,fetch=forbidden,clock=forbidden)
            self.assertFalse(untouched.exists())
            p,_,state,did,_,calls,_=fixture(folder);p.capture(state)
            p.fetch=lambda _:(_ for _ in ()).throw(ValueError('network failure'))
            with self.assertRaises(ValueError):p.capture(state)
            with self.assertRaisesRegex(ValueError,'MONTHLY_CAPTURE_REQUIRED'):p.resolve(state['ledger']['account_id'],did)

    def test_superseded_old_capture_cannot_restore_and_write_failure(self):
        with TemporaryDirectory() as folder:
            p,_,state,did,_,_,_=fixture(folder);entered=Event();release=Event();original=p.fetch
            def slow(ticker):entered.set();release.wait(5);return original(ticker)
            p.fetch=slow
            with ThreadPoolExecutor(2) as executor:
                future=executor.submit(p.capture,state);self.assertTrue(entered.wait(3))
                p.fetch=lambda _:(_ for _ in ()).throw(ValueError('latest failed'))
                with self.assertRaises(ValueError):p.capture(state)
                p.fetch=original;release.set()
                with self.assertRaises(ValueError):future.result()
            self.assertIsNone(p._current)
            audits=[p.audit(path.name,state['ledger']['account_id']) for path in (p.storage_root/'captures'/'audit').iterdir()]
            self.assertEqual(len(audits),2);self.assertTrue(all(a['status']=='FAILED' for a in audits))
            self.assertIn('CAPTURE_SUPERSEDED',[a['events'][-1]['payload']['reason'] for a in audits])
            p.fetch=original;p.storage_root=Path(folder)/'broken-storage';p.storage_root.mkdir();(p.storage_root/'blobs').write_bytes(b'not a directory')
            with self.assertRaises(OSError):p.capture(state)
            self.assertIsNone(p._current)

    def test_partial_and_review_failure_raw_audit_is_readonly(self):
        for mode in ('second-fetch','review'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                p,_,state,_,_,_,_=fixture(folder);fetch=p.fetch
                if mode=='second-fetch':
                    def fail_second(ticker):
                        if ticker=='BBB':raise ValueError('SECRET network message')
                        return fetch(ticker)
                    p.fetch=fail_second
                else:p.review_reader=lambda _:(_ for _ in ()).throw(ValueError('SECRET review message'))
                with self.assertRaises(ValueError) as raised:p.capture(state)
                capture_id=raised.exception.capture_id
                self.assertIsNone(p._current)
                def forbidden(*a,**k):raise AssertionError('audit side effect')
                restarted=QuantityV2MonthlySources(storage_root=p.storage_root,decision_reader=forbidden,
                    review_reader=forbidden,fetch=forbidden,clock=forbidden)
                audit=restarted.audit(capture_id,state['ledger']['account_id'])
                self.assertEqual(audit['status'],'FAILED')
                raw_events=[e for e in audit['events'] if e['kind']=='RAW']
                self.assertEqual(len(raw_events),1 if mode=='second-fetch' else 2)
                self.assertNotIn('SECRET',json.dumps(audit['events']))
                with self.assertRaisesRegex(ValueError,'ACCOUNT_MISMATCH'):restarted.audit(capture_id,'other')
                with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):restarted.resolve(state['ledger']['account_id'],'any')
                digest=raw_events[0]['payload']['raw_sha256'];(p.storage_root/'blobs'/digest).write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError,'RAW_CHANGED'):restarted.audit(capture_id,state['ledger']['account_id'])

    def test_late_old_failure_preserves_new_success_and_terminal_disk_failure_blocks(self):
        from unittest.mock import patch
        from data.current_quantity_v2_monthly_capture_audit import CaptureAudit
        with TemporaryDirectory() as folder:
            p,_,state,_,_,_,_=fixture(folder);original=p.fetch;entered=Event();release=Event()
            def slow_failure(ticker):
                entered.set();self.assertTrue(release.wait(5));raise TimeoutError('private upstream')
            p.fetch=slow_failure
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(p.capture,state);self.assertTrue(entered.wait(3))
                p.fetch=original;new=p.capture(state);saved=deepcopy(p._current);release.set()
                with self.assertRaises(TimeoutError):future.result()
            self.assertEqual(p._current,saved)
            self.assertEqual(p.audit(new['capture_id'],state['ledger']['account_id'])['status'],'CAPTURED')
            original_finish=CaptureAudit.finish
            def fail_terminal(audit,status,*a,**k):
                if status=='CAPTURED':raise OSError('terminal disk failure')
                return original_finish(audit,status,*a,**k)
            with patch.object(CaptureAudit,'finish',fail_terminal):
                with self.assertRaises(OSError) as raised:p.capture(state)
            self.assertIsNone(p._current)
            self.assertEqual(p.audit(raised.exception.capture_id,state['ledger']['account_id'])['status'],'FAILED')

    def test_success_audit_does_not_restore_execution_authority(self):
        with TemporaryDirectory() as folder:
            p,_,state,did,_,_,_=fixture(folder);result=p.capture(state)
            def forbidden(*a,**k):raise AssertionError('audit side effect')
            restarted=QuantityV2MonthlySources(storage_root=p.storage_root,decision_reader=forbidden,
                review_reader=forbidden,fetch=forbidden,clock=forbidden)
            audit=restarted.audit(result['capture_id'],state['ledger']['account_id'])
            self.assertEqual(audit['status'],'CAPTURED');self.assertTrue(audit['audit_only'])
            self.assertFalse(audit['selected_for_current_account'])
            with self.assertRaisesRegex(ValueError,'CAPTURE_REQUIRED'):restarted.resolve(state['ledger']['account_id'],did)

    def test_expected_identity_before_fetch_and_persistence_faults(self):
        from unittest.mock import patch
        for mode in ('identity','write','afterwrite'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                p,_,state,did,_,calls,_=fixture(folder)
                if mode=='identity':
                    with self.assertRaisesRegex(ValueError,'DECISION_BINDING_MISMATCH'):
                        p.capture(state,expected_decision_id='0'*64)
                    self.assertEqual(calls,[]);self.assertFalse(p.storage_root.exists())
                elif mode=='write':
                    with patch('data.current_research_intraday_journal.os.fsync',side_effect=OSError('disk failure')):
                        with self.assertRaises(OSError):p.capture(state,expected_decision_id=did)
                    self.assertEqual(list(p.storage_root.rglob('.pending-*')),[])
                else:
                    original=p._publish
                    def tamper(package,identifier):
                        receipt=original(package,identifier)
                        blob=Path(receipt['root'])/'blobs'/next(iter(package['source_hashes'].values()))
                        blob.write_bytes(b'changed after publish')
                        return receipt
                    p._publish=tamper
                    with self.assertRaisesRegex(ValueError,'SAVED_PACKAGE_CHANGED'):p.capture(state,expected_decision_id=did)
                self.assertIsNone(p._current)


if __name__=='__main__':unittest.main()
