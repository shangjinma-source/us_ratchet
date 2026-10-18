import unittest
from unittest.mock import patch

from scripts import ndx_same_execution_dual_benchmark_probe as probe


class SameExecutionProbeTests(unittest.TestCase):
    def test_loaded_source_drift_rejected_before_data_or_long_simulation(self):
        with patch.object(probe, '_LOADED_PROBE_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'changed since import'):
                probe.run()


if __name__ == '__main__':
    unittest.main()
