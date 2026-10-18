from copy import deepcopy
from decimal import localcontext, Inexact
import unittest
from test_ndx_dated_per_task_comparison_independent_readback_20261003 import fixture,verify,producer


class Tests(unittest.TestCase):
    def test_track_metadata_and_extra_distance_cannot_upgrade(self):
        a=fixture();out=producer.compare_per_task_paths(**a)
        changes=[lambda r:r['tracks']['candidate_integer'].update(value_encoding='EXACT_ECONOMIC_ACCOUNT'),
                 lambda r:r['tracks']['candidate_continuous'].update(unknown_certification=True),
                 lambda r:r['absolute_distance_comparisons'].update(SELECTED_BEST_MODE={}),
                 lambda r:r['absolute_distance_comparisons'][producer.MODES[0]]['integer']['annualized_return'].update(formal_pass=True)]
        for mutate in changes:
            bad=deepcopy(out);mutate(bad)
            with self.assertRaises(ValueError):verify(a,bad)

    def test_full_original_zero_sidecar_and_nonpositive_missing(self):
        a=fixture();a['candidate_account']=None;a['source_references']['candidate_integer']=None
        a['candidate_continuous']['positions_preserved'][0]['target_weight']=0.
        a['candidate_continuous']['source_sidecar']={'late_review':True,'early_available':False}
        a['candidate_integer_status'].update(status='NOT_EXECUTED_NONPOSITIVE_TARGET',reason='Actual zero target')
        out=producer.compare_per_task_paths(**a)
        self.assertEqual(verify(a,out)['available_distance_cell_count'],4)
        bad=deepcopy(out);bad['tracks']['candidate_continuous']['original_track_preserved']['positions_preserved'].pop(0)
        with self.assertRaises(ValueError):verify(a,bad)
        bad=deepcopy(out);bad['tracks']['candidate_continuous']['original_track_preserved']['source_sidecar']['early_available']=True
        with self.assertRaises(ValueError):verify(a,bad)

    def test_first_peak_and_metric_display_independent_context(self):
        a=fixture()
        for row in a['candidate_account']['daily'][1:]:row['total_value_usd']=10000.
        out=producer.compare_per_task_paths(**a)
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            self.assertEqual(verify(a,out)['observation_count'],762)
        bad=deepcopy(out);bad['tracks']['candidate_integer']['metrics']['drawdown']['peak_index']=1
        with self.assertRaises(ValueError):verify(a,bad)
        bad=deepcopy(out);bad['tracks']['candidate_integer']['metrics']['maximum_drawdown']['decimal']='60'
        with self.assertRaises(ValueError):verify(a,bad)


if __name__=='__main__':unittest.main()
