"""Independent closed-form and metadata checks; no planner invocation."""
from copy import deepcopy
from math import comb
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_shard_prepare_v3_20260925 as f
from scripts import ndx_new_cutoff_shard_prepare_v3_20260925 as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):f.Tests.setUpClass();cls.docs=f.Tests.documents;cls.sources=f.Tests.sources

    def test_closed_form_original_three_specs_without_old96_deduction(self):
        counts={k:(comb(19,k) if k<=19 else 0)+2*comb(19,k-1) for k in range(1,21)}
        self.assertEqual(sum(counts.values()),1572863)
        excluded=sum(counts[k] for k in (1,2,3));remaining=sum(counts[k] for k in range(4,21))
        result=dict(all_k_combination_count=sum(counts.values()),necessary_bound_excluded_combination_count=excluded,
            planned_combination_count=remaining,planned_canonical_task_count=3*remaining,
            planned_shard_count=sum((counts[k]+999)//1000 for k in range(4,21)),
            completed_canonical_task_count=0,remaining_canonical_task_count=3*remaining,
            cardinalities=[dict(k=k,necessary_bound_certificates=['necessary'] if k<=3 else []) for k in range(1,21)])
        with patch.object(m.planning,'prepare_issuer_shards') as call:
            m.validate_counts(result);call.assert_not_called()
        result['remaining_canonical_task_count']-=96
        with self.assertRaises(ValueError):m.validate_counts(result)

    def test_saved_review_late_and_crwd_block_cannot_upgrade(self):
        for attack in ('late','crwd','external_complete'):
            docs=deepcopy(self.docs)
            if attack=='late':docs['panel']['v3_incremental_evidence_and_projection'][0]['early_window_review_availability_verified']=True
            elif attack=='crwd':docs['panel']['incremental_evidence_and_projection'][1]['numerical_column_added']=True
            else:docs['completed_index']['all_plan_tasks_completed']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inputs_from_documents(docs,self.sources)

    def test_both_v3_source_pins_cannot_be_substituted(self):
        for path in (m.V3_PRODUCER,m.V3_READER):
            with self.subTest(path=path),self.assertRaises(ValueError):m.guard({str(path):'0'*64})


if __name__=='__main__':unittest.main()
