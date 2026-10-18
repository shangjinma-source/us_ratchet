from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from datetime import timedelta

from scripts.bootstrap_current_quantity_v2_simulation import run, remaining_calendar
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS
from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY
from backtest.current_quantity_v2_minute_day_fill import MODEL
from backtest.current_quantity_v2_simulation_store import SimulationStore
from test_current_quantity_v2_current_cash_sources import snapshot_fixture
from test_current_quantity_v2_intraday_reference import NOW,raw

ROOT=Path(__file__).resolve().parents[1]


def fixture(root):
    snapshots,_=snapshot_fixture(root)
    def save(path,value):
        p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
        encoded=json.dumps(value).encode();p.write_bytes(encoded)
        return dict(path=path,sha256=sha256(encoded).hexdigest())
    descriptor=save('descriptor.json',snapshots.loader())
    for withdrawal in SOURCE_WITHDRAWALS:
        for path in withdrawal['evidence']:
            p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/path).read_bytes())
    quote=json.loads(raw('AAA',10))['chart']['result'][0]['meta']['currentTradingPeriod']['regular']
    from datetime import datetime,timezone
    rows=[dict(date='2026-10-14',open_at='2026-10-14T13:30:00+00:00',close_at='2026-10-14T20:00:00+00:00'),
          dict(date='2026-10-15',open_at=datetime.fromtimestamp(quote['start'],timezone.utc).isoformat(),
               close_at=datetime.fromtimestamp(quote['end'],timezone.utc).isoformat()),
          dict(date='2026-10-16',open_at='2026-10-16T13:30:00+00:00',close_at='2026-10-16T20:00:00+00:00')]
    schedule=save('schedule.json',dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',sessions=rows,source_hashes={}))
    fees=save('fees.json',dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1',status='MODELLED_FEES_NOT_BROKER_FEES',fixed_per_order='0',notional_rate='0'))
    config=dict(schema='ISOLATED_CURRENT_CASH_BOOTSTRAP_V1',root=str(root),descriptor=descriptor,
        initial_month=dict(path='month.json',sha256=sha256((root/'month.json').read_bytes()).hexdigest()),schedule=schedule,
        simulation_id='new-isolated',account_id='new-isolated-cash',initial_cash='110',model=MODEL,fees=fees,
        database_path=str(root/'runtime/simulation.sqlite3'),audit_directory=str(root/'runtime/captures'),
        pullback=dict(policy=deepcopy(EXPERIMENTAL_POLICY),database_path=str(root/'runtime/caps.sqlite3')),
        scope='CONDITIONAL_RESEARCH_ONLY_NOT_BROKER_OR_FORWARD_CERTIFICATION')
    pinned=save('config.json',config)
    return config,dict(config_path=root/'config.json',config_sha256=pinned['sha256'])


def fetch(ticker):
    payload=json.loads(raw(ticker,10));quote=payload['chart']['result'][0]
    times=list(range(quote['meta']['currentTradingPeriod']['regular']['start'],int(NOW.timestamp())//60*60,60))
    quote['timestamp']=times;quote['indicators']['quote']=[dict(open=[10]*len(times),high=[11]*len(times),low=[9]*len(times),close=[10]*len(times),volume=[10]*len(times))]
    return json.dumps(payload).encode()


class BootstrapRuntimeTests(unittest.TestCase):
    def test_real_composition_with_pullback_preflight_execute_and_duplicate(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);config,args=fixture(root)
            def forbidden(_):raise AssertionError('Preflight cannot fetch')
            checked=run(**args,clock=lambda:NOW,fetch=forbidden)
            self.assertEqual(checked['status'],'PREFLIGHT_OK_NOT_STARTED');self.assertFalse((root/'runtime').exists())
            self.assertEqual(checked['first_session'],'2026-10-15')
            result=run(**args,execute=True,clock=lambda:NOW,fetch=fetch)
            self.assertEqual(result['status'],'CREATED_ISOLATED_SIMULATION')
            saved=SimulationStore(config['database_path']).read(config['simulation_id'])['simulation']
            self.assertEqual(saved['valuation']['registration']['registered_at'],result['accepted_at'])
            self.assertEqual(saved['valuation']['registration']['calendar']['session_dates'],['2026-10-15','2026-10-16'])
            rows=saved['origin']['ledger']['acceptance']['proposal']['rows']
            self.assertTrue(all(row['limit_price']!='10' for row in rows))
            with self.assertRaisesRegex(ValueError,'BOOTSTRAP_ALREADY_EXISTS'):
                run(**args,execute=True,clock=lambda:NOW,fetch=forbidden)

    def test_config_and_month_fail_before_storage(self):
        for mode in ('cash','model','policy','same_db','month','future_day'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                root=Path(folder);config,args=fixture(root)
                if mode=='cash':config['initial_cash']='0'
                elif mode=='model':config['model']='UNSUPPORTED'
                elif mode=='policy':config['pullback']['policy']['minimum_discount']='0'
                elif mode=='same_db':config['pullback']['database_path']=config['database_path']
                elif mode=='month':
                    value=json.loads((root/'month.json').read_bytes());value['original_source_hashes']={}
                    raw_month=json.dumps(value).encode();(root/'month.json').write_bytes(raw_month)
                    config['initial_month']['sha256']=sha256(raw_month).hexdigest()
                else:
                    value=json.loads((root/'schedule.json').read_bytes());value['sessions']=value['sessions'][:1]
                    raw_schedule=json.dumps(value).encode();(root/'schedule.json').write_bytes(raw_schedule)
                    config['schedule']['sha256']=sha256(raw_schedule).hexdigest()
                encoded=json.dumps(config).encode();(root/'config.json').write_bytes(encoded);args['config_sha256']=sha256(encoded).hexdigest()
                with self.assertRaises(ValueError):run(**args,execute=True,clock=lambda:NOW,fetch=lambda _:self.fail('must not fetch'))
                self.assertFalse((root/'runtime').exists())

    def test_withdrawn_and_expired_capture_never_create_simulation(self):
        for mode in ('withdrawn','expired'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                root=Path(folder);config,args=fixture(root);current=[NOW];calls=[]
                def stale(ticker):
                    calls.append(ticker);body=fetch(ticker);current[0]+=timedelta(minutes=3);return body
                if mode=='withdrawn':
                    descriptor=json.loads((root/'descriptor.json').read_bytes())
                    records=[dict(SOURCE_WITHDRAWALS[0],input_path=descriptor['input_path'],
                                  input_sha256=descriptor['source_hashes'][descriptor['input_path']])]
                    with patch('scripts.bootstrap_current_quantity_v2_simulation.SOURCE_WITHDRAWALS',records):
                        with self.assertRaisesRegex(ValueError,'RESEARCH_SOURCE_WITHDRAWN'):
                            run(**args,execute=True,clock=lambda:current[0],fetch=stale)
                    self.assertEqual(calls,[])
                else:
                    with self.assertRaisesRegex(ValueError,'BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE'):
                        run(**args,execute=True,clock=lambda:current[0],fetch=stale)
                    self.assertTrue(calls)
                    self.assertTrue(Path(config['audit_directory']).exists())
                self.assertFalse(Path(config['database_path']).exists())

    def test_real_cli_default_is_offline_preflight(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);config,args=fixture(root)
            completed=subprocess.run([sys.executable,'-X','utf8','-E','-B','-m',
                'scripts.bootstrap_current_quantity_v2_simulation','--config',str(args['config_path']),
                '--config-sha256',args['config_sha256']],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['status'],'PREFLIGHT_OK_NOT_STARTED')
            self.assertFalse((root/'runtime').exists())


if __name__=='__main__':unittest.main()
