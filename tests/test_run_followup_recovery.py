from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from unittest.mock import patch
import test_capture_followup_evidence as fixtures
from scripts import capture_followup_evidence as old
from scripts import run_followup_recovery as m

class RecoveryExecutionTests(unittest.TestCase):
    def fixture(self,folder):
        helper=fixtures.CaptureTests();self.addCleanup(helper.doCleanups)
        args,ticks,calls,changed=helper.fixture(folder);root=Path(folder)
        with self.assertRaises(ValueError):old.run(**dict(args,rss_fetch=lambda:dict(status=200,body=b'<html>challenge</html>')),execute=True)
        attempt=root/old.STORAGE/'attempts'/args['event_sha256']/'2026-10-16'
        def ref(path):return dict(path=path.relative_to(root).as_posix(),sha256=old.digest(path.read_bytes()))
        bundle=next((root/old.STORAGE/'bundles').glob('*/manifest.json'))
        evidence={k:ref(attempt/(k+'.json')) for k in ('started','failed','review')}
        evidence['bundle']=ref(bundle);evidence['event']=ref(root/'data/quantity_v2_observations/events/2026-10-15'/('b'*32+'.json'))
        request=dict(schema='FOLLOWUP_RECOVERY_REQUEST_V1',target_session='2026-10-16',
            binding={k:args[k] for k in ('decision_id','research_version','available_cash_exact')},recovery_name='recovery_v1',
            evidence=evidence,attempt_source_hashes={p.relative_to(root).as_posix():old.digest(p.read_bytes()) for p in attempt.rglob('*') if p.is_file()},expected_index_sha256=None)
        ticks[0]=datetime.fromisoformat('2026-10-19T22:00:00+00:00')
        runargs={k:args[k] for k in ('root','clock','fetch','action_fetch','rss_fetch')};runargs['request']=request
        return runargs,ticks,calls,changed
    def test_fixed_target_current_capture_and_no_retry(self):
        with TemporaryDirectory() as folder:
            args,ticks,calls,_=self.fixture(folder);before=len(calls)
            plan=m.run(**args);self.assertEqual(len(calls),before)
            with self.assertRaisesRegex(ValueError,'EXACT_RECOVERY_REQUEST'):m.run(**args,execute=True,expected_request_sha256='x')
            self.assertEqual(len(calls),before)
            result=m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertEqual(result['status'],'RECOVERY_FOLLOWUP_PUBLISHED');self.assertEqual(result['target_session'],'2026-10-16')
            self.assertTrue(result['captured_at'].startswith('2026-10-19'))
            count=len(calls)
            with self.assertRaises(ValueError):m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertEqual(len(calls),count)
    def test_failed_recovery_is_terminal_and_index_unchanged(self):
        with TemporaryDirectory() as folder:
            args,_,calls,_=self.fixture(folder);plan=m.run(**args)
            args['rss_fetch']=lambda:dict(status=200,body=b'<html>challenge</html>')
            with self.assertRaises(ValueError):m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertTrue((Path(folder)/plan['recovery_directory']/'failed.json').exists())
            self.assertFalse((Path(folder)/old.STORAGE/'index').exists());count=len(calls)
            with self.assertRaises(ValueError):m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertEqual(len(calls),count)
    def test_old_price_conflict_blocks_publication(self):
        with TemporaryDirectory() as folder:
            args,_,_,changed=self.fixture(folder);plan=m.run(**args);changed[0]=True
            with self.assertRaisesRegex(ValueError,'HISTORICAL_DATA_CONFLICT'):m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertFalse((Path(folder)/old.STORAGE/'index').exists())
    def test_mid_capture_source_drift_blocks_publication(self):
        with TemporaryDirectory() as folder:
            args,_,_,_=self.fixture(folder);plan=m.run(**args);fetch=args['fetch']
            def changed(*a,**k):
                result=fetch(*a,**k)
                (Path(folder)/args['request']['evidence']['failed']['path']).write_text('{}')
                return result
            args['fetch']=changed
            with self.assertRaisesRegex(ValueError,'RECOVERY_SOURCE_DRIFT'):m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertFalse((Path(folder)/old.STORAGE/'index').exists())


