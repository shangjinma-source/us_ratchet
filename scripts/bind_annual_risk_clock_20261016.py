"""Authenticate sources and bind assumed daily clocks; no economic execution."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest.annual_risk_clock_binder import bind_snapshot


def prepare(output):
    destination=(ROOT/output).resolve()
    if destination.exists() or not destination.is_relative_to(ROOT/'tmp'):
        raise ValueError('NEW_TMP_DIRECTORY_REQUIRED')
    pins={}
    def read(path,expected=None):
        path=Path(path).as_posix();raw=(ROOT/path).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected is not None and digest!=expected:raise ValueError('SOURCE_DRIFT:'+path)
        if path in pins and pins[path]!=digest:raise ValueError('PIN_CONFLICT:'+path)
        pins[path]=digest
        return raw
    def document(path):return json.loads(read(path))
    base='tmp/annual_risk_history_candidates_20261016_v1/'
    manifest=document(base+'manifest.json')
    schedule_path='tmp/official_session_closes_20261016_v1/session_close_times.json'
    schedule=document(schedule_path)
    assumption_path='research_contracts/daily_close_availability_assumption_20261016_v1.json'
    assumption=document(assumption_path)
    if assumption['scheduled_close_source']!=schedule_path:raise ValueError('ASSUMPTION_SCHEDULE_MISMATCH')
    scope=document('research_contracts/annual_hon_cmcsa_conditional_scope_20261016_v1.json')
    sources=document('tmp/conditional_calendar_year_inputs_20261016_v2/source_manifest.json')['sources']
    for mapping in (manifest['source_hashes'],manifest['inherited_dependency_hashes'],schedule['source_hashes'],assumption['source_hashes'],scope['source_hashes']):
        for path,digest in mapping.items():read(path,digest)
    raw=read(base+'price_snapshots.jsonl.gz',manifest['snapshot_sha256'])
    document('tmp/annual_risk_history_independent_20261016_v1.json')
    expected_dates=[]; snapshots=[]; count=0; blocked=0
    for line in gzip.decompress(raw).decode('utf-8').splitlines():
        candidate=json.loads(line);decision=candidate['decision_date'];identities={}
        for source in sources:
            ticker=source['ticker'];start=('2025-02-24' if ticker=='SNDK' else '2026-06-29' if ticker=='HONA' else source['first'])
            sid=source['current_security_id'] if decision>=start else None
            if ticker=='HON' and sid:
                sid='security:0000773840:'+('438516106' if decision<'2026-06-29' else '438516205')
            identities[ticker]=sid
        snapshot=bind_snapshot(candidate=candidate,schedule=schedule,expected_identities=identities,
            assumption=assumption,review_reference=assumption_path)
        snapshots.append(dict(decision_date=decision,snapshot=snapshot))
        expected_dates.append(decision);count+=len(snapshot['histories']);blocked+=len(snapshot['blocked_rows'])
    if expected_dates!=sorted(set(expected_dates)) or len(expected_dates)!=manifest['snapshot_count']:
        raise ValueError('EXACT_UNIQUE_DECISIONS_REQUIRED')
    annual=document('tmp/annual_continuous_draft_20261016_v3/draft_prepared.json')
    if expected_dates!=annual['session_dates']:raise ValueError('ANNUAL_DECISION_COVERAGE_MISMATCH')
    destination.mkdir()
    with gzip.open(destination/'resolver_snapshots.jsonl.gz','wt',encoding='utf-8') as handle:
        for row in snapshots:handle.write(json.dumps(row,separators=(',',':'))+'\n')
    for path in ('backtest/annual_risk_clock_binder.py','scripts/bind_annual_risk_clock_20261016.py'):
        read(path)
    # Sources are authenticated before binding; final executable preflight must
    # re-read the hashes rather than trust this historical preparation receipt.
    report=dict(status='CLOCK_BOUND_CONDITIONAL_FULL_DOMAIN_BLOCKED',timestamp_basis=assumption['timestamp_basis'],
        source_hashes=pins,dependencies_authenticated=True,snapshot_count=len(snapshots),
        ready_histories=count,retained_blocked_rows=blocked,economic_runs=0,execution_admitted=False,
        global_blockers=['TRI_COORDINATES_UNRESOLVED'],historical_receipt_verified=False,
        selection_eligibility='253_GUARD_UNCHANGED; 21_PRICE_ROWS_NOT_SELECTION_ADMISSION',
        snapshot_sha256=hashlib.sha256((destination/'resolver_snapshots.jsonl.gz').read_bytes()).hexdigest(),
        loading_contract='Map decision_date to snapshot; use official session_dates/session_close_times in build_signal_history_resolver')
    (destination/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return {k:v for k,v in report.items() if k!='source_hashes'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    print(json.dumps(prepare(parser.parse_args().output)))
