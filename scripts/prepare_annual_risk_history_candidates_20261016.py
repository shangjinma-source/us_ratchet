"""Build isolated conditional history candidates, without search or timestamps."""
import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.annual_risk_history_candidates import snapshot_candidate


def prepare(output):
    destination = (ROOT/output).resolve()
    if not destination.is_relative_to(ROOT/'tmp') or destination.exists():
        raise ValueError('NEW_TMP_DIRECTORY_REQUIRED')
    pins = {}
    def load(path):
        content = (ROOT/path).read_bytes()
        pins[path] = hashlib.sha256(content).hexdigest()
        return json.loads(content)
    simple_path = 'tmp/annual_simple_split_coordinates_20261016_v2/coordinates.json'
    complex_path = 'tmp/annual_hon_cmcsa_coordinates_20261016_v1/mapping_candidate.json'
    wdc_path = 'tmp/wdc_sndk_distribution_evidence_20261016_v1/conditional_assembly_v1.json'
    draft_path = 'tmp/annual_continuous_draft_20261016_v3/draft_prepared.json'
    manifest_path = 'tmp/conditional_calendar_year_inputs_20261016_v2/source_manifest.json'
    simple = load(simple_path)
    complex_doc = load(complex_path)
    wdc = load(wdc_path)
    draft = load(draft_path)
    manifest = load(manifest_path)
    source = {r['ticker']:r for r in manifest['sources']}
    simple_by = {r['ticker']:r for r in simple['rows']}
    complex_by = {r['ticker']:r for r in complex_doc['rows']}
    # Capture the exact inherited dependency contracts without repeatedly reading
    # large old research trees. Final executable binder must authenticate these.
    inherited = {}
    for document in (simple, complex_doc, wdc, draft, manifest):
        for path, digest in document.get('source_hashes', {}).items():
            if path in inherited and inherited[path] != digest:
                raise ValueError('DEPENDENCY_PIN_CONFLICT:'+path)
            inherited[path] = digest
    records = []
    for ticker in manifest['universe']:
        src = source[ticker]
        sid = src['current_security_id']
        ordinary = ('2025-02-24' if ticker == 'SNDK' else
                    '2026-06-29' if ticker == 'HONA' else src['first'])
        spans = [dict(start=ordinary, end='2026-10-13', security_id=sid)]
        link = None
        if ticker == 'HON':
            spans = [dict(start=ordinary,end='2026-06-28',security_id='security:0000773840:438516106'),
                     dict(start='2026-06-29',end='2026-10-13',security_id='security:0000773840:438516205')]
            link = dict(mode='DECLARED_CONDITIONAL_LINK', from_security_id='security:0000773840:438516106', to_security_id='security:0000773840:438516205', effective_date='2026-06-29', share_ratio='1/2', source_reference=complex_path)
        events, blockers, closes = [], [], None
        if ticker == 'TRI':
            blockers = ['TRI_COMPLEX_ACTION_COORDINATES_UNRESOLVED']
            reference = draft_path
        elif ticker in complex_by:
            component = complex_by[ticker]
            closes = {d:r['nominal_ohlc']['close'] for d,r in component['rows'].items()}
            events = component['true_share_events']
            reference = complex_path
        elif ticker in ('WDC','SNDK'):
            closes = {d:r['close'] for d,r in wdc['ohlc'][sid].items()}
            if wdc['true_parent_split_events']:
                raise ValueError('UNEXPECTED_WDC_PARENT_SHARE_EVENTS_REQUIRES_MAPPING')
            reference = wdc_path
        else:
            component = simple_by[ticker]
            closes = {d:r['ohlc']['close'] for d,r in component['nominal_ohlc'].items()}
            events = component['events']
            reference = simple_path
        records.append(dict(ticker=ticker,ordinary_start=ordinary,identity_spans=spans,
            cross_identity_link=link,nominal_closes=closes,true_share_events=events,
            blockers=blockers,source_reference=reference))
    # Existing annual calendar is a conditional research calendar, not a new
    # exchange-close certification. Warmup requires only the last21 sessions.
    first_calendar = load('tmp/conditional_calendar_year_inputs_20261016_v2/2024_calendar.json')
    raw_path = 'data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'
    raw = (ROOT/raw_path).read_bytes()
    pins[raw_path] = hashlib.sha256(raw).hexdigest()
    raw = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
    from datetime import datetime
    from zoneinfo import ZoneInfo
    quote = json.loads(raw)['chart']['result'][0]
    zone = ZoneInfo(quote['meta']['exchangeTimezoneName'])
    calendar = sorted(datetime.fromtimestamp(t,zone).date().isoformat() for t in quote['timestamp'])
    if not set(draft['session_dates']).issubset(calendar):
        raise ValueError('DRAFT_SESSION_MISSING_FROM_WARMUP_CALENDAR')
    destination.mkdir()
    counts = Counter()
    with gzip.open(destination/'price_snapshots.jsonl.gz','wt',encoding='utf-8') as handle:
        for decision in draft['session_dates']:
            snapshot = snapshot_candidate(decision_date=decision,session_dates=calendar,records=records)
            counts.update(r['status'] for r in snapshot['rows'])
            handle.write(json.dumps(snapshot,separators=(',',':'))+'\n')
    for path,digest in pins.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != digest:
            raise ValueError('SOURCE_CHANGED_DURING_BUILD:'+path)
    for path in ('backtest/annual_risk_history_candidates.py','scripts/prepare_annual_risk_history_candidates_20261016.py'):
        pins[path] = hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    result = dict(status='ADAPTER_ONLY_NOT_EXECUTABLE',economic_calls=0,domain_count=len(records),
        snapshot_count=len(draft['session_dates']),first_decision=draft['session_dates'][0],
        last_decision=draft['session_dates'][-1],row_counts=dict(counts),source_hashes=pins,
        inherited_dependency_hashes=inherited,inherited_dependencies_reauthenticated=False,
        snapshot_sha256=hashlib.sha256((destination/'price_snapshots.jsonl.gz').read_bytes()).hexdigest(),
        blockers=['TRI_COORDINATES_UNRESOLVED','SESSION_CLOSE_CLOCK_NOT_BOUND'],
        conditional_assumptions=['CURRENT_OBSERVED_DOMAIN_BACKWARD_LINK_NOT_PIT',
            'HON_CMCSA_WHOLE_SOURCE_COORDINATE_EXTENSION',
            'NO_COMPLETED_AT_OR_OBSERVED_AT_ASSERTION; RESEARCH_AVAILABILITY_BINDING_REQUIRED'],
        selection_eligibility='21_BARS_IS_NOT_253_SELECTION_ADMISSION',
        total_return=False,execution_admitted=False)
    (destination/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('source_hashes','inherited_dependency_hashes')}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True)
    print(json.dumps(prepare(parser.parse_args().output)))
