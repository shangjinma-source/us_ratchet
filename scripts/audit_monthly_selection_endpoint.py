"""Read saved monthly selections against endpoint ranking; no search or book imports."""
import argparse
from collections import defaultdict
from fractions import Fraction as F
from hashlib import sha256
import json
from math import prod
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARED = 'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'
PREPARED_SHA = '83f30b31b941c5a406179ae2625395794d15a1a1e1a2427876ab307d2df19921'
COMPARISON = 'tmp/monthly_latched_exit_comparison_20261016_v1/comparison.json'
COMPARISON_SHA = 'f4bde7366d4e2375952f34d4d1548d0a1032b738d6754836b62c035ab9dace57'
OUTPUT = 'tmp/monthly_selection_endpoint_audit_20261016_v1'
ARMS = {
    'B0': 'tmp/daily_exclusion_B0_20261016_v1/outcome.json',
    'R2': 'tmp/daily_exclusion_R2_20261016_v1/R2/outcome.json',
    'half': 'tmp/partial_trend_exposure_20261016_v1/outcome.json',
    'premium': 'tmp/adaptive_daily_sell_premium_20261016_v1/outcome.json',
    'latch': 'tmp/monthly_latched_sma20_exit_20261016_v1/outcome.json',
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def compare_selection(window, selection):
    args = window['search_arguments']; day = window['decision_date']
    dates = window['training_dates']; scenarios = args['training_scenarios']
    require(dates == sorted(set(dates)) and dates[-1] <= day, 'NONCAUSAL_TRAINING_DATES')
    require(args['decision_date'] == selection['decision_date'] == day, 'DECISION_MISMATCH')
    require(args['scenario_dates'] == sorted(set(args['scenario_dates']))
            and args['scenario_dates'][-1] <= day, 'NONCAUSAL_SCENARIO_DATES')
    require(F(args['fee_bps']) == F(args['minimum_cash_buffer']) == 0, 'NONZERO_COST_OR_BUFFER_UNSUPPORTED')
    prices = {s:F(p) for s,p in args['prices'].items()}
    eligible = [c for c in window['candidates'] if c['security_id'] in prices]
    candidates = {c['security_id']:c for c in eligible}
    require(len(candidates) == len(eligible) and set(prices) == set(candidates), 'CANDIDATE_DOMAIN_MISMATCH')
    require(all(set(row) == set(prices) for row in scenarios), 'SCENARIO_DOMAIN_MISMATCH')
    products = {}
    for sid,candidate in candidates.items():
        closes = list(map(F,candidate['training_close']))
        require(len(closes) == len(dates) and all(p > 0 for p in closes), 'TRAINING_CLOSE_MISMATCH')
        ratios = [F(row[sid]) for row in scenarios]
        require(ratios == list(map(F,candidate['training_gross'])), 'SAVED_SCENARIO_MISMATCH')
        require(prod(ratios) == closes[-1]/closes[0], 'ENDPOINT_TELESCOPING_NOT_PROVEN')
        require(prices[sid] == F(candidate['decision_cost']) and prices[sid] > 0, 'PRICE_COORDINATE_MISMATCH')
        products[sid] = closes[-1]/closes[0]
    saved = selection['search_result']
    require(saved['decision_date'] == day and saved['scenario_dates'] == args['scenario_dates'], 'SAVED_SEARCH_WINDOW_MISMATCH')
    require(F(saved['fee_bps']) == F(saved['minimum_cash_buffer']) == 0, 'SAVED_SEARCH_COST_MISMATCH')
    require(saved['selected']['quantities'] == selection['target_quantities'], 'SAVED_SELECTED_TARGET_MISMATCH')
    cash = F(selection['investable_equity'])
    require(cash > 0 and F(selection['search_result']['entered_cash']) == cash, 'SELECTION_CAPITAL_MISMATCH')
    quantities = {s:q for s,q in selection['target_quantities'].items() if q}
    require(set(quantities) <= set(prices) and all(type(q)is int and q > 0 for q in quantities.values()), 'INVALID_TARGET')
    affordable = [s for s in prices if prices[s] <= cash]
    require(affordable, 'NO_AFFORDABLE_SINGLE_STOCK')
    best = max(products[s] for s in affordable)
    ties = sorted(s for s in affordable if products[s] == best)
    baseline = ties[0]  # Display tie only; report tie set, do not infer unique winner.
    baseline_q = int(cash//prices[baseline]); baseline_targets = {baseline:baseline_q}
    def score(target):
        residual = cash-sum((prices[s]*q for s,q in target.items()),F(0))
        require(residual >= 0,'NEGATIVE_TARGET_CASH')
        growth = [(residual+sum((prices[s]*q*F(row[s]) for s,q in target.items()),F(0)))/cash for row in scenarios]
        return residual,prod(growth)
    residual,selected_product = score(quantities)
    baseline_residual,baseline_product = score(baseline_targets)
    require(F(saved['selected']['residual_cash']) == residual and F(saved['selected']['fees']) == 0, 'SAVED_SELECTED_CASH_MISMATCH')
    if saved['selected'].get('training_gross_growth_product') is not None:
        require(F(saved['selected']['training_gross_growth_product']) == selected_product, 'SAVED_OBJECTIVE_MISMATCH')
    support_equal = len(quantities) == 1 and next(iter(quantities)) in ties
    exact_equal = support_equal and quantities == {next(iter(quantities)):int(cash//prices[next(iter(quantities))])}
    ticker = lambda s: args['metadata'][s]['ticker']
    return dict(decision_date=day,active_date=window['active_date'],year=window['active_date'][:4],
        training_first=dates[0],training_last=dates[-1],candidate_count=len(prices),
        affordable_candidates=len(affordable),scenario_count=len(scenarios),all_candidates_endpoint_identity=True,
        investable_equity=str(cash),selected_quantities=quantities,
        selected_tickers={ticker(s):q for s,q in quantities.items()},
        endpoint_top_ties=[dict(security_id=s,ticker=ticker(s),growth=str(products[s])) for s in ties],
        baseline_quantities=baseline_targets,baseline_ticker=ticker(baseline),
        selected_endpoint_ranks={s:1+sum(value > products[s] for value in products.values()) for s in quantities},
        same_single_stock_support=support_equal,same_full_cash_integer_target=exact_equal,
        selected_residual_cash=str(residual),baseline_residual_cash=str(baseline_residual),
        selected_scenario_wealth_product=str(selected_product),baseline_scenario_wealth_product=str(baseline_product),
        selected_training_objective_relation='EQUAL' if selected_product==baseline_product else 'GREATER' if selected_product>baseline_product else 'LESS',
        conclusion='SAME_INTEGER_TARGET_AT_SAVED_BRANCH_CAPITAL' if exact_equal else 'DIFFERENT_TARGET_NO_PERFORMANCE_CONCLUSION')


def build(root=ROOT):
    root=Path(root);pins={}
    def read(path,expected):
        raw=(root/path).read_bytes();require(sha256(raw).hexdigest()==expected,'SOURCE_DRIFT:'+path)
        pins[path]=expected;return json.loads(raw)
    prepared=read(PREPARED,PREPARED_SHA);comparison=read(COMPARISON,COMPARISON_SHA)
    closure={**prepared['source_hashes']}
    for path,h in comparison['source_hashes'].items():
        require(path not in closure or closure[path]==h,'SOURCE_PIN_CONFLICT');closure[path]=h
    for path,h in closure.items():
        require(sha256((root/path).read_bytes()).hexdigest()==h,'SOURCE_DRIFT:'+path);pins[path]=h
    windows={w['decision_date']:w for w in prepared['windows']}
    rows=[]
    for arm,path in ARMS.items():
        outcome=read(path,closure[path]);require(outcome['status']=='COMPLETE','INCOMPLETE_OUTCOME')
        selections=[a['selection'] for a in outcome['provider_audit'] if a.get('selection')]
        require(len(selections)==len(windows) and {s['decision_date'] for s in selections}==set(windows),'MISSING_OR_DUPLICATE_MONTH')
        for selection in selections:
            row=compare_selection(windows[selection['decision_date']],selection);row['arm']=arm;rows.append(row)
    grouped=defaultdict(list)
    for row in rows:grouped[(row['arm'],row['year'])].append(row)
    annual=[dict(arm=arm,year=year,months=len(group),same_support=sum(r['same_single_stock_support'] for r in group),
        same_integer_target=sum(r['same_full_cash_integer_target'] for r in group),
        different_target_months=[r['decision_date'] for r in group if not r['same_full_cash_integer_target']])
        for (arm,year),group in sorted(grouped.items())]
    script='scripts/audit_monthly_selection_endpoint.py';pins[script]=sha256((root/script).read_bytes()).hexdigest()
    return dict(status='PASS_READ_ONLY_SELECTION_COMPARISON',rows=rows,annual_summary=annual,source_hashes=pins,
        economic_runs=0,optimizer_calls=0,book_calls=0,independent_oos=False,point_in_time_certified=False,
        automatic_promotion=False,scope='98-stock TRI-excluded retrospective observed domain; each saved monthly eligible subset only',
        limitations=['Target equality is at each saved branch own capital, not a replay of standalone baseline wealth.',
            'Zero modeled commission and buffer; no fees, fills, slippage or future performance inferred.',
            'Endpoint identity applies to fully invested single stock training growth; integer residual and multi-stock objectives differ.',
            'Ranking is conditional on sealed training price and identity assumptions, not PIT universe certification.'])


def markdown(report):
    lines=['| 分支 | 年度 | 月度决策数 | 同单股 | 同整股数量 | 不同目标日期 |',
           '|---|---|---:|---:|---:|---|']
    for row in report['annual_summary']:
        lines.append('| {arm} | {year} | {months} | {same_support} | {same_integer_target} | {dates} |'.format(**row,dates=', '.join(row['different_target_months']) or '无'))
    lines += ['', '| 分支 | 决策日 | 当期可选数量 | 选择器目标 | 端点涨幅第一 | 同整股目标 |', '|---|---|---:|---|---|---|']
    for row in report['rows']:
        lines.append(f"| {row['arm']} | {row['decision_date']} | {row['candidate_count']} | {row['selected_tickers']} | {row['baseline_ticker']} | {'是' if row['same_full_cash_integer_target'] else '否'} |")
    lines += ['', '仅比较封存月度决策与同资金简单单股排名；不是基线独立收益回测，不证明策略优势。固定98股剔除TRI实验，非全历史点时资格、非样本外验证。']
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    report=build()
    if args.write:
        directory=ROOT/OUTPUT;directory.mkdir(exist_ok=False)
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (directory/'table.md').write_text(markdown(report),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],rows=len(report['rows']),annual_summary=report['annual_summary']),ensure_ascii=False))
