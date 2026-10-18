"""Six-cutoff505 scoring history; immutable per-provider outputs, no score or fit."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types
import shutil
from datetime import date,datetime,timezone

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_multidecision_scoring_history_research.py';CORE_SHA='91dc5944120fcf0aeadc3c6ec8af428aa5ee37b4170824b4d215e2b58d93c313'
OUTPUT=ROOT/'data/cache/research/multidecision_scoring_history_20261003_v1'
NY_SOURCE=Path(r'D:\python\Lib\site-packages\tzdata\zoneinfo\America\New_York')
NY_SHA='d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9'
BOUND={
 'history':('data/cache/research/bulk_history_requirements_20261003_v1/requirements.json','f3a317fd00800fe025003479358a6798cd893d4305511bcb1c39eb73ae94e2f5'),
 'history_publication':('data/cache/research/bulk_history_requirements_20261003_v1/publication.json','171f4218d2ec3997b53d21d9e0e4c6081425ae963f79e7b7d0b3c5fa2ea5d13d'),
 'history_audit':('DYNAMIC_BULK_HISTORY_REQUIREMENTS_INDEPENDENT_READBACK_20261003.json','22928d8aaa756f11bd7071f7ef4544cfaeca2e17206b46f7dc273a4c6f0ded9d'),
 'history_audit_report':('DYNAMIC_BULK_HISTORY_REQUIREMENTS_INDEPENDENT_READBACK_20261003.md','fcd9f8f97bd15dd255e7fdb497af034cee69e86564345f85078205618ab60217'),
 'history_audit_reader':('scripts/ndx_bulk_history_requirements_independent_review_20261003.py','64652e1966f2f97fbfd3cd02d23018875b36a83fb06cf6657fddb4ff8154ddbd'),
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'bridge':('data/cache/research/new_cutoff_event_policy_20260923_v1/bridge.json','d2f7824197cb30c119eb8297d6dda784e33ff2589010e36f63d4e9850267d7bd')}
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
CONTRACT=dict(decision_cutoffs=CUTOFFS,price_count_per_decision=505,fit_return_count=126,evaluation_return_count=126,step_return_count=21,windows_per_decision=13,receipt_exclusion_date='2026-09-23')
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
    require(hr['reference_calendar']['ticker']=='AAPL','Saved provider reference calendar')
    dates=hr['reference_calendar']['dates']
    require(type(dates) is list and dates==sorted(set(dates)) and len(dates)>=505,'Full saved calendar')
    require(all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in dates),'Canonical calendar')
    require(dates[-1]=='2026-09-21' and all(d in dates and dates.index(d)>=504 for d in CUTOFFS),'Six full505 predecessors')
    fields=panel['universe']['columns'];universe=[dict(zip(fields,row)) for row in panel['universe']['data']]
    exact(hr['universe'],universe,'Original77 full metadata');require(len(universe)==77 and len({r['ticker'] for r in universe})==77 and len({r['security_id'] for r in universe})==77 and len({r['issuer_id'] for r in universe})==76,'77SID/76issuer')
    exact(hr['observed_provenance_and_missing'],panel['observed_provenance_and_missing'],'All101 provenance');require(len(panel['observed_provenance_and_missing'])==101,'Original101 denominator')
    for name in SIDECARS:exact(history['projection_evidence']['complete_panel_sidecars'][name],pdoc[name],'Complete original sidecars')
    exact(hr['original_identity_assumed_window'],dict(first='2026-03-20',last='2026-09-21'),'No early identity extension')
    require(bridge['candidate_cutoff']=='2026-09-21' and len(bridge['rows'])==101,'Full bridge source');by={r['ticker']:(i,r) for i,r in enumerate(bridge['rows'])};require(len(by)==101,'Unique bridge rows')
    observations=hr['ticker_observations_preserved'];require(set(observations)=={r['ticker'] for r in universe},'Full77 observation metadata')
    requests=[]
    for coordinate in universe:
        ticker=coordinate['ticker'];item=observations[ticker];i,row=by[ticker]
        exact(item['complete_bridge_row'],row,'Original event policy not altered');exact(item['bridge_reference'],dict(refs['bridge'],json_pointer=f'/rows/{i}'),'Event reference')
        exact(item['raw_reference'],row['new_raw_reference'],'Original raw source');exact(item['receipt_reference'],row['new_receipt_reference'],'Receipt source');require(item['decoded_sha256']==row['new_decoded_sha256'],'Saved decoded hash')
        requests.append(dict(coordinate=deepcopy(coordinate),raw_reference=deepcopy(item['raw_reference']),receipt_reference=deepcopy(item['receipt_reference']),bridge_row=deepcopy(row),reference_calendar=deepcopy(dates),window_contract=deepcopy(CONTRACT),history_observation_reference=dict(refs['history'],json_pointer='/requirements/ticker_observations_preserved/'+ticker),original_identity_assumed_window=deepcopy(item['identity_assumed_window'])))
    return requests

def outer_contract(refs):
    return dict(inventory_reference=dict(refs['panel'],json_pointer='/panel/universe'),security_count=77,issuer_count=76,observed_provenance_count=101,preserved_sidecar_references={n:dict(refs['panel'],json_pointer='/'+n) for n in SIDECARS})


def validate_channel(value,request,tzif,outer):
    require(value['schema']=='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1' and value['ticker']==request['coordinate']['ticker'],'Channel identity')
    for k in ('score_computed','fit_performed','point_in_time_verified','execution_authorized','promotion_allowed','source_bytes_authenticated','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed','outer_inventory_completeness_verified','provider_price_unit_verified','identity_interval_verified','exchange_calendar_verified','complete_corporate_actions_verified','dividend_cash_flows_included','volume_unit_verified','liquidity_qualified','legal_training_input_admitted','benchmark_qualified','old_outputs_spliced','missing_values_filled','historical_timely_availability_verified','decision_time_action_knowledge_verified'):
        require(value[k] is False,'No channel authority '+k)
    for k,v in [('raw_reference',request['raw_reference']),('receipt_reference',request['receipt_reference']),('bridge_row_preserved',request['bridge_row']),('reference_calendar_preserved',request['reference_calendar']),('window_contract',CONTRACT),('outer_inventory_contract',outer)]:exact(value[k],v,'Channel binding '+k)
    require(type(value['raw_decode_count']) is int and value['raw_decode_count']==1 and value['tzif_sha256']==sha(tzif) and value['decoded_sha256']==request['bridge_row']['new_decoded_sha256'],'Decode/source identity')
    dates=request['reference_calendar'];first=dates[dates.index(CUTOFFS[0])-504];union=[d for d in dates if first<=d<=CUTOFFS[-1]]
    exact(value['calendar'],union,'Union dates');exact([r['session'] for r in value['quote_rows']],union,'All price slots')
    require(len(value['return_rows'])==len(union)-1 and len(value['decisions'])==6,'Full return/decision denominator')
    for i,r in enumerate(value['return_rows']):require(r['previous_session']==union[i] and r['session']==union[i+1],'Adjacent returns')
    for d,cutoff in zip(value['decisions'],CUTOFFS):
        end=dates.index(cutoff);exact(d['required_price_dates'],dates[end-504:end+1],'Full505 dates')
        require(d['cutoff']==cutoff and type(d['window_count']) is int and d['window_count']==13 and len(d['windows'])==13 and d['scoring_allowed'] is False and d['pooling_only_unblocked_windows_allowed'] is False,'Full13 window contract')
    for name in ('quote_rows','return_rows'):require(value[name+'_sha256']==sha(encoded(value[name])),'Numeric content hash')
    copy=deepcopy(value);h=copy.pop('content_sha256');require(h==sha(encoded(copy)),'Channel content hash')


def guard(sources,refs):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for role in ('history','panel','bridge'):
        require(not (Path(refs[role]['path']).parent/'failure.json').exists(),'Parent failure '+role)
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift '+path)


def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64 and all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Pending anchor')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;blob=path.read_bytes();require(sha(blob)==h,'Hard parent '+role);merge(sources,str(path),h);refs[role]=dict(path=str(path),sha256=h)
        if role not in ('history_audit_report','history_audit_reader'):docs[role]=loads(blob)
    requests=prepare(docs,refs)
    tzif=NY_SOURCE.read_bytes();require(sha(tzif)==NY_SHA and docs['bridge']['source_hashes'].get(str(NY_SOURCE))==NY_SHA,'Bound TZif');merge(sources,str(NY_SOURCE),NY_SHA)
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Pure bytes');merge(sources,str(CORE),CORE_SHA);guard(sources,refs)
    core=types.ModuleType('_private_scoring_history');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,requests,tzif,core


def space(size):require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3+size,'Resource reserve plus encoded bytes')

def save(path,value,failure=False):
    blob=encoded(value)
    if not failure:space(len(blob))
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Output readback');return dict(path=str(path),sha256=sha(blob))


def run(*,execute=False):
    require(execute is True,'Explicit execute required');require(not OUTPUT.exists(),'Immutable namespace exists')
    docs,refs,sources,requests,tzif,core=load_inputs();space(0);OUTPUT.mkdir(parents=True,exist_ok=False);written=[];rows=[]
    try:
        written.append(save(OUTPUT/'started.json',dict(schema='MULTIDECISION_SCORING_HISTORY_STARTED_V1',started_at_utc=datetime.now(timezone.utc).isoformat(),input_references=refs,source_hashes=deepcopy(sources),planned_channel_count=77,retry_allowed=False,**dict.fromkeys(FLAGS,False))))
        outer=outer_contract(refs)
        for i,request in enumerate(requests):
            # At most one provider raw and one result resident. No old producer invocation.
            values={}
            for field,label in [('raw_reference','raw_bytes'),('receipt_reference','receipt_bytes')]:
                r=request[field];blob=Path(r['path']).read_bytes();require(sha(blob)==r['sha256'],'Raw/receipt bytes');merge(sources,r['path'],r['sha256']);values[label]=blob
            receipt=loads(values['receipt_bytes'])
            value=core.materialize_scoring_history_channel(raw_bytes=values['raw_bytes'],raw_reference=deepcopy(request['raw_reference']),receipt=receipt,receipt_reference=deepcopy(request['receipt_reference']),bridge_row=deepcopy(request['bridge_row']),reference_calendar=deepcopy(request['reference_calendar']),tzif_bytes=tzif,window_contract=deepcopy(CONTRACT),outer_inventory_contract=deepcopy(outer))
            validate_channel(value,request,tzif,outer)
            ref=save(OUTPUT/f'channel_{i:03d}.json',value);written.append(ref)
            rows.append(dict(index=i,coordinate=deepcopy(request['coordinate']),channel_reference=ref,status=value['status'],regular_floor=value['regular_floor'],history_observation_reference=request['history_observation_reference'],original_identity_assumed_window=request['original_identity_assumed_window'],decision_coverage=[dict(cutoff=d['cutoff'],status=d['status'],complete_thirteen_window_numeric_supply=d['complete_thirteen_window_numeric_supply'],blocked_window_count=sum(w['status']=='BLOCKED_WINDOW' for w in d['windows'])) for d in value['decisions']]))
            del value,values,receipt
        require(len(rows)==77,'No missing channel');guard(sources,refs)
        result=dict(schema='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK',rows=rows,window_contract=CONTRACT,reference_calendar=deepcopy(docs['history']['requirements']['reference_calendar']),outer_inventory_contract=outer,original_provenance_and_missing=deepcopy(docs['panel']['panel']['observed_provenance_and_missing']),preserved_evidence_sidecars={n:deepcopy(docs['panel'][n]) for n in SIDECARS},security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,raw_decode_count=77,input_references=refs,source_hashes=sources,score_computed=False,unequal_window_pooling_allowed=False,historical_retrospective_only=True,full_ndx_universe_certified=False,new_independent_numeric_readback_completed=False,**dict.fromkeys(FLAGS,False))
        out=save(OUTPUT/'index.json',result);written.append(out)
        pub=save(OUTPUT/'publication.json',dict(schema='MULTIDECISION_SCORING_HISTORY_PUBLICATION_V1',status=result['status'],index_reference=out,input_references=refs,source_hashes=sources,**dict.fromkeys(FLAGS,False)));written.append(pub)
        guard(sources,refs)
        require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in written},'Exact publication namespace')
        for r in written:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output drift')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),saved_channel_references=rows,completed_channel_count=len(rows),unprocessed_channel_count=77-len(rows),retry_allowed=False),failure=True);raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute)))
