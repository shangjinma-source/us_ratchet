from copy import deepcopy
import unittest
from backtest import ndx_original_eight_scoring_inspection_research as m
from backtest import ndx_original_eight_scoring_inputs_research as producer
from test_ndx_original_eight_scoring_inputs_research import fixture

class Tests(unittest.TestCase):
    def test_independent_products_full3024(self):
        a=fixture();d=producer.prepare_original_eight_scoring_inputs(**a);r=m.inspect_original_eight_scoring_inputs(saved_inputs=d,**a)
        self.assertEqual(r['return_slot_count'],3024);self.assertEqual(r['window_count'],78)
    def test_resigned_output_and_source_errors(self):
        a=fixture();d=producer.prepare_original_eight_scoring_inputs(**a)
        for mutation in [lambda x:x['decisions'][0]['return_rows'][0].update(return_float=.046),lambda x:x['normalized_scoring_weights'].update(NVDA=.124),lambda x:x['decisions'][-1]['windows'].pop(),lambda x:x.update(source_bytes_authenticated=True)]:
            bad=deepcopy(d);mutation(bad);bad['content_sha256']=m.digest({k:v for k,v in bad.items() if k!='content_sha256'})
            with self.assertRaises(ValueError):m.inspect_original_eight_scoring_inputs(saved_inputs=bad,**a)
    def test_float_order_nonuniform_and_missing_zero_weight(self):
        a=fixture();ss=a['original_control']['securities'];weights=[0.,.07,.11,.03,.19,.23,.29,.08]
        for s,w in zip(ss,weights):s['target_weight']=w
        a['original_control']['complete_original_definition']['securities']=deepcopy(ss);a['original_control']['complete_original_manifest']['definition']=deepcopy(a['original_control']['complete_original_definition'])
        for b,s in zip(a['channel_bindings'],ss):b['coordinate']=deepcopy(s)
        a['channel_bindings'][4]['channel']['original_control_contract']['securities']=deepcopy(ss)
        ch=a['channel_bindings'][0]['channel'];j=ch['decisions'][0]['price_index_start'];ch['return_rows'][j].update(split_only_return_exact=None,split_only_return_float=None)
        for b in a['channel_bindings']:
            c=b['channel'];c['content_sha256']=m.digest({k:v for k,v in c.items() if k!='content_sha256'})
        d=producer.prepare_original_eight_scoring_inputs(**a);m.inspect_original_eight_scoring_inputs(saved_inputs=d,**a);self.assertIsNone(d['decisions'][0]['return_rows'][0]['return_float'])
