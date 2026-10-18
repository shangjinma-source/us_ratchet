import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_bind_monthly_simulation_runtime import setup
from scripts.bind_monthly_simulation_runtime import bind
from scripts.monthly_runtime_routes import resolve,publish
from scripts.run_current_quantity_v2_simulation import preflight
from scripts.run_scheduled_quantity_v2_simulation import run


class MonthlyRuntimeRoutesTests(unittest.TestCase):
    def test_broken_release_link_is_not_missing_month(self):
        with TemporaryDirectory() as folder:
            directory=Path(folder);slot=directory/'2026-12.json'
            try:slot.symlink_to(directory/'absent.json')
            except OSError as error:self.skipTest('Host disallows symlink creation: '+str(error))
            with self.assertRaisesRegex(ValueError,'INVALID_MONTHLY_RELEASE_FILE'):
                resolve(directory=directory,session='2026-12-01',base_path=directory/'base.json',base_hash='0'*64)

    def test_real_publication_binding_and_scheduled_selection(self):
        with TemporaryDirectory() as folder:
            args,config=setup(folder);root=Path(folder);directory=root/'releases'
            before=Path(config['database_path']).read_bytes()
            result=bind(**args,monthly_runtime_directory=str(directory))
            self.assertEqual(result['status'],'VALIDATED_MONTHLY_RUNTIME_RELEASE_PUBLISHED')
            selected,h=resolve(directory=directory,session=args['session'],base_path=args['daily_config'],base_hash=args['daily_sha256'])
            checked=preflight(config_path=selected,config_sha256=h,session=args['session'])
            self.assertEqual(checked['summary']['status'],'PREFLIGHT_OK')
            bootstrap_path=root/'config.json'
            kwargs=dict(bootstrap_config=bootstrap_path,bootstrap_sha256=sha256(bootstrap_path.read_bytes()).hexdigest(),
                        daily_config=args['daily_config'],daily_sha256=args['daily_sha256'],monthly_runtime_directory=directory)
            # 15:00 UTC is 10:00 New York in December, not the UTC month/day shortcut.
            with (patch('scripts.run_scheduled_quantity_v2_simulation._now',return_value=datetime.fromisoformat('2026-12-01T15:00:00+00:00')),
                 patch('scripts.run_scheduled_quantity_v2_simulation.run_runtime',return_value={'status':'CAPTURED'}) as runtime):
                self.assertEqual(run(**kwargs)['status'],'CAPTURED')
                self.assertEqual(runtime.call_args.kwargs['config_path'],selected)
                self.assertEqual(runtime.call_args.kwargs['config_sha256'],h)
                self.assertEqual(runtime.call_args.kwargs['session'],'2026-12-01')
            with self.assertRaises(FileExistsError):
                publish(directory=directory,session=args['session'],base_path=args['daily_config'],base_hash=args['daily_sha256'],candidate_path=selected,candidate_hash=h)
            self.assertEqual(Path(config['database_path']).read_bytes(),before)
            self.assertFalse(list(directory.glob('.release-*')))
            slot=directory/'2026-12.json';slot.write_text('{bad json')
            with (patch('scripts.run_scheduled_quantity_v2_simulation._now',return_value=datetime.fromisoformat('2026-12-01T15:00:00+00:00')),
                  patch('scripts.run_scheduled_quantity_v2_simulation.run_runtime') as runtime):
                with self.assertRaises(ValueError):run(**kwargs)
                runtime.assert_not_called()
            with (patch('scripts.run_scheduled_quantity_v2_simulation._now',return_value=datetime.fromisoformat('2026-12-01T15:01:00+00:00')),
                  patch('scripts.monthly_runtime_routes.resolve',side_effect=AssertionError('Outside window must not read routes'))):
                self.assertEqual(run(**kwargs)['reason'],'OUTSIDE_1000_NEW_YORK')

    def test_missing_corrupt_and_changed_policy_are_not_accepted(self):
        with TemporaryDirectory() as folder:
            args,config=setup(folder);root=Path(folder);directory=root/'releases'
            result=bind(**args,monthly_runtime_directory=directory)
            selected,h=resolve(directory=directory,session='2026-11-02',base_path=args['daily_config'],base_hash=args['daily_sha256'])
            self.assertEqual(Path(selected),args['daily_config'])
            with self.assertRaisesRegex(ValueError,'MONTHLY_CONFIGURATION_REQUIRED'):
                preflight(config_path=selected,config_sha256=h,session='2026-11-02')
            slot=directory/'2026-12.json';original=slot.read_bytes();record=json.loads(original)
            for key,value in [('target_month','2026-11'),('base_sha256','0'*64),('config_sha256','0'*64)]:
                with self.subTest(key=key):
                    slot.write_text(json.dumps(dict(record,**{key:value})))
                    with self.assertRaises(ValueError):resolve(directory=directory,session=args['session'],base_path=args['daily_config'],base_hash=args['daily_sha256'])
            slot.write_bytes(original)
            candidate=Path(result['config_path']);data=json.loads(candidate.read_bytes());data['simulation_id']='different-account'
            candidate.write_text(json.dumps(data));record['config_sha256']=sha256(candidate.read_bytes()).hexdigest();slot.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'MONTHLY_ROUTE_CHANGED_BASE_CONFIGURATION'):
                resolve(directory=directory,session=args['session'],base_path=args['daily_config'],base_hash=args['daily_sha256'])


if __name__=='__main__':unittest.main()
