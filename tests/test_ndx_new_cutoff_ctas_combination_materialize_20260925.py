"""Small synthetic forced-prefix oracles; no actual34 materialization."""
from itertools import combinations,product
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_ctas_combination_materialize_20260925 as m


class Tests(unittest.TestCase):
    def test_all_sealed_anchors_exact_without_materializing(self):
        for path,digest in m.BOUND.values():
            if digest is not None:self.assertEqual(m.codec.sha((m.BASE/path).read_bytes()),digest)
    def test_forced_denominator_closed_form(self):
        from math import comb
        self.assertEqual(sum(comb(21,k-1)+2*comb(21,k-2) for k in range(4,21)),6290694)
    def test_forced_prefix_order_matches_independent_small_fullset(self):
        groups=[('D',['d']),('B',['b2','b1']),('A',['a']),('C',['c'])]
        ordered=sorted((issuer,sorted(sids)) for issuer,sids in groups)
        for k in (2,3,4):
            full=[]
            for issuer_subset in combinations(ordered,k):
                for securities in product(*(s for i,s in issuer_subset)):
                    full.append(tuple(zip([i for i,s in issuer_subset],securities)))
            full.sort();expected=[x for x in full if any(s=='c' for i,s in x)]
            count,rows=m.forced_prefixes(groups,'c',k)
            self.assertEqual(count,len(expected))
            for pos,row in enumerate(rows):
                self.assertEqual(row['prefix_security_ids'],[s for i,s in expected[pos]])
                self.assertEqual(row['full_rank'],full.index(expected[pos]))

    def test_forced_specific_class_does_not_accept_sibling(self):
        count,rows=m.forced_prefixes([('A',['a']),('B',['b1','b2']),('C',['c'])],'b2',2)
        self.assertEqual(count,2)
        self.assertTrue(all('b2' in r['prefix_security_ids'] and 'b1' not in r['prefix_security_ids'] for r in rows))

    def test_no_full_slice_unrank_or_large_scan(self):
        groups=[(f'i{i:02}',[f's{i}']) for i in range(20)];groups[3]=('i03',['s3a','s3b'])
        with patch.object(m.materializer.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('forbidden')),patch.object(m.materializer.indexing.IssuerCombinationIndex,'unrank',side_effect=AssertionError('forbidden')):
            total,rows=m.forced_prefixes(groups,'s15',20)
        self.assertEqual(total,2);self.assertEqual(len(rows),2)

    def test_invalid_bool_sid_and_unavailable_limit(self):
        groups=[('A',['a']),('B',['b'])]
        for sid,k,limit in [('a',True,1),('missing',1,1),('a',1,True),('a',1,2)]:
            with self.subTest(sid=sid,k=k,limit=limit),self.assertRaises(ValueError):m.forced_prefixes(groups,sid,k,limit)

    def test_duplicate_completed_task_is_rejected_after_single_mock_slice(self):
        selection=dict(prefix_security_ids=[m.FORCED_SID],full_rank=4)
        value=dict(combination_count=1,materialized_task_count=3,completed_task_count=0,combinations=[dict(prefix_security_ids=[m.FORCED_SID],rank=4,tasks=[dict(numerical_task_id='old0')])])
        with patch.object(m.materializer,'materialize_slice',return_value=value) as call,self.assertRaises(ValueError):
            m.materialize_new([{}]*34,[selection]*34,[f'old{i}' for i in range(402)])
        self.assertEqual(call.call_count,1)

    def test_pending_rebinding_before_read_or_materialization(self):
        pending=deepcopy(m.BOUND);pending['rebinding']=(pending['rebinding'][0],None)
        with patch.object(m,'BOUND',pending),patch.object(m.Path,'read_bytes') as read,patch.object(m.materializer,'materialize_slice') as call:
            with self.assertRaises(ValueError):m.build()
            read.assert_not_called();call.assert_not_called()

    def test_existing_namespace_and_source_drift(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'queue.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):m.guard({})


if __name__=='__main__':unittest.main()
