"""Use a genuinely generated monthly target in the execution evidence provider."""
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import json
from copy import deepcopy
from core.strategy_account_ledger import canonical
import test_split_monthly_factory_20261105 as fixture


class Tests(unittest.TestCase):
    def test_generated_target_can_capture_execution_evidence(self):
        with TemporaryDirectory() as folder:
            monthly, store, _ = fixture.Tests().case(folder)
            provider = monthly.execution_provider.__self__
            market = next(cell.cell_contents for cell in provider.market.capture.__closure__
                          if hasattr(cell.cell_contents, 'fetch'))
            original_fetch = market.fetch
            def complete_minutes(ticker):
                document = json.loads(original_fetch(ticker))
                series = document['chart']['result'][0]
                opening = series['meta']['currentTradingPeriod']['regular']['start']
                last = series['meta']['regularMarketTime']
                series['timestamp'] = list(range(opening, last, 60))
                count = len(series['timestamp'])
                series['indicators']['quote'][0] = {
                    key: [value] * count for key, value in
                    dict(open=10, high=11, low=9, close=10, volume=10).items()}
                return canonical(document)
            market.fetch = complete_minutes
            before = store.read()
            with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')):
                target = monthly.generate(event_id='execution-target', reason='INITIAL',
                    expected_revision=before['revision'], previous_target_id=None)
                result = monthly.execution_provider(before, target)
            self.assertIn('marks', result)
            self.assertIn('limits', result)
            self.assertEqual(result['marks']['B']['unit_id'], 'new')
            self.assertEqual(store.read(), before)
            package, historical = provider.training()
            manifest_only = dict(files={provider.manifest_path: package['files'][provider.manifest_path]},
                source_hashes={provider.manifest_path: package['source_hashes'][provider.manifest_path]}, documents={})
            changed = deepcopy(historical)
            changed['decision_date'] = '2000-01-01'
            with self.assertRaisesRegex(ValueError, 'MONTHLY_EXECUTION_HISTORY_CHANGED'):
                provider._assemble(before, manifest_only, changed, execution_only=True,
                    target_quantities=target['payload']['target_quantities'])
            manifest_only['files'][provider.manifest_path] = b'changed'
            with self.assertRaisesRegex(ValueError, 'MONTHLY_EXECUTION_SOURCE_CHANGED'):
                provider._assemble(before, manifest_only, historical, execution_only=True,
                    target_quantities=target['payload']['target_quantities'])
            self.assertEqual(store.read(), before)


if __name__ == '__main__':
    unittest.main()
