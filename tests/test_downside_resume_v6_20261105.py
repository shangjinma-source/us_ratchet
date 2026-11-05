import json
import unittest
import importlib.util
from pathlib import Path
from collections import Counter
from copy import deepcopy
from docs.candidates.downside_resume_chain_20261105 import verify_parent,verify_prefix_progress
from docs.candidates.downside_absence_artifact_20261105 import append_execution_artifact
from scripts.research.prepare_downside_max10_resume_v6_freeze_20261105 import verify_current_blocker_coverage
from backtest.research_exact_fraction_json import loads

ROOT=Path(__file__).resolve().parents[1]


class V6Tests(unittest.TestCase):
    def test_five_generation_budget_and_502_prefix(self):
        p=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v5')
        self.assertEqual(p['chain_depth'],5)
        self.assertEqual(sorted(Counter(r['origin'] for r in p['records'].values()).values()),[2,3,3,4,13])
        self.assertEqual(p['summary']['searches']['new'],25)
        self.assertEqual(p['summary']['elapsed_seconds'],1923.490542100044)
        self.assertFalse(verify_prefix_progress(p['book'],p['book']['daily_ledger'][:501]))
        self.assertTrue(verify_prefix_progress(p['book'],p['book']['daily_ledger']))

    def test_real_absence_gate_without_cash_event_and_reject_fake_dividend(self):
        doc=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())
        artifact=json.loads((ROOT/'tmp/insm_absence_evidence_20261105/supplement.json').read_bytes())
        gate=loads((ROOT/'tmp/downside_max10_20261105_late_v5/2025-12-31.exposure.json').read_bytes())
        before=deepcopy(doc['dividend_events']);review=dict(rows=[],source_hashes={})
        append_execution_artifact(doc,review,artifact)
        self.assertEqual(doc['dividend_events'],before)
        self.assertEqual(len(review['rows']),1)
        outcome=verify_current_blocker_coverage(doc,gate,[artifact])
        self.assertEqual(outcome['accepted'],1)
        with self.assertRaisesRegex(ValueError,'PARENT_BLOCKERS_NOT_COVERED'):
            verify_current_blocker_coverage(doc,gate,[])
        bad=deepcopy(artifact);bad['dividend_events']=[]
        with self.assertRaisesRegex(ValueError,'ABSENCE_NOT_DIVIDEND'):
            append_execution_artifact(doc,review,bad)

    def test_real_legacy_inspector_rejects_truncation_symbol_and_missing_event_request(self):
        path=ROOT/'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py'
        spec=importlib.util.spec_from_file_location('insm_negative_inspector',path)
        legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
        base=ROOT/'tmp/next12_missing_quote_capture_20261014_v1'
        payload=(base/'INSM.response.bin').read_bytes()
        receipt=json.loads((base/'INSM.receipt.json').read_bytes());started=json.loads((base/'INSM.started.json').read_bytes())
        sessions=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())['assembled']['session_dates']
        with self.assertRaises(Exception):legacy.inspect(payload[:-8],receipt,started,required_sessions=sessions,expected_symbol='INSM')
        with self.assertRaises(ValueError):legacy.inspect(payload,receipt,started,required_sessions=sessions,expected_symbol='OTHER')
        r=deepcopy(receipt);s=deepcopy(started)
        for obj in (r,s):obj['request_url']=obj['request_url'].replace('&events=div,splits','')
        r['final_url']=r['request_url']
        with self.assertRaisesRegex(ValueError,'EXPLICIT_EVENT_REQUEST'):
            legacy.inspect(payload,r,s,required_sessions=sessions,expected_symbol='INSM')


if __name__=='__main__':unittest.main()
