from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import subprocess
import sys
import unittest

from scripts.bind_monthly_simulation_runtime import bind
from scripts.bootstrap_current_quantity_v2_simulation import run as bootstrap
from scripts.publish_monthly_market_configuration import publish
from scripts.run_current_quantity_v2_simulation import preflight
from test_bootstrap_current_quantity_v2_simulation import fixture,fetch,NOW
from test_publish_monthly_market_configuration import inputs


def setup(folder):
    root=Path(folder);config,arguments=fixture(root)
    schedule=json.loads((root/'schedule.json').read_bytes())
    schedule['sessions'] += [dict(date=d,open_at=d+'T09:30:00-05:00',close_at=d+'T16:00:00-05:00')
                             for d in ('2026-11-02','2026-12-01')]
    raw=json.dumps(schedule).encode();(root/'runtime-schedule.json').write_bytes(raw)
    config['schedule']=dict(path='runtime-schedule.json',sha256=sha256(raw).hexdigest())
    raw=json.dumps(config).encode();(root/'config.json').write_bytes(raw);arguments['config_sha256']=sha256(raw).hexdigest()
    bootstrap(**arguments,execute=True,clock=lambda:NOW,fetch=fetch)
    published=publish(**inputs(folder))
    daily=dict(schema='ISOLATED_V2_DAILY_RUNTIME_V1',root=str(root),database_path=config['database_path'],
        simulation_id=config['simulation_id'],schedule_path=config['schedule']['path'],schedule_sha256=config['schedule']['sha256'],
        runtime_directory=str(root/'daily'),fees_path=config['fees']['path'],fees_sha256=config['fees']['sha256'],
        capture_audit_roots=[],monthly_blob_root=None,monthly=None,pullback=config['pullback'])
    raw=json.dumps(daily).encode();path=root/'daily.json';path.write_bytes(raw)
    return dict(daily_config=path,daily_sha256=sha256(raw).hexdigest(),monthly_path=published['config_path'],
        monthly_sha256=published['config_sha256'],session='2026-12-01',
        monthly_blob_root=str(Path(config['audit_directory'])/'blobs'),output=root/'new-daily.json'),config


class MonthlyRuntimeBindingTests(unittest.TestCase):
    def test_real_publish_bind_and_daily_preflight_without_writes_to_account(self):
        with TemporaryDirectory() as folder:
            args,config=setup(folder);db=Path(config['database_path']);before=db.read_bytes();original=args['daily_config'].read_bytes()
            history=preflight(config_path=args['daily_config'],config_sha256=args['daily_sha256'],session=args['session'])
            self.assertEqual(history['summary']['status'],'PREFLIGHT_OK_HISTORY_ONLY')
            self.assertFalse(history['summary']['new_decisions_allowed'])
            self.assertEqual(history['summary']['decision_block_reason'],'MONTHLY_CONFIGURATION_REQUIRED')
            with (patch('subprocess.run',side_effect=AssertionError('Binding must not research')),
                  patch('urllib.request.urlopen',side_effect=AssertionError('Binding must not fetch'))):
                result=bind(**args)
                checked=preflight(config_path=result['config_path'],config_sha256=result['config_sha256'],session=args['session'])
            self.assertEqual(checked['summary']['status'],'PREFLIGHT_OK')
            self.assertFalse(result['account_writes']);self.assertFalse(result['scheduler_activated'])
            self.assertEqual(db.read_bytes(),before);self.assertEqual(args['daily_config'].read_bytes(),original)
            candidate=json.loads(args['output'].read_bytes());base=json.loads(original)
            for key in base:
                if key not in ('monthly','monthly_blob_root'):self.assertEqual(candidate[key],base[key])
            with self.assertRaisesRegex(ValueError,'CREATE_ONLY_OUTPUT_EXISTS'):bind(**args)
            command=[sys.executable,'-X','utf8','-E','-B','-m','scripts.bind_monthly_simulation_runtime']
            for key,value in dict(args,output=Path(folder)/'cli-daily.json').items():
                command.extend(['--'+key.replace('_','-'),str(value)])
            completed=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr+completed.stdout)
            self.assertEqual(json.loads(completed.stdout)['config_sha256'],result['config_sha256'])
            self.assertEqual(db.read_bytes(),before)

    def test_writer_lock_spans_slot_publication(self):
        import sqlite3
        from scripts.monthly_runtime_routes import publish as original_publish
        with TemporaryDirectory() as folder:
            args,config=setup(folder);db=Path(config['database_path']);before=db.read_bytes();attempts=[]
            def competing_writer(**kwargs):
                connection=sqlite3.connect(db,timeout=0,isolation_level=None)
                try:
                    with self.assertRaises(sqlite3.OperationalError):connection.execute('BEGIN IMMEDIATE')
                    attempts.append('LOCKED')
                finally:connection.close()
                return original_publish(**kwargs)
            with patch('scripts.monthly_runtime_routes.publish',side_effect=competing_writer):
                result=bind(**args,monthly_runtime_directory=str(Path(folder)/'releases'))
            self.assertEqual(attempts,['LOCKED']);self.assertTrue(Path(result['monthly_release']).exists());self.assertEqual(db.read_bytes(),before)

    def test_changed_publication_and_wrong_month_do_not_publish_candidate(self):
        with TemporaryDirectory() as folder:
            args,_=setup(folder)
            for update in ({'expected_revision':'0'*64},{'monthly_sha256':'0'*64},{'session':'2026-11-02'},
                           {'monthly_blob_root':str(Path(folder)/'missing-blobs')}):
                with self.subTest(update=update),self.assertRaises(ValueError):bind(**dict(args,**update))
                self.assertFalse(args['output'].exists())


if __name__=='__main__':unittest.main()