class PublicationTests(unittest.TestCase):
    fixture = RecoveryExecutionTests.fixture
    def test_index_race_preserves_competing_pointer(self):
        with TemporaryDirectory() as folder:
            args,_,_,_=self.fixture(folder);plan=m.run(**args)
            original=args['rss_fetch'];root=Path(folder)
            index=root/old.STORAGE/'index'/old.digest(old.canonical(args['request']['binding']))/(args['request']['evidence']['event']['sha256']+'.json')
            competing=old.canonical(dict(manifest_sha256='a'*64))
            def race():
                result=original();old.save(index,competing);return result
            args['rss_fetch']=race
            with self.assertRaisesRegex(ValueError,'INDEX_HASH_CONFLICT'):m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertEqual(index.read_bytes(),competing)
    def test_current_action_after_original_target_blocks_unit_ambiguity(self):
        with TemporaryDirectory() as folder:
            args,ticks,_,_=self.fixture(folder);plan=m.run(**args);original=args['action_fetch']
            def split(*a,**k):
                result=original(*a,**k);body=json.loads(result['body'])
                timestamp=int(datetime.fromisoformat('2026-10-19T13:30:00+00:00').timestamp())
                body['chart']['result'][0]['events']={'splits':{str(timestamp):dict(date=timestamp,numerator=2,denominator=1,splitRatio='2:1')}}
                result['body']=old.canonical(body);return result
            args['action_fetch']=split
            with self.assertRaises(ValueError):m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertFalse((Path(folder)/old.STORAGE/'index').exists())
    def test_exact_index_cas_rejects_changed_bytes_same_pointer(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);index=root/'index.json';raw=old.canonical(dict(manifest_sha256='a'*64));index.write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError,'INDEX_HASH_CONFLICT'):
                m.publish_exact_index(index=index,expected_index_sha256=old.digest(raw),expected_manifest='a'*64,new_manifest='b'*64,root=root,pins={})
            self.assertEqual(index.read_bytes(),raw+b' ')



class PublicationBoundaryTests(unittest.TestCase):
    fixture=RecoveryExecutionTests.fixture
    def execute_fault(self,folder,kind):
        args,_,_,_=self.fixture(folder);plan=m.run(**args)
        real_save=m.save;real_replace=m.os.replace;real_unlink=Path.unlink
        def save(path,raw):
            if kind=='complete' and path.name=='complete.json':raise OSError('completion write failed')
            return real_save(path,raw)
        def replace(source,target):
            real_replace(source,target)
            if kind=='replace_after':raise OSError('after commit')
        def unlink(path,*a,**k):
            if kind=='lock_cleanup' and path.suffix=='.lock':raise OSError('cleanup failed')
            return real_unlink(path,*a,**k)
        with patch.object(m,'save',side_effect=save),patch.object(m.os,'replace',side_effect=replace),patch.object(Path,'unlink',unlink):
            with self.assertRaises(m.PublicationAttention) as caught:
                m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
        receipt=caught.exception.receipt
        self.assertEqual(receipt['status'],'PUBLICATION_COMMITTED_COMPLETION_UNRECORDED')
        self.assertTrue(receipt['publication_committed']);self.assertFalse(receipt['retry_allowed'])
        self.assertEqual(receipt['index_evidence']['manifest_sha256'],receipt['manifest_sha256'])
        directory=Path(folder)/plan['recovery_directory']
        self.assertTrue((directory/'publication_attention.json').exists());self.assertFalse((directory/'failed.json').exists())
        return receipt
    def test_completion_record_failure_is_committed_attention(self):
        with TemporaryDirectory() as folder:self.execute_fault(folder,'complete')
    def test_replace_commits_then_raises_is_detected(self):
        with TemporaryDirectory() as folder:self.execute_fault(folder,'replace_after')
    def test_lock_cleanup_failure_retains_committed_evidence(self):
        with TemporaryDirectory() as folder:
            receipt=self.execute_fault(folder,'lock_cleanup')
            self.assertTrue(receipt['index_evidence']['lock_exists'])
    def test_new_bundle_disk_drift_blocks_index(self):
        with TemporaryDirectory() as folder:
            args,_,_,_=self.fixture(folder);plan=m.run(**args);real=m.compare_daily
            def drift(**kwargs):
                result=real(**kwargs)
                (kwargs['new_directory']/'manifest.json').write_text('{}')
                return result
            with patch.object(m,'compare_daily',side_effect=drift):
                with self.assertRaisesRegex(ValueError,'RECOVERY_SOURCE_DRIFT'):
                    m.run(**args,execute=True,expected_request_sha256=plan['request_sha256'])
            self.assertFalse((Path(folder)/old.STORAGE/'index').exists())
    def test_recovery_parent_symlink_or_junction_rejected(self):
        for predicate in ('is_symlink','is_junction'):
            if not hasattr(Path,predicate):continue
            with TemporaryDirectory() as folder:
                args,_,calls,_=self.fixture(folder);count=len(calls)
                real=getattr(Path,predicate)
                def alias(path):return path.name=='recoveries' or real(path)
                with patch.object(Path,predicate,alias):
                    with self.assertRaisesRegex(ValueError,'RECOVERY_PATH_ALIAS_REJECTED'):m.run(**args)
                self.assertEqual(len(calls),count)
    def test_cli_attention_is_nonzero(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'request.json').write_text('{}')
            receipt=dict(status='PUBLICATION_COMMITTED_COMPLETION_UNRECORDED',retry_allowed=False)
            with patch.object(m,'run',side_effect=m.PublicationAttention(receipt)),patch('builtins.print') as output:
                code=m.main(['--root',str(root),'--request','request.json'])
            self.assertEqual(code,2);self.assertIn('PUBLICATION_COMMITTED',output.call_args.args[0])

if __name__=='__main__':unittest.main()
