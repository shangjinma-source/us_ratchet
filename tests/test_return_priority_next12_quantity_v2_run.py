"""Isolated injection tests: no historical optimizer or economic experiment."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import return_priority_next12_quantity_v2_run as runner


class RunnerTests(unittest.TestCase):
    def fixture(self, months=2):
        days = ['2026-01-30', '2026-02-02', '2026-02-27', '2026-03-02']
        windows = [dict(decision_date=d, valuation_quotes=[dict(security_id=s, price='10') for s in ('A','B')],
            source_hashes={}, search_arguments=dict(fee_bps='0', max_objective_evaluations=8192)) for d in (days[0],days[2])[:months]]
        assembled = dict(session_dates=days, monthly_inputs=windows,
            close_prices={s:{d:'10' for d in days} for s in ('A','B')}, provider_actions=[], actions=[],
            cash_stock_merger_events=[], fractional_settlements={}, price_source_references={},
            distribution_events=[], distribution_fractional_cash_values={})
        return dict(ohlc={}), assembled

    def selection(self, **kw):
        st=kw['account_state']; equity=Fraction(st['cash'])+sum(st['shares'].values())*10
        return dict(method=runner.VERSION, binding={'selection_method':runner.VERSION,'schema':'CAPITAL_DECISION_MECHANIC_V2'},core_calls=1,
            search_result={'method_version':runner.VERSION},investable_equity=str(equity),target_quantities={'B':int(equity//10)})

    def test_actual_equity_daily_zero_decision_and_sale_not_financing_buy(self):
        prepared, assembled=self.fixture(); calls=[]; responses=[]
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'new'
            def decide(**kw):
                self.assertTrue((directory/('decision_intent_'+kw['decision_date']+'.json')).exists())
                calls.append(deepcopy(kw)); return self.selection(**kw)
            def kernel(**kw):
                self.assertEqual(kw['initial_cash'],'20000');self.assertEqual(kw['initial_shares'],{})
                states=[dict(cash='0',shares={'A':10}),dict(cash='100',shares={}),dict(cash='30',shares={'B':11})]
                for i, st in enumerate(states):
                    responses.append(kw['order_provider'](decision_date=assembled['session_dates'][i],
                        active_date=assembled['session_dates'][i+1],state=dict(st,asof=assembled['session_dates'][i])))
                return dict(status='BLOCKED',daily_ledger=[],order_log=[])
            result=runner.execute(prepared,assembled,directory,kernel=kernel,capital_decide=decide)
            self.assertEqual(len(calls),2)
            self.assertEqual([r['investable_equity_at_reset'] for r in responses],['100',None,'140'])
            self.assertEqual([o['side'] for o in responses[0]['orders']],['SELL'])
            self.assertTrue(responses[0]['wait_cash'])
            self.assertEqual(responses[1]['orders'][0]['quantity'],10)
            self.assertEqual(responses[2]['target_shares'],{'B':14})
            self.assertEqual(result['core_calls'],2);self.assertEqual(result['book_calls'],1)
            self.assertTrue(all(r['method']==runner.VERSION for r in responses))
            with self.assertRaises(FileExistsError): runner.execute(prepared,assembled,directory,kernel=kernel,capital_decide=decide)

    def test_failure_consumes_attempt_duplicate_callback_no_retry(self):
        prepared, assembled=self.fixture(1); calls=[]
        def fail(**kw): calls.append(1);raise ValueError('injected failure')
        def kernel(**kw):
            args=dict(decision_date='2026-01-30',active_date='2026-02-02',state=dict(asof='2026-01-30',cash='100',shares={}))
            first=kw['order_provider'](**args);self.assertEqual(first['status'],'BLOCKED');self.assertEqual(first['orders'],[])
            kw['order_provider'](**args)
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'new'; result=runner.execute(prepared,assembled,directory,kernel=kernel,capital_decide=fail)
            self.assertEqual(calls,[1]);self.assertEqual(result['capital_decision_attempts'],1)
            self.assertIsNone(result['core_calls']);self.assertEqual(result['core_calls_upper_bound'],1)
            self.assertIsNone(result['metrics']['total_return']);self.assertIsNone(result['metrics']['partial_observed_drawdown'])
            self.assertTrue((directory/'exception.json').exists())

    def test_wrong_method_blocked_and_no_orders(self):
        prepared, assembled=self.fixture(1)
        def bad(**kw): return dict(self.selection(**kw),method='V1')
        def kernel(**kw):
            r=kw['order_provider'](decision_date='2026-01-30',active_date='2026-02-02',state=dict(asof='2026-01-30',cash='100',shares={}))
            self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['orders'],[])
            return dict(status='BLOCKED',daily_ledger=[],order_log=[])
        with tempfile.TemporaryDirectory() as tmp:
            r=runner.execute(prepared,assembled,Path(tmp)/'new',kernel=kernel,capital_decide=bad)
            self.assertFalse(r['metrics']['complete_full_period'])

    def test_budget_mutation_rejected_before_adapter(self):
        prepared, assembled=self.fixture(1); calls=[]
        def factory(decide,**kw):
            def provider(**callback):
                row=deepcopy(assembled['monthly_inputs'][0]);row['search_arguments']['max_objective_evaluations']=8193
                return decide(**row,account_state=callback['state'])
            return provider
        def kernel(**kw): return kw['order_provider'](decision_date='2026-01-30',active_date='2026-02-02',state=dict(cash='100',shares={}))
        with tempfile.TemporaryDirectory() as tmp:
            r=runner.execute(prepared,assembled,Path(tmp)/'new',kernel=kernel,provider_factory=factory,capital_decide=lambda **kw:calls.append(kw))
            self.assertEqual(calls,[]);self.assertEqual(r['core_calls_upper_bound'],0)

    def test_registered_run_is_one_shot_and_augments_method_pins(self):
        prepared, assembled=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'input.json';runner.save(source,prepared);out=root/'run'
            with patch.object(runner.sealed,'validate',return_value=deepcopy(assembled)),patch.object(runner,'MODULES',[]),patch.object(runner,'LOADED_ENTRY_HASHES',{}),patch.object(runner,'guards',return_value={}):
                # Stub data only; real prepare still enforces the sealed 12-window protocol.
                prepared['source_hashes']={};source.write_text(json.dumps(prepared))
                regsha=runner.prepare(source,runner.digest(source),out)
                def execute(p,a,d):
                    self.assertIn(str(source),a['monthly_inputs'][0]['source_hashes'])
                    return dict(metrics={'complete_full_period':False},book_calls=1)
                with patch.object(runner,'execute',side_effect=execute) as spy:
                    runner.run(source,runner.digest(source),out,regsha)
                    self.assertEqual(spy.call_count,1)
                    with self.assertRaisesRegex(ValueError,'ALREADY_STARTED'):
                        runner.run(source,runner.digest(source),out,regsha)
                    self.assertEqual(spy.call_count,1)

    def test_real_tiny_v2_adapter_and_v4_kernel_no_legacy_search(self):
        from data.current_research_capital_decision_v2 import REQUIRED_PINS
        days=['2026-01-30','2026-02-02','2026-02-03']
        prices={'A':'10000','B':'15000'}
        args=dict(prices=prices,metadata={s:dict(ticker=s,issuer_id=s) for s in prices},entered_cash='20000',
            fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'1.1','B':'1.2'}],
            scenario_dates=[days[0]],decision_date=days[0],max_objective_evaluations=8192,fixed_seed='synthetic',
            quote_as_of=days[0],price_basis='CURRENT_SHARE_USD')
        quotes=[dict(security_id=s,price=p,as_of=days[0],price_basis='CURRENT_SHARE_USD',source_references=['quote']) for s,p in prices.items()]
        pins={p:runner.digest(p) for p in REQUIRED_PINS}
        pins.update({'quote':'a'*64,'backtest/return_priority_fresh_cash_quantity_search.py':runner.digest('backtest/return_priority_fresh_cash_quantity_search.py')})
        bars={s:{d:dict(open=p,high=p,low=p,close=p) for d in days} for s,p in prices.items()}
        assembled=dict(session_dates=days,monthly_inputs=[dict(decision_date=days[0],valuation_quotes=quotes,source_hashes=pins,search_arguments=args)],
            close_prices={s:{d:p for d in days} for s,p in prices.items()},provider_actions=[],actions=[],
            cash_stock_merger_events=[],fractional_settlements={},price_source_references={},distribution_events=[],distribution_fractional_cash_values={})
        with tempfile.TemporaryDirectory() as tmp, patch('data.current_research_capital_decision.search_fresh_cash_quantities',side_effect=AssertionError('OLD_CORE_FORBIDDEN')):
            directory=Path(tmp)/'new';r=runner.execute({'ohlc':bars},assembled,directory)
            self.assertEqual(r['core_calls'],1);self.assertTrue(r['metrics']['complete_full_period'])
            decision=json.loads((directory/('decision_result_'+days[0]+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(decision['method'],runner.VERSION)
            self.assertEqual(decision['investable_equity'],'20000')
            audit=json.loads((directory/'provider_audit.json').read_text(encoding='utf-8'))
            self.assertIsNone(audit[1]['response']['selection'])

    def test_missing_sealed_baseline_is_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(runner,'BASELINES',[str(Path(tmp)/'absent')]):
            with self.assertRaisesRegex(ValueError,'SEALED_BASELINE_MISSING'): runner.guards()
        # execute tests above have imported the provider; production run must
        # demand a fresh CLI instead of silently trusting such cached objects.
        import sys
        with patch.dict(sys.modules, {'data.current_research_capital_decision_v2': object()}):
            with self.assertRaisesRegex(ValueError,'ALREADY_LOADED'): runner.require_fresh_runtime()


if __name__=='__main__': unittest.main()
