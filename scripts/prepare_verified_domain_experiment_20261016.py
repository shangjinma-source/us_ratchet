"""Authorized isolated data-exclusion experiment; preparation only, no search."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4


def prepare():
    out=ROOT/'tmp/daily_verified_domain_experiment_20261016_v2'
    if out.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
    pins={}
    def read(path,expected=None):
        raw=(ROOT/path).read_bytes();h=hashlib.sha256(raw).hexdigest()
        if expected is not None and h!=expected:raise ValueError('SOURCE_CHANGED:'+path)
        if path in pins and pins[path]!=h:raise ValueError('SOURCE_CONFLICT:'+path)
        pins[path]=h;return raw
    original_path='tmp/annual_risk_execution_preflight_20261016_v1/launch_prepared.json'
    original=json.loads(read(original_path));p=deepcopy(original)
    read('research_contracts/user_verified_domain_experiment_authorization_20261016_v1.json')
    for name,h in original['source_hashes'].items():read(name,h)
    clock_path='tmp/annual_risk_clock_bound_20261016_v2/manifest.json'
    clock=json.loads(read(clock_path))
    raw=read('tmp/annual_risk_clock_bound_20261016_v2/resolver_snapshots.jsonl.gz',clock['snapshot_sha256'])
    issuer='issuer:0001075124'
    excluded={sid for sid,meta in p['metadata'].items() if meta['issuer_id']==issuer}
    if not excluded:raise ValueError('EXCLUSION_ISSUER_NOT_PRESENT')
    tickers={p['metadata'][sid]['ticker'] for sid in excluded}
    audit=dict(excluded_issuer=issuer,excluded_metadata={sid:p['metadata'][sid] for sid in sorted(excluded)},
        reason='USER_AUTHORIZED_SEPARATE_UNVERIFIABLE_PRICE_DOMAIN_EXPERIMENT',
        selection_basis='DATA_VERIFIABILITY_NOT_RETURNS',original_strategy_unchanged=True,
        other_exclusions=[],windows=[],action_references=[])
    for key in ('split_events_reference_only','identity_migrations','cash_stock_merger_events','distribution_events','unsupported_conversions','supported_conversions'):
        for event in p[key]:
            # Only explicit identity fields are action references, not evidence prose.
            linked={v for k,v in event.items() if isinstance(v,str) and (k.endswith('sid') or k.endswith('security_id'))}
            if linked & excluded:raise ValueError('EXCLUDED_ISSUER_ACTION_REQUIRES_REVIEW:'+key+':'+str(event))
        audit['action_references'].append(dict(collection=key,count=len(p[key]),excluded_identity_references=0,unchanged=True))
    if any(q for sid,q in p['initial_shares'].items() if sid in excluded):raise ValueError('EXCLUDED_INITIAL_HOLDING')
    for w in p['windows']:
        args=w['search_arguments'];before=set(args['prices']);removed=before & excluded
        for key in ('prices','metadata'):
            args[key]={sid:v for sid,v in args[key].items() if sid not in excluded}
        args['training_scenarios']=[{sid:v for sid,v in row.items() if sid not in excluded} for row in args['training_scenarios']]
        old=w['candidates'];w['candidates']=[row for row in old if row.get('issuer_id')!=issuer]
        if any(row.get('security_id') in excluded for row in w['candidates']):raise ValueError('CANDIDATE_ISSUER_CONFLICT')
        w['member_denominator']=len(p['full_observed_domain'])-len(tickers)
        w['status']='ISOLATED_CONDITIONAL_DOMAIN_PREPARED'
        audit['windows'].append(dict(date=w['decision_date'],before=len(before),after=len(args['prices']),removed=sorted(removed),candidate_rows_removed=len(old)-len(w['candidates'])))
    for key in ('metadata','ohlc','source_provenance'):
        p[key]={sid:v for sid,v in p[key].items() if sid not in excluded}
    p['full_observed_domain']=[ticker for ticker in p['full_observed_domain'] if ticker not in tickers]
    p['identity_assumptions']=[row for row in p['identity_assumptions'] if row['current_security_id'] not in excluded and row['ticker'] not in tickers]
    snapshots=[];blocked_removed=0
    for line in gzip.decompress(raw).splitlines():
        row=json.loads(line);s=row['snapshot']
        s['histories']={sid:v for sid,v in s['histories'].items() if sid not in excluded}
        before=len(s['blocked_rows']);s['blocked_rows']=[v for v in s['blocked_rows'] if v.get('security_id') not in excluded]
        blocked_removed+=before-len(s['blocked_rows']);s['experiment_excluded_issuer']=issuer
        snapshots.append(row)
    read(Path(__file__).relative_to(ROOT).as_posix())
    out.mkdir()
    snapshot_bytes=gzip.compress(b'\n'.join(json.dumps(r,separators=(',',':')).encode() for r in snapshots)+b'\n',mtime=0)
    (out/'resolver_snapshots.jsonl.gz').write_bytes(snapshot_bytes)
    snap_path=(out/'resolver_snapshots.jsonl.gz').relative_to(ROOT).as_posix();read(snap_path)
    risk_manifest=dict(status='CONDITIONAL_KNOWN_TRI_GAP_EXCLUDED_NOT_PIT',snapshot_sha256=hashlib.sha256(snapshot_bytes).hexdigest(),
        source_hashes=deepcopy(pins),snapshot_count=len(snapshots),excluded_issuers=[issuer],
        ready_histories=sum(len(r['snapshot']['histories']) for r in snapshots),
        retained_blocked_rows=sum(len(r['snapshot']['blocked_rows']) for r in snapshots),
        timestamp_basis=clock['timestamp_basis'],historical_receipt_verified=False,execution_admitted=False,
        scope='Only known TRI coordinate gap excluded; remaining prices retain original conditional assumptions, not comprehensive independent verification')
    (out/'risk_history_manifest.json').write_text(json.dumps(risk_manifest,indent=2),encoding='utf-8')
    risk_path=(out/'risk_history_manifest.json').relative_to(ROOT).as_posix();read(risk_path)
    audit.update(snapshot_count=len(snapshots),removed_blocked_history_rows=blocked_removed,source_hashes=deepcopy(pins))
    (out/'exclusion_manifest.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    read((out/'exclusion_manifest.json').relative_to(ROOT).as_posix())
    p.update(status='ISOLATED_EXCLUSION_ASSEMBLY_PREFLIGHT',execution_admitted=False,source_hashes=deepcopy(pins),
        risk_history_manifest=risk_path,risk_history_snapshots=snap_path,excluded_issuers=[issuer],
        material_blockers=[],experiment_scope='CURRENT_OBSERVED_DOMAIN_MINUS_UNVERIFIABLE_TRI_NOT_PIT',
        no_silent_domain_filter=True)
    error=None;assembled=None
    try:assembled=assemble_monthly_execution_inputs_v4(p)
    except (ValueError,KeyError,TypeError) as e:error=str(e)
    for name,h in pins.items():read(name,h)
    (out/'prepared.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
    if assembled is not None:(out/'assembled.json').write_text(json.dumps(assembled,indent=2),encoding='utf-8')
    receipt=dict(status='BLOCKED_ASSEMBLER' if error else 'ASSEMBLY_PASSED_NOT_ECONOMIC_RESULT',error=error,
        windows=len(p['windows']),assembled_windows=0 if assembled is None else len(assembled['monthly_inputs']),
        observed_domain=len(p['full_observed_domain']),metadata=len(p['metadata']),excluded_issuer=issuer,
        excluded_sids=sorted(excluded),snapshot_count=len(snapshots),removed_blocked_history_rows=blocked_removed,
        source_count=len(pins),search_calls=0,book_calls=0,production_changed=False,point_in_time_certified=False,
        runtime_action_fraction_rights_guards_retained=True)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt))

if __name__=='__main__':prepare()
