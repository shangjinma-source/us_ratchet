from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_strategy_account_target_inputs import setup
from data.strategy_continuous32_target_decision import decide_target, validate_result, REQUIRED_PINS
from backtest.continuous_guided_account_decision import original_search

ROOT = Path(__file__).resolve().parents[1]


class IndependentContinuousTests(unittest.TestCase):
    def test_original_search_only_once_and_inherited_result_not_relabelled(self):
        with TemporaryDirectory() as folder:
            args = setup(folder)
            for name in REQUIRED_PINS:
                raw = (ROOT / name).read_bytes()
                args["source_package"]["files"][name] = raw
                args["source_package"]["source_hashes"][name] = sha256(raw).hexdigest()
            before = deepcopy(args)
            with patch("backtest.continuous_guided_account_decision.original_search", wraps=original_search) as search:
                decision = decide_target(**args)
                search.assert_called_once()
                payload = decision["payload"]
                result = payload["search_result"]
                self.assertEqual(result["continuous_comparison"]["inherited_saved_result"]["method_version"],
                                 "EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2")
                self.assertEqual(validate_result(result, payload["input_binding"]["search_arguments"]),
                                 payload["target_quantities"])
                search.assert_called_once()  # Validation did not start base research again.
            self.assertEqual(before, args)
            self.assertTrue(decision["execution_blocked"])
            self.assertFalse(decision["account_mutated"])
            self.assertFalse(decision["orders_created"])
            bad = deepcopy(result)
            bad["global_optimum_established"] = True
            with self.assertRaisesRegex(ValueError, "CONTINUOUS32_RESULT_CHANGED"):
                validate_result(bad, payload["input_binding"]["search_arguments"])


if __name__ == "__main__":
    unittest.main()
