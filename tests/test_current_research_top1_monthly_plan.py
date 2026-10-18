from copy import deepcopy
import unittest
from unittest.mock import patch
from data.current_research_monthly_plan import build_monthly_research_plan
from data.current_research_fill_ledger import activate_paper_plan, apply_paper_order_event
from data.current_research_capital_decision import decide_quantity_for_account
from backtest.return_priority_monthly_top1_selector import decide_top1_for_account, VERSION
import test_current_research_monthly_plan as monthly_fixtures
session = monthly_fixtures.session


class Top1MonthlyPlanTests(unittest.TestCase):
    def setUp(self):
        fixture = monthly_fixtures.MonthlyPlanTests(); fixture.setUp()
        self.state = fixture.state; self.f = fixture.f
        self.pins = dict(self.f.pins, **{'backtest/return_priority_monthly_top1_selector.py':'d'*64})
        self.args = dict(self.f.args, decision_date='2026-10-30', quote_as_of='2026-10-30',
            training_scenarios=[{'B':'1.2'} for _ in range(12)],
            scenario_dates=['2025-11-01','2025-12-01']+[f'2026-{m:02d}-01' for m in range(1,11)])
        self.kw = dict(expected_revision=self.state['revision'],decision_date='2026-10-30',
            active_date='2026-11-02',calendar=['2026-10-30','2026-11-02'],
            valuation_quotes=[dict(q,as_of='2026-10-30') for q in self.f.quotes],
            source_hashes=self.pins,held_unit_continuity={'X':dict(self.f.continuity['X'],to_date='2026-10-30')},
            market_session=session('2026-11-02'),search_arguments=self.args,capital_decision=decide_top1_for_account)

    def test_real_top1_reselect_then_roll_preserves_method_and_zero_selection(self):
        before = deepcopy(self.state)
        with patch('backtest.return_priority_fresh_cash_quantity_search.search_fresh_cash_quantities', side_effect=AssertionError('no core')):
            result=build_monthly_research_plan(self.state,**self.kw)
        plan=result['plan'];self.assertEqual(self.state,before)
        self.assertEqual(result['capital_decision']['selector_calls'],1)
        self.assertEqual(result['capital_decision']['core_calls'],0)
        self.assertEqual(plan['target_quantities'],{'B':5})
        self.assertEqual(plan['causal_inputs']['research_snapshot']['selection_method'],VERSION)
        self.assertEqual([(o['side'],o['security_id']) for o in plan['orders']],[('SELL','X')])
        state=activate_paper_plan(self.state,plan,dict(event_id='activate',mode='PAPER_MANUAL_FILL',
            event_type='ACTIVATE_PLAN',plan_id=plan['plan_id'],expected_revision=self.state['revision']))
        state=apply_paper_order_event(state,dict(event_id='cancel',mode='PAPER_MANUAL_FILL',event_type='CANCEL',
            plan_id=plan['plan_id'],order_id=plan['orders'][0]['order_id'],expected_revision=state['revision']))
        kw=dict(expected_revision=state['revision'],decision_date='2026-11-02',active_date='2026-11-03',
            calendar=['2026-11-02','2026-11-03'],valuation_quotes=[dict(q,as_of='2026-11-02') for q in self.f.quotes],
            source_hashes=self.pins,held_unit_continuity={s:dict(from_date='2026-10-30',to_date='2026-11-02',
                price_basis='UNIT',status='NO_UNPROCESSED_ACTIONS',source_references=['q']) for s in ['X','B']},
            market_session=session('2026-11-03'))
        with patch('backtest.return_priority_monthly_top1_selector.select_top1_quantities',side_effect=AssertionError('no roll selection')):
            rolled=build_monthly_research_plan(state,**kw)
        next_kw=dict(kw, decision_date='2026-11-30',active_date='2026-12-01',
            calendar=['2026-11-30','2026-12-01'],market_session=session('2026-12-01'),
            valuation_quotes=[dict(q,as_of='2026-11-30') for q in self.f.quotes],
            held_unit_continuity={sid:dict(v,to_date='2026-11-30') for sid,v in kw['held_unit_continuity'].items()},
            search_arguments=dict(self.args,decision_date='2026-11-30',quote_as_of='2026-11-30'))
        with patch('data.current_research_capital_decision.search_fresh_cash_quantities',side_effect=AssertionError('no quantity core')):
            next_month=build_monthly_research_plan(state,**next_kw)
        self.assertEqual(next_month['capital_decision']['selector_calls'],1)
        self.assertEqual(next_month['capital_decision']['core_calls'],0)
        self.assertEqual(next_month['plan']['causal_inputs']['research_snapshot']['selection_method'],VERSION)
        self.assertEqual(rolled['search_calls'],0)
        self.assertEqual(rolled['plan']['research_id'],plan['research_id'])
        self.assertEqual(rolled['plan']['target_quantities'],plan['target_quantities'])
        self.assertEqual(rolled['plan']['causal_inputs']['research_snapshot']['selection_method'],VERSION)
        with self.assertRaisesRegex(ValueError,'ROLL_CANNOT_CHANGE_SELECTION_METHOD'):
            build_monthly_research_plan(state,capital_decision=decide_quantity_for_account,**kw)

    def test_custom_search_conflict_and_untrusted_adapter_rejected(self):
        with self.assertRaisesRegex(ValueError,'CUSTOM_SEARCH_AND_CAPITAL_DECISION_CONFLICT'):
            build_monthly_research_plan(self.state,search=self.f.stub,**self.kw)
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_CAPITAL_DECISION_ADAPTER'):
            build_monthly_research_plan(self.state,**dict(self.kw,capital_decision=lambda **kw:{}))
        self.assertEqual(self.f.calls,[])


if __name__ == '__main__':unittest.main()
