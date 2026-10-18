"""Source-bound two-session GOOG accounting regression, not a strategy result."""
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from backtest.ndx_next_session_execution_research import simulate_next_session_execution_research
from backtest.ndx_next_session_execution_research_v2 import simulate_next_session_execution_research_v2

RAW = ROOT/'data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/raw/GOOG.csv'
AUDIT = ROOT/'data/cache/research/ndx_joint_weight_experiment_v2/SPLIT_ACCOUNTING_AUDIT_20260911.md'
EXPECTED = {RAW: '962f962edc5292f4a10433b41afacd5949c69b10d163ec1e3453710c4962c510',
            AUDIT: '0aa192d2d96c2886cc1945c4001e6729f17f1c4a1ed2364e95dbe3b4a637c89a'}


def run():
    loaded = {p: p.read_bytes() for p in EXPECTED}
    if any(hashlib.sha256(loaded[p]).hexdigest() != h for p, h in EXPECTED.items()):
        raise ValueError('Explicit regression input identity differs')
    frame = pd.read_csv(io.BytesIO(loaded[RAW]), index_col=0, parse_dates=True)
    prices = frame.loc['2022-07-15':'2022-07-18', ['Close']].rename(columns={'Close': 'GOOG'})
    if list(prices.index.strftime('%Y-%m-%d')) != ['2022-07-15', '2022-07-18']:
        raise ValueError('Regression session rows differ')
    arguments = dict(prices=prices, execution_calendar=prices.index,
        schedule=[('2022-07-18', {'GOOG': 1.})], initial_cash=0., initial_shares={'GOOG': 1},
        minimum_cash_buffer_usd=0., transaction_cost_bps=10., risk_chain_by_ticker={'GOOG': 'GOOG'},
        constraints=dict(max_single_weight=1., min_single_weight=.01, top_weight_cap=1.,
            minimum_effective_n_ratio=.7, risk_chain_top1_cap=1.),
        domain_radius=1, max_evaluations_per_rebalance=100, selection_policy='TRACKING_FIRST')
    event = dict(ticker='GOOG', session='2022-07-18', new_shares=20, old_shares=1,
        source_url='https://www.sec.gov/Archives/edgar/data/1652044/000165204422000068/googexhibit991q22022.htm',
        evidence_sha256=EXPECTED[AUDIT])
    old = simulate_next_session_execution_research(**arguments)
    new = simulate_next_session_execution_research_v2(**arguments, corporate_actions=[event])
    if new['terminal_shares'] != {'GOOG': 20} or new['total_fees_usd'] != 0. or new['executions']:
        raise AssertionError('Split accounting regression failed')
    expected_return = 20*float(prices.iloc[1, 0])/float(prices.iloc[0, 0])-1
    if abs(new['path_return_net']-expected_return) > 1e-12:
        raise AssertionError('Share-adjusted marked return differs')
    if any(p.read_bytes() != raw for p, raw in loaded.items()):
        raise ValueError('Input changed during probe')
    return dict(schema='ndx_split_execution_probe_v1', scope='TWO_SESSION_ACCOUNTING_REGRESSION_ONLY',
        source_hashes={str(p): h for p, h in EXPECTED.items()},
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        old_without_split=old, new_with_explicit_split=new,
        event_evidence_kind='LOCAL_REVIEW_NOTE_OF_OFFICIAL_RETROSPECTIVE_RELEASE_NOT_WEB_BYTES',
        event_announcement_point_in_time_verified=False, full_corporate_action_coverage_verified=False,
        constraints_are_regression_only_not_candidate_admission=True, promotion_allowed=False)


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
