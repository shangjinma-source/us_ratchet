"""Exhaustive tiny universes only; no actual panel candidates."""
import itertools
import unittest
from unittest.mock import patch
from backtest import ndx_issuer_combination_index_research as m


class IndependentIndexReview(unittest.TestCase):
    def test_every_small_group_size_matches_filtered_pair_combinations(self):
        for sizes in itertools.product((1,2,3),repeat=3):
            groups=[(issuer,[f'{9-i}:{j}' for j in range(size)]) for i,(issuer,size) in enumerate(zip(('Z','A','M'),sizes))]
            pairs=sorted((issuer,sid) for issuer,sids in groups for sid in sids)
            index=m.IssuerCombinationIndex(groups)
            for k in range(1,4):
                expected=[tuple(s for _,s in row) for row in itertools.combinations(pairs,k) if len({i for i,_ in row})==k]
                self.assertEqual(index.count(k),len(expected))
                for rank,row in enumerate(expected):
                    self.assertEqual(index.unrank(k,rank),row)
                    self.assertEqual(index.rank(k,row),rank)

    def test_groups_copied_fingerprint_changes_on_reassignment(self):
        groups=[['A',['z']],['B',['a','b']]]
        index=m.IssuerCombinationIndex(groups);fingerprint=index.group_fingerprint
        groups[0][1].append('new')
        self.assertEqual(index.count(2),2)
        self.assertEqual(index.group_fingerprint,fingerprint)
        changed=m.IssuerCombinationIndex([('A',['a']),('B',['z','b'])])
        self.assertNotEqual(index.group_fingerprint,changed.group_fingerprint)

    def test_empty_tail_does_not_unrank_and_boolean_rank_rejected(self):
        index=m.IssuerCombinationIndex([('I',['s1','s2'])])
        with patch.object(m.IssuerCombinationIndex,'unrank') as unrank:
            result=index.slice(1,2,2,max_slice_size=1)
            unrank.assert_not_called();self.assertEqual(result['returned_count'],0)
        with self.assertRaises(ValueError):index.rank(True,['s1'])
        with self.assertRaises(ValueError):index.rank(1,[False])


if __name__=='__main__':unittest.main()
