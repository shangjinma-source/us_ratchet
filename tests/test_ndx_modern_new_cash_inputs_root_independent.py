"""Independent whole-operation source drift boundary, no economics replay."""
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_modern_new_cash_inputs_research as loader


class ModernSourceOperationBoundaryTests(unittest.TestCase):
    def test_inputs_drift_after_historical_raw_read_is_rejected(self):
        original = Path.read_bytes
        input_path = loader.ROOT / loader.BOUND['inputs'][0]
        first_raw = loader.ROOT / 'data/cache/research/multidecision_account_execution_20261003_v1/tracks/08/raw_result.json'
        historical_started = False
        detected_read = False

        def read(path):
            nonlocal historical_started, detected_read
            raw = original(path)
            if path == first_raw:
                historical_started = True
            if historical_started and path == input_path:
                detected_read = True
                return raw + b' '
            return raw

        with patch.object(Path, 'read_bytes', read):
            with self.assertRaisesRegex(ValueError, 'Pinned source bytes changed'):
                loader.load_historical_frozen_states()
        self.assertTrue(historical_started)
        self.assertTrue(detected_read)

    def test_input_namespace_drift_after_historical_raw_read_is_rejected(self):
        original_read = Path.read_bytes
        original_inventory = Path.iterdir
        input_folder = (loader.ROOT / loader.BOUND['inputs'][0]).parent
        first_raw = loader.ROOT / 'data/cache/research/multidecision_account_execution_20261003_v1/tracks/08/raw_result.json'
        historical_started = False

        def read(path):
            nonlocal historical_started
            raw = original_read(path)
            if path == first_raw:
                historical_started = True
            return raw

        def inventory(path):
            items = list(original_inventory(path))
            if historical_started and path == input_folder:
                items.append(path / 'unexpected_concurrent_artifact.json')
            return iter(items)

        with patch.object(Path, 'read_bytes', read), patch.object(Path, 'iterdir', inventory):
            with self.assertRaisesRegex(ValueError, 'namespace inventory'):
                loader.load_historical_frozen_states()
        self.assertTrue(historical_started)


if __name__ == '__main__':
    unittest.main()
