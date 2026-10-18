"""Independent raw-price and fixed-control ledger audit; imports no engine."""
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
SOURCE_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
REPORT = ROOT / 'data/cache/research/incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json'
REPORT_SHA = '53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'
OLD = ROOT / 'data/cache/research/dynamic_frozen_v2/strict_return_control_20260911.json'
OLD_SHA = '87b081061374a368c0c7d1b6a3d953ba964c3ac2e30d56f3a7173e21d1c3b58b'
BASIS = ROOT / 'data/cache/research/incumbent_price_source_probe_20260912_v1/incumbent_price_basis_review_20260912.json'
BASIS_SHA = '6565e1cc5233f148d683d134ca95a29886530f8ab25cf48e3c839aa21864293f'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, label):
    require(type(actual) in (int, float) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-8), label)


def read(path, digest):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'Source differs: ' + str(path))
    return json.loads(raw)


def audit(report, old, basis):
    execution = report['execution']
    fixed = report['original_fixed_schedule']
    calendar = fixed['calendar']
    require(len(calendar) == 295 and calendar == sorted(set(calendar)), '295 complete ordered sessions')
    require(calendar[0] == '2023-03-31' and calendar[-1] == '2024-06-03', 'Exact audit interval')
    require(len(execution['decisions']) == 15 and len(execution['executions']) == 15, '15 decision/fill outcomes')
    original_targets = old['execution']['decisions'][0]['targets']
    require(all(row['targets'] == original_targets for row in old['execution']['decisions']), 'Old target vector constant')
    require(all(row['targets'] == original_targets for row in execution['decisions']), 'New target vector unchanged')
    require(fixed['original_weights'] == old['original_weights'], 'Original weights differ')
    require([(r['decision_date'], r['execution_date']) for r in execution['decisions'][:14]] ==
            [(r['decision_date'], r['execution_date']) for r in old['execution']['decisions']], 'Original 14 clocks differ')
    require((execution['decisions'][-1]['decision_date'], execution['decisions'][-1]['execution_date']) ==
            ('2024-05-31', '2024-06-03'), '15th clock differs')
    require(execution['risk_is_order_gate'] is False and execution['original_target_weights_modified'] is False,
            'Control semantics differ')
    require(execution['corporate_actions'] == [] and execution['identity_events'] == [], 'Unexpected action path')
    prices = {}
    for item in basis['rows']:
        ticker = item['ticker']
        data = read(item['price_response_path'], item['price_response_sha256'])['chart']['result'][0]
        require(data['meta']['symbol'] == ticker and data['meta']['currency'] == 'USD', 'Raw quote coordinate')
        quotes = data['indicators']['quote'][0]
        raw_daily = {}
        for position, timestamp in enumerate(data['timestamp']):
            date = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            require(date not in raw_daily, 'Duplicate raw session')
            raw_daily[date] = (quotes['open'][position], quotes['close'][position])
        splits = []
        for event in data.get('events', {}).get('splits', {}).values():
            date = datetime.fromtimestamp(event['date'], timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            splits.append((date, Fraction(str(event['numerator'])) / Fraction(str(event['denominator']))))
        prices[ticker] = {}
        actual = {r['session']: r for r in report['nominal_quotes']['by_ticker'][ticker]['rows']}
        require(set(actual) == set(calendar), 'Normalized quote denominator')
        for date in calendar:
            factor = math.prod(ratio for effective, ratio in splits if effective > date)
            pair = tuple(float(value) * float(factor) for value in raw_daily[date])
            require(actual[date]['nominal_open'] == pair[0] and actual[date]['nominal_close'] == pair[1], 'Raw nominal arithmetic')
            require(actual[date]['split_factor'] == float(factor), 'Factor differs')
            prices[ticker][date] = pair
    require(set(prices) == set(old['original_weights']), 'Eight raw ticker denominator')
    ids = sorted(original_targets)
    targets = {sid: original_targets[sid]['target_weight'] for sid in ids}
    marks = lambda date, channel: {sid: prices[original_targets[sid]['ticker']][date][channel] for sid in ids}
    cash, buffer, rate = 25000., 100., .001
    close(fixed['initial_cash_usd'], cash, 'Capital')
    close(fixed['minimum_cash_buffer_usd'], buffer, 'Buffer')
    close(fixed['transaction_cost_bps'], rate*10000, 'Costs')
    shares, pending, expected_trades, values = {}, None, {}, []
    by_decision = {r['decision_date']: r for r in execution['decisions']}
    by_fill = {r['session']: r for r in execution['executions']}
    require(len(by_decision) == len(by_fill) == 15, 'Unique order clock')
    require([r['session'] for r in execution['daily']] == calendar, 'Daily denominator')
    filled = rejected = 0

    def cash_projection(wanted, price):
        delta = {sid: wanted.get(sid, 0) - shares.get(sid, 0) for sid in sorted(set(wanted) | set(shares))}
        fees = sum(abs(quantity)*price[sid]*rate for sid, quantity in delta.items())
        after = cash - sum(quantity*price[sid] for sid, quantity in delta.items()) - fees
        return after, fees, delta

    for date, daily in zip(calendar, execution['daily']):
        if date in by_fill:
            record = by_fill[date]
            require(pending is not None and pending['execution_date'] == date, 'Missing frozen plan')
            wanted = pending['desired_shares']
            price = marks(date, 0)
            after, fees, delta = cash_projection(wanted, price)
            require(record['shares_before'] == shares and record['desired_shares'] == wanted, 'Fill holdings/target changed')
            require(record['frozen_delta'] == delta == pending['delta'], 'Frozen delta changed')
            close(record['cash_before_usd'], cash, 'Fill cash before')
            close(record['projected_cash_usd'], after, 'Fill projected cash')
            close(record['projected_fees_usd'], fees, 'Fill projected fees')
            for sid, value in record['prices'].items(): close(value, price[sid], 'Fill Open')
            status = 'FILLED' if after >= buffer-1e-8 else 'REJECTED'
            require(record['status'] == status, 'Atomic cash-only control gate differs')
            require(record['failure_reasons'] == ([] if status == 'FILLED' else ['CASH_BUFFER']), 'Control rejection reason')
            if status == 'FILLED':
                before_equity = cash + sum(shares.get(sid, 0)*price[sid] for sid in ids)
                for sid, quantity in delta.items():
                    if quantity:
                        expected_trades[(date, sid)] = (quantity, price[sid], abs(quantity)*price[sid]*rate)
                cash, shares = after, dict(wanted)
                close(cash + sum(shares.get(sid, 0)*price[sid] for sid in ids) + fees, before_equity, 'Self financing')
                filled += 1
            else:
                rejected += 1
            close(record['cash_after_usd'], cash, 'Fill actual cash')
            require(record['shares_after'] == shares, 'Fill actual shares')
            pending = None
        if date in by_decision:
            record = by_decision[date]
            price = marks(date, 1)
            require(record['shares_before'] == shares, 'Decision before holdings')
            close(record['cash_before_usd'], cash, 'Decision before cash')
            for sid, value in record['prices'].items(): close(value, price[sid], 'Decision Close')
            investable = cash + sum(shares.get(sid, 0)*price[sid] for sid in ids) - buffer
            floor = {sid: math.floor(investable*targets[sid]/price[sid]) for sid in ids}
            wanted = dict(floor)
            while all(value >= 1 for value in wanted.values()) and cash_projection(wanted, price)[0] < buffer-1e-8:
                eligible = [sid for sid in ids if wanted[sid] > 1]
                if not eligible: break
                wanted[max(eligible, key=lambda sid: (price[sid], sid))] -= 1
            if cash_projection(wanted, price)[0] < buffer-1e-8:
                wanted = dict(floor)
                while cash_projection(wanted, price)[0] < buffer-1e-8:
                    eligible = [sid for sid in ids if wanted[sid] > 0]
                    require(bool(eligible), 'No financial floor solution')
                    wanted[max(eligible, key=lambda sid: (price[sid], sid))] -= 1
            after, fees, delta = cash_projection(wanted, price)
            require(record['status'] == 'FROZEN' and record['desired_shares'] == wanted, 'Independent Close floor differs')
            require(record['delta'] == delta, 'Decision frozen delta')
            close(record['projected_cash_usd'], after, 'Decision projected cash')
            close(record['projected_fees_usd'], fees, 'Decision projected fees')
            require(calendar.index(record['execution_date']) == calendar.index(date)+1, 'Next-session order')
            pending = record
        price = marks(date, 1)
        total = cash + sum(shares.get(sid, 0)*price[sid] for sid in ids)
        require(daily['shares'] == shares, 'Daily holdings')
        close(daily['cash_usd'], cash, 'Daily cash')
        close(daily['total_value_usd'], total, 'Daily equity')
        require(set(daily['prices']) == set(shares), 'Daily price SID denominator')
        for sid in shares: close(daily['prices'][sid], price[sid], 'Daily Close')
        values.append(total)
    require(pending is None, 'Unexecuted final pending order')
    require(len(execution['trades']) == len(expected_trades), 'Trade denominator')
    observed = set()
    for trade in execution['trades']:
        key = (trade['session'], trade['security_id'])
        require(key not in observed and key in expected_trades, 'Unexpected/duplicate trade')
        observed.add(key)
        quantity, price, fee = expected_trades[key]
        require(trade['share_delta'] == quantity, 'Trade shares')
        close(trade['price_usd'], price, 'Trade price')
        close(trade['transaction_cost_usd'], fee, 'Trade fee')
    peak, maximum_drawdown = values[0], 0.
    for value in values:
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, 1-value/peak)
    summary = execution['summary']
    close(summary['terminal_value_usd'], values[-1], 'Terminal equity')
    close(summary['path_return_net'], values[-1]/25000-1, 'Net path return')
    close(summary['path_max_drawdown'], maximum_drawdown, 'Path drawdown')
    return dict(raw_quote_rows_verified=2360, daily_cash_shares_equity_rows_verified=295,
        frozen_decisions_verified=15, atomic_execution_outcomes_verified=15,
        filled=filled, rejected=rejected, trade_rows_verified=len(expected_trades),
        total_fees_usd=sum(row[2] for row in expected_trades.values()), terminal_value_usd=values[-1],
        path_return_net=values[-1]/25000-1, annualized_return_252_session=(values[-1]/25000)**(252/294)-1,
        path_max_drawdown=maximum_drawdown)


def run():
    report, old, basis = read(REPORT, REPORT_SHA), read(OLD, OLD_SHA), read(BASIS, BASIS_SHA)
    sources = dict(report['source_hashes']) | {str(REPORT): REPORT_SHA, str(OLD): OLD_SHA,
        str(BASIS): BASIS_SHA, str(SOURCE): SOURCE_SHA}
    for path, digest in sources.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, 'Bound source differs')
    result = audit(report, old, basis)
    for path, digest in sources.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, 'Source changed during independent audit')
    return dict(schema='ndx_incumbent_accounting_independent_oracle_v1', **result,
        source_hashes=sources, engine_imported=False, engine_reexecuted=False,
        oracle_uses_raw_quotes=True, risk_metrics_independently_recomputed=False,
        price_identity_authenticity_verified=False, point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    result = run()
    output = REPORT.with_name('nominal_control_accounting_oracle_20260912.json')
    raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    with output.open('xb') as handle: handle.write(raw)
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(raw).hexdigest(),
                         summary={k:v for k,v in result.items() if k != 'source_hashes'})))
