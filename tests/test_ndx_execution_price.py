import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data.ndx_execution_price import (
    NdxExecutionPriceError,
    execution_cache_path,
    load_verified_execution_cache,
    write_execution_cache,
)


class NdxExecutionPriceTests(unittest.TestCase):
    def test_execution_cache_is_purpose_locked_and_hash_verified(self):
        bars = pd.DataFrame([
            {"Date": "2024-05-30", "Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 10},
            {"Date": "2024-05-31", "Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 11},
        ])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = write_execution_cache(
                root, "TEST", bars, source_mode="sina_raw_daily",
                requested_begin="2024-05-30", requested_end="2024-06-02",
            )
            loaded, verified = load_verified_execution_cache(
                root, "TEST", requested_end="2024-06-02",
            )
            self.assertEqual(len(loaded), 2)
            self.assertTrue(manifest["whole_lot_execution_use_only"])
            self.assertFalse(verified["valuation_use_only"])
            self.assertFalse(verified["return_usage_allowed"])
            path = execution_cache_path(root, "TEST")
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(NdxExecutionPriceError):
                load_verified_execution_cache(root, "TEST", requested_end="2024-06-02")


if __name__ == "__main__":
    unittest.main()
