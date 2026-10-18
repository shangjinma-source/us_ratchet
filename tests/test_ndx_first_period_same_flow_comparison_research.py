from copy import deepcopy
from decimal import localcontext, Inexact
from fractions import Fraction
import unittest
from backtest import ndx_first_period_same_flow_comparison_research as core
from test_ndx_first_period_incumbent_cash_flow_independent_readback_20261003 import documents


def fixture():
    d=documents(); candidates=d['docs'][d['refs']['candidates']['path']]; incumbent=d['account']
    calendar=candidates['observed_calendar']
    for i,row in enumerate(candidates['rows']):
        source=incumbent['paths'][0 if row['input_row']['cash_event']['amount_usd']=='1000' else 1]['account']
        row['account']=deepcopy(source)
        row['account']['schema']='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1'
        row['account']['rows']=row['account'].pop('daily')
        row['account']['cash_event_timing']='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES'
        row['account']['rows'][0]['cumulative_twr']=core.window.ratio(Fraction(-1,10))
        row['account']['rows'][-1]['cumulative_twr']=core.window.ratio(Fraction(1,5))
        row['account']['chained_twr']=core.window.ratio(Fraction(1,5))
        row['selected_plan_reference']=dict(path='selected.json',sha256='a'*64,json_pointer=f'/rows/{i}')
        row['saved_selection']={'zero_slot_preserved':0,'gap':'CONDITIONAL'}
        row['selection_reference']=deepcopy(row['selected_plan_reference'])
    nav=dict(schema='RETURN_SIX_PERIOD_REUSED_BENCHMARK_PREFIX_V1',calendar=deepcopy(calendar),formal_dual_benchmark_admission=False,execution_rerun=False,point_in_time_verified=False,promotion_allowed=False,
        nav=dict(role='012922_NATIVE_CURRENCY_RETROSPECTIVE_NAV',publication_time_verified=False,currency_fx_equivalence_verified=False,subscription_redemption_fee_equivalence_verified=False,
        rows=[dict(session=day,nav_date=day,nav=1.0 if i<106 else 1.1) for i,day in enumerate(calendar)]))
    return dict(candidate_accounts=candidates,incumbent_accounts=incumbent,benchmark_document=nav,candidate_reference=d['refs']['candidates'],incumbent_reference=d['account_reference'],benchmark_reference=dict(path='nav.json',sha256='c'*64))


class Tests(unittest.TestCase):
    def test_eight_full_windows_metrics_refs_and_no_input_mutation(self):
        args=fixture();before=deepcopy(args);result=core.compare_first_period_paths(**args)
        self.assertEqual(args,before);self.assertEqual(result['scenario_count'],8)
        for row in result['rows']:
            self.assertEqual(len(row['calendar']),107)
            self.assertEqual(row['metrics']['candidate']['interval_count'],106)
            self.assertEqual(core.window.from_ratio(row['metrics']['candidate']['cumulative_return']),Fraction(1,5))
            self.assertEqual(core.window.from_ratio(row['metrics']['candidate']['maximum_drawdown']),Fraction(1,10))
            self.assertEqual(core.window.from_ratio(row['nav_distances']['absolute_distances']['candidate']['cumulative_return']),Fraction(1,10))
            self.assertFalse(row['decision_information_sets_equivalent'])
        self.assertFalse(result['cohort_statistics_computed'])

    def test_wrong_window_flow_initial_marks_and_mapping_rejected(self):
        for mode in ('short','flow','cash','shares','mapping'):
            args=fixture()
            if mode=='short':args['benchmark_document']['calendar']=args['benchmark_document']['calendar'][20:]
            elif mode=='flow':args['incumbent_accounts']['paths'][0]['account']['daily'][1]['cash_injection_usd']='1'
            elif mode=='cash':args['incumbent_accounts']['paths'][0]['account']['initial']['cash_usd']='26000'
            elif mode=='shares':args['incumbent_accounts']['paths'][0]['account']['initial']['holdings']['A']=1
            else:args['incumbent_accounts']['scenario_mappings'][0]['candidate_account_reference']['json_pointer']='/rows/1'
            with self.subTest(mode=mode),self.assertRaises(ValueError):core.compare_first_period_paths(**args)

    def test_nav_future_conflicting_date_or_permission_rejected(self):
        for mode in ('future','same-date','permission','bool'):
            args=fixture();nav=args['benchmark_document']['nav']
            if mode=='future':nav['rows'][0]['nav_date']='2023-04-01'
            elif mode=='same-date':nav['rows'][1].update(nav_date=nav['rows'][0]['nav_date'],nav=2.0)
            elif mode=='permission':nav['publication_time_verified']=True
            else:nav['rows'][0]['nav']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):core.compare_first_period_paths(**args)

    def test_hostile_context_and_all_cash_twr_not_equity_ratio(self):
        args=fixture()
        for row in args['candidate_accounts']['rows']:
            for day in row['account']['rows']:
                day['cumulative_twr']=core.window.ratio(Fraction(0));day['close_equity_usd']='999999999'
            row['account']['chained_twr']=core.window.ratio(Fraction(0))
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            result=core.compare_first_period_paths(**args)
        self.assertEqual(result['rows'][0]['metrics']['candidate']['cumulative_return'],core.window.ratio(Fraction(0)))
        self.assertEqual(Fraction(result['rows'][0]['metrics']['candidate']['annualized_return_diagnostic_decimal']),0)

if __name__=='__main__':unittest.main()
