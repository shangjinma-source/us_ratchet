import unittest
import tempfile
from pathlib import Path
from copy import deepcopy
from decimal import Inexact,localcontext
from unittest.mock import patch
from scripts import ndx_first_period_same_flow_nav_comparison_independent_readback_20261003 as reader
from test_ndx_first_period_same_flow_comparison_research import fixture,core

def case():
    args=fixture();out=core.compare_first_period_paths(**args)
    refs=dict(candidate_accounts=args['candidate_reference'],incumbent_accounts=args['incumbent_reference'],benchmark=args['benchmark_reference'])
    return out,args['candidate_accounts'],args['incumbent_accounts'],args['benchmark_document'],refs

class Tests(unittest.TestCase):
    def test_complete_independent_metrics_and_context(self):
        values=case();before=deepcopy(values)
        with localcontext() as c:
            c.prec=2;c.traps[Inexact]=True
            detail=reader.inspect(*values)
        self.assertEqual(detail['independent_metrics'],17);self.assertEqual(values,before)
    def test_source_projection_flow_and_distance_attacks(self):
        for mode in ('dd','annual','absolute','sign','navpointer','selection','flow','bool','initial'):
            values=case();out,ca,inc,nav,refs=values;r=out['rows'][0]
            if mode=='dd':r['metrics']['candidate']['maximum_drawdown']=reader.enc(reader.F(0))
            elif mode=='annual':r['metrics']['candidate']['annualized_return_diagnostic_decimal']='0'
            elif mode=='absolute':r['nav_distances']['absolute_distances']['candidate']['cumulative_return']=reader.enc(reader.F(0))
            elif mode=='sign':r['nav_distances']['candidate_minus_incumbent_absolute_distance']['maximum_drawdown']=reader.enc(reader.F(4))
            elif mode=='navpointer':out['nav_reference']['observations'][0]['reference']['json_pointer']='/nav/rows/1'
            elif mode=='selection':r['candidate_saved_selection']['gap']='REMOVED'
            elif mode=='flow':inc['paths'][0]['account']['daily'][1]['cash_injection_usd']='1'
            elif mode=='bool':r['metrics']['candidate']['interval_count']=True
            else:inc['paths'][0]['account']['initial']['cash_usd']='25001'
            with self.subTest(mode=mode),self.assertRaises(ValueError):reader.inspect(*values)
    def test_full_nav_dates_never_intersection(self):
        for mode in ('future','short','conflict'):
            values=case();nav=values[3]
            if mode=='future':nav['nav']['rows'][0]['nav_date']='2023-04-01'
            elif mode=='short':nav['calendar'].pop()
            else:nav['nav']['rows'][1].update(nav_date=nav['nav']['rows'][0]['nav_date'],nav=2.0)
            with self.subTest(mode=mode),self.assertRaises(ValueError):reader.inspect(*values)
    def test_source_base_and_pending_no_io(self):
        refs,base=reader.expected_sources();self.assertEqual(len(base),14);self.assertEqual(len(refs),13)
        with tempfile.TemporaryDirectory() as td, patch.object(reader,'OUTPUT',Path(td)/'audit'), patch.object(reader,'RESULT_SHA',None),patch.object(reader,'PUBLICATION_SHA',None),patch.object(reader.Path,'read_bytes',side_effect=AssertionError('No I/O')):
            with self.assertRaisesRegex(ValueError,'Pending'):reader.readback(execute=True)
if __name__=='__main__':unittest.main()
