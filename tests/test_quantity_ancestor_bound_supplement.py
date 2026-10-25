from copy import deepcopy
from hashlib import sha256
from fractions import Fraction as F
import unittest
from backtest.quantity_ancestor_bound_supplement import build,verify
from backtest.quantity_supplement_frontier_resume import resume
from test_quantity_supplement_frontier_resume import setup
from test_quantity_box_supplemental_certificate import raw
from test_quantity_integer_box_certificate_prototype import fixture,oracle


def fixture_sources(budget=3):
    src=setup();c=resume(**src,additional_node_budget=budget);data=raw(c)
    return dict(continuation_raw=data,expected_continuation_sha256=sha256(data).hexdigest(),continuation_sources=src),c


class AncestorTests(unittest.TestCase):
    def test_tiny_domain_covered_and_bounds_valid(self):
        for budget in (0,1,3,100):
            a,c=fixture_sources(budget);result=build(**a);verify(result,**a)
            self.assertEqual(len(result['rows']),len(c['unsearched_frontier']))
            self.assertEqual(set(result['closed_node_ids'])|set(result['remaining_node_ids']),{n['id'] for n in c['unsearched_frontier']})
            self.assertGreaterEqual(F(result['upper_product']),max(v for v,_ in oracle(fixture())))
            for row in result['rows']:
                values=oracle(fixture(),row['box'])
                if not row['empty'] and values:self.assertGreaterEqual(F(row['effective_upper_product']),max(v for v,_ in values))

    def test_output_ancestor_omission_bound_boolean_tamper(self):
        a,c=fixture_sources();result=build(**a)
        for kind in ('ancestor','omit','bound','bool','scope'):
            changed=deepcopy(result)
            if kind=='ancestor':changed['rows'][0]['original_bounds'][0]['node_id']='fake'
            elif kind=='omit':changed['rows'].pop()
            elif kind=='bound':changed['upper_product']='0'
            elif kind=='bool':changed['search_nodes']=False
            else:changed['scope']='GLOBAL_ALL_MARKETS'
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify(changed,**a)

    def test_rehashed_invalid_parent_containment_and_hash_rejected(self):
        a,c=fixture_sources();changed=deepcopy(c);changed['unsearched_frontier'][0]['box']['A']=[0,999]
        a['continuation_raw']=raw(changed);a['expected_continuation_sha256']=sha256(a['continuation_raw']).hexdigest()
        with self.assertRaises(ValueError):build(**a)
        a,c=fixture_sources();a['continuation_raw']+=b' '
        with self.assertRaisesRegex(ValueError,'RAW_HASH'):build(**a)

if __name__=='__main__':unittest.main()
