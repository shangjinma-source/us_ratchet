"""Bounded pure compilation of fixed old windows; no search or economic ledger."""
import csv
import gzip
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window

OUTPUT = ROOT / 'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v1.json'


def main():
    pins, cache = {}, {}

    def normalize(path):
        p = Path(path)
        return (p.relative_to(ROOT) if p.is_absolute() else p).as_posix()

    def read(path, expected=None):
        path = normalize(path)
        raw = (ROOT / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected and digest != expected:
            raise ValueError('SOURCE_CHANGED:' + path)
        if path in pins and pins[path] != digest:
            raise ValueError('CONFLICTING_SOURCE:' + path)
        pins[path] = digest
        return raw

    def document(path, children=False):
        result = json.loads(read(path))
        if children:
            for source, digest in result.get('source_hashes', {}).items():
                read(source, digest)
        return result

    timeline_path = 'tmp/old_window_membership_timeline_20261026/timeline.json'
    eligibility_path = 'tmp/old_window_regular_way_20261026/review.json'
    calendar_path = 'tmp/old_window_official_calendar_20261026/review.json'
    fixed_path = 'tmp/fixed12_training_prepare_20261014_v6/prepared.json'
    later_path = 'tmp/next12_training_prepare_20261014_v1/prepared.json'
    ilmn_path = 'tmp/ilmn_coordinate_review_20261026/review.json'
    special_path = 'tmp/three_spinoff_signal_review_20261026/review.json'
    timeline = document(timeline_path)
    calendar = document(calendar_path)
    eligibility = document(eligibility_path)
    fixed = document(fixed_path, True)
    later = document(later_path, True)
    document(ilmn_path, True)
    document(special_path, True)
    identity_review = 'tmp/fixed12_identity_pin_review_20261026/review.json'
    document(identity_review)
    read('scripts/compile_old_windows_raw_signal.py')
    read('backtest/return_priority_monthly_training_inputs.py')

    def closes(path, ticker):
        path = normalize(path)
        if path in cache:
            return cache[path]
        raw = read(path)
        if path.endswith('.csv'):
            rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
            values = {r.get('Date', r.get('date')): r.get('Close', r.get('close')) for r in rows}
        else:
            parsed = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw, parse_float=str)
            chart = parsed['chart']['result'][0]
            if chart['meta']['symbol'] != ticker:
                raise ValueError('SOURCE_SYMBOL_MISMATCH:' + ticker)
            zone = ZoneInfo(chart['meta']['exchangeTimezoneName'])
            quote = chart['indicators']['quote'][0]['close']
            values = {datetime.fromtimestamp(ts, zone).date().isoformat(): quote[i]
                      for i, ts in enumerate(chart['timestamp'])}
        cache[path] = values
        return values

    by_day = {w['decision_cutoff']: (w, fixed_path, 'fixed12') for w in fixed['windows']}
    by_day.update({w['decision_cutoff']: (w, later_path, 'later12') for w in later['windows']})
    exclusions = {(r['decision_date'], r['ticker']): r for r in eligibility['rows']
                  if r['status'] == 'EXCLUDED_SHORT_REGULAR_HISTORY'}
    outputs = []
    for member in timeline['monthly_candidates']:
        day = member['decision_date']
        out = dict(decision_date=day, members=member['members'], uncertain_members=member.get('uncertain_members', []),
                   membership_limitations=member.get('unresolved', []), blockers=[], compiled_search_arguments=None,
                   execution_authorized=False, membership_pit_certified=False, identity_certified=False)
        if day not in by_day:
            out.update(status='BLOCKED', blockers=['NO_PREVIOUSLY_REVIEWED_COMPLETE_IDENTITY_AND_DECISION_COST_BINDING'])
            outputs.append(out)
            continue
        old, old_path, group = by_day[day]
        if set(member['members']) != {c['ticker'] for c in old['candidates']}:
            raise ValueError('DOMAIN_MISMATCH:' + day)
        days = old['training_dates']
        expected = [d for d in calendar['official_sessions'] if d <= day][-253:]
        if days != expected:
            raise ValueError('TRAINING_CALENDAR_MISMATCH:' + day)
        candidates, changes, exclusion_evidence = [], [], {}
        for previous in old['candidates']:
            c = deepcopy(previous)
            ticker = c['ticker']
            c.pop('training_gross', None)
            c['source_references'] = [old_path, timeline_path, calendar_path]
            c['identity_certified'] = False
            if (day, ticker) in exclusions:
                c.update(status='EXCLUDED_TRAINING_RULE', blockers=[])
                exclusion_evidence[ticker] = dict(reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY',
                    known_asof=day, source_references=[eligibility_path])
                candidates.append(c)
                continue
            if group == 'fixed12' and not c.get('identity_available_by_cutoff'):
                out['blockers'].append('IDENTITY_NOT_AVAILABLE_BY_CUTOFF:' + ticker)
            if ticker == 'HON' and day >= '2026-06-29':
                out['blockers'].append('HON_DATED_CUSIP_REVERSE_SPLIT_BINDING_PENDING')
            source = normalize(c['training_source'])
            if ticker == 'ILMN':
                source = 'tmp/fixed12_extended_quote_capture_20261014_v1/ILMN.response.bin'
                c['source_references'].append(ilmn_path)
            elif ticker in ('HON', 'CMCSA', 'WDC'):
                source = 'data/cache/research/current_raw_capture_20261014_v1/' + ticker + '.response.bin'
                c['source_references'].append(special_path)
            values = closes(source, ticker)
            missing = [d for d in days if values.get(d) is None]
            c.update(training_source=source, missing_training_dates=missing)
            if missing:
                out['blockers'].append('MISSING_RAW_TRAINING:' + ticker)
            else:
                new = [str(Fraction(values[d])) for d in days]
                old_values = previous['training_close']
                changed = any(Fraction(new[i+21])/Fraction(new[i]) != Fraction(old_values[i+21])/Fraction(old_values[i])
                              for i in range(0, 252, 21))
                if changed:
                    changes.append(ticker)
                c.update(training_close=new, status='READY_CONDITIONAL', blockers=[],
                    training_basis=('PROVIDER_SPINOFF_ADJUSTED_PRICE_SIGNAL_NOT_TOTAL_RETURN'
                        if ticker in ('ILMN', 'HON', 'CMCSA', 'WDC') else 'FIXED_SOURCE_RAW_PRICE_SIGNAL_NOT_TOTAL_RETURN'),
                    decision_cost_basis='UNCHANGED_PREVIOUS_REVIEWED_CONDITIONAL_NOMINAL_COST')
            candidates.append(c)
        out.update(candidates=candidates, training_dates=days, old_prepared_source=old_path,
                   changed_scenario_tickers=changes,
                   uncertain_member_training_exclusions=[r for (d, t), r in exclusions.items()
                       if d == day and t in member.get('uncertain_members', [])])
        admission = dict(status='REVIEWED_CONDITIONAL', decision_date=day, members=member['members'],
            training_exclusions=exclusion_evidence,
            source_references=[old_path, timeline_path, calendar_path, eligibility_path, ilmn_path, special_path, identity_review])
        out['admission'] = admission
        if not out['blockers']:
            out['compiled_search_arguments'] = compile_monthly_training_window(
                window=dict(decision_cutoff=day, training_dates=days, candidates=candidates),
                source_hashes=pins, admission=admission)
            out['status'] = 'PURE_COMPILED_CONDITIONAL_NOT_EXECUTION_ADMITTED'
        else:
            out['status'] = 'BLOCKED'
        outputs.append(out)
    for path, digest in pins.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != digest:
            raise ValueError('SOURCE_CHANGED_DURING_COMPILATION:' + path)
    result = dict(schema='OLD_WINDOWS_UNIFIED_RAW_COMPILATION_V1', windows=outputs, source_hashes=pins,
        window_count=len(outputs), pure_compiled_windows=sum(w['compiled_search_arguments'] is not None for w in outputs),
        search_calls=0, economic_runs=0, execution_authorized=False,
        limitations=['Known member sets retain all original conditional membership limitations; uncertain HONA remains explicit.',
            'Raw close ratios are price-signal proxies, never dividend-inclusive total return.',
            'Conditional identities and nominal costs are inherited without upgrading certification.',
            'Ordinary corporate actions, distributions and entitlement delivery still require execution admission.',
            'Earlier seven windows remain blocked instead of reusing nominal training as raw.'])
    OUTPUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('window_count', 'pure_compiled_windows', 'search_calls', 'economic_runs')}))


if __name__ == '__main__':
    main()
