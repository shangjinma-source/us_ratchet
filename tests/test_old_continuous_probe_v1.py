import unittest
from scripts.run_old_continuous_probe_v1 import build_candidate, validate_scope

class OldRunnerTests(unittest.TestCase):
    def test_forged_empty_envelope_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ENVELOPE_MUST_MATCH'):
            build_candidate({})

    def test_real_schema_preserves_all_31_monthly_inputs(self):
        from pathlib import Path
        from scripts.assemble_old_continuous_inputs_v1 import assemble
        envelope = assemble(Path('tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json'))
        candidate = build_candidate(envelope)
        self.assertEqual(candidate['monthly_inputs'], envelope['monthly_inputs'])
        validate_scope(candidate)
        self.assertIsNone(envelope['prepared_input_candidate']['distribution_events'])

    def test_shortened_scope_rejected(self):
        with self.assertRaisesRegex(ValueError, 'FROZEN_CONTINUOUS'):
            validate_scope({'monthly_inputs': [], 'session_dates': []})

if __name__ == '__main__':
    unittest.main()
