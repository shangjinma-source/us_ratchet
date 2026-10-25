from copy import deepcopy
from hashlib import sha256
import unittest
from backtest.quantity_box_supplemental_certificate import supplement
from backtest.quantity_supplement_frontier_resume import resume,verify,verify_transition
from test_quantity_box_supplemental_certificate import sources,raw
from test_quantity_integer_box_certificate_prototype import fixture,oracle


def setup():
    bound=sources();s=raw(supplement(**bound))
    return dict(supplement_raw=s,expected_supplement_sha256=sha256(s).hexdigest(),bound_sources=bound)


class ContinuationTests(unittest.TestCase):
    def test_tiny_complete_preserves_closed_domain_and_oracle(self):
        a=setup();result=resume(**a,additional_node_budget=1000)
        self.assertTrue(result['objective_value_optimal']);self.assertEqual(result['lower_product'],str(max(v for v,_ in oracle(fixture()))))
        self.assertFalse(result['tie_break_optimality_established']);verify(result,**a)

    def test_segmented_equals_one_shot_and_budget_zero(self):
        a=setup();initial=resume(**a,additional_node_budget=0)
        self.assertTrue(initial['unsearched_frontier']);self.assertFalse(initial['objective_value_optimal'])
        current=initial
        for count in (1,2,3,50):
            prior=raw(current);old=deepcopy(current['coverage_ledger'])
            current=resume(**a,additional_node_budget=count,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest())
            self.assertEqual(current['coverage_ledger'][:len(old)],old)
            verify_transition(current,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest(),**a)
        full=resume(**a,additional_node_budget=56)
        self.assertEqual({k:v for k,v in current.items() if k!='parent_continuation_raw_sha256'},{k:v for k,v in full.items() if k!='parent_continuation_raw_sha256'})

    def test_tampered_binding_partition_authority_and_previous(self):
        a=setup();result=resume(**a,additional_node_budget=1)
        for kind in ('omit','closed','axis','bool','upper','scope','fifo','link'):
            changed=deepcopy(result)
            if kind=='omit':changed['unsearched_frontier'].pop()
            elif kind=='closed':changed['original_closed_count']+=1
            elif kind=='axis':changed['coverage_ledger'][0]['axis']='wrong'
            elif kind=='bool':changed['processed_nodes']=True
            elif kind=='scope':changed['scope']='GLOBAL_ALL_MARKETS'
            elif kind=='fifo':changed['unsearched_frontier'].reverse()
            elif kind=='link':changed['parent_continuation_raw_sha256']=123
            else:changed['upper_product']='0'
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError)):verify(changed,**a)
        old=raw(result)
        with self.assertRaises(ValueError):resume(**a,additional_node_budget=1,previous_raw=old+b' ',expected_previous_sha256=sha256(old).hexdigest())
        changed=dict(a,expected_supplement_sha256='0'*64)
        with self.assertRaises(ValueError):resume(**changed,additional_node_budget=1)

if __name__=='__main__':unittest.main()
