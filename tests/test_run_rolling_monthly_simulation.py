import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from unittest.mock import patch
import unittest

from test_materialize_monthly_successor import completed_fixture
from test_monthly_automatic_review_request import automatic_fixture
from scripts.run_rolling_monthly_simulation import run


def config(root, previous_hash):
    def binding(path): return dict(path=str(root/path),sha256=sha256((root/path).read_bytes()).hexdigest())
    document = dict(schema='ROLLING_MONTHLY_SIMULATION_V1',root=str(root),
        first_coordinator=dict(path=str(root/'coordinator.json'),sha256=previous_hash),
        bootstrap=binding('config.json'),policy=binding('auto-policy.json'),rolling_output_directory='rolling',
        first_evidence_directory='first-month-evidence')
    raw=json.dumps(document).encode();path=root/'rolling.json';path.write_bytes(raw)
    return dict(config_path=path,config_sha256=sha256(raw).hexdigest())


class RollingTests(unittest.TestCase):
    def test_completed_real_pipeline_materializes_and_selects_future_without_execution(self):
        with TemporaryDirectory() as directory:
            root, previous, calls, daily = completed_fixture(directory)
            args=config(root,previous['config_sha256']);before=Path(daily['database_path']).read_bytes()
            with patch('scripts.run_rolling_monthly_simulation.pipeline',side_effect=AssertionError('future must not run')):
                result=run(**args,clock=previous['clock'])
                self.assertEqual(result['status'],'NEXT_PLAN_MATERIALIZATION_REQUIRED')
                self.assertFalse((root/'rolling').exists())
                result=run(**args,execute=True,clock=previous['clock'])
                self.assertEqual(result['status'],'WAITING_SESSION_CLOSE')
                self.assertEqual(result['target_month'],'2027-01')
                self.assertEqual(run(**args,execute=True,clock=previous['clock']),result)
            self.assertEqual(Path(daily['database_path']).read_bytes(),before);self.assertEqual(len(calls),1)
            (root/'rolling/plans/after-2026-12/registry.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'SUCCESSOR_OUTPUT_CHANGED'):run(**args,execute=True,clock=previous['clock'])

    def test_unfinished_month_time_boundary_and_single_dispatch(self):
        with TemporaryDirectory() as directory:
            root, previous, calls, daily, _, _=automatic_fixture(directory)
            args=config(root,previous['config_sha256'])
            with patch('scripts.run_rolling_monthly_simulation.pipeline') as worker:
                early=lambda:datetime.fromisoformat('2026-11-02T20:59:59+00:00')
                result=run(**args,execute=True,clock=early)
                self.assertEqual(result['status'],'WAITING_SESSION_CLOSE');worker.assert_not_called()
                late=lambda:datetime.fromisoformat('2026-12-01T14:30:00+00:00')
                result=run(**args,execute=True,clock=late)
                self.assertEqual(result['status'],'RECOVERY_REQUIRED');worker.assert_not_called()
                result=run(**args,clock=previous['clock'])
                self.assertEqual(result['status'],'DUE_READ_ONLY');worker.assert_not_called()
                worker.return_value={'status':'WAITING_REVIEW','reason':'EVIDENCE_MISSING'}
                result=run(**args,execute=True,clock=previous['clock'])
                self.assertEqual(result['pipeline_calls'],1);self.assertEqual(worker.call_count,1)
                self.assertEqual(worker.call_args.kwargs['output_directory'],'first-month-evidence')
                self.assertEqual(worker.call_args.kwargs['policy_path'],'auto-policy.json')
                self.assertEqual(result['target_month'],'2026-12')
            self.assertEqual(calls,[]);self.assertFalse((root/'rolling').exists())

    def test_due_real_pipeline_with_only_transports_injected(self):
        from test_collect_monthly_automatic_review_evidence import fixture
        from scripts.coordinate_monthly_simulation import run as coordinate
        from scripts.collect_monthly_automatic_review_evidence import collect
        with TemporaryDirectory() as directory:
            root, previous, calls, daily, collection, seen = fixture(directory)
            def save(path, value):
                raw=json.dumps(value).encode();(root/path).write_bytes(raw);return sha256(raw).hexdigest()
            settings=json.loads((root/'settings.json').read_bytes())
            schedule=json.loads((root/'schedule.json').read_bytes())
            for row in schedule['sessions']: row['timezone']='America/New_York'
            for day in ('2026-12-31','2027-01-01'):
                schedule['calendar'].append(day)
                schedule['sessions'].append(dict(date=day,timezone='America/New_York',
                    open_at=day+'T09:30:00-05:00',close_at=day+'T16:00:00-05:00'))
            settings['fixed_source_hashes']['schedule.json']=save('schedule.json',schedule)
            coordinator=json.loads((root/'coordinator.json').read_bytes())
            coordinator['settings_sha256']=save('settings.json',settings)
            previous['config_sha256']=save('coordinator.json',coordinator)
            initial=json.loads((root/'collector-bootstrap.json').read_bytes())
            descriptor=json.loads((root/initial['descriptor']['path']).read_bytes())
            descriptor['source_hashes']={p:sha256((root/p).read_bytes()).hexdigest() for p in descriptor['source_hashes']}
            initial['descriptor']['sha256']=save(initial['descriptor']['path'],descriptor)
            bootstrap_hash=save('collector-bootstrap.json',initial)
            args=config(root,previous['config_sha256'])
            document=json.loads(Path(args['config_path']).read_bytes())
            document['bootstrap']=dict(path=str(root/'collector-bootstrap.json'),sha256=bootstrap_hash)
            args['config_sha256']=save('rolling.json',document)
            before=Path(daily['database_path']).read_bytes()
            # Actual pipeline, collector, publisher, binder, and materializer; replace only HTTP transports.
            with patch('scripts.run_monthly_simulation_pipeline.coordinate',
                       side_effect=lambda **values:coordinate(**values,fetch=previous['fetch'])), \
                 patch('scripts.run_monthly_simulation_pipeline.collect',
                       side_effect=lambda **values:collect(**values,rss_fetch=collection['rss_fetch'])):
                result=run(**args,execute=True,clock=previous['clock'])
                self.assertEqual(result['status'],'MONTHLY_COMPLETE_NEXT_PLAN_READY',result)
                self.assertEqual(result['result']['status'],'MONTHLY_RUNTIME_PUBLISHED')
                self.assertEqual(result['pipeline_calls'],1)
                repeated=run(**args,execute=True,clock=previous['clock'])
                self.assertEqual(repeated['status'],'WAITING_SESSION_CLOSE')
                self.assertEqual(repeated['pipeline_calls'],0)
            self.assertEqual(len(calls),1);self.assertEqual(seen,['RSS'])
            self.assertEqual(Path(daily['database_path']).read_bytes(),before)
            self.assertTrue((root/'first-month-evidence/complete.json').is_file())


if __name__=='__main__':unittest.main()
