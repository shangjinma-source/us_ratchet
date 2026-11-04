"""Independent EMA market gate, original monthly exits and saved account audit.

Never runs the strategy or imports the candidate adapter/signal generator.
"""
import argparse
import gzip
import inspect
import json
import sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backtest import historical_dividend_identity_independent_review_v1 as finance
from scripts.research.review_qqq_risk_budget_20261105 import audit_zero_identity_events


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def verify_pins(pins):
    for name, expected in pins.items():
        require(sha256((ROOT/name).read_bytes()).hexdigest() == expected, 'SOURCE_CHANGED:' + name)


def independent_signals(artifact):
    verify_pins(artifact['source_hashes'])
    panels = []
    all_dates = set()
    for name in artifact['source_hashes']:
        raw = (ROOT/name).read_bytes()
        source = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw, parse_float=str)['chart']['result'][0]
        require(source['meta']['symbol'] == 'QQQ' and not source.get('events', {}).get('splits'), 'QQQ_UNIT')
        quote = source['indicators']['quote'][0]
        panel = {}
        for i, timestamp in enumerate(source['timestamp']):
            day = datetime.fromtimestamp(timestamp, ZoneInfo('America/New_York')).date().isoformat()
            all_dates.add(day)
            if quote['open'][i] is not None and quote['close'][i] is not None:
                panel[day] = tuple(Decimal(str(quote[key][i])) for key in ('open', 'close'))
        panels.append(panel)
    require(len(panels) == 2, 'TWO_FROZEN_QQQ_SOURCES')
    require(all(panels[0][d] == panels[1][d] for d in set(panels[0]) & set(panels[1])), 'QQQ_OVERLAP')
    panel = dict(panels[0], **panels[1])
    days = sorted(panel)
    require(set(days) == all_dates, 'MISSING_QQQ_OPEN_CLOSE')
    month_ends = {}
    for day in days:
        month_ends[day[:7]] = day
    del month_ends[days[-1][:7]]
    require(sorted(month_ends.values()) == artifact['month_ends'], 'FULL_CALENDAR_MONTH_ENDS')
    require(days[0] == '2020-01-02' and days[252] == '2020-12-31', 'FROZEN_SEED_DOMAIN')
    signals = {}
    with localcontext() as context:
        context.prec = 80
        value = sum(panel[d][1] for d in days[:20]) / 20
        for i, day in enumerate(days[20:], 20):
            close = panel[day][1]
            value += (close-value)*Decimal(2)/21
            if i >= 252:
                signals[day] = dict(close=str(close), ema=str(value), on=close > value)
    require(signals == artifact['signals'], 'INDEPENDENT_EMA_RECONSTRUCTION')
    return signals, set(month_ends.values()), days


