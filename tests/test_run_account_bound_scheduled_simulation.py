from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
import io
from contextlib import redirect_stdout

from scripts.run_account_bound_scheduled_simulation import run,main
from test_bootstrap_current_quantity_v2_simulation import fixture, fetch


def pair(root):
    config,args=fixture(root)
    daily=dict(schema='ISOLATED_V2_DAILY_RUNTIME_V1',root=str(root),database_path=config['database_path'],
        simulation_id=config['simulation_id'],schedule_path=config['schedule']['path'],schedule_sha256=config['schedule']['sha256'],
        runtime_directory=str(root/'daily'),fees_path=config['fees']['path'],fees_sha256=config['fees']['sha256'],
        capture_audit_roots=[],monthly_blob_root=None,monthly=None,pullback=config['pullback'])
    raw=json.dumps(daily).encode();(root/'daily.json').write_bytes(raw)
    return config,dict(bootstrap_config=args['config_path'],bootstrap_sha256=args['config_sha256'],
        daily_config=root/'daily.json',daily_sha256=sha256(raw).hexdigest())


class AccountBoundScheduledTests(unittest.TestCase):
    def test_cli_daily_terminal_statuses_and_initial_creation(self):
        argv=['--bootstrap-config','unused','--bootstrap-sha256','unused',
              '--daily-config','unused','--daily-sha256','unused']
        cases=[('CONTINUATION_COMPLETE','COMPLETE',0),('MONTHLY_COMPLETE','COMPLETE',0),
               ('ALREADY_COMPLETED','SKIPPED',0),('LATE_NO_NEW_DECISION','SKIPPED',0),
               ('BLOCKED_UNRESOLVED_ORDERS','BLOCKED',2),('UNRECOGNIZED_FUTURE_STATUS','BLOCKED',2)]
        for daily,status,code in cases:
            with self.subTest(daily=daily),patch('scripts.run_account_bound_scheduled_simulation.run',
                return_value=dict(daily_status=daily,session='2026-10-16',revision='unchanged')):
                with redirect_stdout(io.StringIO()) as output:self.assertEqual(main(argv),code)
                result=json.loads(output.getvalue())
                self.assertEqual(result['status'],status);self.assertEqual(result['daily_status'],daily)
                self.assertIn('finished_at',result)
        with patch('scripts.run_account_bound_scheduled_simulation.run',
                   return_value=dict(status='CREATED_ISOLATED_SIMULATION',accepted_at='actual-time')):
            with redirect_stdout(io.StringIO()) as output:self.assertEqual(main(argv),0)
            self.assertEqual(json.loads(output.getvalue())['status'],'CREATED_ISOLATED_SIMULATION')

    def test_outside_window_zero_io_and_weekend(self):
        with patch('scripts.run_account_bound_scheduled_simulation._now',return_value=datetime.fromisoformat('2026-10-16T09:59:59-04:00')):
            result=run(bootstrap_config='missing',bootstrap_sha256='x',daily_config='missing',daily_sha256='x',execute=True)
        self.assertEqual(result['reason'],'OUTSIDE_1000_NEW_YORK')
        with TemporaryDirectory() as folder:
            config,args=pair(Path(folder))
            with patch('scripts.run_account_bound_scheduled_simulation._now',return_value=datetime.fromisoformat('2026-10-17T10:00:00-04:00')):
                self.assertEqual(run(**args,execute=True)['reason'],'NOT_REGISTERED_SESSION')
            self.assertFalse(Path(config['database_path']).exists())

    def test_actual_bootstrap_repeat_and_expired_capture_window(self):
        for late in (False,True):
            with self.subTest(late=late),TemporaryDirectory() as folder:
                config,args=pair(Path(folder));clock=[datetime.fromisoformat('2026-10-15T10:00:30-04:00')];calls=[]
                def transport(ticker):
                    calls.append(ticker)
                    raw=json.loads(fetch(ticker));chart=raw['chart']['result'][0]
                    # Same real fixture transport, shifted observation to 10:00;
                    # keep official regular session boundaries unchanged.
                    chart['meta']['regularMarketTime']-=7200
                    chart['timestamp']=[t for t in chart['timestamp'] if t<int(clock[0].timestamp())//60*60]
                    n=len(chart['timestamp']);chart['indicators']['quote']=[{k:v[:n] for k,v in chart['indicators']['quote'][0].items()}]
                    if late:clock[0]+=timedelta(minutes=1)
                    return json.dumps(raw).encode()
                with patch('scripts.run_account_bound_scheduled_simulation._now',side_effect=lambda:clock[0]),patch(
                    'scripts.bootstrap_current_quantity_v2_simulation.fetch_intraday_chart',side_effect=transport):
                    if late:
                        with self.assertRaisesRegex(ValueError,'BOOTSTRAP_1000_WINDOW_ELAPSED|BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE'):run(**args,execute=True)
                        self.assertFalse(Path(config['database_path']).exists())
                        count=len(calls);clock[0]=datetime.fromisoformat('2026-10-15T10:00:30-04:00')
                        with self.assertRaisesRegex(ValueError,'ATTEMPT_REQUIRES_REVIEW'):run(**args,execute=True)
                        self.assertEqual(len(calls),count)
                    else:
                        self.assertEqual(run(**args,execute=True)['status'],'CREATED_ISOLATED_SIMULATION')
                        count=len(calls)
                        self.assertEqual(run(**args,execute=True)['reason'],'BOOTSTRAPPED_THIS_SESSION')
                        self.assertEqual(len(calls),count)


    def test_preview_does_not_initialize(self):
        with TemporaryDirectory() as folder:
            config,args=pair(Path(folder))
            with patch('scripts.run_account_bound_scheduled_simulation._now',return_value=datetime.fromisoformat('2026-10-15T10:00:30-04:00')):
                result=run(**args)
            self.assertEqual(result['status'],'PREFLIGHT_OK_NOT_STARTED')
            self.assertFalse(Path(config['database_path']).exists())
            self.assertFalse((Path(config['audit_directory']).parent/'scheduled-bootstrap-attempt.json').exists())

    def test_real_store_foreign_account_blocks_same_day_next_day_and_weekend(self):
        from scripts.bootstrap_current_quantity_v2_simulation import run as bootstrap
        from test_current_quantity_v2_intraday_reference import NOW
        with TemporaryDirectory() as folder:
            root=Path(folder);config,args=pair(root)
            bootstrap(config_path=args['bootstrap_config'],config_sha256=args['bootstrap_sha256'],execute=True,clock=lambda:NOW,fetch=fetch)
            config['account_id']='different-approved-account'
            raw=json.dumps(config).encode();Path(args['bootstrap_config']).write_bytes(raw)
            args['bootstrap_sha256']=sha256(raw).hexdigest()
            before=Path(config['database_path']).read_bytes()
            for date in ('2026-10-15','2026-10-16','2026-10-17'):
                with self.subTest(date=date),patch('scripts.run_account_bound_scheduled_simulation._now',return_value=datetime.fromisoformat(date+'T10:00:30-04:00')),patch('scripts.run_account_bound_scheduled_simulation.run_runtime') as daily:
                    with self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_ORIGIN_MISMATCH'):run(**args,execute=True)
                    daily.assert_not_called()
                self.assertEqual(Path(config['database_path']).read_bytes(),before)

    def test_normal_existing_dispatch_preserves_arguments(self):
        from scripts.bootstrap_current_quantity_v2_simulation import run as bootstrap
        from test_current_quantity_v2_intraday_reference import NOW
        with TemporaryDirectory() as folder:
            config,args=pair(Path(folder))
            bootstrap(config_path=args['bootstrap_config'],config_sha256=args['bootstrap_sha256'],execute=True,clock=lambda:NOW,fetch=fetch)
            when=datetime.fromisoformat('2026-10-16T10:00:30-04:00')
            with patch('scripts.run_account_bound_scheduled_simulation._now',return_value=when),patch('scripts.run_account_bound_scheduled_simulation.run_runtime',return_value={'daily_status':'ALREADY_COMPLETED'}) as daily:
                self.assertEqual(run(**args),{'daily_status':'ALREADY_COMPLETED'})
                kwargs=daily.call_args.kwargs
                self.assertEqual(kwargs['config_path'],args['daily_config'])
                self.assertEqual(kwargs['config_sha256'],args['daily_sha256'])
                self.assertEqual(kwargs['session'],'2026-10-16')
                self.assertEqual(kwargs['triggered_at'],when.isoformat())
                self.assertFalse(kwargs['execute'])

    def test_post_bootstrap_gate_failure_preserves_created_evidence(self):
        from scripts.bootstrap_current_quantity_v2_simulation import run as bootstrap
        from test_current_quantity_v2_intraday_reference import NOW
        from backtest.current_quantity_v2_simulation_store import SimulationStore
        with TemporaryDirectory() as folder:
            config,args=pair(Path(folder))
            def create_foreign(**kwargs):
                if not kwargs.get('execute'):return {'status':'PREFLIGHT_OK_NOT_STARTED'}
                # Real store/replay creation under a different bootstrap account.
                foreign=dict(config,account_id='foreign-account')
                path=Path(folder)/'foreign.json';raw=json.dumps(foreign).encode();path.write_bytes(raw)
                return bootstrap(config_path=path,config_sha256=sha256(raw).hexdigest(),execute=True,clock=lambda:NOW,fetch=fetch)
            with patch('scripts.run_account_bound_scheduled_simulation._now',return_value=datetime.fromisoformat('2026-10-15T10:00:30-04:00')),patch('scripts.run_account_bound_scheduled_simulation.bootstrap_run',side_effect=create_foreign):
                with self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_ORIGIN_MISMATCH'):run(**args,execute=True)
                self.assertTrue(Path(config['database_path']).exists())
                self.assertTrue((Path(config['audit_directory']).parent/'scheduled-bootstrap-attempt.json').exists())
                self.assertEqual(SimulationStore(config['database_path']).read(config['simulation_id'])['simulation']['origin']['ledger']['account_id'],'foreign-account')
                with self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_ORIGIN_MISMATCH'):run(**args,execute=True)


if __name__=='__main__':unittest.main()

