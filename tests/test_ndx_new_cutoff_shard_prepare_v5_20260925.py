"""Synthetic closed-form and fail-closed tests; never invoke the actual planner."""
from copy import deepcopy
from math import comb,ceil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_shard_prepare_v5_20260925 as m


def synthetic_counts():
    counts={k:(comb(21,k) if k<=21 else 0)+2*comb(21,k-1) for k in range(1,23)}
    excluded={1,2,3,21,22}
    planned=sum(v for k,v in counts.items() if k not in excluded)
    return dict(all_k_combination_count=sum(counts.values()),necessary_bound_excluded_combination_count=sum(counts[k] for k in excluded),
        planned_combination_count=planned,planned_canonical_task_count=3*planned,
        planned_shard_count=sum(ceil(v/1000) for k,v in counts.items() if k not in excluded),
        completed_canonical_task_count=0,remaining_canonical_task_count=3*planned,
        cardinalities=[dict(k=k,combination_count=counts[k],planned_combination_count=0 if k in excluded else counts[k],
            planned_canonical_task_count=0 if k in excluded else 3*counts[k],planned_shard_count=0 if k in excluded else ceil(counts[k]/1000),
            necessary_bound_certificates=['synthetic necessary certificate'] if k in excluded else []) for k in counts])


class Tests(unittest.TestCase):
    def test_available_metadata_anchors_exact(self):
        import hashlib
        for role,(path,digest) in m.BOUND.items():
            if digest is not None:
                self.assertEqual(hashlib.sha256((m.BASE/path).read_bytes()).hexdigest(),digest)
        self.assertEqual(m.BOUND['completed_index'][1],'34ed4bf484edd2b060064456d9b6e8afa4258ae3179f4e2acb0d0d8f79433197')
    def test_closed_form_all_k_without_planner(self):
        with patch.object(m.planning,'prepare_issuer_shards') as prepare:
            value=synthetic_counts();m.validate_counts(value)
            self.assertEqual((m.SHARD_SIZE,m.MAX_SHARDS),(1000,8000))
            self.assertEqual(value['planned_shard_count'],6297)
            self.assertEqual(value['necessary_bound_excluded_combination_count'],2070)
            prepare.assert_not_called()
    def test_last_cardinality_certificate_cannot_disappear(self):
        for attack in ('drop','certificate','double','bool_k'):
            value=synthetic_counts()
            if attack=='drop':value['cardinalities'].pop()
            elif attack=='certificate':value['cardinalities'][-1]['necessary_bound_certificates']=[]
            elif attack=='double':value['necessary_bound_excluded_combination_count']+=2
            else:value['cardinalities'][0]['k']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_counts(value)
    def test_no_automatic_completed_deduction_or_boolean(self):
        for key,value in [('completed_canonical_task_count',False),('remaining_canonical_task_count',18868155-300),('planned_shard_count',True)]:
            doc=synthetic_counts();doc[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_counts(doc)
    def test_missing_pin_before_read_or_planner(self):
        bound=deepcopy(m.BOUND);bound['audit']=(bound['audit'][0],None)
        with patch.object(m,'BOUND',bound),patch.object(m.Path,'read_bytes') as read,patch.object(m.planning,'prepare_issuer_shards') as prepare:
            with self.assertRaises(ValueError):m.build()
            read.assert_not_called();prepare.assert_not_called()
    def test_fixed_namespace_rejects_before_build(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'plan.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()


if __name__=='__main__':unittest.main()
