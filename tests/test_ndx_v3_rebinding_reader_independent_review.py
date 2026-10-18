"""Independent synthetic reader attacks; no actual96 audit or production ranking."""
from copy import deepcopy
from itertools import combinations,product
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_v3_completed_task_rebinding_independent_readback_20260925 as f
from scripts import ndx_new_cutoff_v3_completed_task_rebinding_independent_readback_20260925 as m


class IndependentReview(unittest.TestCase):
    def test_rank_issuer_order_not_global_sid_lexical_order(self):
        groups=[dict(issuer_id='A',security_ids=['z','zz']),dict(issuer_id='B',security_ids=['a']),dict(issuer_id='C',security_ids=['b','bb'])]
        for k in (1,2,3):
            values=[]
            for indexes in combinations(range(3),k):
                for sids in product(*(groups[i]['security_ids'] for i in indexes)):
                    values.append((tuple((groups[i]['issuer_id'],s) for i,s in zip(indexes,sids)),list(sids)))
            values.sort()
            self.assertEqual([m.independent_rank(groups,list(reversed(sids))) for _,sids in values],list(range(len(values))))

    def test_old_three_and_new93_cannot_duplicate_or_drop_spec(self):
        for attack in ('duplicate_old','alias'):
            docs,panel=f.fixture()
            if attack=='duplicate_old':docs['completed_index']['old_completed_tasks'][0]=deepcopy(docs['completed_index']['new_tasks'][0])
            else:docs['completed_index']['new_tasks'][1]=deepcopy(docs['completed_index']['new_tasks'][0])
            with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.reconstruct_rows(docs)

    def test_unselected_added_column_must_still_obey_fullpanel_gate(self):
        docs,panel=f.fixture();panel['returns']=panel['returns'].astype(object);panel['returns'].iloc[0,-1]=True
        with patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.reconstruct_rows(docs)

    def test_source_conflict_rejects_loaded_reader_replacement(self):
        with self.assertRaisesRegex(ValueError,'conflict'):
            m.guard({str(m.SOURCE):'0'*64})


if __name__=='__main__':unittest.main()
