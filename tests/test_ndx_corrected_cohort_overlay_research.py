from copy import deepcopy
import unittest
from backtest import ndx_corrected_cohort_overlay_research as overlay


def fixture():
    coordinate=dict(source_batch='old',universe_track='old_subpool',selection_date='2023-04-03')
    task=dict(coordinate,job_id='one',tickers='AAA',holding_count=1,weight_spec='constrained_fixed_shrinkage',training_semantics_sha256='old')
    metrics={key:.1 for key in overlay.ECONOMIC_KEYS};metrics.update(tickers='AAA',holding_count=1,weight_spec=task['weight_spec'],risk_chain_top1=1.)
    old=dict(task=task,origin='NON_EQUAL_BASE',status='EVALUATED',result=metrics)
    action=dict(task=task,origin='NON_EQUAL_BASE',mode='SAVED_WINDOW_ECONOMIC_PATCH',patch={key:.1 for key in overlay.ECONOMIC_KEYS},lineage={'source':'bound'})
    return dict(coordinate=coordinate,original_records=[old],actions={'one':action},expected_counts={'NON_EQUAL_BASE':1},correction_signature='a'*64)


class OverlayTests(unittest.TestCase):
    def test_pending_retains_denominator_but_never_stale_metrics_or_winner(self):
        args=fixture();args['actions']['one'].update(mode='PENDING');args['actions']['one'].pop('patch')
        result=overlay.overlay_date(**args)
        self.assertEqual((result['original_count'],result['available_count'],result['pending_count']),(1,0,1))
        self.assertIsNone(result['records'][0]['result']);self.assertIsNone(result['winner'])
        self.assertFalse(result['pending_is_economic_failure']);self.assertFalse(result['economic_inputs_complete'])

    def test_patch_preserves_risk_and_only_paired_changes(self):
        args=fixture();args['actions']['one']['patch']['paired_return_p50_vs_incumbent']=.2
        result=overlay.overlay_date(**args)
        self.assertEqual(result['records'][0]['result']['risk_chain_top1'],1.)
        self.assertEqual(result['records'][0]['result']['paired_return_p50_vs_incumbent'],.2)
        self.assertEqual(args['original_records'][0]['result']['paired_return_p50_vs_incumbent'],.1)

    def test_wrong_lineage_duplicate_missing_or_stale_pending_rejected(self):
        for fault in ('lineage','duplicate','missing','stale','own_metric','bool'):
            args=fixture()
            if fault=='lineage':args['actions']['one']=deepcopy(args['actions']['one']);args['actions']['one']['task']['source_batch']='different'
            if fault=='duplicate':args['original_records']*=2
            if fault=='missing':args['actions']={}
            if fault=='stale':args['actions']['one']['mode']='PENDING'
            if fault=='own_metric':args['actions']['one']['patch']['return_p50']=.3
            if fault=='bool':args['actions']['one']['patch']['return_p50']=True
            with self.assertRaises(ValueError,msg=fault):overlay.overlay_date(**args)
