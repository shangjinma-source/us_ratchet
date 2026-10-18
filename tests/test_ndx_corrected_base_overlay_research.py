from copy import deepcopy
import unittest

from backtest.ndx_corrected_base_overlay_research import extend_base_overlay
from backtest.ndx_corrected_cohort_overlay_research import ECONOMIC_KEYS


def fixture():
    task=dict(job_id='base',tickers='AAA;BBB',holding_count=2,weight_spec='constrained_fixed_shrinkage')
    pending=dict(task=task,origin='NON_EQUAL_BASE',status='PENDING_NUMERICAL_DELTA',result=None,
                 overlay_mode='PENDING',lineage={'original_checkpoint_sha256':'old'},
                 eligibility=None,promotion_allowed=False)
    other=dict(task=dict(task,job_id='delta'),origin='JOINT_WEIGHT_DELTA',status='PENDING_NUMERICAL_DELTA',
               result=None,lineage={},eligibility=None,promotion_allowed=False)
    equal=dict(task=dict(task,job_id='equal'),origin='EQUAL_WEIGHT_BASE',status='AVAILABLE',
               result={'unchanged':'original'},lineage={},eligibility=None,promotion_allowed=False)
    parent=dict(schema='ndx_corrected_cohort_overlay_v1',records=[pending,other,equal],original_count=3,
                available_count=1,pending_count=2,selection_performed=False,promotion_allowed=False)
    result={key:0.1 for key in ECONOMIC_KEYS}
    result.update({key:task[key] for key in ('tickers','holding_count','weight_spec')})
    return parent,[dict(task=task,result=result,lineage={'sha256':'externally-bound-by-caller'})]


class BaseOverlayTests(unittest.TestCase):
    def test_complete_delta_only_changes_matching_pending_base(self):
        parent,replacements=fixture();before=deepcopy(parent)
        result=extend_base_overlay(parent=parent,replacements=replacements,expected_base_job_ids=['base'])
        self.assertEqual(parent,before)
        self.assertEqual(result['records'][1:],parent['records'][1:])
        self.assertEqual((result['available_count'],result['pending_count']),(2,1))
        self.assertFalse(result['input_artifact_binding_verified'])
        self.assertIsNone(result['winner'])

    def test_partial_duplicate_unknown_or_wrong_identity_rejected(self):
        parent,replacements=fixture()
        for rows,expected in (([],['base']),(replacements*2,['base']),(replacements,['base','missing'])):
            with self.assertRaises(ValueError):
                extend_base_overlay(parent=parent,replacements=rows,expected_base_job_ids=expected)
        replacements[0]['result']['tickers']='CCC;DDD'
        with self.assertRaises(ValueError):
            extend_base_overlay(parent=parent,replacements=replacements,expected_base_job_ids=['base'])

    def test_caller_cannot_redefine_a_partial_date_as_complete(self):
        parent,replacements=fixture()
        omitted=deepcopy(parent['records'][0]);omitted['task']['job_id']='other-base'
        parent['records'].append(omitted);parent['original_count']+=1;parent['pending_count']+=1
        with self.assertRaisesRegex(ValueError,'Every pending BASE'):
            extend_base_overlay(parent=parent,replacements=replacements,expected_base_job_ids=['base'])

    def test_unchanged_or_nonfinite_or_wholelot_replacement_rejected(self):
        for mutation in ('existing','nonfinite','wholelot'):
            parent,replacements=fixture()
            if mutation=='existing':parent['records'][0]['status']='AVAILABLE'
            elif mutation=='nonfinite':replacements[0]['result']['return_p50']=float('nan')
            else:replacements[0]['result']['whole_lot_path_return_net']=1.
            with self.assertRaises(ValueError):
                extend_base_overlay(parent=parent,replacements=replacements,expected_base_job_ids=['base'])
