from copy import deepcopy
import math,unittest
from test_ndx_original_eight_scoring_inputs_research import fixture
from test_ndx_original_eight_scoring_inputs_independent_readback_20261003 import fixture as metadata
from backtest import ndx_original_eight_scoring_inputs_research as producer
from backtest import ndx_original_eight_scoring_inspection_research as inspector
from scripts import ndx_original_eight_scoring_inputs_independent_readback_20261003 as reader

class Review(unittest.TestCase):
    def test_independent_binary_products_and_one_ulp_rejection(self):
        a=fixture();vals=[.125,-.5,.3,.07,-.13,.9,.02,-.04]
        for binding,v in zip(a['channel_bindings'],vals):
            c=binding['channel']
            for r in c['return_rows']:r.update(split_only_return_exact=str(v),split_only_return_float=v)
            c['content_sha256']=inspector.digest({k:v for k,v in c.items() if k!='content_sha256'})
        saved=producer.prepare_original_eight_scoring_inputs(**a)
        expected=0.
        for v in vals:expected+=v*.125
        self.assertTrue(all(row['return_float'].hex()==expected.hex() for d in saved['decisions'] for row in d['return_rows']))
        self.assertEqual(inspector.inspect_original_eight_scoring_inputs(saved_inputs=saved,**a)['return_slot_count'],3024)
        saved['decisions'][0]['return_rows'][0]['return_float']=math.nextafter(expected,math.inf)
        saved['content_sha256']=inspector.digest({k:v for k,v in saved.items() if k!='content_sha256'})
        with self.assertRaises(ValueError):inspector.inspect_original_eight_scoring_inputs(saved_inputs=saved,**a)

    def test_saved_false_zero_and_channel_ref_rebinding(self):
        a=fixture();saved=producer.prepare_original_eight_scoring_inputs(**a)
        for change in (lambda s:s.update(source_bytes_authenticated=0),
                       lambda s:s['channel_binding_evidence'][4]['channel_reference'].update(path='wrong'),
                       lambda s:s['decisions'][0]['windows'][0].update(evaluation_return_start=125)):
            s=deepcopy(saved);change(s);s['content_sha256']=inspector.digest({k:v for k,v in s.items() if k!='content_sha256'})
            with self.assertRaises(ValueError):inspector.inspect_original_eight_scoring_inputs(saved_inputs=s,**a)

    def test_independent_outer_source_and_preserved_inventory(self):
        for change in (lambda a:a[1].update(source_hashes={}),lambda a:a[2].update(retry_allowed=0),
                       lambda a:a[0]['shared_source_provenance']['original101'].pop(),
                       lambda a:a[0]['runtime'].update(numpy='other')):
            a=[deepcopy(x) for x in metadata()];change(a)
            with self.assertRaises(ValueError):reader.inspect_document(*a)

if __name__=='__main__':unittest.main()
