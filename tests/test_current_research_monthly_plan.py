from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from data.current_research_fill_ledger import initialize_paper_ledger, apply_paper_fill
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_monthly_plan import build_monthly_research_plan
from data.current_research_successor_plan import roll_research_plan
import test_current_research_successor_plan as fixtures


def session(day, close_hour=16):
    ny=ZoneInfo('America/New_York')
    return dict(date=day,timezone='America/New_York',
        open_at=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ny).isoformat(),
        close_at=datetime.fromisoformat(day+f'T{close_hour:02d}:00:00').replace(tzinfo=ny).isoformat(),source='q')


class MonthlyPlanTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.SuccessorTests();self.f.setUp()
        c=deepcopy(self.f.initial['plan']['causal_inputs'])
        c['research_snapshot'].update(target_month='2026-10',market_session=session('2026-10-14'))
        plan=build_current_research_limit_plan(research_snapshot=c['research_snapshot'],
            quotes=[dict(v,security_id=s) for s,v in c['quotes'].items()],available_cash=c['available_cash'],
            shares=c['shares'],account_revision=c['account_revision'],decision_date=c['decision_date'],
            active_date=c['active_date'],calendar=c['calendar'],strategy_version=c['strategy_version'],target_quantities=c['target_quantities'])
        initial=initialize_paper_ledger(plan,'synthetic')
        self.state=apply_paper_fill(initial,dict(event_id='f',mode='PAPER_MANUAL_FILL',plan_id=plan['plan_id'],
            order_id=plan['orders'][0]['order_id'],qty=2,price='50',fees='0',session='2026-10-14',expected_revision=initial['revision']))

    def build(self,decision='2026-10-14',active='2026-10-15',market=None):
        quotes=[dict(row,as_of=decision) for row in self.f.quotes]
        declaration={'X':dict(self.f.continuity['X'],to_date=decision)}
        args=dict(self.f.args,decision_date=decision,quote_as_of=decision,scenario_dates=[decision])
        if decision=='2026-10-14':quotes=[q for q in quotes if q['security_id']=='X']
        return build_monthly_research_plan(self.state,expected_revision=self.state['revision'],decision_date=decision,
            active_date=active,calendar=[decision,active],valuation_quotes=quotes,source_hashes=self.f.pins,
            held_unit_continuity=declaration,market_session=market or session(active),search_arguments=args,search=self.f.stub)

    def test_monthly_roll_no_search_keeps_selection_and_binds_new_session(self):
        result=self.build();plan=result['plan']
        self.assertEqual(result['route']['action'],'ROLL')
        self.assertEqual(self.f.calls,[])
        self.assertEqual(plan['research_id'],self.state['plan']['research_id'])
        self.assertEqual(plan['causal_inputs']['selection_as_of'],'2026-10-13')
        self.assertEqual(plan['causal_inputs']['research_snapshot']['market_session']['date'],'2026-10-15')
        self.assertEqual(plan['causal_inputs']['research_snapshot']['target_month'],'2026-10')
        self.assertNotEqual(plan['plan_id'],self.build(market=session('2026-10-15',15))['plan']['plan_id'])

    def test_month_boundary_once_binds_new_research_and_target_month(self):
        result=self.build('2026-10-30','2026-11-02')
        self.assertEqual(result['route']['action'],'RESELECT')
        self.assertEqual(len(self.f.calls),1)
        self.assertEqual(result['plan']['research_id'],result['capital_decision']['research_id'])
        self.assertEqual(result['plan']['causal_inputs']['research_snapshot']['target_month'],'2026-11')
        self.assertEqual(result['plan']['causal_inputs']['research_snapshot']['market_session']['date'],'2026-11-02')

    def test_stale_session_and_missing_target_month_rejected(self):
        with self.assertRaises(ValueError):self.build('2026-10-30','2026-11-02',session('2026-10-15'))
        self.assertEqual(self.f.calls,[])
        with self.assertRaisesRegex(ValueError,'BOUND_TARGET_MONTH_REQUIRED'):
            build_monthly_research_plan(self.f.state,expected_revision=self.f.state['revision'],decision_date='2026-10-14',active_date='2026-10-15',calendar=['2026-10-14','2026-10-15'],valuation_quotes=self.f.quotes,source_hashes=self.f.pins,held_unit_continuity=self.f.continuity,market_session=session('2026-10-15'),search=self.f.stub)

    def test_legacy_roll_strips_old_session_and_month(self):
        plan=roll_research_plan(self.state,expected_revision=self.state['revision'],decision_date='2026-10-14',active_date='2026-10-15',calendar=['2026-10-14','2026-10-15'],valuation_quotes=[self.f.quotes[1]],source_hashes=self.f.pins,held_unit_continuity=self.f.continuity)['plan']
        snapshot=plan['causal_inputs']['research_snapshot']
        self.assertNotIn('market_session',snapshot)
        self.assertNotIn('target_month',snapshot)


if __name__=='__main__':unittest.main()
