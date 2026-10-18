"""Only synthetic attempt races; never executes the seven-security account."""
import json
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_two_period_conditional_execution_20260919 as m


class AttemptReviewTests(unittest.TestCase):
    def test_internal_columns_restore_then_independent_accounting_runs(self):
        from test_ndx_frozen_accounting_independent_audit_research import fixture
        args=fixture();raw=copy.deepcopy(args['execution']);columns={s:'SID_'+s for s in 'ABCDE'}
        for decision in raw['decisions']:
            for sid,value in decision['targets'].items():value['ticker']=columns[sid]
        for trade in raw['trades']:trade['ticker']=columns[trade['security_id']]
        for row in raw['daily']:row['tickers']={sid:columns[sid] for sid in row['shares']}
        prepared=dict(arguments={'risk_chains_by_decision':args['risk_chains_by_decision']},
            labels={sid:{'ticker':sid} for sid in columns},columns=columns,calendar=args['calendar'],
            schedule=args['schedule'],prices=args['prices'],contract=args['contract'])
        with patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value=copy.deepcopy(raw)) as engine:
            execution,review=m.execute_prepared(prepared)
            self.assertEqual(engine.call_count,1)
            self.assertEqual(execution,args['execution'])
            self.assertEqual(review['execution_count'],2)
        raw['daily'][1]['cash_usd']+=1
        with patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value=raw):
            with self.assertRaises(ValueError):m.execute_prepared(prepared)

    def test_concurrent_identical_started_marker_does_not_authorize_second_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/'result.json';identity=root/'identity.json'
            prepared=dict(calendar=['date'],schedule=[],contract={},columns={})
            def prepare(*_):
                # A competing process passes the same preflight and publishes first.
                marker=dict(schema='TWO_PERIOD_CONDITIONAL_EXECUTION_ATTEMPT_V1',status='STARTED_NOT_COMPLETED',
                    identity_reference=dict(path=str(identity.resolve()),sha256='a'*64),source_hashes={})
                Path(str(output)+'.started.json').write_bytes((json.dumps(marker,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())
                return prepared,{},[]
            with patch.object(m,'BASE',root),patch.object(m,'prepare',side_effect=prepare),patch.object(m,'verify_gaps'),\
                 patch.object(m.archive,'load_contract'),patch.object(m.archive,'verify_expected_sources',return_value={}),\
                 patch.object(m,'execute_prepared',return_value=({},{})) as execute:
                with self.assertRaises((FileExistsError,ValueError)):
                    m.run(identity_path=identity,identity_sha256='a'*64,output=output,execute=True)
                self.assertEqual(execute.call_count,0)

    def test_preflight_and_interrupt_do_not_allow_implicit_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/'result.json';identity=root/'identity.json'
            with patch.object(m,'BASE',root),patch.object(m,'prepare',return_value=({}, {}, [])),patch.object(m,'verify_gaps'),\
                 patch.object(m.archive,'load_contract'),patch.object(m.archive,'verify_expected_sources',return_value={}),\
                 patch.object(m,'execute_prepared',side_effect=KeyboardInterrupt) as execute:
                result=m.run(identity_path=identity,identity_sha256='a'*64,output=output)
                self.assertFalse(result['execution_performed']);self.assertEqual(execute.call_count,0)
                with self.assertRaises(KeyboardInterrupt):m.run(identity_path=identity,identity_sha256='a'*64,output=output,execute=True)
                self.assertTrue(Path(str(output)+'.started.json').exists())
                self.assertFalse(output.exists())
                with self.assertRaises(FileExistsError):m.run(identity_path=identity,identity_sha256='a'*64,output=output,execute=True)
                self.assertEqual(execute.call_count,1)


if __name__=='__main__':unittest.main()
