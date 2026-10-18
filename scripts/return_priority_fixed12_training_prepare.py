"""Create-only twelve-window training preparation; never imports or runs search."""
import argparse
import csv
import gzip
import hashlib
import io
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = 'tmp/fixed12_data_coverage_20261014_v3/coverage.json'
PANEL = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
SMCI = 'tmp/smci_quote_capture_20261014_v1/conditional_window_inputs.json'
IDENTITY = 'data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv'
CORE = 'backtest/return_priority_fresh_cash_quantity_search.py'
CORE_SHA = '756a16a83735279db24332d096aa149b54fc7ff4e91cb807410b3f33f425b588'


def prepare():
    pins = {}

    def read(name, expected=None):
        raw = (ROOT / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected and digest != expected:
            raise ValueError('Changed source: ' + name)
        pins[name] = digest
        return raw

    def document(name):
        result = json.loads(read(name))
        for path, digest in result.get('source_hashes', {}).items():
            read(path, digest)
        return result

    def table(name):
        manifest = json.loads(read(name + '.manifest.json'))
        rows = list(csv.DictReader(io.StringIO(read(name, manifest['content_sha256']).decode('utf-8-sig'))))
        if len(rows) != manifest['row_count']:
            raise ValueError('Row count differs: ' + name)
        return rows

    read(CORE, CORE_SHA)
    read('config/ndx_security_lifecycle.yaml')
    membership = document(MEMBERS)
    panel = document(PANEL)
    smci = document(SMCI)
    official = document('tmp/fixed12_official_actions_20261014_v1/observed_primary_facts.json')
    split_notice = next(e for e in official['events'] if e['ticker'] == 'SMCI')
    identities = table(IDENTITY)
    reports = table('data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv')
    stocks = {r['ticker']: r for r in panel['stocks']}
    smci_windows = {w['decision_cutoff']: w for w in smci['windows']}
    quote_cache = {}

    def quotes(ticker):
        if ticker not in quote_cache:
            base = 'data/cache/research/current_raw_capture_20261013_v1/' + ticker
            receipt = json.loads(read(base + '.receipt.json'))
            raw = read(base + '.response.bin', receipt['raw_sha256'])
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            provider = json.loads(decoded)['chart']['result'][0]
            if provider['meta']['symbol'] != ticker:
                raise ValueError('Wrong quote identity')
            zone = ZoneInfo(provider['meta']['exchangeTimezoneName'])
            dates = [datetime.fromtimestamp(t, zone).date().isoformat() for t in provider['timestamp']]
            closes = dict(zip(dates, provider['indicators']['quote'][0]['close']))
            if len(closes) != len(dates):
                raise ValueError('Duplicate quote dates')
            stock = stocks[ticker]
            for d, row in zip(panel['calendar'], stock['values']):
                if closes.get(d) != row[3]:
                    raise ValueError('Raw/panel close mismatch: ' + ticker)
            events = [dict(event_date=datetime.fromtimestamp(e['date'], zone).date().isoformat(), provider_event=e)
                      for e in provider.get('events', {}).get('splits', {}).values()]
            quote_cache[ticker] = (closes, events)
        return quote_cache[ticker]

    windows = []
    for window in membership['windows']:
        decision, days = window['decision_cutoff'], window['training_dates']
        if len(days) != 253 or days[-1] != decision or days != sorted(set(days)):
            raise ValueError('Training calendar invalid')
        candidates = []
        for member in window['candidates']:
            ticker = member['ticker']
            matches = [r for r in identities if ticker in r['ticker_set'].split(';') and r['identity_status'] == 'resolved']
            available = [r for r in reports if r['ticker'] == ticker and r['report_date'] <= decision and r['available_date'] <= decision]
            if available:
                latest = max(r['report_date'] for r in available)
                cusips = {r['cusip'] for r in available if r['report_date'] == latest}
                matches = [r for r in matches if r['cusip'] in cusips]
            pairs = {(r['security_id'], r['issuer_id']) for r in matches}
            sid, issuer = next(iter(pairs)) if len(pairs) == 1 else (None, None)
            identity_bridge = None
            if ticker == 'SMCI' and sid and decision >= split_notice['expected_split_adjusted_trading_date']:
                sid = 'security:' + matches[0]['cik'] + ':' + split_notice['new_cusip']
                identity_bridge = dict(status='CONDITIONAL_OFFICIAL_SPLIT_CUSIP_BRIDGE', old_security_id=matches[0]['security_id'], evidence=split_notice)
            blockers, exclusions = [], []
            if not sid:
                blockers.append('IDENTITY_UNRESOLVED_OR_MULTIPLE')
            values, cost, source, basis, events = [], None, None, None, []
            if ticker == 'SMCI':
                s = smci_windows.get(decision)
                if s and s['training_dates'] == days:
                    values = [s['rows'][d]['quote']['close'] for d in days]
                    cost = s['rows'][decision]['conditional_nominal']['close']
                    source, basis = SMCI, 'CONDITIONAL_PROVIDER_QUOTE_SPLIT_ADJUSTED'
                    events = [dict(event_date=smci['split_date'], new_shares=smci['new_shares'], old_shares=smci['old_shares'])]
                else:
                    blockers.append('SMCI_WHOLE_WINDOW_UNAVAILABLE')
            elif ticker in stocks:
                closes, events = quotes(ticker)
                values = [str(closes[d]) if closes.get(d) is not None else None for d in days]
                cost, source, basis = values[-1], PANEL, 'CONDITIONAL_PROVIDER_QUOTE_SPLIT_ADJUSTED'
            else:
                blockers.append('NONPANEL_WHOLE_SOURCE_UNIT_AND_SPLIT_REVIEW_REQUIRED')
            missing = [d for d, v in zip(days, values) if v is None or Fraction(v) <= 0] if values else days
            if values and missing:
                if ticker == 'ARM':
                    exclusions.append('INSUFFICIENT_253_SESSION_PREDECISION_HISTORY')
                else:
                    blockers.append('INCOMPLETE_PREDECISION_TRAINING')
            ratios = [str(Fraction(values[i+21]) / Fraction(values[i])) for i in range(0,252,21)] if values and not missing else None
            candidates.append(dict(ticker=ticker, security_id=sid, issuer_id=issuer,
                status='BLOCKED' if blockers else ('EXCLUDED_TRAINING_RULE' if exclusions else 'READY_CONDITIONAL'),
                blockers=blockers, exclusion_reasons=exclusions, identity_evidence=matches,
                identity_bridge=identity_bridge, identity_available_by_cutoff=bool(available),
                identity_certified=False, training_basis=basis, training_source=source,
                training_close=values, missing_training_dates=missing, training_gross=ratios,
                decision_cost=cost, decision_cost_basis='CONDITIONAL_RECONSTRUCTED_NOMINAL' if ticker == 'SMCI' else 'CONDITIONAL_QUOTE_UNIT_NOT_CERTIFIED_NOMINAL',
                returned_splits=[e for e in events if days[0] <= e['event_date'] <= decision],
                split_completeness_certified=False, extra_split_multiplier_applied=False,
                source_candidates_for_followup=member['source_candidates'] if ticker not in stocks and ticker != 'SMCI' else [],
                membership_evidence=member['membership_evidence']))
        if len(candidates) != window['member_denominator'] or len({r['ticker'] for r in candidates}) != len(candidates):
            raise ValueError('Member denominator mismatch')
        ready = [r for r in candidates if r['status'] == 'READY_CONDITIONAL']
        windows.append(dict(decision_cutoff=decision, member_denominator=len(candidates),
            status='BLOCKED' if any(r['blockers'] for r in candidates) else 'READY_CONDITIONAL',
            ready_count=len(ready), candidates=candidates, training_dates=days,
            scenario_start_dates=days[:-1:21], scenario_end_dates=days[21::21],
            same_issuer_classes={i:[r['ticker'] for r in candidates if r['issuer_id']==i]
                                for i in {r['issuer_id'] for r in candidates if r['issuer_id']}
                                if sum(r['issuer_id']==i for r in candidates)>1}))
    if len(windows) != 12 or windows[0]['decision_cutoff'] != '2024-07-31' or windows[-1]['decision_cutoff'] != '2025-06-30':
        raise ValueError('Fixed twelve-window schedule differs')
    for name, digest in list(pins.items()):
        read(name, digest)
    return dict(status='PREPARED_WITH_EXPLICIT_BLOCKERS', windows=windows, source_hashes=pins,
        protocol=dict(entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',max_objective_evaluations=8192,
                      fixed_seed='fresh-quantity-20261014-v1',core_sha256=CORE_SHA),
        search_calls=0, network_calls=0, future_outcome_used_for_eligibility=False,
        partial_pool_search_allowed=False, point_in_time_certified=False, economic_total_return=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    if (ROOT/'tmp').resolve() not in destination.parents or destination.exists():
        raise ValueError('Create-only tmp destination required')
    result = prepare()
    result['source_hashes'][str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps([dict(date=w['decision_cutoff'],status=w['status'],ready=w['ready_count'],blocked=[r['ticker'] for r in w['candidates'] if r['blockers']],excluded=[r['ticker'] for r in w['candidates'] if r['exclusion_reasons']]) for w in result['windows']]))
