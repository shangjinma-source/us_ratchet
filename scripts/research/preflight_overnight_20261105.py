"""Read-only fixed-roster overnight pairing inventory; no returns or orders."""
import gzip
import json
import time
from collections import Counter
from datetime import datetime
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'tmp/overnight_preflight_20261105'


def read(name):
    return json.loads((ROOT / name).read_bytes())


def run():
    started = time.monotonic()
    OUT.mkdir(exist_ok=False)
    manifest = 'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json'
    expected = read(manifest)['base_file_dependencies']
    receipts = [manifest]
    for window in ['2021_2023', '2024_2026']:
        name = f'tmp/ema20_economic_20261105/daily/{window}/contract.json'
        receipts.append(name)
        for path, value in read(name)['source_hashes'].items():
            if path in expected and expected[path] != value:
                raise ValueError('EXPECTED_PIN_CONFLICT:' + path)
            expected[path] = value
    verified = {}

    def pinned(name):
        actual = sha256((ROOT / name).read_bytes()).hexdigest()
        if expected.get(name) != actual:
            raise ValueError('FROZEN_SOURCE_CHANGED:' + name)
        verified[name] = actual
        return read(name)

    qqq, qdiv = {}, set()
    for name in ['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin',
                 'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']:
        raw = (ROOT / name).read_bytes()
        assert sha256(raw).hexdigest() == expected[name]
        verified[name] = expected[name]
        body = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)['chart']['result'][0]
        assert not body.get('events', {}).get('splits')
        quote = body['indicators']['quote'][0]
        for i, stamp in enumerate(body['timestamp']):
            day = datetime.fromtimestamp(stamp, ZoneInfo('America/New_York')).date().isoformat()
            row = {k: str(quote[k][i]) for k in ['open', 'close']}
            if day in qqq:
                assert qqq[day] == row
            qqq[day] = row
        qdiv.update(datetime.fromtimestamp(e['date'], ZoneInfo('America/New_York')).date().isoformat()
                    for e in body.get('events', {}).get('dividends', {}).values())

    results = []
    for window, base in [('2021_2023', 'recent_continuous_baseline_20261026_v7'),
                         ('2024_2026', 'old_continuous_baseline_20261026_v9')]:
        assert time.monotonic() - started < 600
        document = pinned(f'tmp/{base}/execution_inputs.json')
        book = pinned(f'tmp/{base}/book.json')
        assert book['status'] == 'COMPLETE'
        days = document['assembled']['session_dates']
        assert days == sorted(set(days))
        states = {x['decision_date']: x for x in book['selection_account_states']}
        rosters = {}
        for audit in book['provider_audit']:
            decision = audit.get('target_decision_date')
            if decision in rosters or not audit.get('selection'):
                continue
            selection = audit['selection']
            quotes = {q['security_id']: q for q in states[decision]['valuation_quotes']}
            targets = selection['target_quantities']
            ranked = sorted((sid for sid, quantity in targets.items() if F(quantity) > 0),
                            key=lambda sid: (-F(targets[sid]) * F(quotes[sid]['price']), sid))
            rosters[decision] = dict(decision=decision, earliest_buy_session=days[days.index(decision)+1],
                                     original_count=len(ranked), selected=ranked[:10],
                                     tickers={sid: quotes[sid]['ticker'] for sid in ranked[:10]},
                                     discarded=ranked[10:])
        assert len(rosters) == len(document['assembled']['monthly_inputs'])
        pairs, missing, events, unknown, counts = [], [], [], [], Counter()
        for i in range(1, len(days)-1):
            previous, buy, sell = days[i-1:i+2]
            eligible = [d for d in rosters if d <= previous]
            if not eligible:
                unknown.append(buy)
                continue
            roster = rosters[max(eligible)]
            assert roster['decision'] < buy and roster['earliest_buy_session'] <= buy
            counts[len(roster['selected'])] += 1
            for sid in roster['selected']:
                ticker = roster['tickers'][sid]
                row = dict(sid=sid, ticker=ticker, previous=previous, buy_close=buy,
                           sell_open=sell, decision=roster['decision'])
                absent = []
                for day, field in [(previous, 'close'), (buy, 'close'), (sell, 'open')]:
                    value = document['ohlc'].get(sid, {}).get(day, {}).get(field)
                    if value is None or F(value) <= 0:
                        absent.append([day, field])
                if absent:
                    missing.append(dict(row, missing=absent))
                else:
                    pairs.append(row)
                for event in document['provider_event_inventory']:
                    if event.get('ticker') == ticker and buy < event['date'] <= sell:
                        events.append(dict(pair=row, event=event, execution_admission='NOT_CHECKED'))
        qmissing = [dict(buy=days[i], sell=days[i+1]) for i in range(1, len(days)-1)
                    if any(qqq.get(d, {}).get(k) in (None, 'None')
                           for d, k in [(days[i-1], 'close'), (days[i], 'close'), (days[i+1], 'open')])]
        exposed_sids = {p['sid'] for p in pairs+missing}
        exposed_tickers = {p['ticker'] for p in pairs+missing}
        stream_unknown = [r for r in document['action_stream_missing']
                          if (isinstance(r, str) and r in exposed_sids) or
                          (isinstance(r, dict) and r.get('ticker') in exposed_tickers)]
        unique_events = {(e['pair']['sid'], e['event']['date'], e['event']['kind']) for e in events}
        result = dict(window=window, scope='CONDITIONAL_FROZEN_BASELINE_ROSTER_NOT_DYNAMIC_ACCOUNT_OR_PIT',
                      roster_months=len(rosters), rosters=list(rosters.values()),
                      overnight_sessions=len(days)-2, roster_size_days=dict(counts),
                      causal_roster_missing_days=unknown, stock_pairs_with_prices=len(pairs),
                      stock_pairs_missing_prices=len(missing), missing=missing,
                      potential_orders_before_cash_rejections=2*(len(pairs)+len(missing)),
                      unique_action_counts=dict(Counter(e[2] for e in unique_events)),
                      provider_events=events, missing_action_stream_observations=stream_unknown,
                      qqq_pairs=len(days)-2-len(qmissing), qqq_missing=qmissing,
                      qqq_ex_dividend_overnights=sum(days[i+1] in qdiv for i in range(1,len(days)-1)),
                      qqq_potential_orders=2*(len(days)-2), pairs=pairs,
                      unit_and_action_certification='NOT_ADMITTED_BY_PRICE_PRESENCE; dynamic exposure review still required')
        results.append(result)
    result = dict(status='LOCAL_PAIRING_COMPLETE_NOT_ECONOMIC_RUN', elapsed_seconds=time.monotonic()-started,
                  expected_pin_receipts=receipts, verified_expected_hashes=verified, results=results,
                  limits=['No auction or broker execution certification', 'No returns calculated',
                          'Source-only event inventory not exhaustive corporate-action clearance'])
    (OUT/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if k not in ['pairs','rosters','provider_events','missing','missing_action_stream_observations']}
                      for r in results], indent=2))


if __name__ == '__main__':
    run()
