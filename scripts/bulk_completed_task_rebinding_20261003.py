"""Reference-only rebinding of 504 saved tasks; never refit or re-audit results."""
import argparse
from copy import deepcopy
from functools import lru_cache
from datetime import date
import hashlib,json,math,os
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'bulk_completed_task_rebinding_20261003_v1/rebinding.json'
BOUND={
 'plan':('bulk_all_k_plan_20261003_v1/plan.json','77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'),
 'plan_publication':('bulk_all_k_plan_20261003_v1/publication.json','c5988351adb898c00626c2473b9e8e363fca3975651522263b07c80bed3b6691'),
 'panel':('bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'panel_publication':('bulk_conditional_panel_20261003_v1/publication.json','895b1d0f71fb3f4b1175845c3390f3d286c672519fa4aa2c0a13bb930f6a2a9d'),
 'old_plan':('new_cutoff_shard_prepare_20260925_v6/plan.json','c18b54c1f1aa41f7833f0b88a8fa7270b3eb0bc7c8ea0cebb0628c3645a78dd9'),
 'completed_index':('new_cutoff_ctas_completed_index_20260925_v1/index.json','5987dd7e7e14567dc5fc264d1886c5f9ba9c6ef1d45926fc45317676f19a799d')}
PINS={}
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
FALSE=('fit_performed','task_readback_repeated','materialization_repeated','panel_audit_repeated','all_plan_tasks_completed','full_shard_completed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','full_transitive_source_closure_reverified','economic_comparison_performed')
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


def prefix_rank(groups,selected):
    """Issuer-prefix lexicographic rank by suffix polynomial counts, no enumeration."""
    groups=[(g['issuer_id'],tuple(g['security_ids'])) for g in groups]
    require(groups==sorted(groups) and len({issuer for issuer,_ in groups})==len(groups) and all(s==tuple(sorted(set(s))) and s for _,s in groups),'Canonical unique issuer groups')
    positions={s:(i,j) for i,(_,ss) in enumerate(groups) for j,s in enumerate(ss)}
    require(len(positions)==sum(len(ss) for _,ss in groups),'Unique SID groups')
    require(len(selected)==len(set(selected)) and all(s in positions for s in selected),'Unique known selected SID')
    chosen=sorted(selected,key=lambda s:positions[s]);require(len({positions[s][0] for s in chosen})==len(chosen),'Duplicate issuer selection')
    @lru_cache(None)
    def count(start,k):
        if k==0:return 1
        if len(groups)-start<k:return 0
        return count(start+1,k)+len(groups[start][1])*count(start+1,k-1)
    rank=0;start=0;k=len(chosen)
    for s in chosen:
        i,j=positions[s]
        for earlier in range(start,i):rank+=len(groups[earlier][1])*count(earlier+1,k-1)
        rank+=j*count(i+1,k-1);start=i+1;k-=1
    return rank

def matrix_and_selected(panel,old):
    universe=panel['universe'];columns=universe['columns'];rows=universe['data']
    by={r[columns.index('security_id')]:dict(zip(columns,r)) for r in rows}
    require(len(by)==len(rows),'Unique panel SID')
    order=sorted(old['selected']);require(all(s in by for s in order),'Missing saved SID')
    selected={s:{k:by[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in order};tickers=[selected[s]['ticker'] for s in order]
    frame=panel['returns'];require(len(frame['index'])==len(frame['data'])==126 and frame['index_kind']=='DatetimeIndex' and all(t in frame['columns'] for t in tickers),'126 return matrix required')
    require(frame['index']==sorted(set(frame['index'])) and all(x==x[:10]+'T00:00:00' and date.fromisoformat(x[:10]).isoformat()==x[:10] for x in frame['index']) and frame['index'][-1][:10]==old['cutoff'],'Canonical dates/cutoff')
    indexes=[frame['columns'].index(t) for t in tickers]
    require(all(frame['dtypes'][i]=='float64' for i in indexes),'Saved float matrix dtype')
    values=[[r[i] for i in indexes] for r in frame['data']]
    require(all(type(v) is float and math.isfinite(v) and v>-1 for r in values for v in r),'Finite saved returns')
    return selected,digest(dict(dates=[x[:10] for x in frame['index']],tickers=tickers,returns=values))

def new_location(plan,old,plan_reference):
    ctx=plan['context'];k=old['holding_count'];rank=prefix_rank(plan['canonical_groups'],list(old['selected']))
    cards=plan['cardinalities'];card=next(c for c in cards if c['k']==k)
    require(type(card['combination_count']) is int and 0<=rank<card['combination_count'],'Rank bounds')
    size=ctx['shard_size'];require(type(size) is int and size==1000,'Frozen shard engineering size')
    local=rank//size;start=local*size;stop=min(start+size,card['combination_count'])
    require(type(card['planned_shard_count']) is int and card['planned_shard_count']>local,'Retained lazy shard required')
    shard_identity=dict(ctx,k=k,start=start,stop=stop);spec=old['weight_spec'];si=ctx['weight_specs'].index(spec)
    location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=plan_reference,plan_id=plan['plan_id'],shard_id=digest(shard_identity),order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=si,weight_spec=spec)
    offset=sum(c['planned_combination_count'] for c in cards if c['k']<k)
    require(type(card['first_global_planned_combination_ordinal']) is int and card['first_global_planned_combination_ordinal']==offset and type(card['first_global_shard_ordinal']) is int,'Exact global offsets')
    return location,dict(local_shard_ordinal=local,global_shard_ordinal=card['first_global_shard_ordinal']+local,start=start,stop=stop,global_task_ordinal=(offset+rank)*len(ctx['weight_specs'])+si)

def rebind_one(original,key,position,panel,plan,plan_reference,index_reference):
    nested=key=='externally_completed_rebound_rows';row=original['old_completed_row'] if nested else original
    if nested:
        require(original['status']=='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND' and type(original['new_wrapper_call_attempt_count']) is int and original['new_wrapper_call_attempt_count']==0,'Prior rebind status')
        require(digest(original['new_location_identity'])==original['new_location_id'] and original['numerical_task_id']==row['numerical_task_id'] and original['verified_fit_data_sha256']==row['fit_data_sha256'],'Prior wrapper identity')
    task=row['full_task'];old=task['numerical_identity'];ctx=plan['context']
    require(digest(old)==row['numerical_task_id']==task['numerical_task_id'] and digest(task['location_identity'])==task['location_id'],'Saved full task identity')
    require(row['status'] in ('FITTED_FIVE_RISKS_PASSED','COMPLETED_EXTERNALLY_AUDITED_ORIGINAL_FIVE_RISKS_PASSED'),'Completed audited pass required')
    for field in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):
        require(set(row[field])=={'path','sha256'} and len(row[field]['sha256'])==64,'Original completion evidence references')
    selected,matrix=matrix_and_selected(panel,old)
    expected=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=len(selected),selected=selected,weight_spec=old['weight_spec'],parameters=ctx['parameters'],requested_previous_target_weights=ctx['previous_target_weights'],fit_data_sha256=matrix,fitter_source_fingerprint=digest(plan['fitter_source_hashes']))
    require(canonical(old)==canonical(expected) and matrix==row['fit_data_sha256'],'Numerical identity changed; no reuse')
    require(task['expected_fitter_previous_target_weights']==({} if ctx['previous_target_weights'] is None else ctx['previous_target_weights']),'None requested prior distinct from fitter empty')
    location,position_info=new_location(plan,old,plan_reference)
    origin=dict(index_reference,json_pointer=f'/{key}/{position}')
    return dict(numerical_task_id=row['numerical_task_id'],old_completed_row=deepcopy(row),old_completed_row_reference=dict(origin,json_pointer=origin['json_pointer']+'/old_completed_row') if nested else origin,original_index_row=deepcopy(original),original_index_row_reference=origin,prior_rebinding_row=deepcopy(original) if nested else None,new_location_identity=location,new_location_id=digest(location),new_lazy_position=position_info,verified_fit_data_sha256=matrix,status='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND',new_wrapper_call_attempt_count=0)
