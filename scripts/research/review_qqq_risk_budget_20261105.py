"""Independent saved-book finance, original monthly exits and risk-budget arithmetic.

Never imports or calls the candidate sizing function or account runner.
"""
import argparse
import json
import sys
import inspect
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backtest import historical_dividend_identity_independent_review_v1 as finance


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def variance(values):
    n = len(values)
    require(n == 63, 'INDEPENDENT_63_OBSERVATIONS_REQUIRED')
    # Different form from candidate: n*sum(x²)-sum(x)².
    return (n * sum((x*x for x in values), F(0)) - sum(values, F(0))**2) / (n*(n-1))


def exact_floor_quantity(quantity, numerator_variance, denominator_variance):
    if denominator_variance == 0 or numerator_variance >= denominator_variance:
        return quantity
    lower, upper = 0, quantity + 1
    while upper - lower > 1:
        middle = (lower + upper) // 2
        if middle * middle * denominator_variance <= quantity * quantity * numerator_variance:
            lower = middle
        else:
            upper = middle
    require(lower**2 * denominator_variance <= quantity**2 * numerator_variance,
            'INTEGER_LOWER_BOUND')
    require((lower+1)**2 * denominator_variance > quantity**2 * numerator_variance,
            'INTEGER_UPPER_BOUND')
    return lower


def audit_zero_identity_events(book, assembled):
    """Prove zero exposure before adapting the liquidation-only checker copy.

    Saved execution inputs and book are never changed. The audit-only checker
    extension retains the action and reconstructs its successor zero key.
    """
    adapted = book
    inputs = assembled
    proofs = []
    for event in assembled.get('actions', []):
        if event['type'] != 'split_identity':
            continue
        old, new = event['security_id'], event['new_security_id']
        index = next(i for i, row in enumerate(book['daily_ledger']) if row['date'] == event['date'])
        require(index > 0, 'ZERO_IDENTITY_NEEDS_PRIOR_ROW')
        prior = book['daily_ledger'][index-1]
        if prior['shares'].get(old, 0) or prior['shares'].get(new, 0):
            continue  # Positive exposure must pass the unchanged original checker.
        audit = book['provider_audit'][index]
        for row in book['daily_ledger'][index-1:]:
            require(not row['shares'].get(old, 0) and not row['shares'].get(new, 0), 'ZERO_IDENTITY_LATER_EXPOSURE')
            require(not row.get('distribution_rights') and not row.get('merger_entitlements')
                    and F(row.get('receivable', '0')) == 0, 'ZERO_IDENTITY_RIGHTS')
        for item in book['provider_audit'][index-1:]:
            require(not any(o['security_id'] in (old, new) for o in item['orders']), 'ZERO_IDENTITY_PENDING_OR_LATER_ORDER')
            for key in ('monthly_ceiling', 'target_shares'):
                require(not any(item[key].get(s, 0) for s in (old, new)), 'ZERO_IDENTITY_TARGET')
        for order in book['order_log']:
            # Provider orders above are checked independently of actual fills.
            if order.get('security_id') in (old, new):
                if order.get('event') == 'CORPORATE_ACTION':
                    require(order.get('action_details') == event, 'ZERO_IDENTITY_ACTION_LOG')
                    continue
                require(order.get('date', order.get('active_date', order.get('session_date', '9999'))) < event['date'],
                        'ZERO_IDENTITY_EXECUTED_ORDER')
        source_hashes = {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in event['source_references']}
        proofs.append(dict(event=event, source_hashes=source_hashes, prior_date=prior['date'],
                           prior_shares={s: prior['shares'].get(s, 0) for s in (old, new)},
                           event_orders=audit['orders'], monthly_ceiling=audit['monthly_ceiling'],
                           later_sessions_checked=len(book['daily_ledger'])-index,
                           equity_effect='0', proof='Zero holdings, target, pending/executed orders and rights; no later old/new exposure.'))
    return adapted, inputs, proofs


