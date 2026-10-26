import json
import unittest
from copy import deepcopy
from pathlib import Path
from scripts.assemble_old_continuous_inputs_v1 import assemble
from scripts.run_old_continuous_probe_v2 import gross_dividend_events, admit_reviewed_dividends, build_candidate
from scripts.run_old_continuous_probe_v1 import build_candidate as frozen_builder

class DividendRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envelope = assemble(Path('tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v2.json'))
        cls.review = json.loads(Path('tmp/old_window_exposed_actions_20261026_v1/review.json').read_text())

    def events(self, review=None):
        return gross_dividend_events(review or self.review, self.envelope, self.envelope['session_dates'])

    def test_official_nominal_paid_once_despite_two_adjusted_sources(self):
        events = self.events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['amount_per_share'], '1/25')
        self.assertEqual(len(self.review['rows'][0]['observed_provider_events']), 2)

    def test_missing_second_source_rejected(self):
        review = deepcopy(self.review)
        source = review['rows'][0]['observed_provider_events'][1]['source']
        del review['source_hashes'][source]
        with self.assertRaisesRegex(ValueError, 'UNBOUND|UNPINNED'):
            self.events(review)

    def test_changed_provider_payload_rejected(self):
        review = deepcopy(self.review)
        review['rows'][0]['observed_provider_events'][1]['provider_payload']['amount'] = '999'
        with self.assertRaisesRegex(ValueError, 'EXACT_ALL'):
            self.events(review)

    def test_unknown_non_dividend_still_blocks(self):
        sid = self.review['rows'][0]['security_id']
        gate = dict(unmapped_events=[dict(security_id=sid,date='2024-03-05',kind='split')], missing_action_streams=[])
        self.assertFalse(admit_reviewed_dividends(gate,self.review,self.events())['admitted'])

    def test_exact_frozen_builder_reused(self):
        self.assertIs(build_candidate, frozen_builder)

if __name__ == '__main__':
    unittest.main()
