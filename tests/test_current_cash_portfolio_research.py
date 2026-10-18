"""Synthetic-only dynamic budget tests; never read actual market artifacts."""
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.current_cash_portfolio_research import (
    CurrentCashPortfolioResearch, ResearchExpiredError, PreviewSourceError,
    normalize_cash, project_research_result, PINS, REGISTRATION,
    PANEL_PATH, PROPOSAL_PATH, RESULT_PATH, FROZEN_PATH, QUOTES,
    apply_exact_integer_projection, ProjectionBudgetExceededError,
    COMMISSION_CONFIRMATION, RESEARCH_VERSION,
)
from scripts.return_priority_latest_saved_snapshot_research import build_latest_saved_snapshot


def commission_confirmation():
    return dict(schema='USER_BROKER_COMMISSION_CONFIRMATION_V1', confirmation_status='USER_CONFIRMED',
                currency='USD', commission_fee_bps=0, minimum_commission_usd=0,
                other_charges_confirmed=False, historical_research_fee_bps=10,
                changes_historical_results=False, authorizes_broker_orders=False)


def synthetic_inputs():
    end = date(2026, 10, 12)
    calendar = [(end - timedelta(days=269-index)).isoformat() for index in range(270)]
    metadata, channels = [], []
    for index in range(6):
        ticker = f'S{index}'
        price = 1000 if index == 0 else 10
        metadata.append(dict(ticker=ticker, security_id=ticker, issuer_id=ticker, risk_chain=ticker,
                             assumption_role='CURRENT_CONDITIONAL_RESEARCH_ASSUMPTION', evidence_references=['synthetic']))
        channels.append(dict(ticker=ticker, values=[[price, price+1, price-1, price, 100] for _ in calendar]))
    return dict(
        panel=dict(calendar=calendar, stocks=channels, price_basis='SYNTHETIC'),
        current_proposal=dict(observation_date=calendar[-1], assumption_role='CURRENT_CONDITIONAL_RESEARCH_ASSUMPTION',
                              proposed_metadata=metadata, exclusions=[]),
        historical_result=dict(status='COMPLETE_CONDITIONAL_FINITE_FAMILY_COMPARISON', rankings=[
            {'rule': 'K6:RANK_TOP:EQUAL:EXPOSURE1'}, {'rule': 'K4:RANK_TOP:EQUAL:EXPOSURE1'}, {'rule': 'ALL_CASH_REFERENCE'}]),
        frozen_method_snapshot=dict(fee_bps=10, minimum_cash_buffer=100, fixed_seed='synthetic',
                                    risk_parameters=dict(min_single_weight='0.05', max_single_weight='0.5',
                                                         top_three_cap='0.8', min_neff_ratio='0.5', chain_cap='0.5')),
        accepted_tickers=[row['ticker'] for row in metadata], source_refs=['synthetic'])


