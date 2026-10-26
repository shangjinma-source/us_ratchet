"""Independent real-date barrier checks, isolated from provider event redundancy."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('exposure_gate', ROOT / 'scripts/assemble_old_continuous_inputs_v1.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SCHEMA = json.loads((ROOT / 'tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json').read_text())
DISTRIBUTIONS = SCHEMA['reusable_reviewed_action_candidates']['prior_distribution_events']


class IndependentGateTests(unittest.TestCase):
    def gate(self, ticker, day, quantity=1, sold=False):
        sid = next(s for s, m in SCHEMA['prepared_input_candidate']['metadata'].items() if m['ticker'] == ticker)
        envelope = {'prepared_input_candidate': {'metadata': {sid: {'ticker': ticker}},
                    'source_provenance': {sid: {'segments': []}}},
                    'provider_event_inventory': [], 'action_stream_missing': [],
                    'dated_identity_transitions': [], 'prior_distribution_events': DISTRIBUTIONS}
        arguments = {'decision_date': '2023-12-29', 'account_state': {'shares': {sid: quantity}}}
        return MODULE.exposure_gate(envelope, arguments, {'target_quantities': {sid: 0 if sold else quantity}}, day, day)

    def test_cash_and_mixed_merger_barriers(self):
        for ticker, day in [('SPLK', '2024-03-18'), ('ANSS', '2025-07-17'), ('WBA', '2025-08-28')]:
            with self.subTest(ticker=ticker):
                self.assertFalse(self.gate(ticker, day)['admitted'])

    def test_sols_known_distribution_without_provider_event(self):
        self.assertFalse(self.gate('HON', '2025-10-30')['admitted'])

    def test_zero_exposure_does_not_require_merger(self):
        self.assertTrue(self.gate('WBA', '2025-08-28', 0)['admitted'])

    def test_cmcsa_rights_on_january_second_not_fifth(self):
        result = self.gate('CMCSA', '2026-01-02')
        self.assertFalse(result['admitted'])
        event = next(e for e in result['unmapped_events'] if e.get('event_id') == 'CMCSA_VSNT_2026-01-02')
        self.assertEqual(event['timing'], 'AFTER_CLOSE')

    def test_all_reviewed_distributions_covered(self):
        for event in DISTRIBUTIONS:
            ticker = SCHEMA['prepared_input_candidate']['metadata'][event['parent_sid']]['ticker']
            with self.subTest(event=event['event_id']):
                result = self.gate(ticker, event['effective_date'])
                self.assertIn(event['event_id'], [e.get('event_id') for e in result['unmapped_events']])


if __name__ == '__main__':
    unittest.main()
