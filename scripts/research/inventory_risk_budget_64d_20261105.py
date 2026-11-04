"""Read-only 67 baseline target lookbacks; no returns, selection or economic replay."""
import gzip
import hashlib
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[2]
PINS = {}

def read(path):
    raw = (ROOT / path).read_bytes()
    PINS[path] = hashlib.sha256(raw).hexdigest()
    return json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)

def day(timestamp):
    return datetime.fromtimestamp(timestamp, ZoneInfo('America/New_York')).date().isoformat()

def main():
    qqq = {}
    qqq_events = {}
    for path in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin',
                 'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
        body = read(path)['chart']['result'][0]
        for index, stamp in enumerate(body['timestamp']):
            if body['indicators']['quote'][0]['close'][index] is not None:
                qqq[day(stamp)] = True
        for event in body.get('events', {}).get('dividends', {}).values():
            qqq_events[day(event['date'])] = event
    rows = []
    dividend_reuse = {}
    coordinate_reuse = {}
    for base, prepared in (
        ('tmp/recent_continuous_baseline_20261026_v7', 'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),
        ('tmp/old_continuous_baseline_20261026_v9', 'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')):
        inputs = read(base + '/execution_inputs.json')
        identities = {}
        for outer in read(prepared)['windows']:
            window = outer.get('window', outer)
            for candidate in window['candidates']:
                if candidate.get('security_id'):
                    identities[candidate['security_id']] = candidate['ticker']
                for event in candidate.get('coordinate_events', []):
                    coordinate_reuse[(candidate['ticker'], event['date'])] = dict(event=event, evidence_path=prepared)
            for event in outer.get('window_coordinate_events', []):
                if event.get('training_allowed'):
                    coordinate_reuse[(event['ticker'], event['date'])] = dict(event=event, evidence_path=prepared)
        for event in inputs['dividend_events']:
            ticker = identities.get(event['security_id'])
            if ticker:
                dividend_reuse[(ticker, event['ex_date'])] = dict(event=event, evidence_path=base + '/execution_inputs.json', scope='Ticker join requires same historical issuer and unit verification before use')
    raw_cache = {}
    for label, base, prepared in (
        ('early', 'tmp/recent_continuous_baseline_20261026_v7', 'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),
        ('later', 'tmp/old_continuous_baseline_20261026_v9', 'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')):
        inputs = read(base + '/execution_inputs.json')
        mapped_dividends = {(e['security_id'], e['ex_date']): e for e in inputs['dividend_events']}
        final_targets = {}
        for audit in read(base + '/book.json')['provider_audit']:
            decision_day = audit.get('target_decision_date')
            if decision_day and decision_day not in final_targets and 'monthly_ceiling' in audit:
                final_targets[decision_day] = audit['monthly_ceiling']
        windows = read(prepared)['windows']
        for outer in windows:
            window = outer.get('window', outer)
            decision = window.get('decision_cutoff', window.get('decision_date'))
            selection = dict(target_quantities=final_targets[decision])
            days = window['training_dates'][-64:]
            candidates = {c['security_id']: c for c in window['candidates'] if c.get('security_id')}
            stocks = []
            for sid, quantity in selection['target_quantities'].items():
                if not quantity:
                    continue
                candidate = candidates[sid]
                ticker = candidate['ticker']
                source = candidate['training_source'].replace('\\', '/')
                gaps = []
                events = []
                try:
                    if source not in raw_cache:
                        raw_cache[source] = read(source)['chart']['result'][0]
                    body = raw_cache[source]
                    for kind, event_map in body.get('events', {}).items():
                        for event in event_map.values():
                            event_day = day(event['date'])
                            if days[0] < event_day <= days[-1]:
                                mapped = (mapped_dividends.get((sid, event_day)) or dividend_reuse.get((ticker, event_day))) if kind == 'dividends' else None
                                coordinate = [e for e in outer.get('window_coordinate_events', []) if e.get('ticker') == ticker and e['date'] == event_day]
                                coordinate += [e for e in candidate.get('coordinate_events', []) if e['date'] == event_day]
                                if not coordinate and (ticker, event_day) in coordinate_reuse:
                                    coordinate = [coordinate_reuse[(ticker, event_day)]]
                                events.append(dict(kind=kind, date=event_day, payload=event, existing_dividend=mapped, training_coordinate=coordinate))
                                if kind == 'dividends' and mapped is None:
                                    gaps.append('UNMAPPED_LOOKBACK_DIVIDEND:' + event_day)
                                elif kind == 'splits' and not coordinate:
                                    gaps.append('SPLIT_LOOKBACK_REVIEW_NOT_LINKED:' + event_day)
                except (ValueError, KeyError, IndexError) as error:
                    gaps.append('SOURCE_EVENT_STREAM_NOT_JSON_CHART:' + type(error).__name__)
                basis = candidate.get('training_basis', 'EARLY_PREPARED_CONDITIONAL_PRICE_SIGNAL')
                nominal = inputs.get('ohlc', {}).get(sid, {})
                values = candidate.get('training_close', [])[-64:]
                nominal_equal = len(values) == 64 and all(d in nominal and Fraction(v) == Fraction(nominal[d]['close']) for d, v in zip(days, values))
                if 'SPINOFF' in basis or ticker in ('EXC', 'WDC', 'HON', 'CMCSA', 'ILMN', 'MTCH', 'AZN', 'TRI'):
                    if not (ticker == 'WDC' and days[0] > '2025-02-24' and nominal_equal and all(e['kind'] == 'dividends' for e in events)):
                        gaps.append('COMPLEX_COORDINATE_TOTAL_RETURN_NOT_CERTIFIED')
                if len(candidate.get('training_close', [])) != 253:
                    gaps.append('TRAINING_PRICE_COUNT_INVALID')
                stocks.append(dict(ticker=ticker, security_id=sid, raw_target_quantity=quantity, source=source, basis=basis,
                                   events=events, gaps=sorted(set(gaps)), training_prices_equal_nominal_all_64=nominal_equal,
                                   coordinate_note='WDC windows entirely after previously reviewed Feb2025 spinoff; same64 nominal quotes; no new complex event claimed' if ticker == 'WDC' else None,
                                   absence_scope='CONDITIONAL_PROVIDER_STREAM_ONLY_NOT_EXHAUSTIVE_OFFICIAL_PROOF'))
            missing = sorted(set(days) - set(qqq))
            row = dict(window=label, decision=decision, start_close=days[0], end_close=days[-1], target_stocks=stocks,
                       qqq_missing_dates=missing, qqq_ex_dates=[d for d in sorted(qqq_events) if days[0] < d <= days[-1]],
                       status='BLOCKED_NAMED_GAPS' if missing or any(s['gaps'] for s in stocks) else 'CONDITIONAL_COMPONENTS_AVAILABLE_NOT_ASSEMBLED_TOTAL_RETURN')
            rows.append(row)
    result = dict(scope='Baseline targets only; no risk return series calculated. No certified directly runnable month; conditional components require common gross return compiler and audit.',
                  rows=rows, summary={s: sum(r['status'] == s for r in rows) for s in sorted({r['status'] for r in rows})},
                  limitations=['Actual baseline first provider_audit monthly_ceiling targets after capped frontier rerank; raw_selection is not used as final target.',
                               'Future risk-budget capital changes can alter subsequent integer selection and expose additional stocks; this is not a guarantee of candidate full coverage.',
                               'Mapped nominal dividends still need conversion into each training price coordinate; existence is not exact unit certification.',
                               'QQQ gross dividends and stock gross dividends must use the same return definition. No mixed bare-price/total-return comparison.',
                               'No economic replay, network calls, return estimates, production changes.'], source_hashes=PINS)
    output = ROOT / 'tmp/risk_budget_64d_inventory_20261105'
    output.mkdir(exist_ok=True)
    (output / 'inventory.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary']))
    for row in rows:
        if row['status'] == 'BLOCKED_NAMED_GAPS':
            print(row['decision'], '; '.join(s['ticker'] + ':' + ','.join(s['gaps']) for s in row['target_stocks'] if s['gaps']))

if __name__ == '__main__':
    main()
