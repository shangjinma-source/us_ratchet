"""Small synthetic rank/identity tests; never rank or rebind the saved96."""
from copy import deepcopy
import unittest
from unittest.mock import Mock
import test_ndx_new_cutoff_v3_completed_task_rebinding_20260925 as f
from scripts import ndx_new_cutoff_v3_completed_task_rebinding_20260925 as m


class IndependentReview(unittest.TestCase):
    def test_issuer_prefix_order_separate_from_sid_matrix_order(self):
        row,reference,panel,plan,_=f.fixture()
        panel['universe'].loc[0,'issuer_id']='Z';panel['universe'].loc[2,'issuer_id']='A'
        identity=row['full_task']['numerical_identity']
        identity['selected']['sA']['issuer_id']='Z';identity['selected']['sC']['issuer_id']='A'
        row['numerical_task_id']=row['full_task']['numerical_task_id']=m.digest(identity)
        index=m.indexing.IssuerCombinationIndex([('Z',['sA']),('B',['sB']),('A',['sC'])])
        plan['context']['group_fingerprint']=index.group_fingerprint
        original=deepcopy(row)
        observed=Mock(wraps=index)
        result=m.rebind(row,reference,panel,plan,observed)
        observed.rank.assert_called_once_with(2,['sC','sA'])
        self.assertEqual(result['verified_fit_data_sha256'],original['fit_data_sha256'])
        self.assertEqual(result['old_completed_row'],original)

    def test_none_prior_not_empty_map_and_class_identity_not_issuer_alias(self):
        for attack in ('prior','class'):
            args=f.fixture()
            if attack=='prior':args[3]['context']['previous_target_weights']={}
            else:args[2]['universe'].loc[0,'security_id']='otherClassSameIssuer'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.rebind(*args)

    def test_three_specs_keep_three_numeric_ids_with_none_prior(self):
        ids=[];locations=[]
        for spec_index in range(3):
            args=f.fixture();task=args[0]['full_task'];identity=task['numerical_identity']
            identity['weight_spec']=args[3]['context']['weight_specs'][spec_index]
            args[0]['numerical_task_id']=task['numerical_task_id']=m.digest(identity)
            result=m.rebind(*args);ids.append(result['numerical_task_id']);locations.append(result['new_location_id'])
            self.assertEqual(result['new_location_identity']['spec_index'],spec_index)
            self.assertEqual(result['new_wrapper_call_attempt_count'],0)
        self.assertEqual(len(set(ids)),3);self.assertEqual(len(set(locations)),3)


if __name__=='__main__':unittest.main()
