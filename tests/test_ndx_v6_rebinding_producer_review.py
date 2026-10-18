"""Synthetic producer boundary review; no 402-row assembly."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_v6_completed_task_rebinding_20260925 as owner

m=owner.m


class Review(unittest.TestCase):
    def test_extra_numeric_field_or_prior_empty_dictionary_cannot_reuse(self):
        for attack in ('extra','prior'):
            args=owner.fixture();task=args[0]['full_task']
            if attack=='extra':task['numerical_identity']['unrecognized']=True
            else:task['numerical_identity']['requested_previous_target_weights']={}
            task['numerical_task_id']=m.digest(task['numerical_identity']);args[0]['numerical_task_id']=task['numerical_task_id']
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.rebind(*args)

    def test_nested_rebinding_id_and_hash_are_not_self_authorizing(self):
        for attack in ('id','matrix','location'):
            row,ref,panel,plan,index=owner.fixture()
            for key in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):row[key]={'path':'synthetic/'+key,'sha256':'a'*64}
            nested=m.rebind(row,ref,panel,plan,index)
            if attack=='id':nested['numerical_task_id']='0'*64
            elif attack=='matrix':nested['verified_fit_data_sha256']='0'*64
            else:nested['new_location_identity']['rank']+=1
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.rebind_index_row('externally_completed_rebound_rows',0,nested,panel,plan,index)

    def test_source_conflict_before_disk(self):
        path,digest=next(iter(m.LOADED.items()))
        with patch.object(m.Path,'read_bytes',side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):m.guard({path:'0'*64 if digest!='0'*64 else '1'*64})


if __name__=='__main__':unittest.main()
