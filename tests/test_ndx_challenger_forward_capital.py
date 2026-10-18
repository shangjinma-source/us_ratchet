import unittest

import pandas as pd

from backtest.ndx_challenger_forward_capital import audit_observation_capital


class NdxChallengerForwardCapitalTests(unittest.TestCase):
    def test_audit_uses_frozen_observation_inputs_and_keeps_track_identity(self):
        rows = [{
            "observation_date": "2026-09-01", "registry_entry_id": "FWD_ONE",
            "candidate_id": "one", "track_role": "CHALLENGER",
            "action_scope": "VARIABLE_CARDINALITY", "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "ticker": ticker, "risk_chain": f"chain_{ticker}", "target_weight": 0.25,
            "observation_close": 100.0,
        } for ticker in "ABCD"]
        result = audit_observation_capital(pd.DataFrame(rows), [450, 5000], minimum_cash_buffer=100)
        small, large = result.sort_values("cash_usd").to_dict("records")
        self.assertFalse(small["constraints_passed"])
        self.assertTrue(large["constraints_passed"])
        self.assertEqual(large["research_track"], "portfolio_optimization")
        self.assertEqual(large["holding_count_interpretation"], "dynamic_k_portfolio_structure")
        self.assertFalse(large["return_data_read"])


if __name__ == "__main__":
    unittest.main()
