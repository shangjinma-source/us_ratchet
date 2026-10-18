import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_two_period_conditional_execution_v2_20260919 as m
from test_ndx_frozen_accounting_independent_audit_research import fixture


def prepared_fixture():
    args=fixture();original=copy.deepcopy(args['schedule'])
    for row in original:
        for value in row['targets'].values():value['target_weight']=.25000000000000006
    normalized,evidence=m.normalization.normalized_schedule(original)
    columns={sid:sid for sid in 'ABCDE'}
    prepared=dict(calendar=args['calendar'],schedule=original,contract=args['contract'],columns=columns,
        labels={sid:{'ticker':sid} for sid in columns},prices=args['prices'],
        arguments={'schedule':copy.deepcopy(original),'risk_chains_by_decision':args['risk_chains_by_decision']})
    return prepared,normalized,evidence,args['execution']


class Tests(unittest.TestCase):
    def test_only_original_inputs_feed_engine_and_raw_precedes_audit(self):
        prepared,normalized,evidence,raw=prepared_fixture()
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);output=base/'two_period_conditional_execution_20260919_v2/account.json'
            with patch.object(m,'BASE',base),patch.object(m,'prepare',return_value=(prepared,normalized,evidence,{},[])),\
                 patch.object(m.prior,'verify_gaps'),patch.object(m.prior.archive,'load_contract'),\
                 patch.object(m.prior.archive,'verify_expected_sources',return_value={}),\
                 patch.object(m.prior.engine,'simulate_dynamic_frozen_execution_research',return_value=raw) as engine:
                saved=m.run(output=output,execute=True)
                self.assertEqual(engine.call_count,1)
                self.assertEqual(engine.call_args.kwargs['schedule'],prepared['schedule'])
                self.assertNotEqual(prepared['schedule'],normalized)
                result=json.loads(output.read_bytes());receipt=json.loads(Path(saved['raw_execution_reference']['path']).read_bytes())
                self.assertEqual(receipt['execution'],raw)
                self.assertEqual(result['normalized_schedule'],normalized)
                self.assertEqual(result['schedule'],prepared['schedule'])
                self.assertEqual(result['independent_decimal_accounting']['execution_count'],2)
                with self.assertRaises(FileExistsError):m.run(output=output,execute=True)

    def test_audit_failure_preserves_raw_and_prohibits_retry(self):
        prepared,normalized,evidence,raw=prepared_fixture()
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);output=base/'two_period_conditional_execution_20260919_v2/account.json'
            def reject(raw_result,*_):
                self.assertTrue(Path(str(output)+'.raw_execution.json').exists())
                raise ValueError('Synthetic downstream audit failure')
            with patch.object(m,'BASE',base),patch.object(m,'prepare',return_value=(prepared,normalized,evidence,{},[])),\
                 patch.object(m.prior,'verify_gaps'),patch.object(m.prior.archive,'load_contract'),\
                 patch.object(m.prior.archive,'verify_expected_sources',return_value={}),\
                 patch.object(m.prior.engine,'simulate_dynamic_frozen_execution_research',return_value=raw) as engine,\
                 patch.object(m,'restore_and_audit',side_effect=reject):
                with self.assertRaises(ValueError):m.run(output=output,execute=True)
                failure=json.loads(Path(str(output)+'.failure.json').read_bytes())
                self.assertIsNotNone(failure['raw_execution_reference'])
                self.assertFalse(output.exists())
                with self.assertRaises(FileExistsError):m.run(output=output,execute=True)
                self.assertEqual(engine.call_count,1)

    def test_preflight_no_engine_and_existing_raw_blocks(self):
        prepared,normalized,evidence,_=prepared_fixture()
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);output=base/'two_period_conditional_execution_20260919_v2/account.json'
            with patch.object(m,'BASE',base),patch.object(m,'prepare',return_value=(prepared,normalized,evidence,{},[])),\
                 patch.object(m.prior,'verify_gaps'),patch.object(m.prior.archive,'load_contract'),\
                 patch.object(m.prior.archive,'verify_expected_sources',return_value={}),\
                 patch.object(m.prior.engine,'simulate_dynamic_frozen_execution_research') as engine:
                self.assertFalse(m.run(output=output)['execution_performed'])
                output.parent.mkdir(parents=True);Path(str(output)+'.raw_execution.json').write_bytes(b'partial')
                with self.assertRaises(FileExistsError):m.run(output=output,execute=True)
                self.assertEqual(engine.call_count,0)


if __name__=='__main__':unittest.main()
