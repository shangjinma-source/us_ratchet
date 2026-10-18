import unittest

from backtest.tactical_dead_zone import summarize_tactical_dead_zone


class TacticalDeadZoneTests(unittest.TestCase):
    def test_aggregates_multiple_snapshots_by_closed_session(self):
        rows = [
            {
                "ts": "2026-09-01T10:00:00",
                "as_of": "2026-09-02",
                "state_freshness": {"latest_closed_session_date": "2026-09-01"},
                "market": {"regime": "BEAR"},
                "execution": {"actionable_count": 0, "strategy_counts": {"place_limit": 2},
                              "items": []},
                "symbols": [{"tactical": {"regime": "BEAR", "execution_context": {
                    "status": "NO_TACTICAL_BUDGET"}}}],
            },
            {
                "ts": "2026-09-01T11:00:00",
                "state_freshness": {"latest_closed_session_date": "2026-09-01"},
                "market": {"regime": "BEAR"},
                "execution": {"actionable_count": 1, "items": [{
                    "side": "BUY", "source": "tactical_limit", "shares": 1,
                    "share_plan_eligible": True,
                }]},
            },
        ]
        result = summarize_tactical_dead_zone(rows)
        self.assertEqual(result["session_count"], 1)
        self.assertEqual(result["whole_lot_buy_session_count"], 1)
        self.assertTrue(result["sessions"][0]["bear_zero_budget_seen"])
        self.assertEqual(result["sessions"][0]["max_strategy_buy_signal_count"], 2)

    def test_deep_reference_is_not_counted_as_executable_buy(self):
        result = summarize_tactical_dead_zone([{
            "as_of": "2026-09-01",
            "execution": {"items": [{
                "side": "BUY", "source": "ratchet_next", "shares": 10,
            }]},
        }])
        self.assertEqual(result["zero_whole_lot_buy_session_count"], 1)


if __name__ == "__main__":
    unittest.main()
