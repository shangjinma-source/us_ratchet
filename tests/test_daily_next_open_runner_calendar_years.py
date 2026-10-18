"""Runner output integration with real yearly metric computation; no economic replay."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_current_quantity_v2_daily_next_open as runner


class DailyRunnerCalendarYearsTests(unittest.TestCase):
    def invoke(self, sessions, equities, status='COMPLETE', source_drift=False):
        temporary = tempfile.TemporaryDirectory(prefix='daily_years_test_', dir=runner.ROOT / 'tmp')
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        prepared = base / 'prepared.json'
        fixture_source = base / 'fixture_source.txt'
        fixture_source.write_bytes(b'initial')
        pins = {str(fixture_source): hashlib.sha256(b'initial').hexdigest()}
        prepared.write_text(json.dumps(dict(source_hashes=pins, ohlc={})), encoding='utf-8')
        output = base / 'output'
        ledger = [dict(date=day, equity=equity, external_flow='0')
                  for day, equity in zip(sessions[1:], equities)]
        result = dict(status=status, reason=None if status == 'COMPLETE' else 'MISSING_PRICE',
                      total_return='-1/10' if status == 'COMPLETE' else None,
                      drawdown={}, daily_ledger=ledger)
        argv = ['runner', '--prepared', str(prepared), '--output', str(output),
                '--initial-cash', '100', '--fee-bps', '0', '--slippage-bps', '0', '--execute']
        def book(**kwargs):
            if source_drift:
                fixture_source.write_bytes(b'changed')
            return result
        with patch('sys.argv', argv), \
             patch.object(runner, 'assemble_monthly_execution_inputs_v4', return_value=dict(session_dates=sessions)), \
             patch.object(runner, 'run_daily_next_open', side_effect=book):
            try:
                runner.main()
            except ValueError as error:
                return output, error
        return output, None

    def read(self, directory, name):
        return json.loads((directory / name).read_text(encoding='utf-8'))

    def test_cross_year_uses_continuous_previous_equity(self):
        output, error = self.invoke(['2023-12-29', '2024-01-02', '2024-12-31', '2025-01-02'],
                                    ['80', '120', '90'])
        self.assertIsNone(error)
        years = self.read(output, 'calendar_year_metrics.json')
        self.assertEqual(years['years'][0]['cumulative_return'], '1/5')
        self.assertEqual(years['years'][1]['opening_equity'], '120')
        self.assertEqual(years['years'][1]['cumulative_return'], '-1/4')
        self.assertFalse(years['calendar_authenticated'])
        self.assertFalse(years['capital_reset_each_year'])
        metrics = self.read(output, 'metrics.json')
        self.assertFalse(metrics['calendar_year_returns_not_computed'])
        self.assertEqual(metrics['calendar_year_metrics'], years)
        self.assertIn('backtest/continuous_calendar_year_metrics.py',
                      self.read(output, 'preflight.json')['source_hashes'])

    def test_midyear_start_keeps_partial_label(self):
        output, error = self.invoke(['2024-07-31', '2024-08-01'], ['90'])
        self.assertIsNone(error)
        row = self.read(output, 'calendar_year_metrics.json')['years'][0]
        self.assertEqual(row['scope'], 'PARTIAL_YEAR_ON_SUPPLIED_CALENDAR')
        self.assertFalse(row['full_year_coverage_verified'])
        self.assertEqual(row['cumulative_return'], '-1/10')

    def test_blocked_book_does_not_publish_yearly_results(self):
        output, error = self.invoke(['2023-12-29', '2024-01-02', '2024-01-03'], ['90'], 'BLOCKED')
        self.assertIsNone(error)
        self.assertFalse((output / 'calendar_year_metrics.json').exists())
        metrics = self.read(output, 'metrics.json')
        self.assertTrue(metrics['calendar_year_returns_not_computed'])
        self.assertNotIn('calendar_year_metrics', metrics)
        self.assertIsNone(metrics['annualized_return'])
        self.assertEqual(self.read(output, 'terminal.json')['status'], 'BLOCKED')

    def test_false_complete_missing_session_fails_real_coverage_validation(self):
        output, error = self.invoke(['2023-12-29', '2024-01-02', '2024-01-03'], ['90'])
        self.assertRegex(str(error), 'INCOMPLETE_OR_DUPLICATED_LEDGER')
        self.assertFalse((output / 'calendar_year_metrics.json').exists())
        self.assertFalse((output / 'metrics.json').exists())
        self.assertEqual(self.read(output, 'terminal.json')['status'], 'ERROR')

    def test_source_drift_still_blocks_publication(self):
        output, error = self.invoke(['2023-12-29', '2024-01-02'], ['90'], source_drift=True)
        self.assertRegex(str(error), 'SOURCE_CHANGED_DURING_RUN')
        self.assertFalse((output / 'calendar_year_metrics.json').exists())
        self.assertFalse((output / 'metrics.json').exists())
        self.assertEqual(self.read(output, 'terminal.json')['status'], 'ERROR')


if __name__ == '__main__':
    unittest.main()
