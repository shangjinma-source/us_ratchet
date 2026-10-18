from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_first_period_incumbent_cash_flow_paths_v2_20261003 as w
from test_ndx_first_period_incumbent_cash_flow_paths_20261003 import fixture


class Tests(unittest.TestCase):
    def test_full_nominal_calendar_extends_window_without_changing_path(self):
        from backtest.ndx_incumbent_cash_flow_research import simulate_incumbent_cash_flow
        inputs,nominal,candidates,refs=fixture()
        nominal['original_fixed_schedule']['calendar']=['2023-03-30']+nominal['original_fixed_schedule']['calendar']+['2023-09-05','2023-09-06']
        before=deepcopy(nominal);calls=[]
        def simulate(**kwargs):calls.append(kwargs);return simulate_incumbent_cash_flow(**kwargs)
        result=w.assemble(inputs,nominal,candidates,refs,simulate)
        self.assertEqual(result['schema'],'FIRST_PERIOD_INCUMBENT_TWO_PATHS_EIGHT_SCENARIOS_V2')
        self.assertEqual(len(calls),2);self.assertEqual(len(result['scenario_mappings']),8)
        self.assertEqual([len(x['account']['daily']) for x in result['paths']],[106,106])
        self.assertEqual([len(x['account']['decisions']) for x in result['paths']],[6,6])
        self.assertEqual(calls[0]['initial']['cash_usd'],'25000.0')
        self.assertEqual(result['paths'][0]['account']['decisions'][0]['desired_shares'],result['paths'][1]['account']['decisions'][0]['desired_shares'])
        self.assertEqual(nominal,before)

    def test_required_window_missing_date_is_not_ignored(self):
        inputs,nominal,candidates,refs=fixture();nominal['original_fixed_schedule']['calendar'].pop(2)
        with self.assertRaises(ValueError):w.validate_candidates(inputs,candidates,nominal,refs)

    def test_prior_exact_failure_context_and_no_account_file(self):
        _,nominal,_,_=fixture();nominal['original_fixed_schedule']['calendar'].append('2023-09-05')
        refs={k:dict(path=str(w.ROOT/p),sha256=h) for k,(p,h) in w.PINS.items()}
        sources={str(w.ROOT/w.PRIOR_SOURCE):w.PRIOR_SOURCE_SHA,**{str(w.ROOT/p):h for k,(p,h) in w.PINS.items() if not k.startswith('prior_')}}
        docs=dict(nominal=nominal,prior_started=dict(source_hashes=sources,retry_allowed=False),prior_failure=dict(error='Exact original107 calendar',retry_allowed=False,status='FAILED_DO_NOT_CONSUME'))
        source=(w.ROOT/w.PRIOR_SOURCE).read_bytes()
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'PRIOR_ROOT',Path(tmp)):
            (Path(tmp)/'started.json').write_text('{}');(Path(tmp)/'failure.json').write_text('{}')
            result=w.validate_prior_attempt(docs,refs,source)
            self.assertTrue(result['prior_attempt_pre_dispatch_failure_only'])
            self.assertLess(result['assemble_validation_call_line'],result['first_simulation_loop_line'])
            self.assertFalse(result['prior_runtime_execution_trace_available'])
            for attack in ('message','source','permission'):
                changed=deepcopy(docs)
                if attack=='message':changed['prior_failure']['error']='kernel failed'
                elif attack=='source':changed['prior_started']['source_hashes']={}
                else:changed['prior_failure']['retry_allowed']=0
                with self.subTest(attack=attack),self.assertRaises(ValueError):w.validate_prior_attempt(changed,refs,source)
            (Path(tmp)/'accounts.json').write_text('{}')
            with self.assertRaises(ValueError):w.validate_prior_attempt(docs,refs,source)

    def test_existing_v2_rejects_before_any_read(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(w,'OUTPUT',Path(tmp)),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):w.run(execute=True)
            read.assert_not_called()


if __name__=='__main__':unittest.main()
