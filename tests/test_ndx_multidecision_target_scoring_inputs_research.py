from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
import unittest

from backtest import ndx_multidecision_target_scoring_inputs_research as subject
from backtest import ndx_nav_usd_observation_alignment_research as alignment_core


def fixture(missing_day=None):
    calendar = []
    day = date(2024, 1, 1)
    while day <= date(2026, 8, 31):
        if day.weekday() < 5:
            calendar.append(day.isoformat())
        day += timedelta(days=1)
    sessions = calendar[calendar.index(subject.CUTOFFS[0]) - 504:]
    nav_ref = dict(path='synthetic-nav', sha256='a' * 64)
    fx_ref = dict(path='synthetic-fx', sha256='b' * 64)
    nav_rows = [dict(date=day, nav_cny_decimal=str(100 + index), available_at=None,
                     source_reference=nav_ref) for index, day in enumerate(calendar)]
    fx_rows = [dict(date=day, rate_decimal=None if day == missing_day else '1',
                    rate_literal='ND' if day == missing_day else '1',
                    status='NOT_AVAILABLE_ND' if day == missing_day else 'REPORTED_RATE',
                    historical_available_at=None, source_reference=fx_ref) for day in calendar]
    context = dict(rate_direction='CNY_PER_USD', historical_available_at_verified=False,
                   page_release_label='Synthetic only', source_references={'china_history': {'raw': fx_ref}},
                   limitations=['CURRENT_PAGE_VINTAGE_NOT_HISTORICAL_RELEASE_ARCHIVE',
                                'OBSERVATION_DATE_NOT_PUBLICATION_TIMESTAMP',
                                'NOON_BUYING_NOT_CLOSE_OR_EXECUTABLE_FX'])
    alignment = alignment_core.align_nav_usd_observations(
        session_dates=sessions, nav_rows=nav_rows, fx_rows=fx_rows,
        nav_reference=nav_ref, fx_reference=fx_ref, fx_context=context)
    return dict(alignment=alignment, alignment_reference=dict(path='synthetic-alignment', sha256='c' * 64),
                reference_calendar=calendar, contract=deepcopy(subject.CONTRACT))


def resign(alignment):
    alignment['content_sha256'] = subject.digest({k: v for k, v in alignment.items() if k != 'content_sha256'})


class Tests(unittest.TestCase):
    def test_original_csv_and_html_row_pointer_shapes(self):
        args = fixture()
        alignment = args['alignment']
        for i, row in enumerate(alignment['nav_rows_preserved']):
            row['source_reference'] = dict(alignment['nav_reference'], row_index=i, csv_record_number=i + 2)
        for i, row in enumerate(alignment['fx_rows_preserved']):
            row['source_reference'] = dict(alignment['fx_context_preserved']['source_references']['china_history']['raw'], table_row_index=i, html_line=1384 + i)
        # Deep copies in the saved per-session observations retain the same row pointers.
        for row in alignment['rows']:
            nav = row['nav_observation']
            nav['original_row'] = deepcopy(alignment['nav_rows_preserved'][nav['original_row_index']])
            for role in ('same_date', 'backward_valid'):
                fx = row['session_fx'][role]
                if fx is not None:
                    fx['original_row'] = deepcopy(alignment['fx_rows_preserved'][fx['original_row_index']])
        resign(alignment)
        subject.prepare_target_scoring_inputs(**args)
        alignment['nav_rows_preserved'][0]['source_reference']['row_index'] = True
        resign(alignment)
        with self.assertRaises(ValueError):
            subject.prepare_target_scoring_inputs(**args)

    def test_both_modes_independent_return_and_all_window_endpoints(self):
        args = fixture()
        before = deepcopy(args)
        result = subject.prepare_target_scoring_inputs(**args)
        self.assertEqual(args, before)
        self.assertEqual([mode['mode'] for mode in result['modes']], list(subject.MODES))
        dates = result['session_dates']
        original_index = args['reference_calendar'].index(dates[0])
        for mode in result['modes']:
            self.assertEqual(mode['return_slots'][0]['return_exact'], str(Fraction(1, 100 + original_index)))
            for decision in mode['decisions']:
                left = dates.index(decision['cutoff']) - 504
                self.assertEqual(len(decision['required_price_dates']), 505)
                self.assertTrue(decision['complete_thirteen_window_numeric_supply'])
                self.assertFalse(decision['scoring_allowed'])
                for ordinal, window in enumerate(decision['windows']):
                    self.assertEqual(window['training_freeze_close'], dates[left + 21 * ordinal + 126])
                    self.assertEqual(window['evaluation_last_return_end'], dates[left + 21 * ordinal + 252])

    def test_nd_keeps_both_adjacent_returns_and_blocks_full13(self):
        args = fixture('2026-03-31')
        result = subject.prepare_target_scoring_inputs(**args)
        strict, backward = result['modes']
        index = result['session_dates'].index('2026-03-31')
        self.assertIsNone(strict['return_slots'][index - 1]['return_exact'])
        self.assertIsNone(strict['return_slots'][index]['return_exact'])
        self.assertIsNotNone(backward['return_slots'][index]['return_exact'])
        self.assertFalse(strict['decisions'][0]['complete_thirteen_window_numeric_supply'])
        self.assertEqual(len(strict['decisions'][0]['windows']), 13)
        self.assertTrue(backward['decisions'][0]['complete_thirteen_window_numeric_supply'])

    def test_resealed_source_scope_forward_date_and_missing_mode_rejected(self):
        args = fixture()
        for mutate in (
            lambda d: d.update(point_in_time_verified=0),
            lambda d: d['modes'].pop(),
            lambda d: d['rows'][0]['conversions'][subject.MODES[0]].update(fx_date='2099-01-01'),
            lambda d: d['rows'].pop(4),
            lambda d: d['rows'][0].update(nav_date_fx_used_for_conversion=True),
        ):
            altered = deepcopy(args)
            mutate(altered['alignment'])
            resign(altered['alignment'])
            with self.assertRaises(ValueError):
                subject.prepare_target_scoring_inputs(**altered)


if __name__ == '__main__':
    unittest.main()
