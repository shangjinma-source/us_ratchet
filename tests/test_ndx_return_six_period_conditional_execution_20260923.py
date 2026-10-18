"""No real engine or full preflight: input assembly and durable mock attempts."""
from copy import deepcopy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'scripts/ndx_return_six_period_conditional_execution_20260923.py'
spec=importlib.util.spec_from_file_location('return_six',SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def documents():
    # Read already-sealed fixture documents; no prepare/source closure/engine work.
    return [json.loads((m.BASE/m.BOUND[k][0]).read_bytes()) for k in ('schedule','price','identity')]


def state():
    prepared=m.assemble(*documents())
    return dict(prepared=prepared,sources={},archive_contract={},resolution={},runtime={})


class RunnerTests(unittest.TestCase):
    def test_eight_columns_decimal_and_single_normalization(self):
        p=m.assemble(*documents())
        self.assertEqual(len(p['columns']),8)
        goog=[sid for sid,row in p['labels'].items() if row['ticker']=='GOOG'][0]
        googl=[sid for sid,row in p['labels'].items() if row['ticker']=='GOOGL'][0]
        self.assertNotEqual(p['columns'][goog],p['columns'][googl])
        self.assertEqual(p['labels'][goog]['issuer_id'],p['labels'][googl]['issuer_id'])
        self.assertIn(goog,p['schedule'][-2]['targets']);self.assertNotIn(goog,p['schedule'][-1]['targets'])
        self.assertIn(googl,p['schedule'][-1]['targets'])
        self.assertIsInstance(p['prices'][p['calendar'][0]][goog]['open'],Decimal)
        self.assertEqual(p['arguments']['opens'].dtypes.unique().tolist(),[float])
        self.assertEqual(p['price_conversion_evidence']['cell_count'],1712)
        self.assertTrue(all(r['normalization_count']==1 for r in p['normalization_evidence']['periods']))

    def test_input_denominator_and_identity_fail_closed(self):
        for attack in ('clock','union','class','price'):
            t,p,i=documents()
            if attack=='clock':t['schedule'].pop()
            if attack=='union':i['rows'].pop()
            if attack=='class':i['rows'][0]['issuer_id']='other'
            if attack=='price':p['matrices']['open'][p['calendar'][0]]['AMAT']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(t,p,i)

    def test_frozen_source_constants_match(self):
        for name,sha in m.FROZEN.items():self.assertEqual(m.LOADED[str(m.ROOT/'backtest'/name)],sha)

    def test_engine_exception_persisted_and_no_second_attempt(self):
        s=state()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'prepare',return_value=s),patch.object(m,'check'),patch.object(m.engine,'simulate_dynamic_frozen_execution_research',side_effect=RuntimeError('synthetic')) as call:
            output=Path(tmp)/'attempt'
            with patch.object(m,'OUTPUT',output),self.assertRaises(RuntimeError):m.run(output,True)
            self.assertEqual({p.name for p in output.iterdir()},{'started.json','failure.json'})
            failure=json.loads((output/'failure.json').read_bytes())
            self.assertFalse(failure['numerical_failure_is_economic_infeasibility'])
            with patch.object(m,'OUTPUT',output),self.assertRaises(ValueError):m.run(output,True)
            self.assertEqual(call.call_count,1)

    def test_raw_saved_before_audit_failure_and_restore_without_engine(self):
        s=state()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'prepare',return_value=s),patch.object(m,'check'),patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={'sentinel':'ledger'}) as call:
            output=Path(tmp)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'restore_and_audit',side_effect=ValueError('audit')),self.assertRaises(ValueError):m.run(output,True)
            started=m.hashlib.sha256((output/'started.json').read_bytes()).hexdigest()
            raw=m.hashlib.sha256((output/'raw_execution.json').read_bytes()).hexdigest()
            with patch.object(m,'OUTPUT',output),patch.object(m,'restore_and_audit',return_value=({'restored':True},{'passed':True})):
                ref=m.recover(output,started,raw)
            self.assertEqual(call.call_count,1)
            self.assertTrue(Path(ref['path']).is_file())


if __name__=='__main__':unittest.main()
