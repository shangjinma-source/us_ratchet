import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from unittest.mock import patch
from scripts.coordinate_monthly_simulation import run,safe_reason
from test_monthly_experimental_domain_capture import fixture
from test_publish_monthly_market_configuration import inputs

def setup(folder):
    root=Path(folder);other=root/'publisher-fixture';other.mkdir();request=inputs(other)
    args,plan,ph,fetch,calls=fixture(folder)
    for path in request['supplemental_hashes']:(root/path).write_bytes((other/path).read_bytes())
    def save(path,value):
        raw=json.dumps(value).encode();(root/path).write_bytes(raw);return sha256(raw).hexdigest()
    review=json.loads((root/'review.json').read_bytes());review['reviewed_members']=['BBB'];request['supplemental_hashes']['review.json']=save('review.json',review)
    settings=dict(root=str(root),plan_path='experiment.json',plan_sha256=ph,previous_manifest_path='previous.json',previous_manifest_sha256=plan['previous_manifest_sha256'],capture_index_path='actual-capture/completion_index.json',preparation_output='prepared',publish_output='published',publish_request='request.json',calendar_path=request['calendar_path'],schedule_path=request['schedule_path'],fixed_source_hashes={k:v for k,v in request['supplemental_hashes'].items() if k in (request['calendar_path'],request['schedule_path'])})
    settings_sha=save('settings.json',settings);daily_sha=save('daily.json',{'placeholder':'binder mocked in this capture-to-publish test'})
    boundary=json.loads((root/settings['calendar_path']).read_bytes())
    config=dict(schema='MONTHLY_PREPARATION_COORDINATOR_V1',root=str(root),settings_path='settings.json',settings_sha256=settings_sha,daily_config=str(root/'daily.json'),daily_sha256=daily_sha,session=boundary['active_open_at'][:10],monthly_blob_root=str(root/'blobs'),daily_output='next-daily.json',monthly_runtime_directory=str(root/'releases'),stage_directory='stages')
    h=save('coordinator.json',config)
    return root,settings,request,dict(config_path=root/'coordinator.json',config_sha256=h,clock=args['clock'],fetch=fetch),calls,save

