"""Independent record-by-record audit of a limited paired DELTA overlay; no fit."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_exact_price_cache_drift_research as drift

PLAN=ROOT/'data/cache/research/delta_three_cell_paired_trace_20260912_v2/plan.json'
PLAN_SHA='fb2e514516123efe67dffb92821410ce2eb52d3e757494c4dfaf517c7ea9b330'
INDEX=ROOT/'data/cache/research/delta_paired_snapshot_20260912_v1/tasks/index_a1a78475e53cb9b2339f839f72f3310ce4c4c1c871406ef384f183d0c599e1b4.json'
INDEX_SHA='6c27c7be1a31d94bbf6052d5c24f58b185abfff04ab0275fc485214dcd66da8c'
AUDIT=INDEX.parent.parent/'limited_drift_independent_audit_20260919.json'
AUDIT_SHA='34e395c008db8b91b8cdc5075af864ba80e216780d523362bc1e402dc292633b'
LOADED={str(p):drift.file_sha(p) for p in (Path(__file__).resolve(),drift.SOURCE)}
PAIRED={'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
        'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent'}


def verify_record_changes(parent,overlay,replacements):
    old=parent['records'];new=overlay['records']
    if len(old)!=len(new) or len({r['task']['job_id'] for r in old})!=len(old):
        raise ValueError('Complete unique original record denominator required')
    seen=set()
    for before,after in zip(old,new):
        job=before['task']['job_id']
        if job not in replacements:
            if before!=after:raise ValueError('Unrelated record changed')
            continue
        source=replacements[job];result=source['result']
        if before['origin']!='DELTA' or before['status']!='PENDING_NUMERICAL_DELTA' or before['result'] is not None:
            raise ValueError('Original paired record was not pending DELTA')
        if before['task']!=source['original']['task'] or after['task']!=before['task']:
            raise ValueError('Replacement task identity differs')
        if {k:v for k,v in result['original_result'].items() if k not in PAIRED}!={k:v for k,v in result['result'].items() if k not in PAIRED}:
            raise ValueError('Fields outside four paired metrics changed')
        expected=deepcopy(before)
        expected.update(result=result['result'],status='AVAILABLE',overlay_mode='DELTA_PAIRED_COMPLETE_SUBQUEUE',
                        original_historical_provenance_verified=False)
        lineage=dict(checkpoint_path=source['_path'],checkpoint_sha256=source['_sha'],
            complete_index_path=str(INDEX),complete_index_sha256=INDEX_SHA,
            independent_audit_path=str(AUDIT),independent_audit_sha256=AUDIT_SHA,
            historical_loader_provenance_gaps=result['historical_loader_provenance_gaps'])
        if after['lineage'].get('completed_delta_paired')!=lineage:
            raise ValueError('New paired record lineage differs')
        expected['lineage']=dict(before['lineage'],completed_delta_paired=lineage)
        if after!=expected:raise ValueError('Unexpected record field mutation')
        seen.add(job)
    if seen!=set(replacements):raise ValueError('Incomplete paired date denominator')
    available=sum(r['status']=='AVAILABLE' for r in new)
    pending=sum(r['status']=='PENDING_NUMERICAL_DELTA' for r in new)
    if (available!=overlay['available_count'] or pending!=overlay['pending_count'] or available+pending!=len(new) or
        available!=parent['available_count']+len(seen) or pending!=parent['pending_count']-len(seen)):
        raise ValueError('Original/available/pending counts differ')
    if any(r['result'] is not None for r in new if r['status']=='PENDING_NUMERICAL_DELTA'):
        raise ValueError('Pending record contains an economic result')
    return dict(record_count=len(new),paired_replaced=len(seen),unchanged_count=len(new)-len(seen),available=available,pending=pending)


def audit(path,sha):
    sources=dict(LOADED)
    def read(p,h):
        p=str(Path(p).resolve());raw=Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('External artifact SHA differs')
        if p in sources and sources[p]!=h:raise ValueError('Conflicting source identity')
        sources[p]=h
        return json.loads(raw)
    overlay=read(path,sha)
    if overlay['schema']!='ndx_corrected_delta_paired_overlay_limited_drift_v2' or any(overlay[k] is not False for k in ('historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','selection_performed')):
        raise ValueError('Explicit nonpromoted limited overlay required')
    for p,h in overlay['historical_expected_source_hashes'].items():
        if p in sources and sources[p]!=h:raise ValueError('Conflicting overlay source')
        sources[p]=h
    contract=drift.load_contract()
    partition=drift.verify_expected_sources(overlay['historical_expected_source_hashes'],contract)
    if partition['verified_source_hashes']!=overlay['verified_source_hashes'] or partition['historical_gap_observations']!=overlay['historical_price_cache_gap_observations']:
        raise ValueError('Overlay source partition differs')
    parent=read(overlay['parent_overlay_path'],overlay['parent_overlay_sha256']);plan=read(PLAN,PLAN_SHA);index=read(INDEX,INDEX_SHA)
    read(AUDIT,AUDIT_SHA)
    for document in (parent,overlay):
        record_sha=hashlib.sha256(json.dumps(document['records'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        if record_sha!=document['records_sha256']:raise ValueError('Record digest differs')
    date=overlay['coordinate']['selection_date']
    if parent['coordinate']!=overlay['coordinate']:raise ValueError('Parent coordinate differs')
    planned={r['new_job_id']:r for d in plan['dates'] for r in d['tasks'] if r['task']['selection_date']==date}
    replacements={}
    for entry in index['completed']:
        # Task files are small enough to read sequentially, never cache all contexts.
        document=read(entry['path'],entry['sha256'])
        if document['new_job_id'] in planned:
            row=planned[document['new_job_id']]
            if document['original']!=row:raise ValueError('Planned source task differs')
            document.update(_path=entry['path'],_sha=entry['sha256'])
            replacements[row['task']['job_id']]=document
    if len(replacements)!=len(planned):raise ValueError('Completed paired tasks missing')
    counts=verify_record_changes(parent,overlay,replacements)
    check=drift.verify_expected_sources(sources,contract)
    return dict(schema='ndx_paired_limited_overlay_independent_diff_audit_20260919_v1',date=date,**counts,
        verified_source_hashes=check['verified_source_hashes'],historical_expected_source_hashes=sources,
        historical_price_cache_gap_observations=check['historical_gap_observations'],
        complete_record_diff_verified=True,no_fit_or_evaluator_called=True,
        historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('overlay','sha256','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();report=audit(args.overlay,args.sha256)
    with Path(args.output).open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    drift.verify_expected_sources(report['historical_expected_source_hashes'],drift.load_contract())
    print(json.dumps(dict(path=str(Path(args.output).resolve()),sha256=drift.file_sha(args.output),count=report['record_count'])))
