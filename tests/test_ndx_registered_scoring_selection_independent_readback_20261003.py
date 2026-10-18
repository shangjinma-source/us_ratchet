from copy import deepcopy
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_registered_scoring_selection_independent_readback_20261003 as m
from backtest import ndx_registered_scoring_selector_adapter_research as adapter
from backtest import ndx_full_ndx_multidecision_selector_research as selector
from backtest import ndx_full_ndx_selection_inspection_research as inspector
from test_ndx_registered_scoring_selector_adapter_research import fixture as fixture_args
from test_ndx_registered_scoring_selection_20261003 import record_fixture


def fixture():
    args=fixture_args();args['selection_registration_reference']=args['budget_plan']['registration_reference_preserved']
    prepared=adapter.assemble_registered_selector_inputs(**args)
    refs=dict(budget=args['budget_reference'],budget_audit=args['budget_audit_reference'],policy=args['selection_registration_reference'])
    return args,prepared,refs

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.args,cls.prepared,cls.refs=fixture()

    def test_source_projection_then_independent_rank_no_producer_oracle(self):
        out=m.inspect_projected_inputs(self.prepared,self.args['budget_plan'],self.refs,self.args['projections'])
        self.assertEqual((out['logical_task_count'],out['evaluated_task_count']),(36,18));self.assertFalse(out['original_scores_recomputed'])
        result=selector.select_full_ndx_lanes(registration=self.prepared['registration'],records=self.prepared['records'])
        report=inspector.inspect_complete_selection(registration=self.prepared['registration'],records=self.prepared['records'],saved_selection=result)
        self.assertEqual(report['status'],'PASS');self.assertFalse(report['selector_called'])

    def test_resigned_value_source_scope_and_blocked_projection_rejected(self):
        for attack in ('metric','source','eligibility','window','ledger','denominator','authority'):
            p=deepcopy(self.prepared)
            if attack=='metric':p['records'][0]['result']['return_p50']+=.01
            elif attack=='source':p['records'][0]['score_reference']['path']='another'
            elif attack=='eligibility':p['records'][0]['eligibility']['liquidity_passed']=1
            elif attack=='window':p['records'][0]['scoring_windows'][0]['fit_price_predecessor']='2020-01-01'
            elif attack=='ledger':p['logical_task_ledger'][0]['outcome']='SCORED_PENDING_INDEPENDENT_READBACK'
            elif attack=='denominator':p['registration']['coordinates'][0]['budget_coverage']['full_three_spec_task_denominator']-=1
            else:p['source_bytes_authenticated']=0
            p['content_sha256']=m.sha(m.enc({k:v for k,v in p.items() if k!='content_sha256'}))
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_projected_inputs(p,self.args['budget_plan'],self.refs,self.args['projections'])

    def test_future_pins_and_independent_byte_location(self):
        with patch.object(m,'INDEX_SHA',None),patch.object(m.Path,'read_bytes',side_effect=AssertionError('no IO')):
            with self.assertRaisesRegex(ValueError,'anchors pending'):m.readback(execute=True)
        blob,r,e=record_fixture();self.assertEqual(list(m.read_scored_records(BytesIO(blob),r,e))[0][1]['weights'],[0,.25,.75])
        blob=blob.replace(b'not score',b'new wrong')
        with self.assertRaises(ValueError):list(m.read_scored_records(BytesIO(blob),r,e))

    def test_frozen_rank_code_pin_matches_real_bytes(self):
        self.assertEqual(len(m.RANK_INSPECTOR_SHA),64)
        self.assertEqual(m.sha(m.RANK_INSPECTOR.read_bytes()),m.RANK_INSPECTOR_SHA)

    def test_producer_functions_not_executed_or_imported(self):
        import ast
        tree=ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        forbidden={'assemble_registered_selector_inputs','select_full_ndx_lanes','run_batch','load_common','fit_weight_spec'}
        for n in ast.walk(tree):
            if isinstance(n,ast.Call):
                name=n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id if isinstance(n.func,ast.Name) else ''
                self.assertNotIn(name,forbidden)
            if isinstance(n,ast.ImportFrom):self.assertFalse((n.module or '').startswith(('scripts.ndx_registered','backtest.ndx_registered')))

if __name__=='__main__':unittest.main()
