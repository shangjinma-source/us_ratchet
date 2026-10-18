import unittest
from copy import deepcopy
from fractions import Fraction as F
import test_current_research_fill_ledger as fixture
from data.current_research_fill_ledger import initialize_paper_ledger,apply_paper_fill,apply_paper_order_event,activate_paper_plan
from data.current_research_paper_performance import compute_paper_performance as report

D=['2030-01-01','2030-01-02','2030-01-03','2030-01-04']
class PerformanceTests(unittest.TestCase):
    def state(self):return initialize_paper_ledger(fixture.plan(),'synthetic')
    def test_partial_fee_and_exact_peak_trough(self):
        s=self.state();s=apply_paper_fill(s,fixture.event(s));before=deepcopy(s)
        r=report(s,session_dates=D,marks={D[0]:{},D[1]:{'a':'20'},D[2]:{'a':'10'},D[3]:{'a':'15'}},through_date=D[-1])
        self.assertEqual([row['equity'] for row in r['daily_ledger']],['100','132','102','117'])
        self.assertEqual(r['total_return'],'17/100');self.assertEqual(r['maximum_close_drawdown'],'5/22')
        self.assertEqual((r['drawdown_peak_date'],r['drawdown_trough_date']),(D[1],D[2]))
        self.assertEqual(r['recorded_fees'],'1');self.assertEqual(r['elapsed_calendar_days'],3)
        self.assertAlmostEqual(r['annualized_return'],1.17**(365/3)-1,places=4)
        self.assertEqual(s,before)
    def test_missing_session_or_held_close_never_ffill(self):
        s=self.state();s=apply_paper_fill(s,fixture.event(s))
        for marks in [{D[0]:{},D[1]:{'a':10},D[3]:{'a':11}}, {D[0]:{},D[1]:{'a':10},D[2]:{},D[3]:{'a':11}}]:
            r=report(s,session_dates=D,marks=marks,through_date=D[-1])
            self.assertEqual(r['status'],'INCOMPLETE');self.assertIsNone(r['annualized_return']);self.assertIsNone(r['maximum_close_drawdown']);self.assertIsNone(r['total_return'])
            self.assertIsNone(r['daily_ledger'][2]['equity'])
    def test_through_excludes_later_fills_and_zero_day(self):
        s=self.state();s=apply_paper_fill(s,fixture.event(s))
        r=report(s,session_dates=D[:1],marks={D[0]:{}},through_date=D[0])
        self.assertEqual(r['daily_ledger'][0]['shares'],{});self.assertEqual(r['daily_ledger'][0]['cash'],'100')
        self.assertEqual(r['recorded_fees'],'0');self.assertEqual(r['excluded_future_fill_count'],1);self.assertIsNone(r['annualized_return'])
        flat=report(self.state(),session_dates=D,marks={d:{} for d in D},through_date=D[-1])
        self.assertEqual(flat['total_return'],'0');self.assertEqual(flat['recorded_fill_count'],0)
    def test_sell_after_activation_cash_history_not_current_shares(self):
        s=self.state();s=apply_paper_fill(s,fixture.event(s));s=apply_paper_order_event(s,fixture.close_event(s))
        new=fixture.next_plan(s,target_quantities={});s=activate_paper_plan(s,new,fixture.activation(s,new))
        s=apply_paper_fill(s,fixture.event(s,event_id='sell',qty=3,price='11',fees='2'))
        r=report(s,session_dates=D,marks={D[0]:{},D[1]:{'a':'10'},D[2]:{},D[3]:{}},through_date=D[-1])
        self.assertEqual(r['daily_ledger'][1]['shares'],{'a':3});self.assertEqual(r['daily_ledger'][2]['shares'],{})
        self.assertEqual(r['daily_ledger'][-1]['cash'],'103');self.assertEqual(r['recorded_fees'],'3')
    def test_missing_fill_calendar_date_is_invalid_not_skipped(self):
        s=self.state();s=apply_paper_fill(s,fixture.event(s))
        with self.assertRaisesRegex(ValueError,'FILL_SESSION_MISSING_FROM_CALENDAR'):
            report(s,session_dates=[D[0],D[2]],marks={D[0]:{},D[2]:{'a':'10'}},through_date=D[2])

    def test_annual_float_overflow_preserves_exact_metrics(self):
        s=self.state();s=apply_paper_fill(s,fixture.event(s))
        r=report(s,session_dates=D[:2],marks={D[0]:{},D[1]:{'a':'100000000000000000000'}},through_date=D[1])
        self.assertEqual(r['status'],'COMPLETE');self.assertIsNone(r['annualized_return'])
        self.assertEqual(r['annualization_unavailable_reason'],'ANNUALIZATION_NOT_REPRESENTABLE_AS_FINITE_FLOAT')
        self.assertEqual(F(r['total_return']),(F(72)+3*10**20)/100-1)
        self.assertEqual(r['maximum_close_drawdown'],'0')

    def test_initial_shares_rejected_and_actions_incomplete(self):
        s=initialize_paper_ledger(fixture.plan(shares={'a':1},target={'a':1}),'initial')
        with self.assertRaisesRegex(ValueError,'FRESH_CASH_GENESIS_REQUIRED'):report(s,session_dates=D,marks={d:{} for d in D},through_date=D[-1])
        r=report(self.state(),session_dates=D,marks={d:{} for d in D},through_date=D[-1],unprocessed_actions=[{'session':D[1],'type':'split'}])
        self.assertEqual(r['status'],'INCOMPLETE');self.assertIsNone(r['total_return'])
        self.assertFalse(r['calendar_verified']);self.assertFalse(r['source_verified'])

if __name__=='__main__':unittest.main()
