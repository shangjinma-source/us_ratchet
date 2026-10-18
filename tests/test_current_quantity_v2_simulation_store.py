from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
import json
import sqlite3
import subprocess
import sys
import unittest

from backtest.current_quantity_v2_simulation_store import SimulationStore, revision
from test_current_quantity_v2_simulated_settlement import fixture, run
from test_current_quantity_v2_monthly_simulation import setup as monthly_setup
from backtest.current_quantity_v2_monthly_simulation import observe_monthly, apply_monthly, monthly_operation_request, digest
from backtest.current_quantity_v2_simulated_settlement import accept_orders
from data.current_quantity_v2_current_cash_plan import canonical


class SimulationStoreTests(unittest.TestCase):
    def test_external_monthly_result_before_prepared_restarts_and_rejects_rebinding(self):
        with TemporaryDirectory() as folder:
            arguments,calls,_=monthly_setup(folder)
            original=arguments.pop('simulation')
            store=SimulationStore(Path(folder)/'external.sqlite3'); initial=store.create(original)
            request=monthly_operation_request(simulation_id=original['simulation_id'],**{k:arguments[k] for k in
                ('root','storage_directory','configuration_path','configuration_sha256','schedule_path','session','triggered_at')})
            operation=dict(simulation_id=original['simulation_id'],expected_revision=initial['revision'],operation_id='external-monthly',request=request)
            with patch.object(store,'_prepare_result',side_effect=KeyboardInterrupt('after external result, before PREPARED')):
                with self.assertRaises(KeyboardInterrupt):
                    apply_monthly(store=store,**{k:v for k,v in operation.items() if k!='request'},**arguments)
            self.assertEqual(calls,['AAA','BBB'])
            directory=Path(arguments['storage_directory'])/digest([original['simulation_id'],arguments['session']])
            attempt_path=directory/'attempt.json'; result_path=directory/'result.json'
            attempt_bytes=attempt_path.read_bytes(); result_bytes=result_path.read_bytes()
            for mode in ('request','base','result','valid_other_acceptance','valid_later_acceptance'):
                attempt=json.loads(attempt_bytes); saved=json.loads(result_bytes)
                if mode=='request':attempt['request']['configuration_sha256']='0'*64
                elif mode=='base':attempt['simulation_sha256']='0'*64
                elif mode=='result':saved['result']['proposal_id']='0'*64
                else:
                    accepted=saved['result']['simulation']['batches'][-1]['request']
                    accepted_at=accepted['accepted_at']
                    if mode=='valid_later_acceptance':
                        accepted_at=(datetime.fromisoformat(accepted_at)+timedelta(seconds=1)).isoformat()
                        saved['result']['accepted_at']=accepted_at
                    saved['result']['simulation']=accept_orders(simulation=original,proposal=accepted['proposal'],
                        acceptance_id=accepted['acceptance_id'] if mode=='valid_later_acceptance' else 'another-valid-operation',
                        accepted_at=accepted_at,kind='MONTHLY_RETARGET')
                saved['sha256']=digest(saved['result'])
                attempt_path.write_bytes(canonical(attempt));result_path.write_bytes(canonical(saved))
                with patch('subprocess.run',side_effect=AssertionError('recovery searched')):
                    with self.assertRaises(ValueError,msg=mode):SimulationStore(store.path).recover_monthly(**operation)
                self.assertEqual(store.read(original['simulation_id'])['revision'],initial['revision'])
                attempt_path.write_bytes(attempt_bytes);result_path.write_bytes(result_bytes)
            operation_path=Path(folder)/'operation.json';operation_path.write_bytes(canonical(operation))
            command=[sys.executable,'-X','utf8','-E','-B','-c',
                'import sys,json;from unittest.mock import patch;from backtest.current_quantity_v2_simulation_store import SimulationStore; p=patch("subprocess.run",side_effect=AssertionError("no research"));p.start();print(json.dumps(SimulationStore(sys.argv[1]).recover_monthly(**json.load(open(sys.argv[2])))))',
                str(store.path),str(operation_path)]
            restored=json.loads(subprocess.run(command,check=True,capture_output=True,text=True,timeout=30).stdout)
            self.assertEqual(restored['simulation'],json.loads(result_bytes)['result']['simulation'])
            self.assertTrue(restored['recovered'])
            with closing(sqlite3.connect(store.path)) as con:
                evidence=json.loads(con.execute('SELECT recovery_evidence FROM isolated_simulation_operations').fetchone()[0])
            self.assertEqual(evidence['base_revision'],initial['revision'])
            self.assertEqual(evidence['result_file_sha256'],__import__('hashlib').sha256(result_bytes).hexdigest())
            self.assertEqual(calls,['AAA','BBB'])

    def test_real_monthly_prepared_result_survives_restart_without_research(self):
        with TemporaryDirectory() as folder:
            arguments,calls,_=monthly_setup(folder)
            store=SimulationStore(Path(folder)/'monthly-simulation.sqlite3')
            initial=store.create(arguments['simulation'])
            request={k:arguments[k] for k in ('configuration_path','configuration_sha256','schedule_path','session','triggered_at')}
            request['kind']='MONTHLY_OBSERVATION'
            operation=dict(simulation_id=arguments['simulation']['simulation_id'],
                expected_revision=initial['revision'],operation_id='monthly',request=request)
            def transform(state):
                return observe_monthly(**dict(arguments,simulation=state))['simulation']
            with patch.object(store,'_commit',side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):store.apply(**operation,transform=transform)
            self.assertEqual(calls,['AAA','BBB'])
            reopened=SimulationStore(store.path)
            with patch('subprocess.run',side_effect=AssertionError('recovery researched')):
                result=reopened.recover(**operation)
                repeated=reopened.apply(**operation,transform=lambda _:self.fail('recovery recaptured'))
            self.assertEqual(result['simulation'],repeated['simulation'])
            self.assertEqual(set(result['simulation']['chain']['ledger']['target_quantities']),{'B'})
            self.assertEqual(calls,['AAA','BBB'])

    def setup_store(self, folder):
        simulation,evidence,_=fixture()
        store=SimulationStore(Path(folder)/'isolated.sqlite3')
        initial=store.create(simulation)
        request=dict(kind='SETTLE',evidence=evidence,at='2026-10-15T12:02:00-04:00')
        arguments=dict(simulation_id=simulation['simulation_id'], expected_revision=initial['revision'],
                       operation_id='first', request=request)
        return store,simulation,evidence,arguments

    def test_true_settlement_restart_cas_completed_retry_and_request_binding(self):
        with TemporaryDirectory() as folder:
            store,state,evidence,args=self.setup_store(folder)
            after=store.apply(**args,transform=lambda s:run(s,evidence))
            self.assertNotEqual(after['revision'],args['expected_revision'])
            self.assertEqual(after['simulation']['chain']['ledger']['cash'],'5001/50')
            command=[sys.executable,'-X','utf8','-E','-B','-c',
                'import sys,json;from backtest.current_quantity_v2_simulation_store import SimulationStore;print(json.dumps(SimulationStore(sys.argv[1]).read(sys.argv[2])))',
                str(store.path),state['simulation_id']]
            restarted=json.loads(subprocess.run(command,check=True,capture_output=True,text=True,timeout=20).stdout)
            self.assertEqual(restarted,dict(revision=after['revision'],simulation=after['simulation']))
            retry=SimulationStore(store.path).apply(**args,transform=lambda _:self.fail('completed retry computed'))
            self.assertTrue(retry['replayed'])
            self.assertEqual(retry['operation_result_revision'],after['revision'])
            with self.assertRaisesRegex(ValueError,'OPERATION_CONFLICT'):
                store.apply(**dict(args,request={'kind':'DIFFERENT'}),transform=lambda _:self.fail())
            with self.assertRaisesRegex(ValueError,'STALE_SIMULATION_REVISION'):
                store.apply(**dict(args,operation_id='other'),transform=lambda _:self.fail())
            self.assertEqual(store.read(state['simulation_id']),restarted)

    def test_prepared_crash_recovery_atomic_and_started_unknown_no_retry(self):
        with TemporaryDirectory() as folder:
            store,state,evidence,args=self.setup_store(folder)
            with patch.object(store,'_commit',side_effect=RuntimeError('simulated process interruption')):
                with self.assertRaises(RuntimeError): store.apply(**args,transform=lambda s:run(s,evidence))
            self.assertEqual(store.read(state['simulation_id'])['simulation'],state)
            reopened=SimulationStore(store.path)
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_AUTOMATIC_RETRY'):
                reopened.apply(**args,transform=lambda _:self.fail('must not repeat'))
            recovered=reopened.recover(**args)
            self.assertTrue(recovered['recovered'])
            self.assertEqual(recovered['simulation'],run(state,evidence))
            self.assertTrue(reopened.recover(**args)['replayed'])
        with TemporaryDirectory() as folder:
            store,state,_,args=self.setup_store(folder)
            def crashed(_): raise KeyboardInterrupt('process dies after STARTED')
            with self.assertRaises(KeyboardInterrupt): store.apply(**args,transform=crashed)
            reopened=SimulationStore(store.path)
            with self.assertRaisesRegex(ValueError,'PREPARED_RESULT_UNAVAILABLE'): reopened.recover(**args)
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_AUTOMATIC_RETRY'):
                reopened.apply(**args,transform=lambda _:self.fail())
            self.assertEqual(reopened.read(state['simulation_id'])['simulation'],state)

    def test_two_workers_one_callback_and_atomic_commit_rollback(self):
        with TemporaryDirectory() as folder:
            store,state,evidence,args=self.setup_store(folder)
            entered=Event();release=Event()
            def slow(s): entered.set();self.assertTrue(release.wait(5));return run(s,evidence)
            with ThreadPoolExecutor(2) as pool:
                future=pool.submit(store.apply,**args,transform=slow)
                self.assertTrue(entered.wait(5))
                other=SimulationStore(store.path)
                with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_AUTOMATIC_RETRY'):
                    other.apply(**args,transform=lambda _:self.fail('same operation competed'))
                with self.assertRaisesRegex(ValueError,'OPERATION_PENDING'):
                    other.apply(**dict(args,operation_id='competing'),transform=lambda _:self.fail())
                release.set(); future.result()
        with TemporaryDirectory() as folder:
            store,state,evidence,args=self.setup_store(folder)
            with closing(sqlite3.connect(store.path)) as con, con:
                con.execute("CREATE TRIGGER stop_complete BEFORE UPDATE ON isolated_simulation_operations WHEN NEW.status='COMPLETE' BEGIN SELECT RAISE(ABORT,'interrupt commit'); END")
            with self.assertRaises(sqlite3.IntegrityError): store.apply(**args,transform=lambda s:run(s,evidence))
            self.assertEqual(store.read(state['simulation_id'])['simulation'],state)
            with closing(sqlite3.connect(store.path)) as con, con:
                self.assertEqual(con.execute('SELECT status FROM isolated_simulation_operations').fetchone()[0],'PREPARED')
                con.execute('DROP TRIGGER stop_complete')
            self.assertTrue(SimulationStore(store.path).recover(**args)['recovered'])

    def test_unknown_observation_revision_history_and_foreign_database(self):
        with TemporaryDirectory() as folder:
            store,state,evidence,args=self.setup_store(folder)
            unknown=deepcopy(evidence)
            for item in unknown.values(): item['minutes']=[]
            after=store.apply(**dict(args,request={'kind':'UNKNOWN','evidence':unknown}),transform=lambda s:run(s,unknown))
            self.assertEqual(after['simulation']['chain']['ledger']['revision'],state['chain']['ledger']['revision'])
            self.assertNotEqual(after['revision'],args['expected_revision'])
            second=dict(args,expected_revision=after['revision'],operation_id='second')
            completed=store.apply(**second,transform=lambda s:run(s,evidence,'2026-10-15T12:03:00-04:00'))
            oldretry=store.apply(**dict(args,request={'kind':'UNKNOWN','evidence':unknown}),transform=lambda _:self.fail())
            self.assertEqual(oldretry['revision'],completed['revision'])
            self.assertEqual(oldretry['operation_result_revision'],after['revision'])
            nextargs=dict(args,expected_revision=completed['revision'],operation_id='rewrite')
            with self.assertRaisesRegex(ValueError,'HISTORY_REWRITE'):
                store.apply(**nextargs,transform=lambda _:state)
        with TemporaryDirectory() as folder:
            missing=SimulationStore(Path(folder)/'missing.sqlite3')
            with self.assertRaisesRegex(ValueError,'DATABASE_NOT_FOUND'): missing.read('x')
            self.assertFalse(missing.path.exists())
            path=Path(folder)/'paper.sqlite3'
            with closing(sqlite3.connect(path)) as con, con: con.execute('CREATE TABLE v2_accounts(id TEXT)')
            with self.assertRaisesRegex(ValueError,'WRONG_SIMULATION_DATABASE'): SimulationStore(path).create(fixture()[0])


if __name__=='__main__':unittest.main()
