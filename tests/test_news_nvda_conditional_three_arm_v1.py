"""Synthetic execution checks only; no historical economic run."""
from copy import deepcopy
from fractions import Fraction
import unittest
from scripts.research.run_news_nvda_conditional_three_arm_v1 import replay,transform,SID
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


def fixture():
    days=['2023-11-20','2023-11-21','2023-11-22','2023-11-24','2023-11-27']
    risk=MonthlyExitCoreResearchAdapter()
    risk.apply(day='2023-10-31',month='2023-10-31',target={SID:7},closes={SID:'100'})
    _,state=risk.apply(day=days[0],month='2023-10-31',target={SID:7},closes={SID:'100'})
    audit={'risk_overlay':state,'monthly_ceiling':{SID:7},'target_decision_date':'2023-10-31'}
    inputs={'assembled':{'session_dates':days,'monthly_inputs':[],'close_prices':{SID:{d:'100' for d in days}}},'ohlc':{SID:{d:{'open':'100','high':'100','low':'100','close':'100'} for d in days}}}
    book={'provider_audit':[deepcopy(audit) for _ in range(4)],'daily_ledger':[{'date':days[1],'cash':'300','shares':{SID:7}}]}
    answer={'A_direct':{'action':'PAUSE_BUY','buy_fraction':'0','holding_fraction':'1'},'B_signal':{'direction':'NEGATIVE','materiality':'HIGH'}}
    return inputs,book,answer

class ConditionalTests(unittest.TestCase):
    def test_two_sessions_and_integer_half_no_compounding(self):
        inputs,book,answer=fixture()
        result=replay(inputs,book,'NO_CHANGE',target_transform=lambda q,state:transform(q,7,7,answer,'B'))
        self.assertEqual([r['date'] for r in result['book']['daily_ledger']],['2023-11-22','2023-11-24','2023-11-27'])
        self.assertEqual([r['shares'][SID] for r in result['book']['daily_ledger']],[3,3,7])
        self.assertEqual(Fraction(result['book']['daily_ledger'][-1]['cash']),Fraction('299.6'))
    def test_event_close_cannot_change_first_order(self):
        inputs,book,answer=fixture();changed=deepcopy(inputs)
        changed['assembled']['close_prices'][SID]['2023-11-22']='70'
        changed['ohlc'][SID]['2023-11-22'].update(close='70',low='70')
        callback=lambda q,state:transform(q,7,7,answer,'B')
        a=replay(inputs,book,'NO_CHANGE',target_transform=callback)
        b=replay(changed,book,'NO_CHANGE',target_transform=callback)
        self.assertEqual(a['trace'][0],b['trace'][0])
        self.assertEqual(b['book']['daily_ledger'][-1]['shares'][SID],0)
    def test_pause_no_sell_and_other_security_unchanged(self):
        _,_,answer=fixture()
        self.assertEqual(transform({SID:7,'other':4},7,7,answer,'A'),{SID:7,'other':4})
        self.assertEqual(transform({SID:7,'other':4},7,7,answer,'B'),{SID:3,'other':4})
    def test_missing_holiday_calendar_rejected(self):
        inputs,book,_=fixture();inputs['assembled']['session_dates'].insert(3,'2023-11-23')
        with self.assertRaises(ValueError):replay(inputs,book,'NO_CHANGE')

if __name__=='__main__':unittest.main()
