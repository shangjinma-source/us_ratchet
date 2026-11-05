import json
import unittest
from pathlib import Path
from collections import Counter
from docs.candidates.downside_resume_chain_20261105 import verify_parent,verify_prefix_progress
from scripts.research.prepare_downside_max10_resume_v4_freeze_20261105 import verify_current_blocker_coverage
from backtest.research_exact_fraction_json import loads

ROOT=Path(__file__).resolve().parents[1]


class V5Tests(unittest.TestCase):
    def test_four_generations_and_417_row_gate(self):
        p=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v4')
        self.assertEqual(p['chain_depth'],4)
        self.assertEqual(sorted(Counter(r['origin'] for r in p['records'].values()).values()),[2,3,3,13])
        self.assertEqual(p['summary']['searches']['new'],21)
        self.assertEqual(p['summary']['elapsed_seconds'],1585.3732661000104)
        self.assertEqual(len(p['book']['daily_ledger']),417)
        self.assertFalse(verify_prefix_progress(p['book'],p['book']['daily_ledger'][:416]))
        self.assertTrue(verify_prefix_progress(p['book'],p['book']['daily_ledger']))

    def test_existing_artifacts_do_not_clear_lrcx(self):
        freeze=json.loads((ROOT/'research_contracts/downside_max10_resume_v4_20261105/freeze.json').read_bytes())
        artifacts=[json.loads((ROOT/n).read_bytes()) for n in freeze['additional_execution_artifacts']]
        document=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())
        gate=loads((ROOT/'tmp/downside_max10_20261105_late_v4/2025-08-29.exposure.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'PARENT_BLOCKERS_NOT_COVERED.*LRCX'):
            verify_current_blocker_coverage(document,gate,artifacts)


if __name__=='__main__':unittest.main()
