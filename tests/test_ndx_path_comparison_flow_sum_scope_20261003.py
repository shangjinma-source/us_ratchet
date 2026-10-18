"""Saved engine cash-flow totals retain the engine's stable summation."""
from copy import deepcopy
import importlib
import math
import unittest
import pandas as pd

from backtest import ndx_multidecision_path_comparison_research as comparison
from backtest.ndx_multidecision_account_inspection_research import inspect_saved_account
from backtest.ndx_multidecision_incumbent_account_inspection_research import inspect_saved_control
from test_ndx_multidecision_path_comparison_research import fixture


class FlowSumScope(unittest.TestCase):
    def test_multiple_independent_same_session_flows_match_real_engine_fsum(self):
        arguments = fixture()
        for role in ('candidate', 'control'):
            track = arguments[role + '_prepared']['rows'][4]['tracks'][0]
            kwargs = track['engine_binding']['keyword_arguments']
            session = kwargs['closes']['index'][2]
            flows = [dict(session=session, amount_usd=value, currency='USD', timing='BEFORE_OPEN', source_reference=dict(path='/synthetic/flow-' + str(index), sha256='b' * 64)) for index, value in enumerate((.1, .2, .3))]
            kwargs['external_flows'] = flows
            if role == 'candidate':
                track['stateful_input']['external_flows'] = deepcopy(flows)
            restored = deepcopy(kwargs)
            for name in ('closes', 'opens'):
                frame = restored[name]
                restored[name] = pd.DataFrame(frame['data'], index=pd.to_datetime(frame['index']), columns=frame['columns'])
            binding = track['engine_binding']
            module = importlib.import_module(binding['source_reference']['path'].replace('/', '.').removesuffix('.py'))
            result = getattr(module, binding['function'])(**restored)
            inspector = inspect_saved_account if role == 'candidate' else inspect_saved_control
            inspection = inspector(prepared_track=track, result=result)
            self.assertEqual(result['daily'][2]['cash_injection_usd'], math.fsum((.1, .2, .3)))
            slot = arguments[role + '_slots'][8]
            slot['result'] = result
            slot['audit_evidence']['inspection'] = inspection
        result = comparison.compare_multidecision_paths(**arguments)
        self.assertIsNotNone(result['rows'][8]['candidate']['metrics'])
        self.assertIsNotNone(result['rows'][8]['control']['metrics'])


if __name__ == '__main__':
    unittest.main()
