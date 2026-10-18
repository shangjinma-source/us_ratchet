from copy import deepcopy
import hashlib
from pathlib import Path
import platform
import tempfile
import unittest

import numpy as np
import pandas as pd
import scipy

from backtest import ndx_candidate_input_equivalence_research as proof


def fixture(directory, engine='equal_weight_fractional_v1'):
    dates = pd.bdate_range('2023-01-02', periods=105)
    columns = ['AAA', 'BBB', 'CCC', 'DDD', 'INC']
    returns = pd.DataFrame(np.random.default_rng(442).normal(.0004, .01, (105, 5)), index=dates, columns=columns)
    universe = pd.DataFrame([dict(ticker=t, security_id='security:' + t, issuer_id='issuer:' + t,
        risk_chain='chain:' + t, synthetic_price=100., median_dollar_volume_usd=100e6,
        old_sector_flag=True) for t in columns])
    inputs = dict(returns=returns, target_returns=returns.INC.copy(), nominal_prices=100 * (1 + returns).cumprod(),
        universe=universe, incumbent_weights={'INC': 1.}, contract=dict(fit_days=63, window_days=21,
        step_days=21, transaction_cost_bps=10., shrinkage_intensity=.35, turnover_anchor_strength=.25,
        max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8, minimum_effective_n_ratio=.7,
        risk_chain_top1_cap=.55, portfolio_cash_usd=5000., minimum_cash_buffer_usd=100.,
        minimum_median_dollar_volume_usd=50e6))
    path = Path(directory) / 'fixture.txt'
    path.write_text('Synthetic numerical comparison; no historical evidence')
    return dict(task=dict(tickers='AAA;BBB;CCC;DDD', holding_count=4,
        weight_spec='equal_weight' if engine == 'equal_weight_fractional_v1' else 'constrained_fixed_shrinkage_turnover_anchor',
        selection_date=str((dates[-1] + pd.offsets.BDay()).date()), decision_data_end=str(dates[-1].date()),
        source_batch='old_subset', universe_track='strict_technology'), inputs=inputs, engine=engine,
        runtime=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__),
        source_hashes=proof.numerical_source_hashes(engine) | {str(path): hashlib.sha256(path.read_bytes()).hexdigest()})


def expand(args):
    result = deepcopy(args)
    data = result['inputs']
    data['returns']['ZZZ'] = .02
    data['nominal_prices']['ZZZ'] = 13.
    row = data['universe'].iloc[0].copy()
    row.update(dict(ticker='ZZZ', security_id='security:ZZZ', issuer_id='issuer:ZZZ', risk_chain='newsector', old_sector_flag=False))
    data['universe'] = pd.concat([data['universe'], row.to_frame().T], ignore_index=True)
    # Preserve numeric dtype so this only changes unused rows/columns/scope.
    data['universe'][['synthetic_price', 'median_dollar_volume_usd']] = data['universe'][['synthetic_price', 'median_dollar_volume_usd']].astype(float)
    result['task'].update(source_batch='new_all_ndx', universe_track='all_point_in_time_ndx')
    return result


class CandidateInputEquivalenceTests(unittest.TestCase):
    def test_extra_unselected_member_preserves_projection_but_not_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            old = fixture(directory)
            result = proof.compare_candidate_numerical_inputs(left=old, right=expand(old))
            self.assertTrue(result['numerical_input_equivalent'])
            self.assertFalse(result['full_training_semantics_equal'])
            self.assertFalse(result['result_reuse_authorized'])
            self.assertFalse(result['new_scope_membership_verified'])

    def test_every_material_channel_breaks_equivalence(self):
        with tempfile.TemporaryDirectory() as directory:
            old = fixture(directory)
            for fault in ('return', 'benchmark', 'target', 'nominal', 'sid', 'issuer', 'risk', 'liquidity',
                          'synthetic', 'contract', 'calendar', 'runtime', 'selection'):
                other = deepcopy(old)
                data = other['inputs']
                if fault == 'return': data['returns'].iloc[0, 0] += .001
                if fault == 'benchmark': data['returns'].iloc[70, 4] += .001
                if fault == 'target': data['target_returns'].iloc[70] += .001
                if fault == 'nominal': data['nominal_prices'].iloc[0, 0] += 1
                if fault in ('sid', 'issuer', 'risk'):
                    key = {'sid': 'security_id', 'issuer': 'issuer_id', 'risk': 'risk_chain'}[fault]
                    data['universe'].loc[0, key] += ':changed'
                if fault == 'liquidity': data['universe'].loc[0, 'median_dollar_volume_usd'] += 1
                if fault == 'synthetic': data['universe'].loc[0, 'synthetic_price'] += 1
                if fault == 'contract': data['contract']['transaction_cost_bps'] += 1
                if fault == 'calendar':
                    for key in ('returns', 'target_returns', 'nominal_prices'):
                        data[key] = data[key].iloc[1:]
                if fault == 'runtime': other['runtime']['numpy'] = 'different'
                if fault == 'selection': other['task']['selection_date'] = '2024-01-01'
                result = proof.compare_candidate_numerical_inputs(left=old, right=other)
                self.assertFalse(result['numerical_input_equivalent'], fault)

    def test_unselected_invalid_data_and_missing_source_cannot_hide_in_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            for fault in ('nan', 'negative_price', 'duplicate_sid', 'source', 'bool'):
                args = expand(fixture(directory))
                if fault == 'nan': args['inputs']['returns'].loc[:, 'ZZZ'] = np.nan
                if fault == 'negative_price': args['inputs']['nominal_prices'].loc[:, 'ZZZ'] = -1
                if fault == 'duplicate_sid': args['inputs']['universe'].loc[5, 'security_id'] = 'security:AAA'
                if fault == 'source': args['source_hashes'].pop(next(iter(proof.numerical_source_hashes(args['engine']))))
                if fault == 'bool': args['inputs']['contract']['transaction_cost_bps'] = True
                with self.assertRaises(ValueError, msg=fault): proof.candidate_numerical_input_fingerprint(**args)

    def test_engine_and_weight_spec_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            for engine in ('unknown', 'joint_weight_v3'):
                changed = dict(args, engine=engine)
                with self.assertRaises(ValueError): proof.candidate_numerical_input_fingerprint(**changed)

    def test_real_synthetic_engines_ignore_added_columns_and_universe_rows(self):
        # These are tiny synthetic executions, never historical training reruns.
        with tempfile.TemporaryDirectory() as directory:
            for engine in sorted(proof.ENGINES):
                old = fixture(directory, engine)
                new = expand(old)
                self.assertTrue(proof.compare_candidate_numerical_inputs(left=old, right=new)['numerical_input_equivalent'])
                def evaluate(args):
                    if engine == 'equal_weight_fractional_v1':
                        inputs = {k: v for k, v in args['inputs'].items() if k != 'nominal_prices'}
                        return proof.equal.evaluate_equal_weight_fractional_batch(combinations=[('AAA','BBB','CCC','DDD')], **inputs)
                    if engine == 'non_equal_fractional_v1':
                        return proof.fractional.evaluate_non_equal_fractional(task=args['task'], inputs=args['inputs'])
                    return proof.joint.evaluate_joint_weight_task_v3(args['task'], **args['inputs'])
                self.assertEqual(evaluate(old), evaluate(new), engine)


if __name__ == '__main__':
    unittest.main()
