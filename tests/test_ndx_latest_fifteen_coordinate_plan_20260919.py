import copy
import json
import unittest
from scripts import ndx_latest_fifteen_coordinate_plan_20260919 as plan


class CoordinatePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert plan.sha(plan.INVENTORY) == plan.INVENTORY_SHA
        cls.rows = {r['ticker']:r for r in json.loads(plan.INVENTORY.read_text(encoding='utf-8'))['rows']}

    def test_all_fifteen_retained_no_new_join(self):
        values = [plan.row_plan(self.rows[t]) for t in plan.TICKERS]
        self.assertEqual(sum(v['proposed_reused_security_id'] is not None for v in values),7)
        self.assertTrue(all(v['proposed_new_security_id'] is None and not v['legal_training_input_ready'] for v in values))

    def test_conflicting_issuer_class_or_coordinate_rejected(self):
        for field,value in [('subject_cik','0000000001'),('security_class',''),('security_id','security:forged')]:
            row=copy.deepcopy(self.rows['ADI']);row['dated_security_fact_candidates'][0]['fact'][field]=value
            with self.assertRaises(ValueError):plan.row_plan(row)

    def test_lrcx_transition_and_crwd_liquidity_stay_blocked(self):
        row=plan.row_plan(self.rows['LRCX'])
        self.assertIsNone(row['proposed_reused_security_id'])
        self.assertEqual(row['candidate_action_cusips'],['512807306'])
        self.assertEqual(plan.row_plan(self.rows['CRWD'])['liquidity_status'],'BLOCKED_VOLUME_UNIT_UNKNOWN')
        row=copy.deepcopy(self.rows['LRCX']);row['historical_original_risk_labels']=['contradiction']
        with self.assertRaises(ValueError):plan.row_plan(row)


if __name__=='__main__':unittest.main()
