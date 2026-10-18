"""Synthetic sequential refits into one continuous frozen-lot account."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from backtest import ndx_dynamic_cutoff_refit_v2_research as fitter
from backtest import ndx_dynamic_refit_schedule_research as builder
from backtest import ndx_dynamic_identity_execution_research as execution
import test_ndx_dynamic_identity_execution_independent_oracle as identity_oracles


def inputs(directory, rename=False):
    account, stable_prices = identity_oracles.IndependentIdentityOracles().fixture(directory, rename=rename)
    decisions = []
    for index, row in enumerate(account['schedule']):
        names = sorted(target['ticker'] for target in row['targets'].values())
        dates = pd.bdate_range(end=row['decision_date'], periods=30)
        returns = pd.DataFrame({name: np.sin(np.arange(30) * (column + 1) + index) * .01
                               for column, name in enumerate(names)}, index=dates)
        path = Path(directory) / ('returns' + str(index) + '.json')
        raw = returns.to_json(orient='split', date_format='iso').encode()
        path.write_bytes(raw)
        parameters = {key: account[key] for key in execution.engine._RISK_KEYS}
        parameters.update(fit_days=20, shrinkage_intensity=.35, turnover_anchor_strength=.25)
        decisions.append(dict(decision_date=row['decision_date'], execution_date=row['execution_date'],
            cutoff=row['decision_date'], returns=returns,
            selected={sid: dict(ticker=target['ticker'], issuer_id=target['issuer_id'], risk_chain=sid)
                      for sid, target in row['targets'].items()},
            weight_spec='constrained_fixed_shrinkage_turnover_anchor', parameters=parameters,
            source_hashes={str(path.resolve()): hashlib.sha256(raw).hexdigest()}))
    return account, stable_prices, decisions


def simulate(account, built):
    arguments = deepcopy(account)
    arguments['schedule'] = built['schedule']
    arguments['risk_chains_by_decision'] = built['risk_chains_by_decision']
    return execution.simulate_dynamic_identity_execution_research(**arguments)


class SequentialRefitExecutionIntegration(unittest.TestCase):
    def test_real_refits_variable_k_one_continuous_account_match_direct_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            account, prices, decisions = inputs(directory)
            built = builder.build_refit_schedule_research(calendar=account['calendar'], decisions=decisions)
            manual, prior = [], None
            for row in decisions:
                fitted = fitter.refit_dynamic_cutoff_weights(returns=row['returns'], cutoff=row['cutoff'],
                    selected=row['selected'], weight_spec=row['weight_spec'],
                    previous_target_weights=prior, **row['parameters'])
                manual.append(dict(decision_date=row['decision_date'], execution_date=row['execution_date'],
                                   targets=fitted['targets']))
                prior = {sid: target['target_weight'] for sid, target in fitted['targets'].items()}
            self.assertEqual(built['schedule'], manual)
            actual = simulate(account, built)
            arguments = {key: value for key, value in account.items() if key not in ('calendar', 'securities')}
            arguments.update(schedule=manual, risk_chains_by_decision=built['risk_chains_by_decision'])
            expected = execution.engine.simulate_dynamic_frozen_execution_research(
                closes=prices, opens=prices, **arguments)
            identity_oracles.IndependentIdentityOracles().assert_economics(actual, expected)
            self.assertEqual(actual['summary']['k_path'], [1, 2, 1])
            self.assertEqual([day['session'] for day in actual['daily']], account['calendar'])
            self.assertEqual(actual['executions'][-1]['status'], 'FILLED')
            self.assertFalse(actual['promotion_allowed'])

    def test_rename_preserves_anchor_sid_and_frozen_economics(self):
        with tempfile.TemporaryDirectory() as directory:
            account, _, decisions = inputs(directory, rename=True)
            built = builder.build_refit_schedule_research(calendar=account['calendar'], decisions=decisions)
            actual = simulate(account, built)
            self.assertEqual(built['schedule'][0]['targets']['S1']['ticker'], 'AAA')
            self.assertEqual(built['schedule'][1]['targets']['S1']['ticker'], 'AXX')
            before, after = actual['daily'][1:3]
            self.assertGreater(before['shares']['S1'], 0)
            self.assertEqual(before['shares'], after['shares'])
            self.assertEqual(before['cash_usd'], after['cash_usd'])
            self.assertEqual(after['tickers']['S1'], 'AXX')
            self.assertFalse(any(trade['session'] == after['session'] for trade in actual['trades']))
            # Replacing the declared decision ticker with a future/wrong label
            # must still fail in the internal bridge, even with a valid fit.
            wrong = deepcopy(built)
            wrong['schedule'][0]['targets']['S1']['ticker'] = 'AXX'
            with self.assertRaises(ValueError):
                simulate(account, wrong)

    def test_rejected_first_fill_does_not_reset_cash_or_rewrite_later_target_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            account, _, decisions = inputs(directory)
            built = builder.build_refit_schedule_research(calendar=account['calendar'], decisions=decisions)
            normal = simulate(account, built)
            reference = account['securities']['S1']['intervals'][0]['price_artifact']
            path = Path(reference['path'])
            payload = json.loads(path.read_text())
            payload['rows'][1]['Open'] = 10000.
            raw = json.dumps(payload).encode()
            path.write_bytes(raw)
            reference['sha256'] = hashlib.sha256(raw).hexdigest()
            changed = simulate(account, built)
            self.assertEqual(changed['executions'][0]['status'], 'REJECTED')
            self.assertEqual(changed['daily'][1]['shares'], {})
            self.assertEqual(changed['daily'][1]['cash_usd'], account['initial_cash_usd'])
            self.assertEqual(changed['decisions'][0], normal['decisions'][0])
            self.assertEqual([row['targets'] for row in changed['decisions']],
                             [row['targets'] for row in normal['decisions']])
            self.assertEqual([day['session'] for day in changed['daily']], account['calendar'])
            self.assertEqual(changed['executions'][1]['status'], 'FILLED')
            self.assertGreater(sum(trade['transaction_cost_usd'] for trade in changed['trades']), 0)


if __name__ == '__main__':
    unittest.main()
