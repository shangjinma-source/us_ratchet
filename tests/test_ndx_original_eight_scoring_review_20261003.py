from copy import deepcopy
import unittest
from test_ndx_original_eight_scoring_inputs_research import fixture
from backtest import ndx_original_eight_scoring_inputs_research as m

def seal(a):
    for b in a['channel_bindings']:
        c=b['channel'];c['content_sha256']=m.digest({k:v for k,v in c.items() if k!='content_sha256'})

class Review(unittest.TestCase):
    def test_original_weights_and_all_window_endpoints(self):
        a=fixture();before=deepcopy(a);out=m.prepare_original_eight_scoring_inputs(**a)
        self.assertEqual(a,before)
        for d in out['decisions']:
            self.assertEqual(len(d['return_rows']),504)
            self.assertTrue(all(abs(x['return_float']-.045)<1e-16 for x in d['return_rows']))
            self.assertEqual(d['windows'][0]['training_freeze_close'],d['price_dates'][126])
            self.assertEqual(d['windows'][-1]['evaluation_last_return_end'],d['cutoff'])
            self.assertEqual(d['windows'][-1]['evaluation_return_stop'],504)
        self.assertEqual(out['original_float_weight_sum'],8.)
        self.assertFalse(out['source_bytes_authenticated'])

    def test_resigned_self_inconsistent_sources_rejected(self):
        for change in (lambda c:c['return_rows'][c['decisions'][0]['price_index_start']].update(split_only_return_exact=None),
                       lambda c:c['return_rows'][c['decisions'][0]['price_index_start']].update(split_only_return_exact='999'),
                       lambda c:c['decisions'][0].update(price_index_start=False),
                       lambda c:c['decisions'][0].update(price_index_start=-1),
                       lambda c:c['calendar'].__setitem__(0,'2023-01-01')):
            a=fixture();change(a['channel_bindings'][0]['channel']);seal(a)
            with self.subTest(change=change),self.assertRaises(ValueError):m.prepare_original_eight_scoring_inputs(**a)

    def test_missing_final_return_blocks_last_window_not_earlier(self):
        a=fixture();c=a['channel_bindings'][0]['channel'];j=c['decisions'][0]['price_index_start']+503
        c['return_rows'][j].update(split_only_return_exact=None,split_only_return_float=None);seal(a)
        d=m.prepare_original_eight_scoring_inputs(**a)['decisions'][0]
        self.assertIsNone(d['return_rows'][-1]['return_float'])
        self.assertEqual([i for i,w in enumerate(d['windows']) if w['status']=='BLOCKED_WINDOW'],[12])
        self.assertEqual(d['status'],'BLOCKED_FULL13_SCORING_SUPPLY')

if __name__=='__main__':unittest.main()
