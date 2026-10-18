import json
import unittest
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
import io
import sqlite3
from contextlib import redirect_stdout,closing

import test_current_quantity_v2_daily_evidence_providers as provider_fixture
import test_current_quantity_v2_current_cash_plan as cash_fixture
from backtest.current_quantity_v2_simulation_store import SimulationStore
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS
from scripts.run_current_quantity_v2_simulation import preflight,run_runtime,_fees,main


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cash_fixture.CurrentCashTests.setUpClass()
    @classmethod
    def tearDownClass(cls):cash_fixture.CurrentCashTests.tearDownClass()

    def setup(self,folder):
        args,bundle,minutes,quotes,actions=provider_fixture.DailyProviderTests.bundle(self,folder)
        state=args['store'].read(args['simulation_id'])['simulation'];root=bundle.root
        fees=dict(schema='EXPLICIT_SIMULATION_ORDER_FEES_V1',order_fees={oid:'0' for oid in state['chain']['ledger']['orders']})
        (root/'runtime-fees.json').write_text(json.dumps(fees))
        for record in SOURCE_WITHDRAWALS:
            for name,h in record['evidence'].items():
                raw=(Path(__file__).resolve().parents[1]/name).read_bytes();self.assertEqual(sha256(raw).hexdigest(),h)
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        config=dict(schema='ISOLATED_V2_DAILY_RUNTIME_V1',root=str(root),database_path=str(args['store'].path),
            simulation_id=args['simulation_id'],schedule_path=bundle.schedule_path,schedule_sha256=bundle.schedule_sha256,
            runtime_directory=str(Path(folder)/'runtime'),fees_path='runtime-fees.json',
            fees_sha256=sha256((root/'runtime-fees.json').read_bytes()).hexdigest(),capture_audit_roots=[],
            monthly_blob_root=None,monthly=None,pullback=None)
        path=Path(folder)/'runtime.json';path.write_text(json.dumps(config));digest=sha256(path.read_bytes()).hexdigest()
        transport=dict(minutes=bundle.minute_fetch,quotes=args['continuation_arguments'](state,args['session'])['fetch'],
            actions=bundle.late_review.sources.fetch,rss=bundle.late_review.sources.rss_fetch)
        return dict(config_path=path,config_sha256=digest,session=args['session'],triggered_at=args['triggered_at']),args,transport,(minutes,quotes,actions)

    def test_preflight_cli_offline_no_writes_and_real_execute(self):
        with TemporaryDirectory() as folder:
            request,args,transport,calls=self.setup(folder)
            before={str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()}
            with patch('urllib.request.urlopen',side_effect=AssertionError('preflight network')):
                checked=run_runtime(**request)
            self.assertEqual(checked['status'],'PREFLIGHT_OK')
            self.assertEqual(before,{str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()})
            self.assertEqual(calls,([],[],[]))
            result=subprocess.run(['D:/python/python.exe','-X','utf8','-E','-B','scripts/run_current_quantity_v2_simulation.py',
                '--config',str(request['config_path']),'--config-sha256',request['config_sha256'],
                '--session',request['session'],'--triggered-at',request['triggered_at']],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            self.assertEqual(json.loads(result.stdout)['status'],'PREFLIGHT_OK')
            result=run_runtime(**request,execute=True,clock=args['clock'],transports=transport)
            self.assertEqual(result['daily_status'],'CONTINUATION_COMPLETE')
            self.assertEqual(result['simulation']['valuation']['records'][0]['status'],'COMPLETE')
            self.assertEqual(tuple(map(len,calls)),(2,2,2))

    def test_late_runtime_only_catches_up_and_missing_fees_reject(self):
        with TemporaryDirectory() as folder:
            request,args,transport,calls=self.setup(folder)
            # All transports and outer runtime use the same actual late clock.
            late=lambda:datetime.fromisoformat('2026-10-16T10:01:00-04:00')
            result=run_runtime(**request,execute=True,clock=late,transports=transport)
            self.assertEqual(result['daily_status'],'LATE_NO_NEW_DECISION');self.assertEqual(calls[1],[])
        with TemporaryDirectory() as folder:
            request,args,transport,calls=self.setup(folder)
            config=json.loads(request['config_path'].read_bytes());path=Path(config['root'])/config['fees_path']
            path.write_text(json.dumps(dict(schema='EXPLICIT_SIMULATION_ORDER_FEES_V1',order_fees={})))
            config['fees_sha256']=sha256(path.read_bytes()).hexdigest();request['config_path'].write_text(json.dumps(config))
            request['config_sha256']=sha256(request['config_path'].read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'EXPLICIT_ORDER_FEES_MISSING'):run_runtime(**request)
            self.assertEqual(calls,([],[],[]))

    def test_missing_new_month_configuration_allows_history_only_without_new_orders(self):
        with TemporaryDirectory() as folder:
            request,args,transport,calls=self.setup(folder)
            state=args['store'].read(args['simulation_id'])['simulation']
            calendar=state['valuation']['registration']['calendar'];calendar['session_dates'].append('2026-11-02')
            calendar['closes']['2026-11-02']='2026-11-02T16:00:00-05:00'
            store=SimulationStore(Path(folder)/'new-month.db');store.create(state)
            config=json.loads(request['config_path'].read_bytes());config['database_path']=str(store.path)
            schedule=Path(config['root'])/config['schedule_path'];value=json.loads(schedule.read_bytes())
            value['sessions'].append(dict(date='2026-11-02',open_at='2026-11-02T09:30:00-05:00',close_at='2026-11-02T16:00:00-05:00'))
            schedule.write_text(json.dumps(value));config['schedule_sha256']=sha256(schedule.read_bytes()).hexdigest()
            request['config_path'].write_text(json.dumps(config));request['config_sha256']=sha256(request['config_path'].read_bytes()).hexdigest()
            request.update(session='2026-11-02',triggered_at='2026-11-02T10:00:00-05:00')
            before={str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()}
            checked=run_runtime(**request)
            self.assertEqual(checked['status'],'PREFLIGHT_OK_HISTORY_ONLY')
            self.assertFalse(checked['new_decisions_allowed'])
            self.assertEqual(checked['decision_block_reason'],'MONTHLY_CONFIGURATION_REQUIRED')
            self.assertEqual(before,{str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()})
            self.assertEqual(calls,([],[],[]))
            original_fetch=transport['minutes']
            def no_fill(url):
                value=json.loads(original_fetch(url));q=value['chart']['result'][0]['indicators']['quote'][0]
                for key in ('open','high','low','close'):q[key]=[1000000]*len(q[key])
                return json.dumps(value).encode()
            transport['minutes']=no_fill
            old_cash=store.read(args['simulation_id'])['simulation']['chain']['ledger']['cash']
            old_orders=set(store.read(args['simulation_id'])['simulation']['chain']['ledger']['orders'])
            with self.assertRaisesRegex(ValueError,'MONTHLY_CONFIGURATION_REQUIRED'):
                run_runtime(**request,execute=True,clock=lambda:datetime.fromisoformat('2026-11-02T10:00:00-05:00'),transports=transport)
            saved=store.read(args['simulation_id'])['simulation']
            self.assertEqual(saved['chain']['ledger']['cash'],old_cash)
            self.assertEqual(set(saved['chain']['ledger']['orders']),old_orders)
            self.assertTrue(all(o['closed']=='EXPIRED' for o in saved['chain']['ledger']['orders'].values()))
            self.assertEqual(len(saved['valuation']['records']),2)
            self.assertTrue(all(row['status']=='COMPLETE' for row in saved['valuation']['records']))
            self.assertEqual(calls[1],[])
            calls_before=tuple(map(len,calls))
            for schema,key in [('QUANTITY_V2_MONTHLY_SERVER_INPUTS_V2','market_entries'),('QUANTITY_V2_MONTHLY_SERVER_INPUTS_V1','training_entries')]:
                monthly=Path(config['root'])/'runtime-monthly.json'
                monthly.write_text(json.dumps(dict(schema=schema,account_reviews=[],**{key:[]})))
                config['monthly']=dict(path=monthly.name,sha256=sha256(monthly.read_bytes()).hexdigest(),review_mode='DERIVED_PAPER_BOUNDED')
                request['config_path'].write_text(json.dumps(config));request['config_sha256']=sha256(request['config_path'].read_bytes()).hexdigest()
                with self.assertRaises(ValueError):run_runtime(**request)
            self.assertEqual(tuple(map(len,calls)),calls_before)

    def test_explicit_modelled_cost_rule_and_cli_blocked_exit(self):
        with TemporaryDirectory() as folder:
            request,args,transport,calls=self.setup(folder)
            config=json.loads(request['config_path'].read_bytes());root=Path(config['root']);path=root/config['fees_path']
            path.write_text(json.dumps(dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1',status='MODELLED_FEES_NOT_BROKER_FEES',
                fixed_per_order='0.25',notional_rate='0.001')))
            config['fees_sha256']=sha256(path.read_bytes()).hexdigest()
            state=args['store'].read(args['simulation_id'])['simulation'];fees=_fees(config,root,state)
            from fractions import Fraction
            for oid,order in state['chain']['ledger']['orders'].items():
                self.assertEqual(Fraction(fees[oid]),Fraction(1,4)+Fraction(1,1000)*order['quantity']*Fraction(order['limit_price']))
            # Explicit modeled zero remains a named assumption, not inferred commission.
            value=json.loads(path.read_bytes());value.update(fixed_per_order='0',notional_rate='0');path.write_text(json.dumps(value))
            config['fees_sha256']=sha256(path.read_bytes()).hexdigest();request['config_path'].write_text(json.dumps(config))
            request['config_sha256']=sha256(request['config_path'].read_bytes()).hexdigest()
            result=run_runtime(**request,execute=True,clock=args['clock'],transports=transport)
            self.assertEqual(result['daily_status'],'CONTINUATION_COMPLETE')
        with patch('scripts.run_current_quantity_v2_simulation.run_runtime',return_value=dict(daily_status='BLOCKED_UNRESOLVED_ORDERS')):
            output=io.StringIO()
            with redirect_stdout(output):code=main(['--config','unused','--config-sha256','unused','--session','2026-10-16','--triggered-at','unused','--execute'])
            value=json.loads(output.getvalue());self.assertEqual(code,2);self.assertEqual(value['status'],'BLOCKED')
            self.assertLessEqual(value['started_at'],value['finished_at'])

    def test_cap_database_alias_foreign_schema_and_policy_rejected_without_writes(self):
        from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY
        for mode in ('same','foreign','policy'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                request,args,transport,calls=self.setup(folder)
                config=json.loads(request['config_path'].read_bytes());cap=Path(folder)/'cap.db'
                if mode=='same':cap=args['store'].path
                if mode=='foreign':
                    with closing(sqlite3.connect(cap)) as connection:
                        connection.execute('CREATE TABLE real_account (id TEXT)');connection.commit()
                config['pullback']=dict(database_path=str(cap),policy={} if mode=='policy' else EXPERIMENTAL_POLICY)
                request['config_path'].write_text(json.dumps(config));request['config_sha256']=sha256(request['config_path'].read_bytes()).hexdigest()
                before={str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):run_runtime(**request)
                self.assertEqual(calls,([],[],[]))
                self.assertEqual(before,{str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()})

    def test_accepted_continuation_archive_is_found_next_day_without_config_edit(self):
        with TemporaryDirectory() as folder:
            request,args,transport,calls=self.setup(folder)
            config=json.loads(request['config_path'].read_bytes());root=Path(config['root'])
            state=args['store'].read(args['simulation_id'])['simulation']
            calendar=state['valuation']['registration']['calendar'];calendar['session_dates'].append('2026-10-19')
            calendar['closes']['2026-10-19']='2026-10-19T16:00:00-04:00'
            store=SimulationStore(Path(folder)/'continuing.db');store.create(state);config['database_path']=str(store.path)
            schedule=root/config['schedule_path'];rows=json.loads(schedule.read_bytes())
            rows['sessions'].append(dict(date='2026-10-19',open_at='2026-10-19T09:30:00-04:00',close_at='2026-10-19T16:00:00-04:00'))
            schedule.write_text(json.dumps(rows));config['schedule_sha256']=sha256(schedule.read_bytes()).hexdigest()
            fee=root/config['fees_path'];fee.write_text(json.dumps(dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1',
                status='MODELLED_FEES_NOT_BROKER_FEES',fixed_per_order='0',notional_rate='0')))
            config['fees_sha256']=sha256(fee.read_bytes()).hexdigest()
            request['config_path'].write_text(json.dumps(config));request['config_sha256']=sha256(request['config_path'].read_bytes()).hexdigest()
            original_fetch=transport['minutes']
            def no_fill(url):
                value=json.loads(original_fetch(url));q=value['chart']['result'][0]['indicators']['quote'][0]
                for key in ('open','high','low','close'):q[key]=[1000000]*len(q[key])
                return json.dumps(value).encode()
            transport['minutes']=no_fill
            original_commit=SimulationStore._commit
            def interrupted_commit(instance,**parameters):
                if parameters['request']['kind']=='SAME_MONTH_CONTINUATION_V1':raise RuntimeError('synthetic PREPARED interruption')
                return original_commit(instance,**parameters)
            with patch.object(SimulationStore,'_commit',new=interrupted_commit):
                with self.assertRaisesRegex(RuntimeError,'PREPARED interruption'):
                    run_runtime(**request,execute=True,clock=args['clock'],transports=transport)
            before_recovery=preflight(config_path=request['config_path'],config_sha256=request['config_sha256'],session=request['session'])
            result=run_runtime(**request,execute=True,clock=args['clock'],transports=transport)
            self.assertEqual(result['daily_status'],'ALREADY_COMPLETED')
            self.assertTrue(any(not order['closed'] for order in result['simulation']['chain']['ledger']['orders'].values()))
            from backtest.current_quantity_v2_simulated_settlement import _references
            for reference in _references(result['simulation']['chain']).values():
                self.assertTrue(before_recovery['origins'](result['simulation'],reference))
            before=tuple(map(len,calls))
            checked=preflight(config_path=request['config_path'],config_sha256=request['config_sha256'],session='2026-10-19')
            self.assertEqual(checked['summary']['status'],'PREFLIGHT_OK');self.assertEqual(tuple(map(len,calls)),before)
            self.assertEqual(config['capture_audit_roots'],[])

    def test_completed_monthly_operation_resolves_its_exact_capture_root(self):
        from test_current_quantity_v2_monthly_simulation import setup
        from backtest.current_quantity_v2_monthly_simulation import apply_monthly
        from scripts.run_current_quantity_v2_simulation import _accepted_archive_roots
        from data.current_quantity_v2_simulation_origin_files import SimulationOriginFilesReader
        from backtest.current_quantity_v2_simulated_settlement import _references
        with TemporaryDirectory() as folder:
            args,_,_=setup(folder);simulation=args.pop('simulation');store=SimulationStore(Path(folder)/'monthly.db')
            current=store.create(simulation)
            result=apply_monthly(store=store,simulation_id=simulation['simulation_id'],expected_revision=current['revision'],
                operation_id=simulation['simulation_id']+':daily-monthly:'+args['session'],**args)
            roots,blobs=_accepted_archive_roots(store,result['simulation'])
            self.assertEqual(len(roots),1);self.assertEqual(blobs,roots[0]/'blobs');self.assertTrue(blobs.is_dir())
            reader=SimulationOriginFilesReader(capture_audit_roots=roots)
            for reference in _references(result['simulation']['chain']).values():self.assertTrue(reader(result['simulation'],reference))


if __name__=='__main__':unittest.main()
