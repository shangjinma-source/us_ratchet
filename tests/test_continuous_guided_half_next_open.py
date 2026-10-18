from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from test_current_quantity_v2_risk_next_open import fixture
from test_current_quantity_v2_risk_overlays import fixture as signal_fixture
from backtest import continuous_guided_account_decision as selector
from backtest.continuous_guided_half_next_open import run_continuous_guided_half_next_open
from backtest.partial_trend_exposure import partial_sma20_target


class GuidedHalfTests(unittest.TestCase):
    def data(self):
        a,bars,resolver=fixture()
        a['monthly_inputs'][0]['source_hashes'].update({p:'a'*64 for p in selector.REQUIRED_PINS})
        return a,bars,resolver

    def run_book(self,a,bars,resolver):
        return run_continuous_guided_half_next_open(assembled=a,ohlc=bars,history_resolver=resolver,
            initial_cash='1000',fee_bps='0',slippage_bps='0')

    def test_real_selector_half_recovery_and_future_open_isolation(self):
        a,bars,resolver=self.data()
        with patch.object(selector,'original_search',wraps=selector.original_search) as calls:
            result=self.run_book(a,bars,resolver)
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(calls.call_count,1)
        rows=result['provider_audit'];ceiling=rows[0]['monthly_ceiling']['A']
        self.assertEqual(rows[1]['target_shares']['A'],ceiling//2)
        self.assertEqual(rows[2]['target_shares']['A'],ceiling)
        self.assertEqual(rows[0]['selection']['binding']['continuous_iterations'],32)
        self.assertIn('search_arguments',result['selection_account_states'][0])
        changed=deepcopy(bars);changed['A'][a['session_dates'][1]]=dict(open='999',high='999',low='8',close='8')
        self.assertEqual(self.run_book(a,changed,resolver)['provider_audit'][0],rows[0])

    def test_second_month_receives_actual_half_branch_state(self):
        a,bars,resolver=self.data();day=a['session_dates'][2]
        second=deepcopy(a['monthly_inputs'][0]);second['decision_date']=day
        second['search_arguments'].update(decision_date=day,quote_as_of=day,prices={'A':a['close_prices']['A'][day]})
        second['valuation_quotes'][0].update(as_of=day,price=a['close_prices']['A'][day])
        a['monthly_inputs'].append(second)
        with patch.object(selector,'original_search',wraps=selector.original_search) as calls:
            result=self.run_book(a,bars,resolver)
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(calls.call_count,2)
        state=result['selection_account_states'][1]['account_state']
        ledger=next(x for x in result['daily_ledger'] if x['date']==day)
        self.assertEqual(state['cash'],ledger['cash']);self.assertEqual(state['shares'],ledger['shares'])
        wealth=Fraction(state['cash'])+sum(q*Fraction(a['close_prices'][sid][day]) for sid,q in state['shares'].items())
        self.assertEqual(Fraction(calls.call_args_list[1].kwargs['entered_cash']),wealth)
        self.assertNotEqual(wealth,1000)

    def test_unchanged_odd_floor_and_invalid_history_stop(self):
        args=signal_fixture({'A':[100]*20},quantities={'A':7})
        self.assertEqual(partial_sma20_target(**args)['target_quantities'],{'A':3})
        for fault in ('unit','future','missing'):
            a,bars,resolver=self.data()
            def bad(**kwargs):
                data=resolver(**kwargs)
                if fault=='unit':data['base_target']['price_units']['A']='wrong'
                elif fault=='future':data['histories']['A']['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
                else:data['histories']['A']['closes'].pop(0)
                return data
            self.assertEqual(self.run_book(a,bars,bad)['status'],'BLOCKED')

    def test_all_on_matches_unmodified_enhanced_execution(self):
        from backtest.continuous_guided_next_open import run_continuous_guided_next_open
        a,bars,resolver=self.data()
        def always_on(**kwargs):
            data=resolver(**kwargs)
            for history in data['histories'].values():
                for row in history['closes'][:-1]:row['close']='1'
            return data
        half=self.run_book(a,bars,always_on)
        base=run_continuous_guided_next_open(assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='0')
        self.assertEqual(half['status'],'COMPLETE')
        self.assertEqual(half['daily_ledger'],base['daily_ledger'])
        self.assertEqual(half['selection_account_states'],base['selection_account_states'])
        from scripts import run_continuous_guided_half_exposure as runner
        with TemporaryDirectory() as directory, patch.object(runner,'ROOT',Path(directory)), \
                patch.object(runner,'prepare',return_value=({'ohlc':bars},a,{'source_hashes':{}},always_on)), \
                patch.object(runner,'run_continuous_guided_half_next_open',return_value=half), \
                patch.object(runner,'calendar_year_metrics',return_value={'years':[]}):
            (Path(directory)/'tmp').mkdir()
            self.assertEqual(runner.main(['--execute']),0)
            saved=json.loads((Path(directory)/runner.OUTPUT/'outcome.json').read_bytes())
            terminal=json.loads((Path(directory)/runner.OUTPUT/'terminal.json').read_bytes())
            self.assertEqual(saved['selection_account_states'],half['selection_account_states'])
            self.assertEqual(terminal['search_calls'],1)
            self.assertEqual(terminal['status'],'COMPLETE')


if __name__=='__main__':unittest.main()
