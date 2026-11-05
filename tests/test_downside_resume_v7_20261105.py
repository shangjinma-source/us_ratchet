import json
import unittest
from pathlib import Path
from collections import Counter
from docs.candidates.downside_resume_chain_20261105 import verify_parent,verify_prefix_progress
from scripts.research.prepare_downside_max10_resume_v7_freeze_20261105 import verify_current_blocker_coverage
from backtest.research_exact_fraction_json import loads

ROOT=Path(__file__).resolve().parents[1]


class V7Tests(unittest.TestCase):
    def test_six_generations_budget_and_541_boundary(self):
        p=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v6')
        self.assertEqual(p['chain_depth'],6)
        self.assertEqual(sorted(Counter(r['origin'] for r in p['records'].values()).values()),[2,2,3,3,4,13])
        self.assertEqual(p['summary']['searches']['new'],27)
        self.assertEqual(p['summary']['elapsed_seconds'],2131.3361789000337)
        self.assertEqual(len(p['book']['daily_ledger']),541)
        self.assertFalse(verify_prefix_progress(p['book'],p['book']['daily_ledger'][:540]))
        self.assertTrue(verify_prefix_progress(p['book'],p['book']['daily_ledger']))

    def test_missing_new_dividends_cannot_mark_ready(self):
        f=json.loads((ROOT/'research_contracts/downside_max10_resume_v6_20261105/freeze.json').read_bytes())
        artifacts=[json.loads((ROOT/n).read_bytes()) for n in f['additional_execution_artifacts']]
        doc=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())
        gate=loads((ROOT/'tmp/downside_max10_20261105_late_v6/2026-02-27.exposure.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'PARENT_BLOCKERS_NOT_COVERED'):
            verify_current_blocker_coverage(doc,gate,artifacts)


if __name__=='__main__':unittest.main()
