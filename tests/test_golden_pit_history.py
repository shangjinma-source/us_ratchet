from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from api.server import _golden_pit_review_payload


def _snapshot(day: str, limit: float) -> dict:
    return {
        "ts": f"{day}T16:00:00",
        "snapshot_id": f"snapshot-{day}-{limit}",
        "as_of": day,
        "market": {"regime": "NEUTRAL", "items": []},
        "symbols": [{
            "ticker": "NVDA",
            "market_time": f"{day} 16:00:00",
            "tactical": {"stock_regime": "NEUTRAL", "regime": "NEUTRAL"},
        }],
        "execution": {"items": [{
            "source": "tactical_limit",
            "ticker": "NVDA",
            "action": "PLACE_LIMIT",
            "side": "BUY",
            "status": "pending",
            "limit": limit,
            "live_price": limit + 5,
        }]},
    }


class GoldenPitHistoryTests(unittest.TestCase):
    def test_review_scans_older_rows_beyond_physical_tail_limit(self):
        snapshots = [_snapshot("2026-07-10", 190.0), _snapshot("2026-07-14", 202.22)]
        dates = pd.to_datetime(["2026-07-10", "2026-07-11", "2026-07-14"])
        bars = pd.DataFrame({
            "Open": [190.0, 192.0, 202.0],
            "High": [195.0, 196.0, 210.0],
            "Low": [189.0, 191.0, 201.0],
            "Close": [193.0, 195.0, 208.0],
        }, index=dates)
        with patch("api.server.iter_advice_snapshots", return_value=iter(snapshots)), \
                patch("api.server._bars_for", return_value=bars):
            result = _golden_pit_review_payload(object(), limit=1)

        self.assertEqual(result["summary"]["snapshot_count"], 2)
        self.assertEqual(result["summary"]["candidate_snapshot_count"], 2)
        self.assertEqual(result["summary"]["candidate_count"], 2)
        self.assertEqual(result["summary"]["oldest_bar_date"], "2026-07-10")
        self.assertEqual(result["summary"]["latest_bar_date"], "2026-07-14")
        self.assertEqual(len(result["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
