import copy
import unittest
import pandas as pd
from backtest import ndx_dynamic_frozen_execution_research as engine
from backtest import ndx_frozen_accounting_independent_audit_research as independent


def fixture(first_open=100., expensive=False):
    calendar=['2023-03-31','2023-04-03','2023-04-04','2023-04-05']
    names=list('ABCDE')
    schedule=[]
    for decision,execution,selected in [(calendar[0],calendar[1],'ABCD'),(calendar[2],calendar[3],'BCDE')]:
        schedule.append(dict(decision_date=decision,execution_date=execution,
            targets={s:dict(ticker=s,issuer_id='issuer:'+s,target_weight=.25) for s in selected}))
    prices={d:{s:dict(ticker=s,open=100000. if expensive else first_open if d==calendar[1] else 100.,
        close=100000. if expensive else 100.) for s in names} for d in calendar}
    chains={r['decision_date']:{s:s for s in r['targets']} for r in schedule}
    contract=dict(initial_cash_usd=25000.,minimum_cash_buffer_usd=100.,transaction_cost_bps=10.,
        max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
    frames={kind:pd.DataFrame({s:[prices[d][s][kind] for d in calendar] for s in names},index=pd.DatetimeIndex(calendar)) for kind in ('open','close')}
    result=engine.simulate_dynamic_frozen_execution_research(opens=frames['open'],closes=frames['close'],schedule=schedule,
        risk_chains_by_decision=chains,corporate_actions=[],valuation_end_date=calendar[-1],max_repair_evaluations=64,**contract)
    return dict(execution=result,calendar=calendar,schedule=schedule,prices=prices,risk_chains_by_decision=chains,contract=contract)


class IndependentAccountingTests(unittest.TestCase):
    def test_real_engine_two_baskets_class_exit_and_entry(self):
        args=fixture(); report=independent.audit(**args)
        self.assertEqual(report['execution_count'],2)
        self.assertEqual(set(report['terminal_shares']),set('BCDE'))
        self.assertFalse(report['engine_called'])

    def test_gap_reject_then_next_decision_fills(self):
        report=independent.audit(**fixture(first_open=1000.))
        self.assertEqual(report['rejected_count'],1)
        self.assertEqual(set(report['terminal_shares']),set('BCDE'))

    def test_no_plan_no_execution(self):
        report=independent.audit(**fixture(expensive=True))
        self.assertEqual(report['execution_count'],0)
        self.assertEqual(report['terminal_shares'],{})

    def test_reject_saved_mutations_and_price_coordinate(self):
        original=fixture()
        changes=[lambda a:a['execution']['daily'][1].update(cash_usd=999.),
            lambda a:a['execution']['executions'][0].update(status='REJECTED'),
            lambda a:a['execution']['decisions'][0]['delta'].update(A=1),
            lambda a:a['execution']['trades'].pop(),
            lambda a:a['execution']['daily'].pop(),
            lambda a:a['prices'][original['calendar'][1]]['A'].update(open=True)]
        for change in changes:
            with self.subTest(change=change):
                args=copy.deepcopy(original);change(args)
                with self.assertRaises(ValueError): independent.audit(**args)


if __name__=='__main__': unittest.main()
