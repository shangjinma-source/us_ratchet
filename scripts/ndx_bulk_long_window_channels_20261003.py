"""New 253-date raw reconstruction; immutable attempt and no old producer calls."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_bulk_long_window_channels_research.py';CORE_SHA='419c8c36b8720609211910347f4c088a9a1a6e3bd874cd3a72f62d8a9fecbd40'
OUTPUT=ROOT/'data/cache/research/bulk_long_window_channels_20261003_v1'
NY_SOURCE=Path(r'D:\python\Lib\site-packages\tzdata\zoneinfo\America\New_York')
NY_SHA='d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9'
BOUND={
 'prior_fit_batch':('data/cache/research/bulk_budgeted_batch_20261003_v1/result.json','0bbc85b1768cb45e846fe5706bdd873de77be1faa9023497ecbffeaf09074d2d'),
 'history':('data/cache/research/bulk_history_requirements_20261003_v1/requirements.json','f3a317fd00800fe025003479358a6798cd893d4305511bcb1c39eb73ae94e2f5'),
 'history_publication':('data/cache/research/bulk_history_requirements_20261003_v1/publication.json','171f4218d2ec3997b53d21d9e0e4c6081425ae963f79e7b7d0b3c5fa2ea5d13d'),
 'history_audit':('DYNAMIC_BULK_HISTORY_REQUIREMENTS_INDEPENDENT_READBACK_20261003.json','22928d8aaa756f11bd7071f7ef4544cfaeca2e17206b46f7dc273a4c6f0ded9d'),
 'history_audit_report':('DYNAMIC_BULK_HISTORY_REQUIREMENTS_INDEPENDENT_READBACK_20261003.md','fcd9f8f97bd15dd255e7fdb497af034cee69e86564345f85078205618ab60217'),
 'history_audit_reader':('scripts/ndx_bulk_history_requirements_independent_review_20261003.py','64652e1966f2f97fbfd3cd02d23018875b36a83fb06cf6657fddb4ff8154ddbd'),
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'bridge':('data/cache/research/new_cutoff_event_policy_20260923_v1/bridge.json','d2f7824197cb30c119eb8297d6dda784e33ff2589010e36f63d4e9850267d7bd')}
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
CONTRACT=dict(cutoff='2026-09-21',fit_return_count=126,evaluation_return_count=126,receipt_exclusion_date='2026-09-23')
FLAGS=('http_performed','fit_performed','account_simulation_performed','old_127_producer_called','old_127_audit_repeated','old_outputs_spliced','identity_interval_extended','historical_identity_verified','historical_risk_verified','complete_corporate_actions_verified','volume_unit_certified','provider_binding_verified','point_in_time_verified','legal_training_input_admitted','execution_authorized','promotion_allowed','future_oos_evaluation_performed','formal_benchmark_evaluation_performed','full_transitive_source_closure_reverified')
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def loads(blob):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'Duplicate JSON key');result[k]=v
        return result
    def invalid(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)
def merge(sources,path,h):require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h

def prepare(docs,refs):
    history=docs['history'];hr=history['requirements'];pub=docs['history_publication'];audit=docs['history_audit'];pdoc=docs['panel'];panel=pdoc['panel'];bridge=docs['bridge']
    require(history['schema']=='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1' and hr['schema']=='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1','Saved historical requirements')
    require(pub['schema']=='BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1' and pub['status']=='PUBLISHED_REQUIREMENTS_ONLY' and pub['requirements_reference']==refs['history'],'History publication');exact(pub['source_hashes'],history['source_hashes'],'History source map')
    require(audit['status']=='PASS' and audit['requirements_sha256']==refs['history']['sha256'] and audit['publication_sha256']==refs['history_publication']['sha256'] and audit['reader_sha256']==refs['history_audit_reader']['sha256'],'Independent history readback source')
    require(pdoc['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and panel['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','Parent77 panel')
    for value in (history,pdoc,panel):require(all(value[k] is False for k in ('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted')),'Conditional-only inputs')
    scenario=hr['scenarios'][0];require(scenario['price_window_length']==253 and scenario['constructed_window_count']==1 and scenario['security_denominator']==77,'Entire253x77 required')
    dates=scenario['required_reference_price_dates'];require(len(dates)==253 and dates==sorted(set(dates)) and dates[0]=='2025-09-18' and dates[-1]=='2026-09-21' and dates[126]=='2026-03-20','Explicit historical calendar and freeze')
    prior_dates=panel['returns']['index'];exact(prior_dates,[d+'T00:00:00' for d in dates[127:]],'New evaluation dates equal previously used fitting dates')
    prior_batch=docs['prior_fit_batch'];require(prior_batch['status']=='BUDGETED_QUEUE_FINISHED' and type(prior_batch['new_readback_count']) is int and prior_batch['new_readback_count']==1630 and len(prior_batch['initial_completed_rows'])==2,'Saved prior fitting batch context')
    fields=panel['universe']['columns'];universe=[dict(zip(fields,row)) for row in panel['universe']['data']]
    exact(hr['universe'],universe,'Original77 full metadata');require(len(universe)==77 and len({r['ticker'] for r in universe})==77 and len({r['security_id'] for r in universe})==77 and len({r['issuer_id'] for r in universe})==76,'77SID/76issuer')
    exact(hr['observed_provenance_and_missing'],panel['observed_provenance_and_missing'],'All101 provenance');require(len(panel['observed_provenance_and_missing'])==101,'Original101 denominator')
    for name in SIDECARS:exact(history['projection_evidence']['complete_panel_sidecars'][name],pdoc[name],'Complete original sidecars')
    exact(hr['original_identity_assumed_window'],dict(first='2026-03-20',last='2026-09-21'),'No early identity extension')
    require(bridge['candidate_cutoff']==CONTRACT['cutoff'] and len(bridge['rows'])==101,'Full bridge source');by={r['ticker']:(i,r) for i,r in enumerate(bridge['rows'])};require(len(by)==101,'Unique bridge rows')
    observations=hr['ticker_observations_preserved'];require(set(observations)=={r['ticker'] for r in universe},'Full77 observation metadata')
    requests=[]
    for coordinate in universe:
        ticker=coordinate['ticker'];item=observations[ticker];i,row=by[ticker]
        exact(item['complete_bridge_row'],row,'Original event policy not altered');exact(item['bridge_reference'],dict(refs['bridge'],json_pointer=f'/rows/{i}'),'Event reference')
        exact(item['raw_reference'],row['new_raw_reference'],'Original raw source');exact(item['receipt_reference'],row['new_receipt_reference'],'Receipt source');require(item['decoded_sha256']==row['new_decoded_sha256'],'Saved decoded hash')
        requests.append(dict(coordinate=deepcopy(coordinate),raw_reference=deepcopy(item['raw_reference']),receipt_reference=deepcopy(item['receipt_reference']),bridge_row=deepcopy(row),calendar253=deepcopy(dates),window_contract=deepcopy(CONTRACT),history_observation_reference=dict(refs['history'],json_pointer='/requirements/ticker_observations_preserved/'+ticker),original_identity_assumed_window=deepcopy(item['identity_assumed_window'])))
    return requests

def validate_channel(value,request,tzif_bytes):
    require(value['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1' and value['ticker']==request['coordinate']['ticker'] and value['status'] in ('CONDITIONAL_NUMERIC_RESULT','BLOCKED_PRICE_INPUT'),'Explicit channel state')
    for key in ('source_bytes_authenticated','provider_price_unit_verified','identity_interval_verified','point_in_time_verified','exchange_calendar_verified','complete_corporate_actions_verified','dividend_cash_flows_included','volume_unit_verified','liquidity_qualified','legal_training_input_admitted','benchmark_qualified','promotion_allowed','execution_authorized','fit_performed','old_outputs_spliced','missing_values_filled','historical_timely_availability_verified'):require(value[key] is False,'No channel authority upgrade')
    for key,expected in [('calendar',request['calendar253']),('raw_reference',request['raw_reference']),('receipt_reference',request['receipt_reference']),('bridge_row_preserved',request['bridge_row']),('window_contract',CONTRACT)]:exact(value[key],expected,'Channel source/window binding')
    require(value['tzif_sha256']==sha(tzif_bytes) and value['decoded_sha256']==request['bridge_row']['new_decoded_sha256'],'Timezone/decoded byte identity')
    if value['status']=='BLOCKED_PRICE_INPUT':require(bool(value['reasons']) and all(value[k] is None for k in ('quote_rows','return_rows','training_returns','evaluation_returns')),'Blocked channel retains no invented numbers')
    else:
        require(value['reasons']==[] and len(value['quote_rows'])==253 and len(value['return_rows'])==252 and len(value['training_returns'])==len(value['evaluation_returns'])==126,'Complete numerical dimensions')
        exact([r['session'] for r in value['quote_rows']],request['calendar253'],'All nominal price dates')
        exact(value['return_rows'][:126],value['training_returns'],'Train partition');exact(value['return_rows'][126:],value['evaluation_returns'],'Evaluation partition')
        for i,row in enumerate(value['return_rows']):require(row['previous_session']==request['calendar253'][i] and row['session']==request['calendar253'][i+1] and row['dividends_included'] is False,'Return predecessor, no included dividends')
        for field in ('quote_rows','training_returns','evaluation_returns'):require(value[field+'_sha256']==sha(encoded(value[field])),'Core numeric payload checksum')

def assemble(requests,raw_inputs,tzif_bytes,core,docs,refs):
    require(len(requests)==77 and len({r['coordinate']['ticker'] for r in requests})==77 and set(raw_inputs)=={r['coordinate']['ticker'] for r in requests},'Exactly77 unique inputs')
    rows=[]
    for request in requests:
        ticker=request['coordinate']['ticker'];data=raw_inputs[ticker]
        require(sha(data['raw_bytes'])==request['raw_reference']['sha256'] and sha(data['receipt_bytes'])==request['receipt_reference']['sha256'],'Consumed bytes bound before arithmetic')
        receipt=loads(data['receipt_bytes']);require(receipt['ticker']==ticker and receipt['raw_path']==request['raw_reference']['path'] and receipt['raw_sha256']==request['raw_reference']['sha256'],'Receipt/raw coordinate binding')
        value=core.reconstruct_long_channel(raw_bytes=data['raw_bytes'],raw_reference=deepcopy(request['raw_reference']),receipt=receipt,receipt_reference=deepcopy(request['receipt_reference']),bridge_row=deepcopy(request['bridge_row']),calendar253=deepcopy(request['calendar253']),tzif_bytes=tzif_bytes,window_contract=deepcopy(CONTRACT))
        validate_channel(value,request,tzif_bytes)
        rows.append(dict(coordinate=deepcopy(request['coordinate']),history_observation_reference=deepcopy(request['history_observation_reference']),original_identity_assumed_window=deepcopy(request['original_identity_assumed_window']),channel=value))
    return dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',rows=rows,input_references=deepcopy(refs),window_contract=deepcopy(CONTRACT),calendar253=deepcopy(requests[0]['calendar253']),training_return_count=126,evaluation_return_count=126,training_freeze_close_date=requests[0]['calendar253'][126],evaluation_first_return_date=requests[0]['calendar253'][127],security_count=77,issuer_count=76,observed_security_count=101,new_raw_channel_reconstruction_count=77,conditional_numeric_channel_count=sum(r['channel']['status']=='CONDITIONAL_NUMERIC_RESULT' for r in rows),blocked_price_channel_count=sum(r['channel']['status']=='BLOCKED_PRICE_INPUT' for r in rows),original_provenance_and_missing=deepcopy(docs['panel']['panel']['observed_provenance_and_missing']),preserved_evidence_sidecars={name:deepcopy(docs['panel'][name]) for name in SIDECARS},preserved_sidecar_references={name:dict(refs['panel'],json_pointer='/'+name) for name in SIDECARS},history_requirement_reference=deepcopy(refs['history']),original_identity_assumed_window=dict(first='2026-03-20',last='2026-09-21'),evaluation_interval_previously_used_for_fitting=True,future_independent_oos=False,untouched_holdout=False,evaluation_prior_fit_overlap_evidence=dict(panel_returns_reference=dict(refs['panel'],json_pointer='/panel/returns/index'),saved_batch_reference=deepcopy(refs['prior_fit_batch']),evaluation_dates=deepcopy(requests[0]['calendar253'][127:]),evaluation_dates_sha256=sha(encoded(requests[0]['calendar253'][127:])),exact_same_126_dates=True,prior_fit_task_count=1632,meaning='HISTORICAL_DIAGNOSTIC_NOT_UNTOUCHED_HOLDOUT'),new_independent_long_arithmetic_readback_completed=False,**dict.fromkeys(FLAGS,False))

def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift '+path)
def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64,'Core pin pending');docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;blob=path.read_bytes();require(sha(blob)==h,'Hard parent bytes');sources[str(path)]=h;refs[role]=dict(path=str(path),sha256=h)
        if role not in ('history_audit_report','history_audit_reader'):docs[role]=loads(blob)
    require({p.name for p in Path(refs['history']['path']).parent.iterdir()}=={'started.json','requirements.json','publication.json'},'Completed history namespace')
    requests=prepare(docs,refs);raw_inputs={}
    for item in requests:
        values={}
        for field,label in [('raw_reference','raw_bytes'),('receipt_reference','receipt_bytes')]:
            ref=item[field];blob=Path(ref['path']).read_bytes();require(sha(blob)==ref['sha256'],'Raw/receipt hard bytes');merge(sources,ref['path'],ref['sha256']);values[label]=blob
        raw_inputs[item['coordinate']['ticker']]=values
    tzif=NY_SOURCE.read_bytes();require(sha(tzif)==NY_SHA and docs['bridge']['source_hashes'].get(str(NY_SOURCE))==NY_SHA,'Original timezone source bytes');sources[str(NY_SOURCE)]=NY_SHA
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Pure source pin');sources[str(CORE)]=CORE_SHA;guard(sources)
    core=types.ModuleType('_fresh_long_channel');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,requests,raw_inputs,tzif,core

def save(path,value):
    blob=encoded(value)
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Durable output readback');return dict(path=str(path),sha256=sha(blob))
def run():
    require(not OUTPUT.exists(),'Immutable long-window namespace exists');docs,refs,sources,requests,raw_inputs,tzif,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,planned_raw_channel_count=77,retry_allowed=False,**dict.fromkeys(FLAGS,False)))
        value=assemble(requests,raw_inputs,tzif,core,docs,refs);value['source_hashes']=sources;guard(sources);out=save(OUTPUT/'channels.json',value);guard(sources)
        receipt=save(OUTPUT/'publication.json',dict(schema='BULK_LONG_WINDOW_CHANNELS_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_INDEPENDENT_READBACK',channels_reference=out,source_hashes=sources,**dict.fromkeys(FLAGS,False)))
        guard(sources);require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(receipt['path']).read_bytes())==receipt['sha256'],'Final output bytes');require({p.name for p in OUTPUT.iterdir()}=={'started.json','channels.json','publication.json'},'Exact namespace');return out
    except Exception as exc:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(exc),retry_allowed=False));raise

if __name__=='__main__':print(json.dumps(run()))
