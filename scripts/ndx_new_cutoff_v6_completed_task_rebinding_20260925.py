"""Reference-only rebinding of audited numerical tasks to V6 plan positions."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from backtest import ndx_issuer_combination_index_research as indexing
from scripts import ndx_new_cutoff_typed_panel_independent_readback_20260923 as codec
OUTPUT=BASE/'new_cutoff_v6_completed_task_rebinding_20260925_v1/rebinding.json'
BOUND={
 'plan':('new_cutoff_shard_prepare_20260925_v6/plan.json','c18b54c1f1aa41f7833f0b88a8fa7270b3eb0bc7c8ea0cebb0628c3645a78dd9'),
 'panel':('new_cutoff_conditional_panel_20260925_v6/panel.json','d5feacbfbe85d38fd8c66aef9dc30686316cfd1c7ccaf4eafb58cc8c5e26e269'),
 'audit':('new_cutoff_conditional_panel_20260925_v6/independent_increment_readback.json','6229a3655bb4d73c9d113d941f9dbec149da047c113be92193559cf5dbbd0717'),
 'completed_index':('new_cutoff_orly_completed_index_20260925_v1/index.json','274e194d7d00fd2cf5130476b9d82e1a9c6f4decc5a62ab6a9e3ff842b425db8')}
PINS={str(Path(indexing.__file__).resolve()):'bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',str(Path(codec.__file__).resolve()):'0b5fbb5ae38a91e7919c16b9846bf165b72c7b2aae89f281125ee23ad18fe3f9'}
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),**{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in PINS}}
FALSE=('fit_performed','task_readback_repeated','materialization_repeated','panel_audit_repeated','all_plan_tasks_completed','full_shard_completed',
 'point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','economic_comparison_performed')

def require(ok,message):
    if not ok:raise ValueError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def ref(role):return dict(path=str(BASE/BOUND[role][0]),sha256=BOUND[role][1])


def merge(sources,other):
    for path,digest in other.items():
        require(path not in sources or sources[path]==digest,'Conflicting source map');sources[path]=digest


def guard(sources):
    require(all(LOADED[p]==h for p,h in PINS.items()),'Loaded frozen code differs')
    expected=dict(sources);merge(expected,LOADED)
    for path,digest in expected.items():require(sha(Path(path).read_bytes())==digest,'Source drift: '+path)


def load_bound(reference,sources):
    path=Path(reference['path']);raw=path.read_bytes();require(sha(raw)==reference['sha256'],'Consumed source bytes differ')
    merge(sources,{str(path):reference['sha256']})
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,'Duplicate JSON key');value[key]=item
        return value
    def fail(value):raise ValueError('Nonfinite JSON')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=fail)


def digest(value):return sha(canonical(value))


def rebind(row,row_reference,panel,plan,index):
    task=row['full_task'];old=task['numerical_identity'];ctx=plan['context'];sid_order=sorted(old['selected'])
    require(digest(old)==task['numerical_task_id']==row['numerical_task_id'] and digest(task['location_identity'])==task['location_id'],'Original task digest')
    require(row['status'] in ('FITTED_FIVE_RISKS_PASSED','COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED'),'Saved completed pass required')
    universe={r['security_id']:r for r in panel['universe'].to_dict('records')}
    require(all(s in universe for s in sid_order),'Selected SID absent')
    selected={s:{key:universe[s][key] for key in ('ticker','issuer_id','risk_chain')} for s in sid_order}
    tickers=[selected[s]['ticker'] for s in sid_order];frame=panel['returns']
    payload=dict(dates=[d.date().isoformat() for d in frame.index],tickers=tickers,returns=frame[tickers].to_numpy().tolist())
    matrix=digest(payload);spec=old['weight_spec'];require(spec in ctx['weight_specs'],'Unrecognized weight spec')
    numerical=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=len(sid_order),selected=selected,
        weight_spec=spec,parameters=deepcopy(ctx['parameters']),requested_previous_target_weights=deepcopy(ctx['previous_target_weights']),
        fit_data_sha256=matrix,fitter_source_fingerprint=digest(plan['fitter_source_hashes']))
    require(canonical(numerical)==canonical(old) and matrix==row['fit_data_sha256'],'Full numerical contract changed; reuse forbidden')
    require(task['expected_fitter_previous_target_weights']==({} if ctx['previous_target_weights'] is None else ctx['previous_target_weights']),'Requested/fitter prior distinction')
    prefix=sorted(sid_order,key=lambda sid:(selected[sid]['issuer_id'],sid));k=len(prefix);rank=index.rank(k,prefix)
    shards=[s for s in plan['shards'] if s['k']==k and s['start']<=rank<s['stop']];require(len(shards)==1,'Unique new shard required')
    location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=ref('plan'),plan_id=plan['plan_id'],shard_id=shards[0]['shard_id'],
        order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=ctx['weight_specs'].index(spec),weight_spec=spec)
    return dict(numerical_task_id=task['numerical_task_id'],old_completed_row=deepcopy(row),old_completed_row_reference=row_reference,
        new_location_identity=location,new_location_id=digest(location),verified_fit_data_sha256=matrix,
        status='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND',new_wrapper_call_attempt_count=0)


def rebind_index_row(key,position,original,panel,plan,index):
    parent_reference=dict(ref('completed_index'),json_pointer=f'/{key}/{position}')
    if key=='externally_completed_rebound_rows':
        require(original['status']=='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND' and
            type(original['new_wrapper_call_attempt_count']) is int and original['new_wrapper_call_attempt_count']==0,'Prior reference-only rebinding')
        row=original['old_completed_row']
        require(original['numerical_task_id']==row['numerical_task_id'] and
            original['verified_fit_data_sha256']==row['fit_data_sha256'] and
            digest(original['new_location_identity'])==original['new_location_id'],'Prior rebinding identity')
        row_reference=dict(ref('completed_index'),json_pointer=f'/{key}/{position}/old_completed_row')
    else:row=original;row_reference=parent_reference
    for name in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):
        evidence=row[name];require(type(evidence) is dict and set(evidence)=={'path','sha256'},'Complete original completion references required')
    item=rebind(row,row_reference,panel,plan,index)
    item['original_index_row']=deepcopy(original);item['original_index_row_reference']=parent_reference
    item['prior_rebinding_row']=deepcopy(original) if key=='externally_completed_rebound_rows' else None
    return item


def assemble(documents):
    outer=documents['plan'];candidate=documents['panel'];audit=documents['audit'];saved=documents['completed_index'];plan=outer['plan']
    require(outer['schema']=='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V6' and outer['input_references']['panel']==ref('panel') and outer['input_references']['audit']==ref('audit'),'New plan lineage')
    require(audit['status']=='PASSED' and audit['candidate_reference']==ref('panel') and audit['panel_content_sha256']==candidate['panel']['panel_content_sha256'],'Saved V6 audit')
    require(saved['schema']=='NEW_CUTOFF_ORLY_COMPLETED_TASK_INDEX_V1' and type(saved['batch_saved_attempt_and_readback_count']) is int and saved['batch_saved_attempt_and_readback_count']==402,'Exact saved402 index')
    require(all(d[k] is False for d in (outer,candidate,audit,saved) for k in ('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified','full_transitive_source_closure_reverified')),'Authority upgrade')
    panel=codec.decode_frames(candidate['panel']);frame=panel['returns'];ctx=plan['context']
    require(len(panel['observed_provenance_and_missing'])==101 and outer['complete_observed_provenance_and_missing']==panel['observed_provenance_and_missing'],'Full101 gap binding')
    for key,pointer in [('preserved_evidence_sidecar_reference','original_evidence_and_projection'),('preserved_incremental_evidence_sidecar_reference','incremental_evidence_and_projection'),
        ('preserved_v3_incremental_evidence_sidecar_reference','v3_incremental_evidence_and_projection'),('preserved_v4_incremental_evidence_sidecar_reference','v4_incremental_evidence_and_projection'),('preserved_v5_incremental_evidence_sidecar_reference','v5_incremental_evidence_and_projection'),('preserved_v6_incremental_evidence_sidecar_reference','v6_incremental_evidence_and_projection')]:
        require(outer[key]==dict(ref('panel'),json_pointer='/'+pointer) and pointer in candidate,'Six full sidecar references')
    require(panel['schema']=='LATEST_CONDITIONAL_TYPED_PANEL_V6' and type(panel['conditional_security_count']) is int and panel['conditional_security_count']==24 and
        type(panel['conditional_issuer_count']) is int and panel['conditional_issuer_count']==23 and len(frame)==126 and all(str(dtype)=='float64' for dtype in frame.dtypes),'Full V6 typed input')
    require(frame.index.is_unique and frame.index.is_monotonic_increasing and all(d.tzinfo is None and d==d.normalize() for d in frame.index) and
        frame.index[-1].date().isoformat()==ctx['decision_cutoff']=='2026-09-21','Full126 date contract')
    require(all(type(v) is not bool and math.isfinite(float(v)) and float(v)>-1 for v in frame.to_numpy().flat),'Full finite returns')
    groups={}
    for r in panel['universe'].to_dict('records'):groups.setdefault(r['issuer_id'],[]).append(r['security_id'])
    require([dict(issuer_id=i,security_ids=sorted(s)) for i,s in sorted(groups.items())]==plan['canonical_groups'],'Entire universe grouping differs')
    index=indexing.IssuerCombinationIndex(list(groups.items()))
    require(index.group_fingerprint==ctx['group_fingerprint'] and ctx['order_version']==indexing.ORDER_VERSION and len(plan['fitter_source_hashes'])==25 and
        digest(plan['fitter_source_hashes'])==ctx['fitter_source_fingerprint'] and ctx['previous_target_weights'] is None,'Group/source/prior contract')
    rows=[]
    for key,count in [('new_tasks',102),('externally_completed_rebound_rows',300)]:
        require(type(saved[key]) is list and len(saved[key])==count,'Saved task row denominator')
        for position,original in enumerate(saved[key]):
            rows.append(rebind_index_row(key,position,original,panel,plan,index))
    require(len({r['numerical_task_id'] for r in rows})==len({r['new_location_id'] for r in rows})==402,'Unique402 identity/location')
    combinations={tuple(sorted(r['old_completed_row']['full_task']['numerical_identity']['selected'])) for r in rows}
    require(len(combinations)==134,'Exactly134 old combinations')
    for selection in combinations:
        require({r['new_location_identity']['weight_spec'] for r in rows if tuple(sorted(r['old_completed_row']['full_task']['numerical_identity']['selected']))==selection}==set(ctx['weight_specs']) and len(ctx['weight_specs'])==3,'No specification omitted or aliased')
    require(type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==37740237,'New full task denominator')
    return dict(schema='NEW_CUTOFF_V6_COMPLETED_TASK_REBINDING_V1',input_references={k:ref(k) for k in BOUND},rows=rows,
        externally_rebound_task_count=402,externally_rebound_combination_count=134,full_plan_task_denominator=37740237,remaining_uncompleted_task_count=37739835,
        complete_observed_provenance_and_missing=deepcopy(outer['complete_observed_provenance_and_missing']),
        preserved_sidecar_references=[deepcopy(outer[key]) for key in ('preserved_evidence_sidecar_reference','preserved_incremental_evidence_sidecar_reference','preserved_v3_incremental_evidence_sidecar_reference','preserved_v4_incremental_evidence_sidecar_reference','preserved_v5_incremental_evidence_sidecar_reference','preserved_v6_incremental_evidence_sidecar_reference')],
        new_wrapper_call_attempt_count=0,new_fit_count=0,old_full_tasks_and_completion_references_preserved=True,
        rank_calculation_performed=True,combination_enumeration_performed=False,**dict.fromkeys(FALSE,False))


def build():
    sources=dict(LOADED);merge(sources,codec.LOADED);guard(sources)
    documents={role:load_bound(ref(role),sources) for role in BOUND}
    merge(sources,documents['plan']['plan']['fitter_source_hashes']);guard(sources)
    value=assemble(documents);value['source_hashes']=sources;guard(sources);return value


def publish():
    require(not OUTPUT.parent.exists(),'Fresh immutable rebinding namespace required')
    value=build();guard(value['source_hashes']);blob=encode(value);OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'rebinding.json'},'Output drift')
    return dict(path=str(OUTPUT),sha256=sha(blob))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))