class CoordinatorTests(unittest.TestCase):
    def test_safe_diagnostic_codes_only(self):
        self.assertEqual(safe_reason(ValueError('MONTHLY_SLOT_CONFLICT')),'MONTHLY_SLOT_CONFLICT')
        self.assertEqual(safe_reason(ValueError('private path /secret')),'ValueError')
        self.assertEqual(safe_reason(OSError('secret')),'OSError')

    def test_real_capture_prepare_publish_wait_and_hash_checked_resume(self):
        with TemporaryDirectory() as folder:
            root,s,request,args,calls,save=setup(folder)
            result=run(**args);self.assertEqual(result['status'],'PREFLIGHT_ONLY');self.assertFalse((root/'stages').exists());self.assertEqual(calls,[])
            result=run(**args,execute=True);self.assertEqual(result['status'],'WAITING_REVIEW');self.assertEqual(len(calls),1)
            before={p:p.read_bytes() for p in (root/'stages').iterdir()}
            self.assertEqual(run(**args,execute=True)['status'],'WAITING_REVIEW');self.assertEqual(len(calls),1);self.assertEqual(before,{p:p.read_bytes() for p in (root/'stages').iterdir()})
            request['preparation_arguments']={k:s[k] for k in ('previous_manifest_path','previous_manifest_sha256','capture_index_path','plan_path','plan_sha256')};request['preparation_arguments']['capture_index_sha256']=sha256((root/s['capture_index_path']).read_bytes()).hexdigest()
            h=save('request.json',request)
            def fake_bind(**kwargs):
                # Existing publisher and compiler were real; isolate only account-dependent binder.
                raw=b'{"test":"candidate"}';Path(kwargs['output']).write_bytes(raw);release=root/'release.json';release.write_bytes(b'{}')
                return dict(config_path=str(kwargs['output']),config_sha256=sha256(raw).hexdigest(),monthly_release=str(release))
            with patch('scripts.coordinate_monthly_simulation.bind',side_effect=fake_bind) as bound:
                result=run(**args,execute=True,review_request_sha256=h);self.assertEqual(result['status'],'MONTHLY_RUNTIME_PUBLISHED');self.assertEqual(bound.call_count,1)
                self.assertEqual(run(**args,execute=True,review_request_sha256=h),result);self.assertEqual(bound.call_count,1)
            self.assertEqual(len(calls),1)
            (root/'prepared/input.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):run(**args,execute=True,review_request_sha256=h)
            self.assertEqual(len(calls),1)

    def test_real_account_binder_after_real_capture_publish(self):
        from test_bind_monthly_simulation_runtime import setup as account_setup
        with TemporaryDirectory() as folder:
            binding,account=account_setup(folder)
            daily_raw=Path(binding['daily_config']).read_bytes();db=Path(account['database_path']);db_before=db.read_bytes()
            # Fixture scratch training is not the account's frozen execution archive.
            (Path(folder)/'training').rename(Path(folder)/'original-fixture-training')
            root,settings,request,args,calls,save=setup(folder)
            # The existing account fixture already published its own package; use a new output.
            settings['publish_output']='published-coordinated'
            config=json.loads((root/'coordinator.json').read_bytes())
            config['settings_sha256']=save('settings.json',settings)
            (root/'daily.json').write_bytes(daily_raw)
            config['daily_sha256']=sha256(daily_raw).hexdigest()
            config['monthly_blob_root']=binding['monthly_blob_root']
            args['config_sha256']=save('coordinator.json',config)
            self.assertEqual(run(**args,execute=True)['status'],'WAITING_REVIEW')
            request['output_directory']=settings['publish_output']
            request['preparation_arguments']={k:settings[k] for k in ('previous_manifest_path','previous_manifest_sha256','capture_index_path','plan_path','plan_sha256')}
            request['preparation_arguments']['capture_index_sha256']=sha256((root/settings['capture_index_path']).read_bytes()).hexdigest()
            h=save('request.json',request)
            with patch('scripts.monthly_runtime_routes.publish',side_effect=OSError('simulated interrupted slot write')):
                with self.assertRaises(OSError):run(**args,execute=True,review_request_sha256=h)
            self.assertTrue((root/'next-daily.json').exists())
            self.assertFalse((root/'releases'/ (config['session'][:7]+'.json')).exists())
            # Recovery must recheck the bounded clock inside its own final writer lock.
            from contextlib import contextmanager
            from scripts.bind_monthly_simulation_runtime import publication_guard
            expired=[False]; original_clock=args['clock']; candidate_before=(root/'next-daily.json').read_bytes()
            @contextmanager
            def late_recovery_lock(*values):
                with publication_guard(*values):
                    expired[0]=True
                    yield
            def deadline_clock():
                if expired[0]:raise ValueError('ROLLING_WINDOW_ELAPSED')
                return original_clock()
            with patch('scripts.coordinate_monthly_simulation.publication_guard',late_recovery_lock):
                with self.assertRaisesRegex(ValueError,'ROLLING_WINDOW_ELAPSED'):
                    run(**dict(args,clock=deadline_clock),execute=True,review_request_sha256=h)
            self.assertFalse((root/'releases'/ (config['session'][:7]+'.json')).exists())
            self.assertEqual((root/'next-daily.json').read_bytes(),candidate_before)
            self.assertEqual(db.read_bytes(),db_before)
            result=run(**args,execute=True,review_request_sha256=h)
            self.assertEqual(result['status'],'MONTHLY_RUNTIME_PUBLISHED')
            self.assertTrue(Path(result['release']).exists())
            self.assertEqual(db.read_bytes(),db_before)
            self.assertEqual(run(**args,execute=True,review_request_sha256=h),result)
            self.assertEqual(len(calls),1)
            # Simulate completion receipt loss after the slot itself was published.
            (root/'stages/bind.complete.json').unlink()
            self.assertEqual(run(**args,execute=True,review_request_sha256=h),result)
            self.assertEqual(db.read_bytes(),db_before)

    def test_future_and_failed_partial_capture_never_retry(self):
        from datetime import datetime,timezone
        with TemporaryDirectory() as folder:
            root,s,request,args,calls,save=setup(folder)
            future=dict(args,clock=lambda:datetime(2020,1,1,tzinfo=timezone.utc))
            self.assertEqual(run(**future,execute=True)['status'],'WAITING_SESSION_CLOSE');self.assertEqual(calls,[]);self.assertFalse((root/'stages').exists())
            with patch('scripts.coordinate_monthly_simulation.capture',side_effect=OSError('failure')) as failed:
                with self.assertRaises(OSError):run(**args,execute=True)
                with self.assertRaisesRegex(ValueError,'NO_AUTOMATIC_RETRY'):run(**args,execute=True)
                self.assertEqual(failed.call_count,1)

if __name__=='__main__':unittest.main()
