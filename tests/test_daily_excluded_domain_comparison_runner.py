import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
from unittest.mock import patch
from scripts import run_daily_excluded_domain_comparison as runner


class ComparisonRunnerTests(unittest.TestCase):
    def test_actual_253_status_adapter_preserves_prices_and_rejects_identity_drift(self):
        days = [(date(2023, 1, 1)+timedelta(days=i)).isoformat() for i in range(253)]
        prices = [str(100+i) for i in range(253)]
        row = dict(security_id='A', ticker='AAA', issuer_id='issuer-a', status='DRAFT_CONDITIONAL_INPUT_COMPUTED',
            training_close=prices, decision_cost=prices[-1], identity_history_guard=dict(
                status='READY_CONDITIONAL_IDENTITY_HISTORY', window_dates=days, missing_or_invalid_dates=[],
                security_id='A', ticker='AAA', decision_date=days[-1], required_closes=253,
                valid_regular_closes=253, pre_regular_dates=[], reasons=[]))
        window = dict(decision_cutoff=days[-1], training_dates=days, candidates=[row])
        arguments = dict(decision_date=days[-1], scenario_dates=days[21::21], prices={'A': prices[-1]},
            metadata={'A': dict(ticker='AAA', issuer_id='issuer-a')},
            training_scenarios=[{'A': str(Fraction(prices[i+21])/Fraction(prices[i]))} for i in range(0,252,21)])
        monthly = [dict(decision_date=days[-1], search_arguments=arguments)]
        original = deepcopy(window)
        adapted = runner.simple_training_windows([window], monthly)[0]
        self.assertEqual(runner.validate_training(window=adapted, arguments=arguments, calendar=days), {'A': Fraction(352,100)})
        self.assertEqual(window, original)
        self.assertEqual(adapted['candidates'][0]['training_close'], prices)
        self.assertEqual(adapted['candidates'][0]['source_candidate_status'], 'DRAFT_CONDITIONAL_INPUT_COMPUTED')
        row['identity_history_guard']['security_id'] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'IDENTITY_GUARD'):
            runner.simple_training_windows([window], monthly)

    def setup_input(self):
        temporary = tempfile.TemporaryDirectory(prefix='daily_four_test_', dir=runner.ROOT / 'tmp')
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        def save(name, value, binary=False):
            path = directory / name
            path.write_bytes(value if binary else json.dumps(value).encode())
            return path.relative_to(runner.ROOT).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()
        dates = ['2023-12-29', '2024-12-31', '2025-01-02']
        schedule, schedule_sha = save('schedule.json', dict(session_dates=dates,
            closes={d: d+'T16:00:00-05:00' for d in dates}, review_reference='synthetic', source_hashes={}))
        rows = [dict(decision_date=d, snapshot=dict(observed_at=d+'T16:01:00-05:00', review_reference='synthetic', histories={})) for d in dates]
        snapshots, snapshot_sha = save('snapshots.gz', gzip.compress('\n'.join(json.dumps(r) for r in rows).encode()), True)
        manifest, manifest_sha = save('manifest.json', dict(snapshot_count=3, snapshot_sha256=snapshot_sha, source_hashes={}))
        prepared, _ = save('prepared.json', dict(experiment_scope=runner.SCOPE, excluded_issuers=['issuer:0001075124'],
            source_hashes={schedule: schedule_sha, snapshots: snapshot_sha, manifest: manifest_sha},
            session_dates=dates, windows=[], ohlc={}, risk_history_manifest=manifest, risk_history_snapshots=snapshots))
        return directory, prepared, schedule, dates

    def invoke(self, execute=False, arm='all', blocked=False, drift=False, baseline=False):
        directory, prepared, schedule, dates = self.setup_input()
        output = directory / 'output'
        argv = ['runner', '--prepared', prepared, '--schedule', schedule, '--output', str(output),
                '--arm', arm, '--fee-bps', '0', '--slippage-bps', '0'] + (['--execute'] if execute else [])
        if baseline:
            argv.extend(['--baseline-outcome', 'not-read-until-safe-arm.json'])
        calls = []
        def kernel(name):
            def run(**kwargs):
                self.assertEqual(kwargs['initial_cash'], '20000')
                self.assertNotIn('mutation', kwargs['assembled'])
                kwargs['assembled']['mutation'] = name
                calls.append(name)
                if name in ('R1', 'R2'):
                    self.assertEqual(kwargs['policy'], name)
                    resolved = kwargs['history_resolver'](decision_date=dates[0], target_quantities={}, monthly_decision_date=dates[0], count=21)
                    self.assertEqual(resolved['observed_at'], dates[0]+'T16:01:00-05:00')
                kwargs['progress'](dict(decision_date=dates[0]))
                if drift:
                    (runner.ROOT / schedule).write_text('{}')
                return dict(status='BLOCKED' if blocked else 'COMPLETE', reason='fixture' if blocked else None,
                    total_return=None if blocked else '2/25', drawdown={}, daily_ledger=[
                        dict(date=dates[1], equity='24000', external_flow='0'),
                        dict(date=dates[2], equity='21600', external_flow='0')])
            return run
        with patch('sys.argv', argv), patch.object(runner, 'assemble_monthly_execution_inputs_v4',
                return_value=dict(session_dates=dates, monthly_inputs=[])), \
             patch.object(runner, 'run_daily_next_open', side_effect=kernel('B0')), \
             patch.object(runner, 'run_simple253_next_open', side_effect=kernel('B1')), \
             patch.object(runner, 'run_risk_next_open', side_effect=lambda **kw: kernel(kw['policy'])(**kw)):
            try:
                runner.main()
            except ValueError as error:
                return output, calls, error
        return output, calls, None

    def test_default_preflight_never_calls_book(self):
        output, calls, error = self.invoke()
        self.assertIsNone(error); self.assertEqual(calls, [])
        self.assertEqual(json.loads((output/'terminal.json').read_text())['status'], 'PREFLIGHT_ONLY')
        self.assertFalse((output/'B0').exists())

    def test_four_arms_use_fresh_states_and_continuous_years(self):
        output, calls, error = self.invoke(execute=True)
        self.assertIsNone(error); self.assertEqual(calls, list(runner.ARMS))
        for arm in runner.ARMS:
            years = json.loads((output/arm/'calendar_year_metrics.json').read_text())['years']
            self.assertEqual(years[1]['opening_equity'], '24000')
            self.assertEqual(years[1]['cumulative_return'], '-1/10')
            self.assertTrue((output/arm/'progress.jsonl').exists())

    def test_single_blocked_arm_has_no_full_year_results(self):
        output, calls, error = self.invoke(execute=True, arm='R2', blocked=True)
        self.assertIsNone(error); self.assertEqual(calls, ['R2'])
        self.assertFalse((output/'R2'/'calendar_year_metrics.json').exists())
        self.assertFalse((output/'B0').exists())
        self.assertEqual(json.loads((output/'terminal.json').read_text())['status'], 'INCOMPLETE')

    def test_source_drift_stops_remaining_arms_and_no_metrics(self):
        output, calls, error = self.invoke(execute=True, drift=True)
        self.assertRegex(str(error), 'SOURCE_DRIFT'); self.assertEqual(calls, ['B0'])
        self.assertFalse((output/'B0'/'metrics.json').exists())
        self.assertEqual(json.loads((output/'terminal.json').read_text())['status'], 'ERROR')

    def test_existing_baseline_cannot_accidentally_rerun_b0(self):
        output, calls, error = self.invoke(execute=True, baseline=True)
        self.assertRegex(str(error), 'EXISTING_BASELINE_REQUIRES_SINGLE_NON_B0_ARM')
        self.assertEqual(calls, [])


if __name__ == '__main__': unittest.main()
