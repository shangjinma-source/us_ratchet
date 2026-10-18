"""Independent arithmetic replay of saved records; never imports the executor."""
import gzip
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'data/cache/research/dynamic_frozen_v2/preference_retrospective_accounting_20260912.json'
SHA = '3b0fd632ba5c53839b90199d7edf74dafdc73bdc9b3369d09bef24fdae177e59'
SCHEDULE = ROOT / 'data/cache/research/dynamic_frozen_v2/preference_refit_schedule_20260912.json'
SCHEDULE_SHA = '4325a37801e915179bd0c428b132be56d5c2e6273524c6e2ad1101741587b559'


def close(actual, expected):
    if not math.isfinite(float(actual)) or abs(actual - expected) > 1e-7:
        raise ValueError(f'Accounting mismatch: {actual} versus {expected}')


def main():
    assert hashlib.sha256(REPORT.read_bytes()).hexdigest() == SHA
    assert hashlib.sha256(SCHEDULE.read_bytes()).hexdigest() == SCHEDULE_SHA
    report = json.loads(REPORT.read_bytes())
    built = json.loads(SCHEDULE.read_bytes())['schedule_result']
    sources = dict(report['source_hashes'])
    sources.update({str(REPORT): SHA, str(SCHEDULE): SCHEDULE_SHA,
                    str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    def verify():
        for path, digest in sources.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
    verify()
    calendar = built['calendar']
    targets = built['schedule'][0]['targets']
    symbols = {sid: row['ticker'] for sid, row in targets.items()}
    prices = {}
    # Independent raw decoding/date mapping and future split reversal.
    for sid, ticker in symbols.items():
        path = ROOT / ('data/cache/research/preference_price_action_supplement_20260912_v1/yahoo_' + ticker.lower() + '_through_received_daily_events.response.bin')
        raw = path.read_bytes()
        assert sources[str(path)] == hashlib.sha256(raw).hexdigest()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        data = json.loads(raw)['chart']['result'][0]
        assert data['meta']['symbol'] == ticker and data['meta']['currency'] == 'USD'
        def session(stamp):
            return datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat()
        events = [(session(e['date']), e['numerator'] / e['denominator'])
                  for e in data.get('events', {}).get('splits', {}).values()]
        assert not any(calendar[0] <= day <= calendar[-1] for day, _ in events)
        quotes = data['indicators']['quote'][0]
        daily = {}
        for i, stamp in enumerate(data['timestamp']):
            day = session(stamp)
            assert day not in daily
            factor = math.prod(ratio for split_day, ratio in events if split_day > day)
            daily[day] = (quotes['open'][i] * factor, quotes['close'][i] * factor)
        prices[sid] = {day: daily[day] for day in calendar}
    e = report['execution']
    decisions = {row['decision_date']: row for row in e['decisions']}
    executions = {row['session']: row for row in e['executions']}
    assert len(decisions) == len(executions) == 15
    assert [row['session'] for row in e['daily']] == calendar
    assert not e['corporate_actions'] and not e['dividend_modelled']
    for submitted in built['schedule']:
        d = decisions[submitted['decision_date']]
        assert d['targets'] == submitted['targets']
        assert d['execution_date'] == submitted['execution_date']
        assert calendar[calendar.index(d['decision_date']) + 1] == d['execution_date']
    shares, cash, fees, peak, drawdown = {}, 25000.0, 0.0, 25000.0, 0.0
    expected_trades, daily_values = [], []
    rejected = 0
    for row in e['daily']:
        day = row['session']
        if day in executions:
            execution = executions[day]
            d = decisions[execution['decision_date']]
            assert execution['shares_before'] == shares == d['shares_before']
            close(execution['cash_before_usd'], cash)
            assert execution['frozen_delta'] == d['delta']
            assert execution['desired_shares'] == d['desired_shares']
            delta = {sid: d['desired_shares'].get(sid, 0) - shares.get(sid, 0) for sid in d['delta']}
            assert delta == d['delta']
            for sid in delta:
                assert type(delta[sid]) is int
                close(execution['prices'][sid], prices[sid][day][0])
            cost = sum(abs(q) * prices[sid][day][0] * .001 for sid, q in delta.items())
            projected = cash - sum(q * prices[sid][day][0] for sid, q in delta.items()) - cost
            close(execution['projected_fees_usd'], cost)
            close(execution['projected_cash_usd'], projected)
            if execution['status'] == 'FILLED':
                assert projected >= 100 - 1e-9 and not execution['failure_reasons']
                cash = projected
                fees += cost
                shares = {sid: shares.get(sid, 0) + q for sid, q in delta.items() if shares.get(sid, 0) + q}
                for sid, q in delta.items():
                    if q:
                        expected_trades.append({'session': day, 'security_id': sid, 'ticker': symbols[sid],
                            'share_delta': q, 'price_usd': prices[sid][day][0],
                            'transaction_cost_usd': abs(q) * prices[sid][day][0] * .001})
            else:
                rejected += 1
            assert shares == execution['shares_after']
            close(execution['cash_after_usd'], cash)
        assert row['shares'] == shares
        close(row['cash_usd'], cash)
        for sid in shares:
            assert row['tickers'][sid] == symbols[sid]
            close(row['prices'][sid], prices[sid][day][1])
        equity = cash + sum(q * prices[sid][day][1] for sid, q in shares.items())
        close(row['total_value_usd'], equity)
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
        daily_values.append({'session': day, 'cash_usd': cash, 'equity_usd': equity})
        if day in decisions:
            d = decisions[day]
            assert d['shares_before'] == shares
            close(d['cash_before_usd'], cash)
            for sid, price in d['prices'].items():
                close(price, prices[sid][day][1])
            decision_fees = sum(abs(q) * prices[sid][day][1] * .001 for sid, q in d['delta'].items())
            close(d['projected_fees_usd'], decision_fees)
            close(d['projected_cash_usd'], cash - sum(q * prices[sid][day][1] for sid, q in d['delta'].items()) - decision_fees)
    assert len(expected_trades) == len(e['trades'])
    for expected, actual in zip(expected_trades, e['trades']):
        assert set(expected) == set(actual)
        for key in expected:
            if key in ('price_usd', 'transaction_cost_usd'):
                close(actual[key], expected[key])
            else:
                assert actual[key] == expected[key]
    close(e['summary']['terminal_value_usd'], equity)
    close(e['summary']['path_return_net'], equity / 25000 - 1)
    close(e['summary']['path_max_drawdown'], drawdown)
    verify()
    out = {'schema': 'ndx_preference_accounting_independent_oracle_v1', 'status': 'PASS',
        'scope': 'CONDITIONAL_FIXED_USER_PREFERENCE_ACCOUNTING_NOT_WINNER_OR_PIT',
        'engine_called': False, 'source_hashes': sources, 'session_count': len(calendar),
        'execution_count': len(executions), 'trade_count': len(expected_trades), 'fees_usd': fees,
        'terminal_cash_usd': cash, 'terminal_shares': shares, 'terminal_value_usd': equity,
        'path_return_net': equity / 25000 - 1, 'path_max_drawdown': drawdown,
        'rejected_execution_count': rejected, 'rejection_no_partial_fill_exercised': rejected > 0,
        'frozen_delta_next_session_open_verified': True, 'schedule_source_unchanged': True,
        'daily': daily_values, 'point_in_time_verified': False, 'promotion_allowed': False}
    path = REPORT.with_name('preference_retrospective_accounting_independent_oracle_20260912.json')
    with path.open('x', encoding='utf-8') as handle:
        json.dump(out, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    verify()
    print(json.dumps({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'fees_usd': fees, 'trades': len(expected_trades), 'rejected': rejected}))


if __name__ == '__main__':
    main()
