import json
import unittest
from pathlib import Path
from collections import Counter
from docs.candidates.downside_resume_chain_20261105 import verify_parent,verify_prefix_progress,append_ordinary_artifact
from scripts.research.prepare_downside_max10_resume_v8_freeze_20261105 import verify_current_blocker_coverage
from backtest.research_exact_fraction_json import loads
from fractions import Fraction as F

ROOT=Path(__file__).resolve().parents[1]


class V8Tests(unittest.TestCase):
    def test_seven_generations_and_563_prefix(self):
        p=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v7')
        self.assertEqual(p['chain_depth'],7)
        self.assertEqual(sorted(Counter(r['origin'] for r in p['records'].values()).values()),[1,2,2,3,3,4,13])
        self.assertEqual(p['summary']['searches']['new'],28)
        self.assertEqual(p['summary']['elapsed_seconds'],2260.365469100012)
        self.assertEqual(len(p['book']['daily_ledger']),563)
        self.assertFalse(verify_prefix_progress(p['book'],p['book']['daily_ledger'][:562]))
        self.assertTrue(verify_prefix_progress(p['book'],p['book']['daily_ledger']))

    def test_final_amount_not_provider_estimate_and_gate_coverage(self):
        doc=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())
        gate=loads((ROOT/'tmp/downside_max10_20261105_late_v7/2026-03-31.exposure.json').read_bytes())
        artifact=json.loads((ROOT/'tmp/asml_remaining_dividend_review_20261105/supplement.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'PARENT_BLOCKERS_NOT_COVERED'):
            verify_current_blocker_coverage(doc,gate,[])
        self.assertEqual(verify_current_blocker_coverage(doc,gate,[artifact])['remaining_events'],[])
        review=dict(rows=[],source_hashes={});append_ordinary_artifact(doc,review,artifact)
        events=artifact['dividend_events']
        self.assertEqual([F(x['amount_per_share']) for x in events],[F('3.168450'),F('2.137748')])
        self.assertEqual([x['payment_date'] for x in events],['2026-05-05','2026-08-05'])


if __name__=='__main__':unittest.main()
