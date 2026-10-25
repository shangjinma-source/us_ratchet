from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.strategy_monthly_supplement_capture import capture_supplement

class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.binding=dict(account_id='test',account_revision='r1',target_id='t1',session='2026-10-23')
        self.current=dict(self.binding);self.calls=0
        self.request=dict(account_id='test',state_revision='r1',window_start='2026-10-01T13:30:00+00:00',
            observed_floor='2026-10-23T14:00:00+00:00',securities={'A':{'ticker':'TEST'}},current_target_quantities={'A':1})
        self.now=datetime(2026,10,23,14,tzinfo=timezone.utc)
    def fetch(self,*args):
        self.calls+=1
        if args:self.assertLessEqual(args[1],datetime(2026,10,1,tzinfo=timezone.utc))
        return dict(status=200,body=b'{"raw":"fixture"}')
    def run_capture(self,folder):
        return capture_supplement(directory=folder,request=self.request,binding=self.binding,
            read_binding=lambda:dict(self.current),execute=True,fetch_daily=self.fetch,
            fetch_official=self.fetch,clock=lambda:self.now)
    def test_reuse_full_window_no_duplicate_network(self):
        with TemporaryDirectory() as folder:
            first=self.run_capture(folder);second=self.run_capture(folder)
            self.assertEqual(self.calls,2);self.assertFalse(first['reused']);self.assertTrue(second['reused'])
            self.assertEqual(first['files'],second['files']);self.assertFalse(first['policy_approved'])
            self.current['target_id']='t2'
            with self.assertRaisesRegex(ValueError,'SUPPLEMENT_SNAPSHOT_CHANGED'):self.run_capture(folder)
            self.assertEqual(self.calls,2)
    def test_changed_snapshot_preserves_partial_and_does_not_retry(self):
        with TemporaryDirectory() as folder:
            original=self.fetch
            def changed(*args):
                response=original(*args);self.current['account_revision']='r2';return response
            self.fetch=changed
            with self.assertRaisesRegex(ValueError,'SUPPLEMENT_SNAPSHOT_CHANGED'):self.run_capture(folder)
            self.current=dict(self.binding)
            self.assertEqual(self.run_capture(folder)['status'],'NEEDS_RECOVERY')
            self.assertEqual(self.calls,1)
            self.assertEqual(len(list(Path(folder).glob('*/failed.json'))),1)
            self.assertEqual(len(list(Path(folder).glob('*/transport-001.bin'))),1)
    def test_changed_saved_bytes_rejected(self):
        with TemporaryDirectory() as folder:
            result=self.run_capture(folder)
            digest=next(iter(result['source_hashes'].values()))
            (Path(folder)/result['capture_id']/(digest+'.bin')).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'SUPPLEMENT_SOURCE_CHANGED'):self.run_capture(folder)
            self.assertEqual(self.calls,2)

if __name__=='__main__':unittest.main()