def run(window, output):
    # User-approved bounded offline setting, not production or imported global policy.
    sys.set_int_max_str_digits(100000)
    directory = ROOT / output
    contract = read(directory / 'contract.json')
    require(contract['window'] == window, 'CONTRACT_WINDOW')
    for name, expected in contract['source_hashes'].items():
        require(sha256((ROOT/name).read_bytes()).hexdigest() == expected, 'SOURCE_CHANGED:' + name)
    book = read(directory / 'book.json')
    require(book['status'] == 'COMPLETE', 'COMPLETE_BOOK_REQUIRED_NO_PREFIX_PASS')
    artifact = contract.get('risk_input_artifact')
    if artifact is None:
        # The original pre-extension run has one explicitly pinned input path.
        original_path = 'tmp/risk_budget_64d_inventory_20261105/risk_inputs.json'
        require(original_path in contract['source_hashes'], 'EXPLICIT_RISK_ARTIFACT_REQUIRED')
        artifact = dict(path=original_path, sha256=contract['source_hashes'][original_path])
    require(contract['source_hashes'].get(artifact['path']) == artifact['sha256'], 'CONTRACT_ARTIFACT_PIN')
    risk_path = ROOT / artifact['path']
    require(sha256(risk_path.read_bytes()).hexdigest() == artifact['sha256'], 'RISK_ARTIFACT_CHANGED')
    risk_document = read(risk_path)
    if artifact.get('parent_path'):
        require(risk_document.get('parent_artifact') == dict(path=artifact['parent_path'], sha256=artifact['parent_sha256']), 'EXTENSION_PARENT_LINEAGE')
        require(risk_document['source_hashes'].get(artifact['parent_path']) == artifact['parent_sha256'], 'EXTENSION_PARENT_PIN')
        require(sha256((ROOT/artifact['parent_path']).read_bytes()).hexdigest() == artifact['parent_sha256'], 'EXTENSION_PARENT_CHANGED')
    label = 'early' if window == '2021_2023' else 'later'
    inputs = {r['decision_date']: r for r in risk_document['windows'] if r['window'] == label}
    original_checker = finance.review_selection
    checked = {}

    def review_scaled_selection(selected, rerank_enabled):
        original = selected['risk_budget_original_selection']
        proof = original_checker(original, rerank_enabled=rerank_enabled)
        require(selected['raw_selection'] == original['raw_selection'], 'ORIGINAL_SELECTION_PRESERVED')
        require(selected['investable_equity'] == original['investable_equity'], 'CAPITAL_UNCHANGED')
        raw = original['raw_selection']
        day = raw['decision_date']
        source = inputs[day]
        require(source['status'] == 'CONDITIONAL_INPUT_READY', 'RISK_INPUT_NOT_ADMITTED')
        require(selected['risk_budget_source_binding'] == source['source_binding'], 'RISK_INPUT_BINDING')
        targets = proof['target_quantities']
        require(targets == original['target_quantities'], 'ORIGINAL_TARGET_PROOF')
        positive = {s: q for s, q in targets.items() if q > 0}
        saved = source['arguments']
        dates = sorted(saved['qqq_gross_returns'])
        require(len(dates) == 63 and dates[-1] == day, 'CURRENT_63_SESSION_END')
        require(set(positive) <= set(saved['stock_gross_returns']), 'UNREVIEWED_DYNAMIC_SECURITY')
        binding = raw['binding']
        quotes = {s: F(q['price']) for s, q in binding['valuation_quotes'].items()}
        equity = F(binding['available_cash']) + sum((q * quotes[s] for s, q in binding['shares'].items() if q), F(0))
        require(equity == F(original['investable_equity']) > 0, 'TRADEABLE_EQUITY_EXCLUDES_RIGHTS')
        weights = {s: q * quotes[s] / equity for s, q in positive.items()}
        require(sum(weights.values(), F(0)) <= 1, 'UNLEVERED_ORIGINAL_WEIGHT')
        for s in positive:
            require(set(saved['stock_gross_returns'][s]) == set(dates), 'STOCK_DATE_DOMAIN')
        benchmark = [F(saved['qqq_gross_returns'][d])-1 for d in dates]
        portfolio = [sum((weights[s]*(F(saved['stock_gross_returns'][s][d])-1) for s in positive), F(0)) for d in dates]
        pv, qv = variance(portfolio), variance(benchmark)
        expected = {s: exact_floor_quantity(q, qv, pv) if q else 0 for s, q in targets.items()}
        budget = selected['risk_budget']
        require(budget['decision_date'] == day and budget['dates'] == dates and budget['observations'] == 63,
                'BUDGET_DATES_AND_COUNT')
        require(selected['target_quantities'] == expected == budget['target_quantities'], 'SCALED_INTEGER_TARGET')
        require(budget['original_target_quantities'] == targets, 'PRE_SCALE_DOMAIN')
        require(budget['zero_target_securities_excluded_from_covariance'] == sorted(set(targets)-set(positive)), 'ZERO_TARGET_PROJECTION')
        require(F(budget['portfolio_variance']) == pv and F(budget['qqq_variance']) == qv, 'INDEPENDENT_VARIANCES')
        ratio = min(F(1), qv/pv) if pv else F(1)
        require(F(budget['scale_squared_exact']) == ratio, 'VARIANCE_RATIO')
        require({s: F(v) for s, v in budget['original_weights'].items()} == weights, 'INDEPENDENT_WEIGHTS')
        require(F(budget['original_cash_weight']) == 1-sum(weights.values(), F(0)), 'CASH_WEIGHT')
        notional = sum((q*quotes[s] for s, q in expected.items()), F(0))
        require(F(budget['target_value_after']) == notional and F(budget['cash_after_at_decision_prices']) == equity-notional,
                'SIZING_NOTIONAL_CASH')
        checked[day] = dict(original=targets, scaled=expected, tradeable_equity=str(equity),
                            portfolio_variance=str(pv), qqq_variance=str(qv), scale_squared=str(ratio))
        result = deepcopy(proof)
        result['target_quantities'] = expected
        return result

    name = 'recent_continuous_baseline_20261026_v7' if window == '2021_2023' else 'old_continuous_baseline_20261026_v9'
    document = read(ROOT / 'tmp' / name / 'execution_inputs.json')
    supplement = read(ROOT / 'tmp/equal_four_20261105/source_review/admitted_supplement.json')
    document['dividend_events'].extend(supplement['dividend_events'][window])
    review_book, review_assembled, zero_identity_proofs = audit_zero_identity_events(book, document['assembled'])
    reviewer = finance.review
    if zero_identity_proofs:
        # Audit-only extension: preserve every byte of book/binding and the
        # action, but replace the positive-position-only branch for proved zeros.
        # This also reconstructs the successor zero dictionary key exactly.
        source = inspect.getsource(finance.review)
        old_branch = "            if successor != sid:\n                require(successor not in terminated"
        new_branch = "            if successor != sid and (day, sid) not in proved_zero_identities:\n                require(successor not in terminated"
        old_transform = "            if shares.get(sid, 0) or any(o['security_id'] == sid for o in orders):"
        new_transform = "            if shares.get(sid, 0) or any(o['security_id'] == sid for o in orders) or (day, sid) in proved_zero_identities:"
        require(source.count(old_branch) == 1 and source.count(old_transform) == 1, 'AUDIT_EXTENSION_ANCHORS')
        source = source.replace(old_branch, new_branch).replace(old_transform, new_transform)
        namespace = dict(finance.__dict__)
        namespace.update(review_selection=review_scaled_selection,
                         proved_zero_identities={(p['event']['date'], p['event']['security_id']) for p in zero_identity_proofs})
        exec(compile(source, '<independent-zero-exposure-identity-review>', 'exec'), namespace)
        reviewer = namespace['review']
    try:
        finance.review_selection = review_scaled_selection
        result = reviewer(review_book, review_assembled, document['ohlc'], initial_cash='20000',
                                dividend_events=document['dividend_events'], verify_selections=True,
                                verify_risk_provider=True, expected_fee_bps='0', expected_slippage_bps='5')
    finally:
        finance.review_selection = original_checker
    if zero_identity_proofs:
        result['integer_identity_liquidations_checked'] -= len(zero_identity_proofs)
        result['zero_exposure_identity_events_checked'] = len(zero_identity_proofs)
        result['identity_scope'] = 'ORIGINAL_POSITIVE_FULL_LIQUIDATION_PLUS_INDEPENDENT_ZERO_EXPOSURE_PROOF'
    report = dict(status='INDEPENDENT_RISK_BUDGET_FINANCE_MONTHLY_EXIT_PASS', finance=result,
                  zero_exposure_identity_alternative_proofs=zero_identity_proofs,
                  selection_risk_checks=checked, candidate_scale_function_called=False, economic_replays=0,
                  limits='Conditional supplied data and original finance checker corporate-action scope; no future-profit or PIT/OOS guarantee.',
                  source_hashes={str(p.relative_to(ROOT)).replace('\\','/'): sha256(p.read_bytes()).hexdigest()
                                 for p in [directory/'book.json', directory/'contract.json', risk_path, Path(__file__), Path(finance.__file__)]})
    (directory / 'independent_review.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(status=report['status'], checked_months=len(checked), finance=result)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', choices=['2021_2023','2024_2026'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.window, args.output)
