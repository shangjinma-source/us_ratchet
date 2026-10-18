from copy import deepcopy
from datetime import date,timedelta
import unittest
from unittest.mock import patch
from backtest import ndx_return_priority_126_126_counterexample_research as subject


def fixture():
    days=['2025-09-18']+[(date(2025,9,19)+timedelta(days=i)).isoformat() for i in range(125)]+['2026-03-20']
    days += [(date(2026,3,21)+timedelta(days=i)).isoformat() for i in range(125)]+['2026-09-21']
    securities=[dict(security_id=f'S{i}',issuer_id=f'I{i}',ticker=f'T{i}',risk_chain=f'C{i}') for i in range(77)]
    rows=[]
    for coordinate in securities:
        quotes=[dict(session=day,nominal_close='100',nominal_close_exact='100') for day in days]
        returns=[dict(session=current,previous_session=previous,dividends_included=False,
            split_only_return_exact='0' if i<126 else '1/100',split_only_return_float=0. if i<126 else .01)
            for i,(previous,current) in enumerate(zip(days,days[1:]))]
        channel=dict(status='CONDITIONAL_NUMERIC_RESULT',ticker=coordinate['ticker'],quote_rows=quotes,return_rows=returns,
                     training_returns=deepcopy(returns[:126]),evaluation_returns=deepcopy(returns[126:]))
        rows.append(dict(coordinate=coordinate,channel=channel))
    bulk=dict(calendar253=days,training_return_count=126,evaluation_return_count=126,security_count=77,issuer_count=76,
        observed_security_count=101,point_in_time_verified=False,future_independent_oos=False,evaluation_interval_previously_used_for_fitting=True,
        rows=rows,conditional_numeric_channel_count=77,blocked_price_channel_count=0,original_identity_assumed_window=dict(first='2026-03-20',last='2026-09-21'))
    # Original77/76 count is represented by a two-class issuer; candidate below uses distinct first4.
    securities[-1]['issuer_id']=securities[-2]['issuer_id']
    rows[-1]['coordinate']['issuer_id']=securities[-2]['issuer_id']
    prepared=dict(securities=securities,original8_definition=[dict(security_id=f'S{i}',issuer_id=f'I{i}',ticker=f'T{i}',risk_chain=f'C{i}',target_weight=.125) for i in range(7)]
        +[dict(security_id='TSM',issuer_id='ITSM',ticker='TSM',risk_chain='foundry',target_weight=.125)],
        policy=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),
        observed_provenance=[dict(ticker=f'P{i}') for i in range(101)],source_bindings={},source_checks=[],
        plan=dict(cash_usd=20000,fee_bps=10,research_buffer_usd=100,finite_budgets=dict(support_proposals_per_k=64,objective_evaluations_per_support=64,
            integer_deployment_proposals_per_support=128,global_objective_evaluations=311296,global_integer_deployment_proposals=622592)))
    tsm=dict(quotes=[dict(session=day,nominal_close=100.) for day in days[126:]],returns=[dict(session=day,price_return=.01) for day in days[127:]])
    return prepared,bulk,tsm


class Counterexample126(unittest.TestCase):
    def test_126_boundary_target_and_future_mutation_excluded_from_solver(self):
        prepared,bulk,tsm=fixture();a=subject.prepare_chronology(prepared=prepared,bulk=bulk,tsm=tsm)
        altered=deepcopy(bulk);c=altered['rows'][0]['channel']
        c['quote_rows'][-1].update(nominal_close='99999',nominal_close_exact='99999')
        c['return_rows'][-1].update(split_only_return_exact='-9/10',split_only_return_float=-.9)
        c['evaluation_returns']=deepcopy(c['return_rows'][126:])
        b=subject.prepare_chronology(prepared=prepared,bulk=altered,tsm=tsm)
        self.assertEqual(a['train_returns'],b['train_returns'])
        self.assertEqual(a['initial_prices'],b['initial_prices'])
        self.assertEqual(a['target_prices'],b['target_prices'])
        self.assertNotEqual(a['heldout_returns'],b['heldout_returns'])
        self.assertEqual(a['fit_cutoff'],'2026-03-20')
        self.assertEqual(len(a['train_dates']),126)
        self.assertEqual(len(a['evaluation_dates']),126)

    def test_fixed_quantities_128_point_paths_cagr2_and_single_control_call(self):
        prepared,bulk,tsm=fixture();sliced=subject.prepare_chronology(prepared=prepared,bulk=bulk,tsm=tsm)
        winner=dict(quantities={f'S{i}':49 for i in range(4)},training_metrics=dict(cagr=0.),net_wealth_path=[20000.]*128)
        selected=dict(co_winners=[winner],budget=dict(objective_calls=10,integer_proposals=3))
        with patch.object(subject,'run_bounded_search',return_value=selected) as mock:
            result=subject.calculate_counterexample(prepared=prepared,sliced=sliced)
        args=mock.call_args.kwargs
        self.assertEqual(args['cutoff'],'2026-03-20')
        self.assertEqual(args['returns']['S0'],[0.]*126)
        self.assertEqual(args['target_prices']['S0'],100.)
        self.assertEqual(args['seed'],20261013)
        held=result['heldout_evaluations'][0];final=380.4+19600*1.01**126
        self.assertEqual(len(held['net_wealth_path']),128)
        self.assertAlmostEqual(held['net_wealth_path'][-1],final)
        self.assertAlmostEqual(held['historical_evaluation_metrics']['cagr'],(final/20000)**2-1)
        self.assertEqual(held['quantities'],winner['quantities'])
        self.assertEqual(result['budgets']['total_objective_calls'],12)
        self.assertEqual(result['budgets']['original8_evaluation_calls'],1)
        self.assertEqual(result['budgets']['original8_training_metric_calls'],0)
        self.assertEqual(result['frozen_training_co_winners'],[winner])
        self.assertEqual(len(result['original8_heldout_control']['original8_definition']),8)
        self.assertEqual(len(result['original8_heldout_control']['net_wealth_path']),128)
        self.assertFalse(result['fresh_future_oos'])

    def test_missing_boundary_or_nonfinite_channel_rejected(self):
        prepared,bulk,tsm=fixture();altered=deepcopy(bulk);altered['rows'][0]['channel']['quote_rows'].pop(126)
        with self.assertRaises(ValueError):subject.prepare_chronology(prepared=prepared,bulk=altered,tsm=tsm)
        altered=deepcopy(bulk);altered['rows'][0]['channel']['return_rows'][0]['split_only_return_float']=float('nan')
        altered['rows'][0]['channel']['training_returns'][0]['split_only_return_float']=float('nan')
        with self.assertRaises(ValueError):subject.prepare_chronology(prepared=prepared,bulk=altered,tsm=tsm)


if __name__=='__main__':unittest.main()
