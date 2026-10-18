from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
import test_current_quantity_v2_followup_review as fixtures
from data.current_quantity_v2_followup_provider import FollowupBundleProvider,canonical,STORAGE


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.FollowupTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.provider=FollowupBundleProvider(repository_root=self.root,clock=lambda:datetime.fromisoformat('2026-11-13T22:00:00+00:00'))
        self.f=self.fixture

    def read(self):return self.provider.read(binding=self.f.binding,event_path='event',event_bytes=self.f.files['event'])

    def save(self,mutate=None,event_path='event'):
        self.f.actions();files=dict(self.f.files)
        files[event_path]=files['event']
        for path in self.f.root.rglob('*'):
            if path.is_file():files[path.relative_to(self.f.root).as_posix()]=path.read_bytes()
        manifest=dict(schema='V2_FOLLOWUP_BUNDLE_V1',binding=self.f.binding,event_path=event_path,event_sha256=sha256(files['event']).hexdigest(),
            source_hashes={p:sha256(raw).hexdigest() for p,raw in files.items()},daily_observations=self.f.observations,action_evidence=self.f.action_evidence)
        if mutate:mutate(manifest)
        raw=canonical(manifest);digest=sha256(raw).hexdigest();directory=self.root/STORAGE/'bundles'/digest
        directory.mkdir(parents=True);(directory/'manifest.json').write_bytes(raw)
        for path,content in files.items():
            target=directory/'sources'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        index=self.root/STORAGE/'index'/sha256(canonical(self.f.binding)).hexdigest()/(manifest['event_sha256']+'.json')
        index.parent.mkdir(parents=True,exist_ok=True);index.write_bytes(canonical(dict(manifest_sha256=digest)))
        return directory,index

    def test_construct_and_missing_bundle_are_readonly(self):
        self.assertEqual(list(self.root.iterdir()),[])
        self.assertEqual(self.read()['status'],'PENDING_SOURCE_CAPTURE')
        self.assertEqual(list(self.root.iterdir()),[])

    def test_full_saved_bundle_conditionally_computes_and_detects_tampering(self):
        directory,index=self.save();before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=self.read();self.assertEqual(result['orders'][0]['horizons'][0]['price_change_vs_reference'],'1/10')
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        (directory/'sources'/'actions.raw').write_bytes(b'changed')
        self.assertEqual(self.read()['status'],'BLOCKED_BUNDLE_VALIDATION')

    def test_outside_path_and_binding_and_manifest_hash_rejected(self):
        directory,index=self.save(lambda m:m['source_hashes'].update({'../escape':'0'*64}))
        self.assertEqual(self.read()['status'],'BLOCKED_BUNDLE_VALIDATION')
        self.f.binding=dict(self.f.binding,available_cash_exact='30000')
        self.assertEqual(self.read()['status'],'BLOCKED_BUNDLE_VALIDATION')

    def test_declared_closure_must_include_daily_sources(self):
        self.save(lambda m:m['source_hashes'].pop(self.f.observations[0]['date']+'/AAA.response.bin'))
        result=self.read()
        self.assertEqual(result['orders'][0]['horizons'][0]['status'],'BLOCKED_UNADMITTED_DAILY_SOURCE')

    def test_public_review_derives_event_path_and_preserves_binding_on_failure(self):
        event=json.loads(self.f.files['event']);event.update(event_id='a'*32,request_started_at=event['observed_at'])
        self.f.files['event']=canonical(event)
        self.save(event_path='events/2026-10-15/'+'a'*32+'.json')
        result=self.provider.review(event_raw=self.f.files['event'],binding=self.f.binding,now=self.provider.clock())
        self.assertEqual(result['orders'][0]['horizons'][0]['status'],'CONDITIONAL_PRICE_CHANGE')
        bad=self.provider.review(event_raw=b'{}',binding=self.f.binding,now=self.provider.clock())
        self.assertEqual(bad['binding'],self.f.binding);self.assertFalse(bad['actual_fill_inferred'])
        self.assertEqual(bad['status'],'BLOCKED_BUNDLE_VALIDATION')


if __name__=='__main__':unittest.main()