def run(output):
    sys.set_int_max_str_digits(100000)
    directory = ROOT/output
    contract = read(directory/'contract.json')
    verify_pins(contract['source_hashes'])
    require(contract['candidate'] == 'QQQ_EMA20_MARKET_GATE', 'CANDIDATE_CONTRACT')
    require(contract['mode'] in ('daily', 'monthly_reentry'), 'MODE')
    require((contract['initial_cash'], contract['fee_bps'], contract['slippage_bps']) == ('20000', '0', '5'), 'COST_CONTRACT')
    freeze_path = ROOT/'research_contracts/ema20_20261105/freeze.json'
    require(freeze_path.relative_to(ROOT).as_posix() in contract['source_hashes'], 'FREEZE_PIN_REQUIRED')
    freeze = read(freeze_path)
    verify_pins(freeze['source_hashes'])
    require(freeze['signal_artifact'] in contract['source_hashes'], 'SIGNAL_PIN_REQUIRED')
    signals, month_ends, full_days = independent_signals(read(ROOT/freeze['signal_artifact']))
    book = read(directory/'book.json')
    require(book['status'] == 'COMPLETE', 'COMPLETE_BOOK_REQUIRED')
    late = contract['window'] == '2024_2026'
    base = ROOT/'tmp'/('old_continuous_baseline_20261026_v9' if late else 'recent_continuous_baseline_20261026_v7')
    document = read(base/'execution_inputs.json')
    supplement = read(ROOT/'tmp/equal_four_20261105/source_review/admitted_supplement.json')
    document['dividend_events'].extend(supplement['dividend_events'][contract['window']])
    assembled = document['assembled']
    days = assembled['session_dates']
    require(days == [d for d in full_days if days[0] <= d <= days[-1]], 'COMPLETE_EXECUTION_CALENDAR')
    require((contract['start'], contract['end']) == (days[0], days[-1]), 'WINDOW')
    require(len(days)-1 == (646 if late else 753), 'FULL_WINDOW_COUNT')
    checked = []
    market_on = None

    def layered_risk(audit, decision, active, shares, prices, splits, selected_targets, state):
        nonlocal market_on
        require(full_days[full_days.index(active)-1] == decision, 'NEXT_REAL_OPEN')
        # Independently reconstruct the original layer before any market gate.
        original = deepcopy(state)
        if selected_targets is not None:
            original.update(baseline=dict(selected_targets), peaks={}, exited=set(), month=decision)
        else:
            require(original['baseline'] is not None, 'INITIAL_SELECTION')
            for event in splits:
                sid = event['security_id']
                if event['date'] == decision and sid in original['baseline']:
                    ratio = F(event['new_shares'])/F(event['old_shares'])
                    quantity = original['baseline'][sid]*ratio
                    require(quantity.denominator == 1, 'INTEGER_SPLIT_TARGET')
                    original['baseline'][sid] = int(quantity)
                    if sid in original['peaks']:
                        original['peaks'][sid] /= ratio
        for sid in original['baseline']:
            close = F(prices[sid][decision])
            original['peaks'][sid] = max(original['peaks'].get(sid, close), close)
            if close*5 <= original['peaks'][sid]*4:
                original['exited'].add(sid)
        effective = {sid: 0 if sid in original['exited'] else q for sid, q in original['baseline'].items()}

        def orders(target):
            result = []
            for sid in sorted(set(shares) | set(target)):
                delta = target.get(sid, 0)-shares.get(sid, 0)
                if delta:
                    result.append(dict(security_id=sid, side='BUY' if delta > 0 else 'SELL', quantity=abs(delta),
                                       decision_date=decision, active_date=active, decision_mark=str(F(prices[sid][decision]))))
            return result

        shadow = deepcopy(audit)
        shadow['target_shares'] = effective
        shadow['orders'] = orders(effective)  # Proof-only orders, never executed.
        shadow['risk_overlay'].pop('market_gate', None)
        finance._review_risk_orders(shadow, decision, active, shares, prices, splits, selected_targets, state)
        require(original == state, 'ORIGINAL_RISK_STATE_RECONSTRUCTION')
        signal = signals[decision]
        if contract['mode'] == 'daily' or market_on is None:
            market_on = signal['on']
        elif not signal['on']:
            market_on = False
        elif decision in month_ends:
            market_on = True
        target = effective if market_on else dict.fromkeys(effective, 0)
        gate = dict(signal_date=decision, mode=contract['mode'], market_on=market_on,
                    qqq_above_ema20=signal['on'], monthly_ceiling=original['baseline'],
                    original_exit_effective=effective, effective=target)
        require(audit['risk_overlay']['market_gate'] == gate, 'INDEPENDENT_MARKET_GATE')
        require(audit['target_shares'] == target, 'GATED_TARGET')
        actual = [{k: (str(F(o[k])) if k == 'decision_mark' else o[k]) for k in ('security_id', 'side', 'quantity', 'decision_date', 'active_date', 'decision_mark')} for o in audit['orders']]
        require(sorted(actual, key=lambda o: o['security_id']) == orders(target), 'ACTUAL_GATED_ORDER')
        checked.append(gate)

    _, _, zero_proofs = audit_zero_identity_events(book, assembled)
    namespace = dict(finance.__dict__)
    namespace['_review_risk_orders'] = layered_risk
    source = inspect.getsource(finance.review)
    if zero_proofs:
        old = "            if successor != sid:\n                require(successor not in terminated"
        new = "            if successor != sid and (day, sid) not in proved_zero_identities:\n                require(successor not in terminated"
        old_transform = "            if shares.get(sid, 0) or any(o['security_id'] == sid for o in orders):"
        require(source.count(old) == 1 and source.count(old_transform) == 1, 'ZERO_IDENTITY_ANCHORS')
        source = source.replace(old, new).replace(old_transform, old_transform[:-1] + ' or (day, sid) in proved_zero_identities:')
        namespace['proved_zero_identities'] = {(p['event']['date'], p['event']['security_id']) for p in zero_proofs}
    exec(compile(source, '<independent-ema20-layered-finance>', 'exec'), namespace)
    result = namespace['review'](book, assembled, document['ohlc'], initial_cash='20000',
        dividend_events=document['dividend_events'], verify_selections=True, verify_risk_provider=True,
        expected_fee_bps='0', expected_slippage_bps='5')
    require(read(directory/'market_audit.json') == checked, 'FULL_MARKET_AUDIT')
    result['integer_identity_liquidations_checked'] -= len(zero_proofs)
    result['zero_exposure_identity_events_checked'] = len(zero_proofs)
    result['identity_scope'] = 'ORIGINAL_POSITIVE_FULL_LIQUIDATION_PLUS_INDEPENDENT_ZERO_EXPOSURE_PROOF'
    paths = [Path(__file__), Path(finance.__file__), ROOT/'scripts/research/review_qqq_risk_budget_20261105.py', directory/'book.json', directory/'contract.json', directory/'market_audit.json']
    report = dict(status='INDEPENDENT_EMA20_ORIGINAL_EXIT_FINANCE_PASS', finance=result,
        mode=contract['mode'], sessions_checked=len(checked), market_checks=checked,
        zero_exposure_identity_alternative_proofs=zero_proofs, candidate_adapter_called=False, economic_replays=0,
        limits='Conditional supplied data; not proof of profitability, full PIT or out-of-sample validity.',
        source_hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths})
    (directory/'independent_review.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('market_checks', 'source_hashes', 'zero_exposure_identity_alternative_proofs')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    run(parser.parse_args().output)
