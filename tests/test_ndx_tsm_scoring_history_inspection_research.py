from copy import deepcopy
import unittest
from backtest import ndx_tsm_scoring_history_inspection_research as m
from backtest import ndx_original_eight_tsm_scoring_history_research as producer
from test_ndx_original_eight_tsm_scoring_history_research import fixture

class Tests(unittest.TestCase):
    def test_all78_and_unchanged_weight(self):
        a=fixture();a['original_control_contract']['securities'][0]['target_weight']=0
        d=producer.materialize_tsm_control_history(**a);r=m.inspect_tsm_control_history(saved_channel=d,**a)
        self.assertEqual(r['window_count'],78);self.assertEqual(r['status'],'PASS')
        self.assertEqual(d['original_control_contract']['securities'][0]['target_weight'],0)
    def test_resigned_arithmetic_scope_and_weights(self):
        a=fixture();d=producer.materialize_tsm_control_history(**a)
        for mutate in [lambda x:x['quote_rows'][0].update(nominal_close_exact='1'),lambda x:x['return_rows'][0].update(split_only_return_exact='1'),lambda x:x.update(role='NDX_CANDIDATE'),lambda x:x['original_control_contract']['securities'][4].update(target_weight=.8),lambda x:x['decisions'][0]['windows'].pop()]:
            bad=deepcopy(d);mutate(bad);bad['content_sha256']=m.digest({k:v for k,v in bad.items() if k!='content_sha256'})
            with self.assertRaises(ValueError):m.inspect_tsm_control_history(saved_channel=bad,**a)
    def test_floor_slots_preserved(self):
        a=fixture();a['bridge_row']['event_policy_bridge']['regular_floor']='2025-02-24';d=producer.materialize_tsm_control_history(**a)
        r=m.inspect_tsm_control_history(saved_channel=d,**a);self.assertGreater(r['blocked_price_slots'],0);self.assertEqual(r['window_count'],78)
