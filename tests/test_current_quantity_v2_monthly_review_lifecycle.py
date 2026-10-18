"""Review capture once, immutable replay thereafter; temporary raw-byte fixtures."""
from copy import deepcopy
from datetime import timedelta
from tempfile import TemporaryDirectory
import unittest
from test_current_quantity_v2_monthly_sources import fixture
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge


class ReviewReader:
    def __init__(self,legacy):
        self.legacy=legacy;self.captures=0;self.reads=0;self.snapshot=None;self.frozen=None
    def capture(self,snapshot):
        self.captures+=1;self.snapshot=deepcopy(snapshot)
        self.frozen=self.legacy(snapshot)
        return deepcopy(self.frozen)
    def read(self,snapshot):
        self.reads+=1
        if snapshot!=self.snapshot:raise ValueError('SNAPSHOT_CHANGED')
        return deepcopy(self.frozen)


class LifecycleTests(unittest.TestCase):
    def test_one_capture_then_bridge_resolve_accept_replay_zero_fetch(self):
        with TemporaryDirectory() as folder:
            source,paper,state,did,clock,calls,base=fixture(folder)
            reader=ReviewReader(source.review_reader);source.review_reader=reader
            source.capture(state)
            self.assertEqual(reader.captures,1);self.assertEqual(reader.reads,2)
            self.assertEqual(reader.snapshot['base_files'],base['files'])
            self.assertEqual(reader.snapshot['base_source_hashes'],base['source_hashes'])
            self.assertEqual(reader.snapshot['base_documents'],base['documents'])
            bridge=QuantityV2MonthlySourceBridge(store=paper.store,resolver=source.resolve,clock=lambda:clock[0])
            aid=state['ledger']['account_id']
            result=bridge.preview(account_id=aid,decision_id=did,expected_revision=state['ledger']['revision'])
            clock[0]+=timedelta(seconds=1)
            paper.store.accept_monthly_retarget(account_id=aid,proposal_id=result['proposal_id'],operation_id='month',
                expected_revision=state['ledger']['revision'],factory=lambda current,now:bridge.monthly_resolver(current,result['proposal_id'],now),clock=lambda:clock[0])
            self.assertEqual(reader.captures,1);self.assertEqual(calls,['AAA','BBB']);self.assertGreater(reader.reads,2)
            source.resolve(aid,did)['files'].clear()
            self.assertTrue(source.resolve(aid,did)['files'])

    def test_missing_replay_or_original_bytes_rejects_before_fetch(self):
        for mode in ('reader','bytes'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                source,_,state,_,_,calls,base=fixture(folder)
                if mode=='reader':
                    class CaptureOnly:
                        def capture(self,snapshot):raise AssertionError('must not capture')
                    source.review_reader=CaptureOnly()
                else:base['files'].pop(next(iter(base['files'])))
                with self.assertRaises((ValueError,KeyError)):source.capture(state)
                self.assertEqual(calls,[]);self.assertIsNone(source._current)

    def test_changed_review_and_slow_capture_do_not_publish_authority(self):
        for mode in ('changed','expired'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                source,_,state,did,clock,calls,_=fixture(folder)
                reader=ReviewReader(source.review_reader);source.review_reader=reader
                if mode=='expired':
                    original=reader.capture
                    def slow(snapshot):
                        result=original(snapshot);clock[0]+=timedelta(seconds=121);return result
                    reader.capture=slow
                    with self.assertRaises(ValueError):source.capture(state)
                    self.assertIsNone(source._current)
                else:
                    source.capture(state);reader.frozen['files'][next(iter(reader.frozen['files']))]=b'changed'
                    with self.assertRaises(ValueError):source.resolve(state['ledger']['account_id'],did)
                self.assertEqual(reader.captures,1);self.assertEqual(calls,['AAA','BBB'])

if __name__=='__main__':unittest.main()
