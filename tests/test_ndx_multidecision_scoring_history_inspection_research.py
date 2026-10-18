from copy import deepcopy
from decimal import Context,Inexact,localcontext
import json,unittest
from backtest import ndx_multidecision_scoring_history_inspection_research as m
from backtest import ndx_multidecision_scoring_history_research as fixture_writer
from test_ndx_multidecision_scoring_history_research import fixture,bind

def saved_case():
    a=fixture();return a,fixture_writer.materialize_scoring_history_channel(**a)
def resign(d):
    d['quote_rows_sha256']=m.digest(d['quote_rows']);d['return_rows_sha256']=m.digest(d['return_rows']);d['content_sha256']=m.digest({k:v for k,v in d.items() if k!='content_sha256'})
class Tests(unittest.TestCase):
    def test_full_independent_raw_positive_and_context(self):
        a,d=saved_case();before=deepcopy(d)
        ctx=Context(prec=2);ctx.traps[Inexact]=True
        with localcontext(ctx):r=m.inspect_scoring_history_channel(saved_channel=d,**a)
        self.assertEqual(r['window_count'],78);self.assertEqual(d,before)
        split=d['calendar'].index('2026-06-12');self.assertEqual(d['quote_rows'][split-1]['nominal_close_exact'],'405/4');self.assertEqual(d['quote_rows'][split]['nominal_close_exact'],'81/8');self.assertEqual(d['return_rows'][split-1]['split_only_return_exact'],'0')
    def test_rehashed_numeric_and_causal_slot_attacks(self):
        a,d=saved_case()
        for mutate in [lambda x:x['quote_rows'][0].update(nominal_open_exact='999'),lambda x:x['quote_rows'][0].update(raw_volume=True),lambda x:x['return_rows'][3].update(split_only_return_exact='1',split_only_return_float=1.),lambda x:x['decisions'][0]['windows'][0].update(training_return_index_stop=127),lambda x:x['decisions'][0].update(required_return_count=503),lambda x:x.update(fit_performed=0),lambda x:x['quote_rows'].pop(3)]:
            bad=deepcopy(d);mutate(bad);resign(bad)
            with self.assertRaises(ValueError):m.inspect_scoring_history_channel(saved_channel=bad,**a)
    def test_floor_gap_and_no_bridging_missing_day(self):
        a=fixture();a['bridge_row']['event_policy_bridge']['regular_floor']='2025-02-24';body=json.loads(a['raw_bytes']);raw=body['chart']['result'][0];i=a['reference_calendar'].index('2026-03-31');raw['indicators']['quote'][0]['close'][i]=None;bind(a,body,True)
        d=fixture_writer.materialize_scoring_history_channel(**a);r=m.inspect_scoring_history_channel(saved_channel=d,**a);self.assertGreater(r['blocked_price_slots'],0);self.assertEqual(len(d['decisions'][0]['windows']),13)
        j=d['calendar'].index('2026-03-31');self.assertIsNone(d['return_rows'][j-1]['split_only_return_exact']);self.assertIsNone(d['return_rows'][j]['split_only_return_exact'])
        bad=deepcopy(d);bad['return_rows'][j]['split_only_return_exact']='0';bad['return_rows'][j]['split_only_return_float']=0.;resign(bad)
        with self.assertRaises(ValueError):m.inspect_scoring_history_channel(saved_channel=bad,**a)
    def test_missing_raw_date_keeps_original_calendar_slot(self):
        a=fixture();body=json.loads(a['raw_bytes']);raw=body['chart']['result'][0];i=a['reference_calendar'].index('2026-04-01');raw['timestamp'].pop(i)
        for values in raw['indicators']['quote'][0].values():values.pop(i)
        bind(a,body);d=fixture_writer.materialize_scoring_history_channel(**a);m.inspect_scoring_history_channel(saved_channel=d,**a)
        row=next(r for r in d['quote_rows'] if r['session']=='2026-04-01');self.assertIsNone(row['raw_row_index']);self.assertEqual(row['reasons'],['MISSING_REQUIRED_PRICE_DATE'])
        self.assertEqual(len(d['return_rows']),len(d['calendar'])-1)
    def test_source_and_whole_split_inventory_attacks(self):
        a,d=saved_case()
        for mutate in [lambda x:x['receipt'].update(point_in_time_verified=True),lambda x:x['bridge_row']['event_policy_bridge']['events'].clear(),lambda x:x['outer_inventory_contract'].update(security_count=True),lambda x:x.update(raw_bytes=x['raw_bytes']+b' ')]:
            b=deepcopy(a);mutate(b)
            with self.assertRaises((ValueError,KeyError)):m.inspect_scoring_history_channel(saved_channel=d,**b)