EXTRA_PINS={
 str(ROOT/'DYNAMIC_BULK_CONDITIONAL_PANEL_INDEPENDENT_READBACK_20261003.md'):'8a432b70dfc3393850242873b700eb54097bec9981c8f488cc88bd578295c879',
 str(ROOT/'scripts/ndx_bulk_conditional_panel_independent_review_20261003.py'):'5a3d35ba39e6a719dfafaa3e4e348f065c5cd297c403a08e087c78f02c5c1b0b'}
AUDIT_REFERENCE={'path':next(iter(EXTRA_PINS)),'sha256':next(iter(EXTRA_PINS.values()))}

def assemble(documents):
    outer=documents['plan'];candidate=documents['panel'];saved=documents['completed_index'];oldplan=documents['old_plan']['plan'];plan=outer['plan'];ctx=plan['context'];panel=candidate['panel']
    receipt=documents['plan_publication']
    require(receipt['schema']=='BULK_ALL_K_LAZY_PLAN_PUBLICATION_V1' and receipt['status']=='PLANNED_NOT_ENUMERATED' and receipt['plan_reference']==ref('plan') and receipt['source_hashes']==outer['source_hashes'],'New plan publication binding')
    require(outer['schema']=='BULK_ALL_K_LAZY_PLAN_V1' and plan['schema']=='ISSUER_ALL_K_LAZY_INTERVAL_PLAN_V1','New lazy schema')
    require(digest(ctx)==plan['plan_id'] and digest({k:v for k,v in plan.items() if k!='content_sha256'})==plan['content_sha256'],'Lazy plan content identity')
    require(type(plan['completed_canonical_task_count']) is int and plan['completed_canonical_task_count']==0 and type(outer['old_completed_tasks_deducted']) is int and outer['old_completed_tasks_deducted']==0,'Old completion not already deducted')
    require(outer['complete_observed_provenance_and_missing']==panel['observed_provenance_and_missing'] and len(panel['observed_provenance_and_missing'])==101,'All101 provenance')
    require(set(outer['preserved_evidence_sidecar_references'])=={'original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection'},'All seven evidence layers')
    for key,value in outer['preserved_evidence_sidecar_references'].items():require(key in candidate and value==dict(ref('panel'),json_pointer='/'+key),'Evidence sidecar reference')
    require(ctx['panel_reference']==ref('panel') and ctx['panel_audit_reference']==AUDIT_REFERENCE,'Panel and saved independent report references')
    require(documents['panel_publication']['panel_reference']==ref('panel') and documents['panel_publication']['source_hashes']==candidate['source_hashes'],'Panel publication')
    require(saved['schema']=='NEW_CUTOFF_CTAS_COMPLETED_TASK_INDEX_V1' and type(saved['batch_saved_attempt_and_readback_count']) is int and saved['batch_saved_attempt_and_readback_count']==504,'Saved504 denominator')
    require(all(d[k] is False for d in (outer,candidate,saved) for k in ('promotion_allowed','execution_authorized','legal_training_input_admitted','point_in_time_verified')),'Authority upgrade')
    require(panel['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1' and panel['conditional_security_count']==77 and panel['conditional_issuer_count']==76,'77/76 panel')
    require(all(v['exact'] is True and v['original_sha256']==v['projected_sha256'] for v in candidate['original24_frame_exact_proof'].values()) and len(candidate['original24_frame_exact_proof'])==5,'Sealed old24 proof')
    require(canonical(ctx['parameters'])==canonical(oldplan['context']['parameters']) and len(ctx['parameters'])==8 and ctx['weight_specs']==oldplan['context']['weight_specs'] and len(ctx['weight_specs'])==3 and ctx['previous_target_weights'] is None,'Original8params/prior/3spec order')
    require(plan['fitter_source_hashes']==oldplan['fitter_source_hashes'] and len(plan['fitter_source_hashes'])==25 and digest(plan['fitter_source_hashes'])==ctx['fitter_source_fingerprint'],'Original25 numeric sources')
    u=panel['universe'];by=[dict(zip(u['columns'],r)) for r in u['data']];groups={}
    for r in by:groups.setdefault(r['issuer_id'],[]).append(r['security_id'])
    canonical_groups=[dict(issuer_id=i,security_ids=sorted(ss)) for i,ss in sorted(groups.items())]
    require(canonical_groups==plan['canonical_groups'] and len(by)==len({r['security_id'] for r in by})==77 and len(groups)==76,'Entire canonical universe')
    require(digest(dict(order_version=ctx['order_version'],groups=[(g['issuer_id'],g['security_ids']) for g in canonical_groups]))==ctx['group_fingerprint'],'Group digest')
    cards=plan['cardinalities'];require([c['k'] for c in cards]==list(range(1,77)),'Entire k1..76 denominator')
    counts=[1]+[0]*76
    for group in canonical_groups:
        for k in range(76,0,-1):counts[k]+=len(group['security_ids'])*counts[k-1]
    cumulative=shards=0
    for card in cards:
        k=card['k'];require(all(type(card[n]) is int for n in ('k','combination_count','planned_combination_count','planned_canonical_task_count','planned_shard_count','first_global_shard_ordinal','first_global_planned_combination_ordinal')),'Exact integer cardinality fields')
        n=card['planned_combination_count'];require(card['combination_count']==counts[k] and n in (0,counts[k]) and card['planned_canonical_task_count']==3*n and card['planned_shard_count']==(n+999)//1000 and card['first_global_shard_ordinal']==shards and card['first_global_planned_combination_ordinal']==cumulative,'Complete lazy integer intervals')
        cumulative+=n;shards+=card['planned_shard_count']
    require(type(plan['planned_canonical_task_count']) is int and plan['planned_canonical_task_count']==3*cumulative,'Full untruncated task denominator')
    old_sids={s for g in oldplan['canonical_groups'] for s in g['security_ids']}
    require(len(old_sids)==24,'Original universe24')
    rows=[]
    for key,count in [('new_tasks',102),('externally_completed_rebound_rows',402)]:
        require(type(saved[key]) is list and len(saved[key])==count,'Full504 index partitions')
        for i,original in enumerate(saved[key]):
            item=rebind_one(original,key,i,panel,plan,ref('plan'),ref('completed_index'))
            require(set(item['old_completed_row']['full_task']['numerical_identity']['selected'])<=old_sids,'New53 cannot masquerade as old task')
            rows.append(item)
    require(len({r['numerical_task_id'] for r in rows})==len({r['new_location_id'] for r in rows})==504,'504 unique identities and new locations')
    combos={}
    for r in rows:
        key=tuple(sorted(r['old_completed_row']['full_task']['numerical_identity']['selected']));combos.setdefault(key,[]).append(r['new_location_identity']['spec_index'])
    require(len(combos)==168 and all(sorted(v)==[0,1,2] for v in combos.values()),'168 combinations each three ordered specifications')
    total=plan['planned_canonical_task_count'];require(type(total) is int and total>=504,'Exact full denominator')
    return dict(schema='BULK_COMPLETED_TASK_REBINDING_V1',rows=rows,input_references={k:ref(k) for k in BOUND},panel_audit_reference=AUDIT_REFERENCE,externally_rebound_task_count=504,externally_rebound_combination_count=168,full_plan_task_denominator=total,remaining_uncompleted_task_count=total-504,new_wrapper_call_attempt_count=0,new_fit_count=0,old_full_tasks_and_completion_references_preserved=True,numerical_contracts_unchanged=True,combination_enumeration_performed=False,complete_observed_provenance_and_missing=deepcopy(panel['observed_provenance_and_missing']),preserved_panel_evidence_reference=ref('panel'),**dict.fromkeys(FALSE,False))

def read_inputs():
    require(all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'New plan pin pending')
    sources=dict(LOADED);merge(sources,EXTRA_PINS);guard(sources)
    require({p.name for p in Path(ref('plan')['path']).parent.iterdir()}=={'started.json','plan.json','publication.json'},'Failed/incomplete new plan namespace')
    documents={role:load_bound(ref(role),sources) for role in BOUND}
    merge(sources,documents['plan']['plan']['fitter_source_hashes']);guard(sources)
    return documents,sources

def write_new(path,value):
    raw=encode(value)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output changed');return {'path':str(path),'sha256':sha(raw)}

def publish():
    require(not OUTPUT.parent.exists(),'Immutable namespace; no retry')
    docs,sources=read_inputs();OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT.parent/'started.json',dict(source_hashes=sources,retry_allowed=False))
        value=assemble(docs);value['source_hashes']=sources;guard(sources);result=write_new(OUTPUT,value);guard(sources)
        receipt=write_new(OUTPUT.parent/'publication.json',dict(schema='BULK_COMPLETED_TASK_REBINDING_PUBLICATION_V1',status='PUBLISHED_REFERENCE_ONLY',rebinding_reference=result,source_hashes=sources,**dict.fromkeys(FALSE,False)))
        guard(sources);require(sha(OUTPUT.read_bytes())==result['sha256'] and sha(Path(receipt['path']).read_bytes())==receipt['sha256'] and {p.name for p in OUTPUT.parent.iterdir()}=={'started.json','rebinding.json','publication.json'},'Final readback')
        return dict(rebinding_reference=result,publication_reference=receipt)
    except Exception as error:
        write_new(OUTPUT.parent/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error)));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');require(parser.parse_args().publish,'Explicit --publish required');print(json.dumps(publish()))
