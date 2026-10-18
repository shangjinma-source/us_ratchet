from copy import deepcopy
from unittest.mock import patch
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import test_current_research_capital_decision_v2 as fixtures
from backtest import continuous_guided_account_decision as adapter
from backtest.continuous_guided_next_open import run_continuous_guided_next_open


class GuidedBookTests(unittest.TestCase):
    def arguments(self):
        args=fixtures.CapitalV2Tests().arguments()
        args['source_hashes'].update({p:'a'*64 for p in adapter.REQUIRED_PINS})
        return args

    def test_original_once_bound_and_incomplete_skip(self):
        args=self.arguments()
        with patch.object(adapter,'original_search',wraps=adapter.original_search) as original:
            result=adapter.decide_continuous_guided_for_account(**args)
        self.assertEqual(original.call_count,1);self.assertEqual(result['investable_equity'],'100')
        comparison=result['search_result']['continuous_comparison']
        self.assertEqual(comparison['additional_generation']['iterations_completed'],32)
        self.assertEqual(result['binding']['continuous_iterations'],32)
        self.assertEqual(result['method'],adapter.VERSION)
        args['search_arguments']['max_objective_evaluations']=1
        with patch.object(adapter,'compare_saved_candidates',side_effect=AssertionError('must not compare incomplete')):
            result=adapter.decide_continuous_guided_for_account(**args)
        self.assertIsNone(result['target_quantities'])
        self.assertEqual(result['search_result']['status'],'INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE')

    def test_second_month_uses_actual_branch_cash_and_shares(self):
        args=self.arguments();days=['2026-10-13','2026-10-14','2026-11-13','2026-11-16'];plans=[]
        for day,price in [(days[0],'1'),(days[2],'2')]:
            search=deepcopy(args['search_arguments']);search.update(decision_date=day,quote_as_of=day,prices={'A':price})
            quotes=[dict(security_id='A',as_of=day,price=price,price_basis='SYNTHETIC_USD',source_references=['quote'])]
            plans.append(dict(decision_date=day,search_arguments=search,valuation_quotes=quotes,source_hashes=args['source_hashes']))
        close={'A':dict(zip(days,['1','1','2','2']))}
        bars={'A':{d:dict(open=close['A'][d],high=close['A'][d],low=close['A'][d],close=close['A'][d]) for d in days}}
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices=close,provider_actions=[],actions=[],
            cash_stock_merger_events=[],fractional_settlements=[],price_source_references={'A':['quote']},distribution_events=[],distribution_fractional_cash_values={})
        progress=[]
        with patch.object(adapter,'original_search',wraps=adapter.original_search) as original:
            result=run_continuous_guided_next_open(assembled=assembled,ohlc=bars,initial_cash='100',fee_bps='0',slippage_bps='0',progress=progress.append)
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(original.call_count,2)
        self.assertEqual([call.kwargs['entered_cash'] for call in original.call_args_list],['100','150'])
        selections=[r['selection'] for r in result['provider_audit'] if r.get('selection')]
        self.assertEqual(result['selection_account_states'][1]['account_state']['cash'],'50')
        self.assertEqual(result['selection_account_states'][1]['account_state']['shares'],{'A':50})
        self.assertEqual(len([r for r in progress if r.get('stage')=='MONTHLY_SEARCH_STARTED']),2)
        # Exercise the isolated CLI terminal serialization with this real tiny
        # branch result; no second selector/book run is made by the CLI fixture.
        from scripts import run_continuous_guided_monthly_book as runner
        with TemporaryDirectory() as directory, patch.object(runner,'ROOT',Path(directory)), \
                patch.object(runner,'prepare',return_value=({'ohlc':bars},assembled,{'source_hashes':{}})), \
                patch.object(runner,'run_continuous_guided_next_open',return_value=result), \
                patch.object(runner,'calendar_year_metrics',return_value={'years':[]}):
            (Path(directory)/'tmp').mkdir()
            self.assertEqual(runner.main(['--execute']),0)
            terminal=json.loads((Path(directory)/runner.OUTPUT/'terminal.json').read_bytes())
            self.assertEqual(terminal['search_calls'],2);self.assertEqual(terminal['status'],'COMPLETE')


if __name__=='__main__':unittest.main()
