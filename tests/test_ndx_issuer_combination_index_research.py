"""Small independent itertools oracle; no real panel or numerical fitting."""
from dataclasses import FrozenInstanceError
import itertools
import math
import unittest
from unittest.mock import patch
from backtest import ndx_issuer_combination_index_research as m


def independent(groups,k):
    ordered=sorted((issuer,sorted(sids)) for issuer,sids in groups)
    values=[]
    for chosen in itertools.combinations(ordered,k):
        for securities in itertools.product(*(group for _,group in chosen)):
            values.append(tuple((entry[0],sid) for entry,sid in zip(chosen,securities)))
    values.sort()
    return [tuple(sid for issuer,sid in row) for row in values]


class IndexTests(unittest.TestCase):
    def test_exact_order_and_both_inverse_directions(self):
        for groups in ([('Z',['z1'])],[('C',['c2','c1']),('A',['a2','a1']),('B',['b1'])],
                       [('issuer2',['z','a']),('issuer1',['x']),('issuer3',['q','r','s'])]):
            index=m.IssuerCombinationIndex(groups)
            for k in range(1,len(groups)+1):
                expected=independent(groups,k)
                self.assertEqual(index.count(k),len(expected))
                for position,selection in enumerate(expected):
                    self.assertEqual(index.unrank(k,position),selection)
                    self.assertEqual(index.rank(k,selection),position)
                    self.assertEqual(index.unrank(k,index.rank(k,selection)),selection)

    def test_slices_partition_without_gaps_or_duplicates_and_empty(self):
        groups=[('A',['a0','a1']),('B',['b0','b1']),('C',['c0','c1'])]
        index=m.IssuerCombinationIndex(groups);expected=independent(groups,2)
        result=[]
        for start in range(0,len(expected),3):result+=index.slice(2,start,min(start+3,len(expected)),max_slice_size=3)['combinations']
        self.assertEqual(result,expected);self.assertEqual(len(set(result)),len(expected))
        self.assertEqual(index.slice(2,len(expected),len(expected),max_slice_size=1)['combinations'],[])

    def test_large_integer_count_and_tail_slice_only(self):
        groups=[(f'i{i:02}',[f's{i:02}-{j}' for j in range(10)]) for i in range(30)]
        index=m.IssuerCombinationIndex(groups);total=index.count(15)
        self.assertEqual(total,math.comb(30,15)*10**15);self.assertGreater(total,2**63)
        original=m.IssuerCombinationIndex.unrank
        calls=[]
        def observed(this,k,position):calls.append(position);return original(this,k,position)
        with patch.object(m.IssuerCombinationIndex,'unrank',observed):result=index.slice(15,total-2,total,max_slice_size=2)
        self.assertEqual(calls,[total-2,total-1]);self.assertEqual(result['returned_count'],2)

    def test_input_order_normalization_is_versioned_and_immutable(self):
        first=m.IssuerCombinationIndex([('B',['b']),('A',['a2','a1'])])
        second=m.IssuerCombinationIndex([('A',['a1','a2']),('B',['b'])])
        self.assertEqual(first.group_fingerprint,second.group_fingerprint)
        self.assertEqual(first.issuer_ids,('A','B'))
        with self.assertRaises(FrozenInstanceError):first.issuer_ids=()
        with self.assertRaises(TypeError):first._locations['fake']=(0,0)

    def test_duplicate_groups_empty_and_duplicate_sid_fail(self):
        cases=[[],[('A',[])],[('A',['x']),('A',['y'])],[('A',['x','x'])],[('A',['x']),('B',['x'])],
               [(' A',['x'])],[('A',[True])],[('A','x')],{'A':['x']}]
        for groups in cases:
            with self.subTest(groups=groups),self.assertRaises(ValueError):m.IssuerCombinationIndex(groups)

    def test_k_rank_and_noncanonical_selection_boundaries(self):
        index=m.IssuerCombinationIndex([('A',['a1','a2']),('B',['b'])])
        for k in (True,0,3,1.0):
            with self.subTest(k=k),self.assertRaises(ValueError):index.count(k)
        for position in (True,-1,index.count(1),0.5):
            with self.subTest(position=position),self.assertRaises(ValueError):index.unrank(1,position)
        for selection in (['b','a1'],['a1','a2'],['a1','a1'],['a1','unknown'],['a1',False],['a1']):
            with self.subTest(selection=selection),self.assertRaises(ValueError):index.rank(2,selection)

    def test_slice_budget_and_exact_integer_bounds(self):
        index=m.IssuerCombinationIndex([('A',['a']),('B',['b'])])
        for start,stop,budget in ((True,1,1),(0,True,1),(0,1,True),(-1,1,2),(1,0,2),(0,3,3),(0,2,1),(0,0,0),(0,0,10001)):
            with self.subTest(bounds=(start,stop,budget)),self.assertRaises(ValueError):index.slice(1,start,stop,max_slice_size=budget)
        result=index.slice(1,0,1,max_slice_size=1)
        self.assertEqual(result['status'],'ENUMERATED_ONLY_NOT_RISK_FEASIBILITY')
        self.assertFalse(result['risk_feasibility_evaluated']);self.assertFalse(result['task_identity_generated'])


if __name__=='__main__':unittest.main()