class CurrentCashTests(unittest.TestCase):
    def repair_service(self):
        service = self.service()
        for channel, price in zip(service.inputs['panel']['stocks'], (1000, 700, 300, 100, 250, 500)):
            channel['values'] = [[price, price+1, price-1, price, 100] for _ in channel['values']]
        return service

    def test_exact_repair_precedes_lower_rule_and_preserves_original_coverage(self):
        service = self.repair_service()
        result = service.calculate(5000)
        self.assertEqual(len(result['stocks']), 6)
        self.assertEqual(result['rule_id'], 'K6:RANK_TOP:EQUAL:EXPOSURE1')
        self.assertTrue(result['integer_projection_search']['selected_rule_repaired'])
        self.assertEqual(result['integer_projection_search']['completed_neighborhood_evaluations'], 64)
        trace = result['search_coverage']['rule_application_trace']
        self.assertEqual(trace[0]['original_floor_status'], 'BLOCKED')
        self.assertEqual(trace[0]['integer_projection_status'], 'FEASIBLE')
        self.assertTrue(trace[0]['selected'])
        self.assertTrue(all(not row['selected'] for row in trace[1:]))
        self.assertEqual(result['search_coverage']['per_k_scope'], 'ORIGINAL_FLOOR_ONLY_NOT_REPAIRED_SEARCH_COVERAGE')
        self.assertFalse(result['historical_performance_inherited'])
        exact = result['budget_identity_exact']
        self.assertEqual(Fraction(exact['entered_cash']), sum(Fraction(exact[key]) for key in ('stock_notional', 'fees', 'residual_cash')))
        self.assertLessEqual(Fraction(exact['stock_notional']), 4900)
        self.assertTrue(service.calculate('5000')['cache_hit'])

    def test_incomplete_neighborhood_has_no_fallback_or_cache(self):
        service = self.repair_service()
        with patch('data.current_cash_portfolio_research.apply_exact_integer_projection',
                   side_effect=lambda result: apply_exact_integer_projection(result, max_evaluations=63)):
            with self.assertRaises(ProjectionBudgetExceededError) as caught:
                service.calculate(5000)
        self.assertEqual(caught.exception.diagnostics['unresolved_neighborhood_size'], 64)
        self.assertEqual(caught.exception.diagnostics['completed_evaluations'], 0)
        self.assertEqual(service.results, {})

    def test_api_incomplete_is_explicit_503_without_alternative_stocks(self):
        # Compile only the actual route body, avoiding unrelated server startup IO.
        from starlette.responses import JSONResponse
        source = Path(__file__).resolve().parents[1] / 'api' / 'server.py'
        node = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'api_current_portfolio_research')
        node.decorator_list = []
        def incomplete(amount):
            raise ProjectionBudgetExceededError({'max_evaluations': 63, 'completed_evaluations': 0})
        namespace = dict(Body=lambda value: value, JSONResponse=JSONResponse,
                         calculate_current_cash_research=incomplete,
                         ProjectionBudgetExceededError=ProjectionBudgetExceededError, PreviewSourceError=PreviewSourceError)
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        response = namespace['api_current_portfolio_research']({'entered_cash': '5000'})
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload['status'], 'INCOMPLETE')
        self.assertTrue(payload['execution_blocked'])
        self.assertIn('尚未完成', payload['error'])
        self.assertNotIn('stocks', payload)

    def service(self, cache_size=8):
        service = CurrentCashPortfolioResearch(max_cached_budgets=cache_size)
        service.inputs = synthetic_inputs()
        service.commission_confirmation = commission_confirmation()
        service._load = lambda: None
        return service

    def test_current_zero_commission_preserves_historical_method_and_versions_cache(self):
        service = self.repair_service()
        original = deepcopy(service.inputs)
        old_id = hashlib.sha256(json.dumps(['CURRENT_CASH_RESEARCH_V2_EXACT_FLOOR_CEIL', '5000.00', service.pins],
                                          sort_keys=True).encode()).hexdigest()[:24]
        service.results[old_id] = {'stale_historical_fee_result': True}
        with patch('data.current_cash_portfolio_research.build_latest_saved_snapshot', wraps=build_latest_saved_snapshot) as build:
            result = service.calculate(5000)
        self.assertEqual(build.call_args.kwargs['frozen_method_snapshot']['fee_bps'], 0)
        self.assertIsNot(build.call_args.kwargs['frozen_method_snapshot'], service.inputs['frozen_method_snapshot'])
        self.assertEqual(service.inputs, original)
        self.assertEqual(service.inputs['frozen_method_snapshot']['fee_bps'], 10)
        self.assertNotEqual(result['research_id'], old_id)
        self.assertEqual(result['research_version'], RESEARCH_VERSION)
        self.assertFalse(result['cache_hit'])
        self.assertEqual(result['fees'], 0)
        exact = result['budget_identity_exact']
        self.assertEqual(Fraction(exact['stock_notional']) + Fraction(exact['residual_cash']), 5000)
        policy = result['commission_policy']
        self.assertEqual((policy['current_fee_bps'], policy['current_minimum_commission_usd'], policy['historical_research_fee_bps']), (0, 0, 10))
        self.assertFalse(policy['other_charges_confirmed'])
        self.assertFalse(policy['other_charges_included'])
        self.assertEqual(policy['source']['sha256'], PINS[COMMISSION_CONFIRMATION])
        self.assertTrue(service.calculate(5000)['cache_hit'])

    def test_full_amount_regeneration_changes_k_and_preserves_cash(self):
        service = self.service()
        original = deepcopy(service.inputs)
        with patch('data.current_cash_portfolio_research.build_latest_saved_snapshot', wraps=build_latest_saved_snapshot) as build:
            results = [service.calculate(amount) for amount in (50, 5000, 10000)]
            self.assertEqual([row['status'] for row in results], ['ALL_CASH', 'AVAILABLE', 'AVAILABLE'])
            self.assertEqual([len(row['stocks']) for row in results], [0, 4, 6])
            self.assertEqual(build.call_count, 3)
            self.assertEqual([call.kwargs['entered_cash'] for call in build.call_args_list], ['50.00', '5000.00', '10000.00'])
            cached = service.calculate('10000.0')
            self.assertEqual(build.call_count, 3)
            self.assertTrue(cached['cache_hit'])
            self.assertEqual(cached['generator_calls_this_request'], 0)
        self.assertEqual(service.inputs, original)
        for result in results:
            identity = result['budget_identity_exact']
            self.assertEqual(Fraction(identity['entered_cash']), sum(Fraction(identity[key]) for key in ('stock_notional', 'fees', 'residual_cash')))
            self.assertEqual(result['search_coverage']['considered_k_count'], 6)
            self.assertEqual(result['book_calls'], 0)
            self.assertTrue(all(row['latest_reference_quote'] is None for row in result['stocks']))
        self.assertNotEqual(results[1]['stocks'][0]['target_weight'], results[1]['stocks'][0]['actual_weight'])

    def test_dynamic_bars_not_fixed_six_allowlist_and_cache_expiry(self):
        service = self.service(cache_size=1)
        first = service.calculate(5000)
        self.assertEqual(len(service.bars(first['research_id'], 'S3', 'week', 2)['bars']), 2)
        with self.assertRaises(ValueError):
            service.bars(first['research_id'], 'S5')
        second = service.calculate(10000)
        self.assertTrue(service.bars(second['research_id'], 'S5')['bars'])
        with self.assertRaises(ResearchExpiredError):
            service.bars(first['research_id'], 'S0')
        self.assertEqual(len(service.results), 1)

    def test_input_boundaries(self):
        for value in (True, False, None, [], {}, 'NaN', float('nan'), float('inf'), '-0', -0.0, -1,
                      0, '0.001', '1000000000.01', '1e6', '1/2', '1,000', '9'*100):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_cash(value)
        self.assertEqual(normalize_cash('0.01'), '0.01')
        self.assertEqual(normalize_cash(1000000000), '1000000000.00')

    def test_no_legal_separate_from_cash_reference_and_quote_display_only(self):
        inputs = synthetic_inputs()
        inputs['historical_result']['rankings'] = [{'rule': 'K6:RANK_TOP:EQUAL:EXPOSURE1'}]
        result = build_latest_saved_snapshot(entered_cash=50, **inputs)
        payload = project_research_result(result, {})
        self.assertEqual(payload['status'], 'NO_LEGAL')
        self.assertEqual((payload['cash'], payload['invested'], payload['fees']), (50, 0, 0))
        selected = build_latest_saved_snapshot(entered_cash=10000, **inputs)
        quote = dict(reference_snapshot_date='2026-10-12', reference_snapshot_close=1000,
                     display_price='2000', display_market_date='2026-10-13', source='synthetic')
        payload = project_research_result(selected, {'S0': quote})
        self.assertEqual(payload['stocks'][0]['close'], 1000)
        self.assertEqual(payload['stocks'][0]['latest_reference_quote'], 2000)
        self.assertIsNone(payload['stocks'][1]['latest_reference_quote'])

    def test_fixed_sources_cache_hash_failure_and_optional_missing_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            accepted = [f'T{index}' for index in range(84)]
            contents = {key: b'# synthetic code' for key in PINS}
            fake = {
                COMMISSION_CONFIRMATION: commission_confirmation(),
                REGISTRATION: {'accepted_current_conditional_tickers': accepted},
                PROPOSAL_PATH: {'proposed_metadata': [{'ticker': ticker, 'issuer_id': f'I{max(0,index-1)}'} for index,ticker in enumerate(accepted)]},
                PANEL_PATH: {'calendar': ['2026-10-12'], 'stocks': [{} for _ in range(101)]},
                FROZEN_PATH: [{'decision_date': '2026-09-21', 'fee_bps': '10', 'minimum_cash_buffer': 100, 'risk_parameters': {}, 'fixed_seed': 'synthetic'}],
            }
            for relative, value in fake.items():
                contents[relative] = json.dumps(value).encode()
            frozen_hash = hashlib.sha256(contents[FROZEN_PATH]).hexdigest()
            contents[RESULT_PATH] = json.dumps({'status': 'synthetic', 'rankings': [{'rule': str(index)} for index in range(46)],
                                              'frozen_candidates_sha256': frozen_hash}).encode()
            pins = {}
            for relative, raw in contents.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                pins[relative] = hashlib.sha256(raw).hexdigest()
            service = CurrentCashPortfolioResearch(root, pins)
            service._load()
            self.assertEqual(service.quote_status, 'UNAVAILABLE')
            self.assertEqual(service.quotes, {})
            self.assertEqual(service.commission_confirmation['commission_fee_bps'], 0)
            self.assertEqual(service.inputs['frozen_method_snapshot']['fee_bps'], '10')
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('unchanged sources reread')):
                service._load()
            service.results['cached'] = {}
            path = root / COMMISSION_CONFIRMATION
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaises(PreviewSourceError):
                service._load()
            self.assertEqual(service.results, {})
            self.assertIsNone(service.inputs)
            self.assertIsNone(service.commission_confirmation)


if __name__ == '__main__':
    unittest.main()
