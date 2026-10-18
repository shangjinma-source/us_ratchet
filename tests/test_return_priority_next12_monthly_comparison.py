"""Synthetic runner persistence and failure tests; no real optimizer or book."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.return_priority_next12_monthly_comparison import execute_method, save


class Next12RunnerTests(unittest.TestCase):
    def fixture(self):
        days = ['2026-01-02', '2026-01-05']
        assembled = dict(session_dates=days, monthly_inputs=[dict(decision_date=days[0])],
            close_prices={}, provider_actions=[], actions=[], cash_stock_merger_events=[],
            fractional_settlements={}, price_source_references={}, distribution_events=[],
            distribution_fractional_cash_values={})
        return dict(ohlc={}), assembled

    def test_top1_intent_before_call_and_result_counts(self):
        prepared, assembled = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'top1'
            def factory(**kwargs):
                def provider(**kw):
                    self.assertTrue((directory/'monthly_intent_2026-01-02.json').is_file())
                    self.assertEqual(kw['state']['cash'], '20000')
                    return dict(status='READY', orders=[], target_shares={}, capital_decision_attempts=1, selector_calls=1)
                return provider
            def kernel(**kw):
                self.assertEqual(kw['initial_cash'], '20000')
                kw['order_provider'](decision_date='2026-01-02', active_date='2026-01-05',
                    state=dict(asof='2026-01-02',cash='20000',shares={}))
                return dict(status='COMPLETE',daily_ledger=[dict(date='2026-01-05',equity='20000')],
                    order_log=[],cash='20000',shares={},receivable='0',
                    terminal_state_valuation_synchronized=True,final_wealth_basis='REGULAR_CLOSE_CURRENT_STATE')
            result=execute_method('top1', prepared, assembled, directory, kernel=kernel, provider_factory=factory)
            self.assertEqual(result['selector_calls'],1)
            self.assertEqual(result['core_calls'],0)
            self.assertTrue(result['metrics']['complete_full_period'])
            with self.assertRaises(FileExistsError):
                execute_method('top1',prepared,assembled,directory,kernel=kernel,provider_factory=factory)

    def test_duplicate_callback_never_invokes_provider_twice(self):
        prepared, assembled = self.fixture(); calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            def factory(**kwargs):
                def provider(**kw):
                    calls.append(1)
                    return dict(status='READY',orders=[],target_shares={},capital_decision_attempts=1,selector_calls=1)
                return provider
            def kernel(**kw):
                for _ in range(2):
                    kw['order_provider'](decision_date='2026-01-02',active_date='2026-01-05',state=dict(cash='20000',shares={}))
            directory=Path(tmp)/'top1'
            result=execute_method('top1',prepared,assembled,directory,kernel=kernel,provider_factory=factory)
            self.assertEqual(len(calls),1)
            self.assertFalse(result['metrics']['complete_full_period'])
            self.assertIsNone(result['metrics']['partial_observed_drawdown'])
            self.assertIsNone(result['selector_calls'])
            self.assertTrue((directory/'callback_2026-01-02.json').is_file())
            self.assertTrue((directory/'exception.json').is_file())

    def test_provider_construction_failure_persisted_not_zero_return(self):
        prepared, assembled = self.fixture()
        def fail(**kwargs):raise ValueError('synthetic failure')
        with tempfile.TemporaryDirectory() as tmp:
            result=execute_method('quantity',prepared,assembled,Path(tmp)/'quantity',provider_factory=fail)
            self.assertIsNone(result['metrics']['annualized_return'])
            self.assertIsNone(result['metrics']['last_observed_equity'])
            self.assertEqual(result['core_calls'],0)

    def test_exception_preserves_observed_prior_ledger_and_rights(self):
        prepared, assembled = self.fixture()
        def factory(**kwargs):
            def provider(**kw):raise ValueError('synthetic callback failure')
            return provider
        def kernel(**kw):
            kw['order_provider'](decision_date='2026-01-02',active_date='2026-01-05',state=dict(
                asof='2026-01-02',cash='100',shares={'A':2},receivable='0',
                distribution_rights=[{'synthetic_right':True}],order_log=[],
                daily_ledger=[dict(date='2026-01-02',equity='19000')]))
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'top1'
            result=execute_method('top1',prepared,assembled,directory,kernel=kernel,provider_factory=factory)
            self.assertEqual(result['metrics']['last_observed_equity'],'19000')
            self.assertEqual(result['metrics']['partial_observed_drawdown'],'1/20')
            self.assertIsNone(result['metrics']['total_return'])
            outcome=json.loads((directory/'outcome.json').read_text())
            self.assertEqual(outcome['shares'],{'A':2})
            self.assertEqual(outcome['distribution_rights'],[{'synthetic_right':True}])

    def test_createonly_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'intent.json';save(path,{'first':True})
            with self.assertRaises(FileExistsError):save(path,{'second':True})
            self.assertEqual(json.loads(path.read_text()),{'first':True})

    def test_quantity_exact_core_arguments_and_duplicate_attempt(self):
        prepared, assembled = self.fixture()
        args = dict(decision_date='2026-01-02',entered_cash='20000',prices={'A':'10'},
                    max_objective_evaluations=8192,fixed_seed='fixed')
        assembled['monthly_inputs'][0]['search_arguments'] = dict(args,quote_as_of='2026-01-02',price_basis='conditional')
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'quantity'
            def adapter(search, **kwargs):return search(**kwargs)
            def factory(decide, **kwargs):
                def provider(**kw):
                    changed=dict(args,entered_cash='21000')
                    decide(**changed)
                    decide(**changed)  # Must be rejected before a second core invocation.
                return provider
            def core(**kwargs):
                self.assertTrue((directory/'core_intent_2026-01-02.json').is_file())
                calls.append(kwargs);return {'selected':'synthetic'}
            def kernel(**kw):
                kw['order_provider'](decision_date='2026-01-02',active_date='2026-01-05',state=dict(cash='21000',shares={}))
            with patch('data.current_research_capital_decision.decide_quantity_for_account',adapter):
                result=execute_method('quantity',prepared,assembled,directory,kernel=kernel,provider_factory=factory,core=core)
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['entered_cash'],'21000')
            self.assertEqual(result['core_calls'],1)
            self.assertIsNone(result['metrics']['total_return'])
            self.assertTrue((directory/'core_result_2026-01-02.json').is_file())


if __name__ == '__main__':unittest.main()
