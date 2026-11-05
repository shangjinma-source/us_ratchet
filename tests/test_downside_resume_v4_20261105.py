import unittest
from pathlib import Path
from collections import Counter
from unittest.mock import patch
from docs.candidates.downside_resume_chain_20261105 import verify_parent,verify_prefix_progress
from scripts.research import run_downside_account_candidate_20261105_v4 as wrapper
from scripts.research.prepare_downside_max10_resume_v4_freeze_20261105 import verify_current_blocker_coverage
from backtest.research_exact_fraction_json import loads
import json

ROOT=Path(__file__).resolve().parents[1]


class V4Tests(unittest.TestCase):
    def test_real_three_generation_budget_and_latest_prefix(self):
        p=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v3')
        self.assertEqual(p['chain_depth'],3)
        self.assertEqual(sorted(Counter(r['origin'] for r in p['records'].values()).values()),[2,3,3])
        self.assertEqual(p['summary']['searches']['new'],8)
        self.assertEqual(p['summary']['elapsed_seconds'],609.5263517999556)
        self.assertEqual(len(p['book']['daily_ledger']),146)
        self.assertFalse(verify_prefix_progress(p['book'],p['book']['daily_ledger'][:145]))
        self.assertTrue(verify_prefix_progress(p['book'],p['book']['daily_ledger']))

    def test_wrapper_requires_freeze_before_loading_implementation(self):
        with patch.object(wrapper,'validate_execution_freeze',side_effect=ValueError('NOT_FROZEN')):
            with patch.object(wrapper.importlib.util,'spec_from_file_location') as loader:
                with self.assertRaisesRegex(ValueError,'NOT_FROZEN'):
                    wrapper.run('2024_2026','unused','unused')
                loader.assert_not_called()

    def test_azn_alone_cannot_mark_actual_parent_ready(self):
        document=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())
        gate=loads((ROOT/'tmp/downside_max10_20261105_late_v3/2024-07-31.exposure.json').read_bytes())
        azn=json.loads((ROOT/'tmp/azn_ads_dividends_20261105/supplement.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'PARENT_BLOCKERS_NOT_COVERED.*CTSH'):
            verify_current_blocker_coverage(document,gate,[azn])


if __name__=='__main__':unittest.main()
