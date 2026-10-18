from copy import deepcopy
from datetime import date,timedelta
import unittest
from unittest.mock import patch
from backtest import ndx_return_priority_historical_counterexample_research as subject


def fixture():
    days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(127)]
    securities=[dict(security_id=f'S{i}',issuer_id=f'I{i}',ticker=f'T{i}',risk_chain=f'C{i}') for i in range(77)]
    prepared=dict(securities=securities,initial_prices={f'S{i}':50. for i in range(77)},
        target_prices={f'S{i}':99999. for i in range(77)},returns={f'S{i}':[0.]*84+[.01]*42 for i in range(77)},
        return_dates=days[1:],initial_price_date=days[0],cutoff=days[-1],observed_provenance=[dict(ticker=f'P{i}') for i in range(101)],
        source_bindings={},source_checks=[],policy=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),
        original8_definition=[dict(security_id=f'S{i}',issuer_id=f'I{i}',ticker=f'T{i}',risk_chain=f'C{i}',target_weight=.125) for i in range(7)]
        +[dict(security_id='TSM',issuer_id='ITSM',ticker='TSM',risk_chain='foundry',target_weight=.125)],
        plan=dict(cash_usd=20000,fee_bps=10,research_buffer_usd=100,finite_budgets=dict(support_proposals_per_k=64,objective_evaluations_per_support=64,
            integer_deployment_proposals_per_support=128,global_objective_evaluations=311296,global_integer_deployment_proposals=622592)))
    data=[[50.]*77 for _ in days];data[84]=[100.]*77;data[-1]=[99999.]*77
    panel=dict(nominal_close=dict(index=[day+'T00:00:00' for day in days],columns=[f'T{i}' for i in range(77)],data=data))
    tsm=dict(quotes=[dict(session=day,nominal_close=100.) for day in days],returns=[dict(session=day,price_return=.01 if i>=84 else 0.) for i,day in enumerate(days[1:])])
    return prepared,panel,tsm


class Counterexample(unittest.TestCase):
    def test_chronology_actual_fit_price_and_heldout_perturbation_isolation(self):
        prepared,panel,tsm=fixture()
        a=subject.chronology_inputs(prepared=prepared,panel=panel,tsm_sidecar=tsm)
        altered=deepcopy(prepared);altered['returns']['S0'][84:]=[-.9]*42
        altered_panel=deepcopy(panel);altered_panel['nominal_close']['data'][-1]=[1.e9]*77
        b=subject.chronology_inputs(prepared=altered,panel=altered_panel,tsm_sidecar=tsm)
        self.assertEqual(a['train_returns'],b['train_returns'])
        self.assertEqual(a['target_prices'],b['target_prices'])
        self.assertEqual(a['target_prices']['S0'],100.)
        self.assertEqual(len(a['train_dates']),84)
        self.assertEqual(len(a['evaluation_dates']),42)
        self.assertLess(a['train_dates'][-1],a['evaluation_dates'][0])

    def test_selector_never_receives_last42_or_last_price_and_no_heldout_ranking(self):
        prepared,panel,tsm=fixture();sliced=subject.chronology_inputs(prepared=prepared,panel=panel,tsm_sidecar=tsm)
        selected=[dict(quantities={f'S{i}':49 for i in range(4)},training_metrics=dict(cagr=0.)),
                  dict(quantities={f'S{i}':48 for i in range(4)},training_metrics=dict(cagr=0.))]
        selection=dict(co_winners=deepcopy(selected),budget=dict(objective_calls=5,integer_proposals=3))
        with patch.object(subject,'run_bounded_search',return_value=selection) as mock:
            result=subject.calculate_counterexample(prepared=prepared,sliced=sliced)
        call=mock.call_args.kwargs
        self.assertEqual(call['returns']['S0'],[0.]*84)
        self.assertEqual(call['target_prices']['S0'],100.)
        self.assertEqual(call['return_dates'],prepared['return_dates'][:84])
        self.assertEqual(result['frozen_training_co_winners'],selected)
        self.assertEqual(len(result['heldout_evaluations']),2)
        self.assertEqual(result['budgets']['total_objective_calls'],8)
        self.assertEqual(result['budgets']['original8_training_metric_calls'],0)
        winner=result['heldout_evaluations'][0]
        self.assertEqual(winner['quantities'],selected[0]['quantities'])
        final=380.4+19600*1.01**42
        self.assertAlmostEqual(winner['net_wealth_path'][-1],final)
        self.assertAlmostEqual(winner['historical_evaluation_metrics']['cagr'],(final/20000)**6-1)
        self.assertAlmostEqual(winner['historical_evaluation_metrics']['maximum_drawdown'],19.6/20000)
        self.assertFalse(result['fresh_future_oos'])

    def test_missing_boundary_session_is_not_compressed(self):
        prepared,panel,tsm=fixture();panel['nominal_close']['index'].pop(84)
        with self.assertRaises(ValueError):subject.chronology_inputs(prepared=prepared,panel=panel,tsm_sidecar=tsm)


if __name__=='__main__':unittest.main()
