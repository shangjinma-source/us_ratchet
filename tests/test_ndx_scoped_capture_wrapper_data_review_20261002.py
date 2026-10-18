import base64
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_forward_source_capture_scoped_20261002 as module
from test_ndx_forward_capture_wrapper_data_review_20261002 import fixture


def scoped_result(frontier, current, raw):
    evidence = {'source': {}, 'baseline': {}}
    mappings = {'source': current, 'baseline': {ticker: raw['baseline_' + ticker] for ticker in ('QQQ', 'SPY')}}
    for role, mapping in mappings.items():
        for ticker, blob in mapping.items():
            derived = b'Date,Close\n2026-10-01,100\n'
            evidence[role][ticker] = {'original_csv_bytes_base64': base64.b64encode(blob).decode(),
                'original_sha256': module.sha(blob), 'original_byte_count': len(blob),
                'original_row_count': 1, 'original_rows': [{'session': '2026-10-01'}],
                'scoped_csv_utf8': derived.decode(), 'scoped_sha256': module.sha(derived),
                'scoped_byte_count': len(derived), 'scope_start': '2026-10-01'}
    scoped = {role: {ticker: row['scoped_sha256'] for ticker, row in value.items()} for role, value in evidence.items()}
    plan = {'schema': 'FORWARD_SOURCE_CAPTURE_PLANNING_V1', 'capture_started_at_utc': 'start', 'observed_at_utc': 'end',
        'source_sha256': scoped['source'], 'baseline_sha256': scoped['baseline'], 'tzif_sha256': module.sha(raw['tzif']),
        'accounted_prefix_dates': ['2026-10-01'], 'last_observed_session_unchanged': '2026-09-24',
        'last_accounted_session_unchanged': '2026-10-01', 'month_first_semantics': 'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE',
        'classifications': [], 'timeliness_candidate': None, **dict.fromkeys(module.PLAN_FALSE, False)}
    return {'schema': 'FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1', 'scope_start': '2026-10-01', 'capture_plan': plan,
        'original_source_sha256': {t: module.sha(v) for t, v in mappings['source'].items()},
        'original_baseline_sha256': {t: module.sha(v) for t, v in mappings['baseline'].items()},
        'scoped_source_sha256': scoped['source'], 'scoped_baseline_sha256': scoped['baseline'], 'csv_scope_evidence': evidence,
        'frozen_capture_source_sha256': module.PINS['base_core'][1], 'full_original_bytes_preserved': True,
        **dict.fromkeys(('frozen_capture_consumed_full_original_csv', 'out_of_scope_ohlc_anomalies_repaired',
            'scope_chosen_from_prices', 'source_bytes_authenticated_by_this_module', 'old_failed_namespace_modified',
            'original_calendar_reverified', 'source_price_execution_verified', 'historical_first_observation_claimed',
            'fresh_observation', 'decision_eligible', 'candidate_seal_allowed', 'cohort_registration_allowed',
            'canonical_calendar_append_allowed', 'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
            'oos_recovery_completed'), False)}


class Tests(unittest.TestCase):
    def setUp(self):
        # Each fixture models a fresh CLI; restore the discovery import state afterward.
        isolation = patch.dict(module.sys.modules)
        isolation.start()
        self.addCleanup(isolation.stop)
        module.sys.modules.pop('backtest.ndx_forward_source_capture_scoped_research', None)
        module.sys.modules.pop('backtest.ndx_forward_source_capture_research', None)

    def test_original_scoped_hash_and_outer_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, refs, frontier, _ = fixture(Path(directory))
            frontier['known_accounted_rows'] = [{'session': '2026-10-01'}]
            current = {t: raw['baseline_' + t] + b'\n' for t in ('QQQ', 'SPY')}
            result = scoped_result(frontier, current, raw)
            module.validate_result(result, frontier, current, raw, 'start', 'end')
            for alter in (
                lambda r: r['csv_scope_evidence']['source']['QQQ'].update(scoped_csv_utf8='forged bytes'),
                lambda r: r['csv_scope_evidence']['source']['QQQ'].update(original_csv_bytes_base64=base64.b64encode(b'other original').decode()),
                lambda r: r.update(frozen_capture_consumed_full_original_csv=True),
                lambda r: r.update(candidate_seal_allowed=True),
            ):
                changed = copy.deepcopy(result); alter(changed)
                with self.assertRaises(ValueError): module.validate_result(changed, frontier, current, raw, 'start', 'end')

    def test_raw_failure_preserves_failed_v1_and_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); raw, refs, frontier, _ = fixture(root)
            base = root / 'base_core.py'; base.write_bytes(b'# fake base core')
            refs['base_core'] = {'path': str(base), 'sha256': module.sha(base.read_bytes())}
            old = root / 'data/cache/research/forward_source_capture_20261002_v1'
            old.mkdir(parents=True); (old / 'failure.json').write_bytes(b'original failed evidence')
            called = []
            def classify(**kwargs):
                called.append(kwargs); raise ValueError('synthetic scope failure')
            fake = SimpleNamespace(__file__=refs['core']['path'], plan_scoped_forward_source_capture=classify)
            def load(name):
                module.sys.modules['backtest.ndx_forward_source_capture_research'] = SimpleNamespace(__file__=str(base))
                return fake
            with patch.object(module, 'ROOT', root), patch.object(module, 'OUTPUT', root / 'new_output'), \
                    patch.object(module, 'PINS', {role: (ref['path'], ref['sha256']) for role, ref in refs.items()}), \
                    patch.dict(module.sys.modules, {}), patch.object(module.importlib, 'import_module', side_effect=load):
                with self.assertRaisesRegex(ValueError, 'synthetic scope'): module.run()
                self.assertEqual((old / 'failure.json').read_bytes(), b'original failed evidence')
                self.assertTrue((module.OUTPUT / 'failure.json').exists())
                for ticker in ('QQQ', 'SPY'):
                    self.assertEqual((module.OUTPUT / (ticker + '.csv')).read_bytes(), raw['baseline_' + ticker])
                    self.assertEqual(called[0]['source_csv_bytes'][ticker], raw['baseline_' + ticker])
                self.assertEqual((module.OUTPUT / 'New_York.tzif').read_bytes(), raw['tzif'])
                with self.assertRaisesRegex(ValueError, 'no retry'): module.run()
                self.assertEqual(len(called), 1)


if __name__ == '__main__': unittest.main()
