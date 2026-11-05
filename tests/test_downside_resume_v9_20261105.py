import ast
import unittest
from pathlib import Path
from docs.candidates.downside_resume_chain_20261105 import verify_parent,verify_prefix_progress,reusable
from scripts.research.run_downside_account_candidate_20261105_v9 import load_accounting_only_implementation

ROOT=Path(__file__).resolve().parents[1]


class V9Tests(unittest.TestCase):
    def test_eight_parent_nodes_31_records_and_625_boundary(self):
        p=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v8')
        self.assertEqual(p['chain_depth'],8)
        self.assertEqual(len(p['records']),31)
        self.assertEqual(p['summary']['searches']['new'],31)
        self.assertEqual(p['summary']['elapsed_seconds'],2550.014866100042)
        self.assertEqual(len(p['book']['daily_ledger']),625)
        self.assertFalse(verify_prefix_progress(p['book'],p['book']['daily_ledger'][:624]))
        self.assertTrue(verify_prefix_progress(p['book'],p['book']['daily_ledger']))
        for r in p['records'].values():self.assertEqual(reusable(p,r['selection']['arguments']),r)

    def test_actual_v3_select_callback_global_resolves_to_reject_stub(self):
        module=load_accounting_only_implementation()
        tree=ast.parse((ROOT/'scripts/research/run_downside_account_candidate_20261105_v3.py').read_text())
        select=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='select')
        self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='decide_observed_for_account' for n in ast.walk(select)))
        # The real nested callback looks up this exact module global, not a cached import.
        with self.assertRaisesRegex(ValueError,'ACCOUNTING_ONLY_NO_NEW_SEARCH'):
            module.run.__globals__['decide_observed_for_account'](decision_date='2026-06-30')


if __name__=='__main__':unittest.main()
