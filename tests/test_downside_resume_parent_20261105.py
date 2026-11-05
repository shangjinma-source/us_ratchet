"""Fixed parent resume prerequisites; no economic run."""
import unittest
from pathlib import Path
from copy import deepcopy
from docs.candidates.downside_resume_parent_20261105 import verify_parent,reusable,verify_prefix,verify_prefix_progress
ROOT=Path(__file__).resolve().parents[1]


class ResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parent=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v1')

    def test_real_parent_two_full_arguments_reused_without_budget_reset(self):
        parent=self.parent
        self.assertEqual(parent['summary']['searches'],{'new':2,'reused':0})
        self.assertEqual(parent['summary']['elapsed_seconds'],149.63515230000485)
        self.assertEqual(len(parent['book']['daily_ledger']),21)
        for day,record in parent['records'].items():
            result=reusable(parent,record['selection']['arguments'])
            self.assertEqual(result,record)
            result['selection']['arguments']['account_state']['cash']='0'
            self.assertNotEqual(result,parent['records'][day])
        self.assertIsNone(reusable(parent,{'decision_date':'2024-02-29'}))

    def test_changed_wealth_or_sources_cannot_reuse_by_date(self):
        record=next(iter(self.parent['records'].values()))
        for field in ('cash','revision'):
            args=deepcopy(record['selection']['arguments']);args['account_state'][field]='changed'
            with self.assertRaisesRegex(ValueError,'FULL_ARGUMENTS'):reusable(self.parent,args)
        args=deepcopy(record['selection']['arguments']);args['source_hashes']['fake']='0'*64
        with self.assertRaisesRegex(ValueError,'FULL_ARGUMENTS'):reusable(self.parent,args)

    def test_prefix_exact_and_truncated_rejected(self):
        book=self.parent['book']
        self.assertFalse(verify_prefix_progress(book,book['daily_ledger'][:10]))
        broken=deepcopy(book['daily_ledger'][:10]);broken[0]['cash']='changed'
        with self.assertRaisesRegex(ValueError,'PREFIX_CHANGED'):verify_prefix_progress(book,broken)
        self.assertTrue(verify_prefix_progress(book,book['daily_ledger']))
        self.assertEqual(verify_prefix(book,deepcopy(book)),21)
        changed=deepcopy(book);changed['daily_ledger'][0]['cash']='1'
        with self.assertRaisesRegex(ValueError,'PREFIX_CHANGED'):verify_prefix(book,changed)
        changed=deepcopy(book);changed['daily_ledger'].pop()
        with self.assertRaisesRegex(ValueError,'PREFIX_CHANGED'):verify_prefix(book,changed)


if __name__=='__main__':unittest.main()
