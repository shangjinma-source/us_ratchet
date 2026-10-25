"""Offline fixture copies; no network, capture, publication, or account writes."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from scripts import preflight_followup_recovery as module

ROOT=Path(__file__).resolve().parents[1]

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        diagnostic=json.loads((ROOT/'tmp/followup_rss_diagnostics_20261019_v1/diagnosis.json').read_text())['events'][0]
        failed=diagnostic['failure']['path'];attempt=failed.rsplit('/',1)[0]
        def ref(path):return dict(path=path,sha256=sha256((ROOT/path).read_bytes()).hexdigest())
        refs={k:ref(attempt+'/'+k+'.json') for k in ('started','failed','review')}
        refs['bundle']=ref(diagnostic['manifest']['path'])
        refs['event']=ref('data/quantity_v2_observations/'+diagnostic['event'])
        started=json.loads((ROOT/refs['started']['path']).read_text())
        self.request=dict(schema='FOLLOWUP_RECOVERY_REQUEST_V1',target_session=diagnostic['target_session'],
            binding=started['binding'],recovery_name='explicit_recovery_v1',evidence=refs,expected_index_sha256=None,
            attempt_source_hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in (ROOT/attempt).rglob('*') if p.is_file()})
        paths=set(self.request['attempt_source_hashes'])|{r['path'] for r in refs.values()}
        manifest=json.loads((ROOT/refs['bundle']['path']).read_text())
        paths.update(refs['bundle']['path'].rsplit('/',1)[0]+'/sources/'+p for p in manifest['source_hashes'])
        event=json.loads((ROOT/refs['event']['path']).read_text())
        paths.update('data/quantity_v2_observations/'+c['path'] for c in event['captures'])
        calendar=json.loads((ROOT/module.CALENDAR).read_text());paths.add(module.CALENDAR);paths.update(calendar['source_hashes'])
        for path in paths:
            dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/path).read_bytes())
    def run_request(self,request=None,now='2026-10-20T23:00:00+00:00'):
        return module.preflight(root=self.root,request=request or self.request,observed_at=datetime.fromisoformat(now))
    def test_readonly_original_target_not_latest(self):
        before={p.relative_to(self.root).as_posix():sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        result=self.run_request()
        self.assertEqual(result['target_session'],'2026-10-16');self.assertEqual(result['http_calls'],0)
        self.assertFalse(result['execution_available']);self.assertFalse((self.root/result['recovery_directory']).exists())
        after={p.relative_to(self.root).as_posix():sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
    def test_source_drift_and_incomplete_evidence(self):
        bad=deepcopy(self.request);bad['attempt_source_hashes'].pop(next(iter(bad['attempt_source_hashes'])))
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_ATTEMPT'):self.run_request(bad)
        path=self.root/self.request['evidence']['failed']['path'];path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):self.run_request()
    def test_wrong_identity_path_target_binding(self):
        for kind in ('path','target','binding'):
            bad=deepcopy(self.request)
            if kind=='path':bad['evidence']['failed']['path']='../outside.json'
            if kind=='target':bad['target_session']='2026-10-19'
            if kind=='binding':bad['binding']['available_cash_exact']='1'
            with self.assertRaises(ValueError):self.run_request(bad)
    def test_existing_recovery_and_index_conflict(self):
        result=self.run_request();directory=self.root/result['recovery_directory'];directory.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'RECOVERY_ALREADY_EXISTS'):self.run_request()
        bad=deepcopy(self.request);bad['expected_index_sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'INDEX_HASH_CONFLICT'):self.run_request(bad)
    def test_unclosed_original_target_rejected(self):
        # Future failure records are also invalid at this observation time; never pretend recovery preceded failure.
        with self.assertRaises(ValueError):self.run_request(now='2026-10-16T12:00:00+00:00')

if __name__=='__main__':unittest.main()
