"""Independent exact metric oracle and source guards, synthetic only."""
from fractions import Fraction
from decimal import localcontext, Inexact
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_same_window_nav_reference_metrics_research import fixture,resign
from test_ndx_same_window_nav_reference_metrics_20261003 import fixture as documents
from backtest import ndx_same_window_nav_reference_metrics_research as core
from scripts import ndx_same_window_nav_reference_metrics_20261003 as wrapper

class Review(unittest.TestCase):
    def test_exact_all_pairs_peak_oracle_and_distinct_modes(self):
        args=fixture();values=[Fraction(10),Fraction(12),Fraction(12),Fraction(6),Fraction(12),Fraction(6)]+[Fraction(8)]*121
        for i,row in enumerate(args['alignment']['rows'][126:]):
            row['conversions'][core.MODES[0]]['nav_usd_exact']=str(values[i])
            row['conversions'][core.MODES[1]]['nav_usd_exact']=str(Fraction(10+i,10))
        resign(args['alignment'])
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True;result=core.calculate_reference_metrics(**args)
        a=result['modes'][core.MODES[0]];metrics=a['metrics']
        loss=max(Fraction(0),max(1-values[j]/values[i] for j in range(127) for i in range(j+1)))
        self.assertEqual(Fraction(metrics['maximum_drawdown']['exact']),loss)
        self.assertEqual(metrics['drawdown']['peak_index'],1);self.assertEqual(metrics['drawdown']['trough_index'],3)
        self.assertEqual(Fraction(metrics['annualized_return']['exact']),(values[-1]/values[0])**2-1)
        self.assertEqual([Fraction(r['return_exact']) for r in a['interval_returns']],[values[i+1]/values[i]-1 for i in range(126)])
        self.assertFalse(result['mode_values_exactly_equal']);self.assertFalse(result['mode_selected_using_results'])

    def test_missing_first_and_last_never_renormalize(self):
        for index in (126,252):
            args=fixture();args['alignment']['rows'][index]['conversions'][core.MODES[0]].update(status='MISSING_ALIGNMENT_INPUT',reason='ND',nav_usd_exact=None,nav_usd_decimal=None);resign(args['alignment'])
            result=core.calculate_reference_metrics(**args);bad=result['modes'][core.MODES[0]]
            self.assertIsNone(bad['metrics']);self.assertEqual(len(bad['observations']),127);self.assertEqual(len(bad['interval_returns']),126)
            self.assertTrue(all(r['normalized_value_exact'] is None for r in bad['observations']))
            self.assertIsNotNone(result['modes'][core.MODES[1]]['metrics'])

    def test_source_and_rehashed_authority_rejected(self):
        args=fixture();args['alignment']['point_in_time_verified']=0;resign(args['alignment'])
        with self.assertRaises(ValueError):core.calculate_reference_metrics(**args)
        for role,field in [('alignment_publication','source_hashes'),('requirements_publication','source_hashes')]:
            docs,refs=documents();docs[role][field]={'forged':'a'*64}
            with self.assertRaises(ValueError):wrapper.project_inputs(docs,refs)
        docs,refs=documents();docs['alignment_audit']['reader_sha256']='b'*64
        with self.assertRaises(ValueError):wrapper.project_inputs(docs,refs)

    def test_source_drift_and_failed_namespace_no_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'source';p.write_bytes(b'a');sources={str(p):wrapper.sha(b'a')};p.write_bytes(b'b')
            with self.assertRaises(ValueError):wrapper.guard(sources)
            out=Path(folder)/'failed';out.mkdir();(out/'failure.json').write_text('{}')
            with patch.object(wrapper,'OUTPUT',out),patch.object(wrapper,'load_inputs',side_effect=AssertionError('no load')):
                with self.assertRaises(ValueError):wrapper.run(execute=True)
                with self.assertRaises(ValueError):wrapper.run(execute=1)

if __name__=='__main__':unittest.main()
