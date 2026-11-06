import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.inspect_roa_monthly_preparation import inspect

class MonthlyStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        def write(name,value):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            raw=json.dumps(value).encode();path.write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        self.write=write
        active=write('active.json',{})
        request=write('request.json',dict(active=active,package=dict(expected_month='2026-12')))
        self.ref=write('descriptor.json',dict(schema='ROA_MONTHLY_PREPARATION_LAUNCHER_V1',root=str(self.root),request=request,source_pins={},log_directory='logs'))
    def read(self):return inspect(root=self.root,descriptor_path=self.ref['path'],descriptor_sha256=self.ref['sha256'])
    def test_old_active_cannot_report_prepared(self):
        self.write('logs/prepared.json',dict(descriptor_sha256=self.ref['sha256'],result={}))
        self.write('active.json',dict(changed=True))
        self.assertEqual(self.read()['status'],'INPUT_REVIEW_REQUIRED')
    def test_lock_is_not_claimed_live_or_deleted(self):
        lock=self.root/'logs/running.lock';lock.parent.mkdir();lock.write_text('token')
        result=self.read();self.assertEqual(result['status'],'LOCK_RECONCILIATION_REQUIRED')
        self.assertFalse(result['process_liveness_verified']);self.assertEqual(lock.read_text(),'token')
    def test_prepared_does_not_mean_adopted(self):
        self.write('logs/prepared.json',dict(descriptor_sha256=self.ref['sha256'],result=dict(publication_directory='publication')))
        result=self.read();self.assertEqual(result['status'],'PREPARED_PENDING_REVALIDATION');self.assertFalse(result['runtime_month_verified'])
    def test_wrong_saved_descriptor_rejected(self):
        self.write('logs/blocked.json',dict(descriptor_sha256='wrong'))
        self.assertEqual(self.read()['status'],'INPUT_REVIEW_REQUIRED')

if __name__=='__main__':unittest.main()
