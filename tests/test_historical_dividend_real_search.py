import unittest
from backtest.historical_dividend_independent_review import review
from copy import deepcopy
from fractions import Fraction
import test_continuous_guided_half_next_open as fixture
from backtest.frontier_capped_next_open_research import run_frontier_capped_next_open as old
from backtest.historical_dividend_frontier_research import run_frontier_capped_next_open as new
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter

class RealSearchWiring(unittest.TestCase):
    def test_two_real_searches_and_saved_prefix_parity(self):
        a,bars,_=fixture.GuidedHalfTests().data()
        # Stable synthetic prices isolate payment/account binding from price exits.
        for day in a['session_dates']:
            a['close_prices']['A'][day]='11'
            bars['A'][day]=dict(open='11',high='11',low='11',close='11')
        kwargs=dict(assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5')
        original=old(**kwargs,max_new_searches=1,risk=MonthlyExitCoreResearchAdapter([]))
        self.assertEqual(original['status'],'COMPLETE')
        prefix=[dict(arguments=original['selection_account_states'][0],raw_selection=original['provider_audit'][0]['selection']['raw_selection'])]
        baseline=old(**kwargs,verified_prefix=prefix,risk=MonthlyExitCoreResearchAdapter([]))
        isolated=new(**kwargs,verified_prefix=prefix,risk=MonthlyExitCoreResearchAdapter([]))
        self.assertEqual(baseline,isolated)
        day=a['session_dates'][3]
        second=deepcopy(a['monthly_inputs'][0]);second['decision_date']=day
        second['search_arguments'].update(decision_date=day,quote_as_of=day)
        second['valuation_quotes'][0]['as_of']=day
        a['monthly_inputs'].append(second)
        event=dict(event_id='d',security_id='A',ex_date=a['session_dates'][2],payment_date=a['session_dates'][2],amount_per_share='1',withholding_rate='0',assumption='explicit gross mechanism only',currency='USD')
        result=new(**kwargs,verified_prefix=prefix,max_new_searches=1,dividend_events=[event],risk=MonthlyExitCoreResearchAdapter([]))
        self.assertEqual(result['status'],'COMPLETE')
        state=result['selection_account_states'][1]['account_state']
        selection=next(row['selection'] for row in result['provider_audit'] if row.get('selection') and row['selection']['raw_selection']['decision_date']==day)
        binding=selection['raw_selection']['binding']
        self.assertEqual(Fraction(binding['available_cash']),Fraction(state['cash']))
        self.assertEqual(Fraction(binding['investable_equity']),Fraction(state['cash'])+11*state['shares']['A'])
        prior=next(row for row in baseline['daily_ledger'] if row['date']==day)
        self.assertEqual(Fraction(state['cash'])-Fraction(prior['cash']),state['shares']['A'])
        self.assertEqual(result['new_searches'],1)
        self.assertTrue(any(r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' for r in result['order_log']))

        proof=review(result,a,bars,initial_cash='1000',dividend_events=[event],expected_fee_bps='0',expected_slippage_bps='5',verify_selections=True)
        self.assertEqual(proof['selection_proofs_checked'],2)
        for field,reason in [('source_hashes','SELECTION_SOURCE_BINDING'),('search_arguments','SELECTION_SEARCH_BINDING'),('valuation_quotes','SELECTION_QUOTES_BINDING')]:
            tampered=deepcopy(a)
            if field=='source_hashes':tampered['monthly_inputs'][0][field]={'tamper':'other-source'}
            elif field=='search_arguments':tampered['monthly_inputs'][0][field]['entered_cash']='999'
            else:tampered['monthly_inputs'][0][field][0]['source_references']=['other-source']
            if field=='search_arguments':tampered['monthly_inputs'][0][field]['fee_bps']='2'
            with self.assertRaisesRegex(ValueError,reason):
                review(result,tampered,bars,initial_cash='1000',dividend_events=[event],expected_fee_bps='0',expected_slippage_bps='5',verify_selections=True)

        self.assertEqual(proof['status'],'REVIEWED_ORDINARY_DIVIDEND_ACCOUNT')
        print('REAL_SELECTION_INDEPENDENT_REVIEW',proof)
        print('INDEPENDENT_ACCOUNT',dict(cash=result['cash'],paid_cash=result['dividend_ledger']['paid_cash'],receivable=result['dividend_receivable'],total_return=result['total_return']))
