"""Synthetic account execution only; no historical strategy or model run."""
from copy import deepcopy
from fractions import Fraction
import unittest
from scripts.research.run_news_cross_company_three_arm_v1 import CASES, replay, transform
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


def fixture(case='APP_20251105'):
    spec=CASES[case]; sid=spec['security_id']; quantity=spec['held']
    previous='2025-11-04' if case.startswith('APP') else '2024-11-19'
    days=[previous]+spec['days']; month=previous[:7]+'-01'
    risk=MonthlyExitCoreResearchAdapter()
    risk.apply(day=month,month=month,target={sid:quantity},closes={sid:'100'})
    _,state=risk.apply(day=previous,month=month,target={sid:quantity},closes={sid:'100'})
    audit=dict(risk_overlay=state,monthly_ceiling={sid:quantity},target_decision_date=month)
    inputs={'assembled':{'session_dates':days,'monthly_inputs':[],'close_prices':{sid:{day:'100' for day in days}}},'ohlc':{sid:{day:{'open':'100','high':'100','low':'100','close':'100'} for day in days}}}
    book={'provider_audit':[deepcopy(audit) for _ in range(4)],'daily_ledger':[dict(date=spec['days'][0],cash='300',shares={sid:quantity})]}
    answer={'A_direct':{'action':'PAUSE_BUY','buy_fraction':'0','holding_fraction':'1'},'B_signal':{'direction':'NEGATIVE','materiality':'HIGH'}}
    return inputs,book,answer


class CrossCompanyTests(unittest.TestCase):
    def run_case(self, case, inputs,book,answer):
        spec=CASES[case]
        return replay(inputs,book,case_id=case,published=spec['days'][1]+'T12:00:00Z',target_transform=lambda q,state:transform(q,spec['held'],spec['target'],answer,'B',security_id=spec['security_id']))

    def test_two_identities_integer_half_and_cash_reentry(self):
        for case in CASES:
            inputs,book,answer=fixture(case);sid=CASES[case]['security_id'];h=CASES[case]['held']
            result=self.run_case(case,inputs,book,answer)
            self.assertEqual([r['shares'][sid] for r in result['book']['daily_ledger']],[h//2,h//2,h])
            self.assertEqual(Fraction(result['book']['daily_ledger'][-1]['cash']),Fraction(300)-Fraction(h-h//2,10))

    def test_first_open_no_future_close_and_exit_prevents_rebuy(self):
        inputs,book,answer=fixture();a=self.run_case('APP_20251105',inputs,book,answer)
        sid=CASES['APP_20251105']['security_id'];inputs['assembled']['close_prices'][sid]['2025-11-06']='70'
        inputs['ohlc'][sid]['2025-11-06'].update(close='70',low='70')
        b=self.run_case('APP_20251105',inputs,book,answer)
        self.assertEqual(a['trace'][0],b['trace'][0]);self.assertEqual(b['book']['daily_ledger'][-1]['shares'][sid],0)

    def test_rights_actions_dividends_and_calendar_fail_closed(self):
        for mutation in ('rights','action','dividend','calendar'):
            inputs,book,answer=fixture()
            if mutation=='rights': book['daily_ledger'][0]['dividend_receivable']='1'
            if mutation=='action': inputs['assembled']['actions']=[{'date':'2025-11-07'}]
            if mutation=='dividend': inputs['dividend_events']=[{'ex_date':'2025-11-01','payment_date':'2025-11-07'}]
            if mutation=='calendar': inputs['assembled']['session_dates'][3]='2025-11-08'
            with self.assertRaises(ValueError): self.run_case('APP_20251105',inputs,book,answer)

    def test_overlay_cannot_drop_other_original_targets(self):
        inputs,book,_=fixture()
        with self.assertRaisesRegex(ValueError,'OVERLAY_EXCEEDS'):
            replay(inputs,book,case_id='APP_20251105',published='2025-11-06T12:00:00Z',target_transform=lambda q,state:{})


if __name__=='__main__': unittest.main()
