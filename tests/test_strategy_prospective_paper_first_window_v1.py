from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_prospective_paper_first_window_v1 import review_paper_first_window,CODE_PATHS
from scripts.capture_paper_first_window_v1 import capture
import test_strategy_daily_first_window_v3 as old

ROOT=Path(__file__).resolve().parents[1]


class PaperFirstTests(unittest.TestCase):
    def case(self,folder):
        root=Path(folder);c,config,cap=old.FirstWindowTests().case(folder)
        original=old.FirstWindowTests().run_case(folder,c,config,cap)
        self.assertIsNotNone(original['receipt'])
        binding=c.target['payload']['decision']['payload']['input_binding']
        unit_path=root/config['unit_source_paths'][binding['documents']['unit_review']]
        base=unit_path.parent
        def save(path,value):
            body=canonical(value);path.write_bytes(body)
            return dict(path=path.relative_to(root).as_posix(),sha256=sha256(body).hexdigest())
        training=save(root/'paper-training.json',dict(decision_date=binding['training_cutoff_date'],
            candidates=[dict(ticker='BBB',security_id='B')]))
        review=json.loads(unit_path.read_bytes());review['training_manifest_sha256']=training['sha256']
        for unit in review['securities'].values():unit['training_manifest_sha256']=training['sha256']
        unit_ref=save(unit_path,review)
        complete=json.loads((base/'complete.json').read_bytes())
        complete['source_hashes'][binding['documents']['unit_review']]=unit_ref['sha256']
        complete_ref=save(base/'complete.json',complete)
        pins=[]
        for name in CODE_PATHS:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);raw=(ROOT/name).read_bytes();path.write_bytes(raw)
            pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
        cfg=dict(config,schema='PAPER_FIRST_WINDOW_SOURCE_PREPARATION_V1',source_pins=pins,training=training,
            baseline_review=unit_ref,baseline_complete=complete_ref,
            baseline_marks=dict(path=(base/'marks.json').relative_to(root).as_posix(),sha256=sha256((base/'marks.json').read_bytes()).hexdigest()))
        return c,cfg,cap,original

    def run_case(self,folder,c,cfg,cap):
        raw=canonical(cfg)
        return review_paper_first_window(root=folder,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
            capture_files=cap,clock=lambda:c.clock[0])

    def test_same_source_core_prices_without_account_or_target_authority(self):
        with TemporaryDirectory() as folder:
            c,cfg,cap,old_result=self.case(folder);before=c.store.path.read_bytes()
            result=self.run_case(folder,c,cfg,cap)
            self.assertIsNotNone(result['receipt'],result)
            self.assertNotIn('account_id',result['receipt']);self.assertNotIn('target_id',result['receipt'])
            self.assertFalse(result['registration_created']);self.assertFalse(result['book_created'])
            self.assertEqual(before,c.store.path.read_bytes())
            new=json.loads(result['files'][result['receipt']['normalized_inputs_path']])
            old_inputs=json.loads(old_result['files'][old_result['receipt']['normalized_inputs_path']])
            self.assertEqual(new['histories']['B']['closes'],old_inputs['histories']['B']['closes'])

    def test_capture_large_pinned_training_manifest_dry_run(self):
        with TemporaryDirectory() as folder:
            c,cfg,_,_=self.case(folder)
            path=Path(folder)/cfg['training']['path']
            doc=json.loads(path.read_bytes());doc['padding']='x'*(1024*1024)
            body=canonical(doc);path.write_bytes(body)
            cfg['training']['sha256']=sha256(body).hexdigest();raw=canonical(cfg)
            result=capture(root=folder,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
                output=Path(folder)/'unused',clock=lambda:c.clock[0])
            self.assertEqual(result['status'],'DRY_RUN_SINGLE_SECURITY')
            self.assertFalse((Path(folder)/'unused').exists())

    def test_changed_overlap_fails_and_future_unrelated_notice_passes(self):
        with TemporaryDirectory() as folder:
            c,cfg,cap,_=self.case(folder)
            doc=json.loads(cap['daily.response.bin']);doc['chart']['result'][0]['indicators']['quote'][0]['close'][-2]=101
            doc['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'][-2]=101
            bad=deepcopy(cap);bad['daily.response.bin']=canonical(doc)
            receipt=json.loads(bad['daily.receipt.json']);receipt.update(raw_sha256=sha256(bad['daily.response.bin']).hexdigest(),stored_bytes=len(bad['daily.response.bin']))
            bad['daily.receipt.json']=canonical(receipt)
            result=self.run_case(folder,c,cfg,bad)
            self.assertEqual(result['reason'],'WAIT_PRICE_CONTINUITY_REVIEW')
            raw=b'<rss><channel><item><title>Unrelated issuer</title><pubDate>Wed, 04 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
            cap['official.response.bin']=raw;rec=json.loads(cap['official.receipt.json']);rec.update(raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw));cap['official.receipt.json']=canonical(rec)
            self.assertIsNotNone(self.run_case(folder,c,cfg,cap)['receipt'])

    def test_baseline_unit_and_release_tampering_rejected(self):
        with TemporaryDirectory() as folder:
            c,cfg,cap,_=self.case(folder)
            cfg['release_sha256']='a'*64
            with self.assertRaisesRegex(ValueError,'PAPER_FIRST_NO_RELEASE'):self.run_case(folder,c,cfg,cap)
            cfg['release_sha256']=None;cfg['baseline_review']['sha256']='b'*64
            with self.assertRaises(ValueError):self.run_case(folder,c,cfg,cap)

    def test_capture_writes_unregistered_source_root_and_closed_session_does_nothing(self):
        with TemporaryDirectory() as folder:
            c,cfg,cap,_=self.case(folder);raw=canonical(cfg);digest=sha256(raw).hexdigest();root=Path(folder)
            calls=[]
            def daily(*args):calls.append('daily');return dict(status=200,body=cap['daily.response.bin'])
            def official():calls.append('official');return dict(status=200,body=cap['official.response.bin'])
            result=capture(root=root,configuration_bytes=raw,configuration_sha256=digest,output=root/'capture-new',
                execute=True,clock=lambda:c.clock[0],fetch_daily=daily,fetch_official=official)
            self.assertEqual(result['status'],'UNBOUND_PAPER_PARENT_SAVED_NOT_REGISTERED',result)
            self.assertEqual(calls,['daily','official'])
            self.assertTrue((root/'capture-new/source-root/parent-receipt.json').is_file())
            result=capture(root=root,configuration_bytes=raw,configuration_sha256=digest,output=root/'closed',
                execute=True,clock=lambda:__import__('datetime').datetime.fromisoformat('2026-11-03T22:00:00+00:00'),
                fetch_daily=daily,fetch_official=official)
            self.assertEqual(result['status'],'WAIT_NEXT_SESSION_NO_CAPTURE');self.assertFalse((root/'closed').exists())
            self.assertEqual(calls,['daily','official'])


if __name__=='__main__':unittest.main()
