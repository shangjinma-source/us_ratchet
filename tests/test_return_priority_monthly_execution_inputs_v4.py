from copy import deepcopy
import unittest
from backtest.return_priority_monthly_execution_inputs import BASIS
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4


class V4AssemblyTests(unittest.TestCase):
    def fixture(self):
        days = ['2026-01-02', '2026-01-05', '2026-01-06']
        metadata = {s: dict(ticker=s, issuer_id=s) for s in ('P', 'C')}
        return dict(session_dates=days, metadata=metadata,
            source_hashes={'raw': 'a'*64, 'alternate': 'b'*64, 'official': 'c'*64,
                           'backtest/return_priority_fresh_cash_quantity_search.py': 'd'*64},
            source_provenance={s: dict(whole_source='raw', price_basis=BASIS) for s in metadata},
            ohlc={s: {d: dict(close='10') for d in days} for s in metadata},
            windows=[dict(decision_date=days[0], search_arguments=dict(decision_date=days[0],
                prices={'P': '10'}, metadata={'P': metadata['P']}, training_scenarios=[{'P': '1'}]))],
            split_events_reference_only=[], identity_migrations=[], cash_stock_merger_events=[], fractional_settlements={},
            distribution_events=[dict(event_id='spin', effective_date=days[1], timing='AFTER_CLOSE',
                parent_sid='P', post_parent_sid='P', child_sid='C', parent_ratio='1', child_ratio='1/25',
                source_references=['official'])], distribution_fractional_cash_values={})

    def test_wires_distributions_separately_without_mutation(self):
        p = self.fixture(); before = deepcopy(p)
        r = assemble_monthly_execution_inputs_v4(p)
        self.assertEqual(p, before)
        self.assertEqual(r['actions'], [])
        self.assertEqual(r['distribution_events'], p['distribution_events'])
        self.assertEqual(r['provider_actions'][0]['type'], 'distribution')
        self.assertEqual(r['provider_actions'][0]['timing'], 'AFTER_CLOSE')

    def test_exact_dated_source_segment_and_missing_gap(self):
        p = self.fixture()
        p['source_provenance']['P'] = dict(price_basis=BASIS, segments=[
            dict(start='2026-01-02', end='2026-01-02', source_path='alternate'),
            dict(start='2026-01-05', end='2026-01-06', source_path='raw')])
        r = assemble_monthly_execution_inputs_v4(p)
        quote = next(q for q in r['monthly_inputs'][0]['valuation_quotes'] if q['security_id'] == 'P')
        self.assertEqual(quote['source_references'], ['alternate'])
        self.assertNotIn('whole_source', r['source_provenance']['P'])
        p['source_provenance']['P']['segments'][1]['start'] = '2026-01-06'
        with self.assertRaisesRegex(ValueError, 'MISSING_OR_OVERLAPPING_SOURCE_SEGMENT'):
            assemble_monthly_execution_inputs_v4(p)

    def test_double_parent_adjustment_and_unpinned_event_rejected(self):
        p = self.fixture()
        p['split_events_reference_only'] = [dict(date='2026-01-05', security_id='P', new_shares=1, old_shares=2, source_references=['official'])]
        with self.assertRaisesRegex(ValueError, 'DOUBLE_APPLIED_PARENT_ACTION'):
            assemble_monthly_execution_inputs_v4(p)
        p = self.fixture(); p['distribution_events'][0]['source_references'] = ['unknown']
        with self.assertRaisesRegex(ValueError, 'UNPINNED_DISTRIBUTION_EVENT'):
            assemble_monthly_execution_inputs_v4(p)

    def test_fractional_cash_evidence_must_be_pinned(self):
        p = self.fixture()
        p['distribution_fractional_cash_values'] = {'spin': {'CHILD_FRACTIONAL_CASH_RIGHT':
            dict(amount='1', security_id='C', units='1/2', known_asof='2026-01-05', source_references=['unrecorded'])}}
        with self.assertRaisesRegex(ValueError, 'UNPINNED_DISTRIBUTION_FRACTION_VALUE'):
            assemble_monthly_execution_inputs_v4(p)
        p['distribution_fractional_cash_values']['spin']['CHILD_FRACTIONAL_CASH_RIGHT']['source_references'] = ['official']
        self.assertEqual(assemble_monthly_execution_inputs_v4(p)['distribution_fractional_cash_values'], p['distribution_fractional_cash_values'])

    def test_unsupported_conversion_becomes_explicit_execution_guard(self):
        p = self.fixture(); p['distribution_events'] = []
        p['unsupported_conversions'] = [dict(date='2026-01-05', old_sid='P', new_sid='C', source_references=['official'])]
        result = assemble_monthly_execution_inputs_v4(p)
        self.assertEqual(result['actions'][0]['type'], 'UNSUPPORTED_SECURITY_CONVERSION')
        self.assertEqual(result['provider_actions'][0]['security_id'], 'P')
        self.assertEqual(result['unsupported_conversions'], p['unsupported_conversions'])
        from backtest.return_priority_limit_book_v4 import run_limit_book_v4
        book = run_limit_book_v4(session_dates=p['session_dates'], orders=[], ohlc=p['ohlc'],
                                initial_cash='0', initial_shares={'P': 2}, events=result['actions'])
        self.assertEqual(book['reason'], 'UNMODELLED_HELD_OR_ORDERED_ACTION')
        self.assertEqual(book['shares'], {'P': 2})

    def test_supported_conversion_requires_model_and_no_duplicate_guard(self):
        p = self.fixture(); p['distribution_events'] = []
        p['supported_conversions'] = [dict(type='ads_conversion', date='2026-01-05', event_id='ads',
            security_id='P', new_security_id='C', new_shares='1', old_shares='2',
            delivery_model='DTC_BENEFICIAL_INTERESTS', source_references=['official'])]
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_DTC_ACCOUNT_MODEL_REQUIRED'):
            assemble_monthly_execution_inputs_v4(p)
        p['account_model'] = 'DTC_BENEFICIAL_INTERESTS'
        result = assemble_monthly_execution_inputs_v4(p)
        self.assertEqual(result['actions'][0]['type'], 'ads_conversion')
        self.assertEqual(result['account_model'], p['account_model'])
        p['unsupported_conversions'] = [dict(date='2026-01-05', old_sid='P', new_sid='C', source_references=['official'])]
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_CONVERSION_OR_OTHER_ACTION'):
            assemble_monthly_execution_inputs_v4(p)


if __name__ == '__main__':
    unittest.main()
