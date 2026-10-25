from copy import deepcopy
from fractions import Fraction as F
import json
import unittest
from hashlib import sha256
from backtest import quantity_box_supplemental_certificate as module
from test_quantity_box_supplemental_certificate import sources,raw,repack_manifest
from test_quantity_integer_box_certificate_prototype import fixture

class IndependentSupplementTests(unittest.TestCase):
    def test_external_input_and_invalid_parent_even_if_raw_hash_matches(self):
        a=sources();a['expected_input_sha256']='0'*64
        with self.assertRaises(ValueError):module.supplement(**a)
        a=sources();p=json.loads(a['parent_raw']);p['lower_product']='999999'
        a['parent_raw']=raw(p);a['expected_parent_sha256']=sha256(a['parent_raw']).hexdigest()
        with self.assertRaises(ValueError):module.supplement(**a)

    def test_coverage_same_count_duplicates_extra_and_swapped(self):
        for kind in ['duplicate_same_count','extra','swapped']:
            a=sources();rows=json.loads(a['evidence_manifest_raw'])['rows']
            self.assertGreaterEqual(len(rows),2)
            if kind=='duplicate_same_count':rows[1]=deepcopy(rows[0])
            elif kind=='extra':rows[0]['id']='foreign'
            else:
                i,j=rows[0]['id'],rows[1]['id'];a['evidence_raw_by_id'][i],a['evidence_raw_by_id'][j]=a['evidence_raw_by_id'][j],a['evidence_raw_by_id'][i]
                for row in rows:row['sha256']=sha256(a['evidence_raw_by_id'][row['id']]).hexdigest()
            repack_manifest(a,rows)
            with self.subTest(kind=kind),self.assertRaises(ValueError):module.supplement(**a)

    def test_equal_bound_and_strict_claim_types(self):
        args=fixture();args['training_scenarios']=[{s:'1' for s in 'ABC'}];args['fee_bps']='0'
        a=sources(args);result=module.supplement(**a)
        self.assertTrue(result['objective_value_optimal']);self.assertEqual(F(result['upper_product']),F(result['lower_product']))
        self.assertFalse(result['tie_break_optimality_established'])
        for field,value in [('objective_value_optimal',1),('new_search_nodes',False),('data_authenticated',0),('tie_break_optimality_established',True),('parent_processed_nodes',True),('upper_product','0')]:
            altered=deepcopy(result);altered[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):module.verify(altered,**a)

    def test_unresolved_requires_maximum_and_no_completion(self):
        a=sources();result=module.supplement(**a);self.assertTrue(result['remaining_frontier'])
        upper=max([F(result['lower_product'])]+[F(n['supplemental_bound']['upper_product']) for n in result['remaining_frontier']])
        self.assertEqual(upper,F(result['upper_product']))
        for field,value in [('objective_value_optimal',True),('remaining_frontier',[]),('upper_product',result['lower_product']),('status','COMPLETE_SUPPLEMENTAL_OBJECTIVE_COVERAGE')]:
            altered=deepcopy(result);altered[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):module.verify(altered,**a)

if __name__=='__main__':unittest.main()
