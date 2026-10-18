from copy import deepcopy
import hashlib
import unittest
from test_ndx_full_ndx_multidecision_selector_research import fixture
from backtest.ndx_full_ndx_multidecision_selector_research import select_full_ndx_lanes
from backtest import ndx_full_ndx_selection_inspection_research as inspector


class Tests(unittest.TestCase):
    def test_independent_rank_with_blocked_and_risk_rejected_coordinates(self):
        registration, records = fixture()
        registration['coordinates'][0].update(source_status='SOURCE_BLOCKED', source_blockers=[{'reason_code':'missing', 'evidence_reference':registration['registration_reference']}])
        records = records[3:]
        for record in records[:3]:
            record['eligibility']['liquidity_passed'] = False
        saved = select_full_ndx_lanes(registration=registration, records=records)
        before = inspector.encoded((registration, records, saved))
        report = inspector.inspect_complete_selection(registration=registration, records=records, saved_selection=saved)
        self.assertEqual(report['selected_lane_count'], 40)
        self.assertEqual(report['source_blocked_task_count'], 3)
        self.assertEqual(before, inspector.encoded((registration, records, saved)))

    def test_resigned_wrong_winner_or_authority_is_rejected(self):
        registration, records = fixture()
        original = select_full_ndx_lanes(registration=registration, records=records)
        for mutation in (lambda x:x['rows'][0]['choices'][0].update(selected=deepcopy(x['rows'][0]['choices'][1]['selected'])), lambda x:x.update(promotion_allowed=0), lambda x:x['rows'][0].update(eligible_count=3.0)):
            saved=deepcopy(original);mutation(saved)
            saved['content_sha256']=hashlib.sha256(inspector.encoded({k:v for k,v in saved.items() if k!='content_sha256'})).hexdigest()
            with self.assertRaises(ValueError):
                inspector.inspect_complete_selection(registration=registration, records=records, saved_selection=saved)

    def test_partial_budget_is_not_certified_as_complete_rank(self):
        registration, records = fixture();records.pop()
        saved=select_full_ndx_lanes(registration=registration, records=records)
        with self.assertRaises(ValueError):
            inspector.inspect_complete_selection(registration=registration, records=records, saved_selection=saved)

    def test_saved_metrics_independently_drive_all_lanes_after_reordering(self):
        registration, records = fixture();records.reverse()
        saved=select_full_ndx_lanes(registration=registration, records=records)
        report=inspector.inspect_complete_selection(registration=registration, records=records, saved_selection=saved)
        self.assertEqual(report['selected_lane_count'],48)
        self.assertFalse(report['selector_called'])
