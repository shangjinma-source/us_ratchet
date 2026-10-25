from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backtest.known_us_regular_boundary_guard import review_window, guarded_search_arguments
from scripts.prepare_known_us_boundary_inputs import load_registry, prepare_window


def registry():
    return dict(schema='KNOWN_US_REGULAR_BOUNDARIES_V1', reviewed_on='2026-10-25',
        knowledge_basis='RETROSPECTIVELY_REVIEWED_PRIMARY_SOURCES', boundaries=[
            dict(ticker=ticker, security_id=ticker + '-sid', market='US',
                 channel='ORDINARY_REGULAR_WAY', us_regular_start=start,
                 sources=[dict(url='https://example.test/official', path='official.html', sha256='a' * 64)])
            for ticker, start in [('FER', '2024-05-09'), ('GEHC', '2023-01-04')]])


def ending(day):
    last = date.fromisoformat(day)
    return [(last - timedelta(days=offset)).isoformat() for offset in reversed(range(253))]


def candidate(ticker):
    return dict(ticker=ticker, security_id=ticker + '-sid', training_closes=['10'] * 253)


class KnownOrdinaryBoundaryTests(unittest.TestCase):
    def test_fer_before_us_listing_is_excluded_despite_253_prices(self):
        dates = ending('2024-04-30')
        result = review_window(decision_date=dates[-1], training_dates=dates,
                               candidates=[candidate('FER')], registry=registry())
        self.assertEqual(result['excluded_security_ids'], ['FER-sid'])
        self.assertIn('NOT_YET_US_ORDINARY_LISTED_AT_DECISION', result['rows'][0]['reasons'])
        self.assertEqual(result['rows'][0]['valid_us_regular_observations'], 0)

    def test_when_issued_history_does_not_satisfy_ordinary_253(self):
        dates = ['2022-12-28', '2022-12-29', '2022-12-30', '2023-01-03']
        dates += [(date(2023, 1, 4) + timedelta(days=index)).isoformat() for index in range(249)]
        result = review_window(decision_date=dates[-1], training_dates=dates,
                               candidates=[candidate('GEHC')], registry=registry())
        row = result['rows'][0]
        self.assertEqual(row['pre_regular_dates'], dates[:4])
        self.assertEqual(row['valid_us_regular_observations'], 249)
        self.assertIn('INSUFFICIENT_253_VALID_US_ORDINARY_CLOSES', row['reasons'])

    def test_current_window_pass_is_narrow_and_uncovered_members_stay_uncertified(self):
        dates = ending('2026-10-14')
        result = review_window(decision_date=dates[-1], training_dates=dates,
                               candidates=[candidate('FER'), candidate('GEHC'), candidate('OTHER')], registry=registry())
        self.assertEqual(result['excluded_security_ids'], [])
        self.assertEqual(result['rows'][-1]['status'], 'NOT_COVERED_BY_KNOWN_BOUNDARIES')
        self.assertFalse(result['point_in_time_certified'])
        self.assertFalse(result['historical_observation_available_at_decision'])

    def test_missing_or_future_data_and_wrong_identity_fail_closed(self):
        dates, item = ending('2026-10-14'), candidate('FER')
        cases = [
            (dates[:-1], item),
            (dates[:-1] + ['2026-10-15'], item),
            (dates, dict(item, security_id='wrong')),
            (dates, dict(item, training_closes=['10'] * 252 + ['0'])),
            (dates, dict(item, training_closes=['10'] * 252 + [True])),
        ]
        for index, (training, candidate_row) in enumerate(cases):
            with self.subTest(index=index):
                result = review_window(decision_date='2026-10-14', training_dates=training,
                                       candidates=[candidate_row], registry=registry())
                self.assertTrue(result['excluded_security_ids'])

    def test_new_assembly_filters_all_search_fields_without_changing_original(self):
        dates = ending('2024-04-30')
        arguments = dict(decision_date=dates[-1], metadata={'FER-sid': dict(ticker='FER'),
            'OTHER-sid': dict(ticker='OTHER')}, prices={'FER-sid': '10', 'OTHER-sid': '20'},
            scenario_dates=dates[21::21],
            training_scenarios=[{'FER-sid': '2', 'OTHER-sid': '1'}] * 12)
        original = deepcopy(arguments)
        monthly = dict(decision_date=dates[-1], search_arguments=arguments)
        training = dict(training_dates=dates, candidates=[dict(ticker=ticker,
            security_id=ticker + '-sid', training_close=['10'] * 253) for ticker in ['FER', 'OTHER']])
        # The historical source preserves unresolved, already-excluded members.
        # They have no search ID and must not collide with each other as None.
        training['candidates'].extend([dict(ticker=ticker, security_id=None)
                                       for ticker in ['UNRESOLVED1', 'UNRESOLVED2']])
        result = prepare_window(monthly, training, registry())
        self.assertEqual(arguments, original)
        filtered = result['guarded_search_arguments']
        self.assertEqual(set(filtered['prices']), {'OTHER-sid'})
        self.assertEqual(set(filtered['metadata']), {'OTHER-sid'})
        self.assertTrue(all(set(row) == {'OTHER-sid'} for row in filtered['training_scenarios']))
        future_monthly = deepcopy(monthly)
        future_monthly['search_arguments']['scenario_dates'][-1] = '2024-05-01'
        with self.assertRaisesRegex(ValueError, 'SCENARIO_DATES_NOT_BOUND_TO_TRAINING_WINDOW'):
            prepare_window(future_monthly, training, registry())
        bad = deepcopy(arguments)
        bad['training_scenarios'][0]['extra'] = '1'
        with self.assertRaisesRegex(ValueError, 'SEARCH_INPUT_DOMAIN_MISMATCH'):
            guarded_search_arguments(bad, result['eligibility'])

    def test_changed_primary_source_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            raw = b'Official synthetic source'
            (root / 'official.html').write_bytes(raw)
            registered = registry()
            for boundary in registered['boundaries']:
                boundary['sources'][0]['sha256'] = hashlib.sha256(raw).hexdigest()
            (root / 'registry.json').write_text(json.dumps(registered), encoding='utf-8')
            load_registry(root, 'registry.json')
            (root / 'official.html').write_bytes(raw + b' modified')
            with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
                load_registry(root, 'registry.json')

    def test_actual_search_returns_must_use_the_reviewed_known_security_history(self):
        dates = ending('2026-10-14')
        arguments = dict(decision_date=dates[-1], metadata={'FER-sid': dict(ticker='FER')},
            prices={'FER-sid': '10'}, scenario_dates=dates[21::21],
            training_scenarios=[{'FER-sid': '1'} for _ in range(12)])
        monthly = dict(decision_date=dates[-1], search_arguments=arguments)
        training = dict(training_dates=dates, candidates=[dict(ticker='FER',
            security_id='FER-sid', training_close=['10'] * 253)])
        prepare_window(monthly, training, registry())
        arguments['training_scenarios'][3]['FER-sid'] = '2'
        with self.assertRaisesRegex(ValueError, 'KNOWN_SECURITY_SCENARIO_NOT_BOUND_TO_REVIEWED_CLOSES'):
            prepare_window(monthly, training, registry())


if __name__ == '__main__':
    unittest.main()
