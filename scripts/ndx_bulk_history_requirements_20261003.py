"""Source-bound long-history requirements from saved observation metadata only."""
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_bulk_history_requirements_research.py'
CORE_SHA='fa4d19ed2cdae45615023f1921b6ff80be74cc6c61ee3e8f261e4fa1b4336a71'
OUTPUT=BASE/'bulk_history_requirements_20261003_v1'
BOUND={
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'panel_publication':('data/cache/research/bulk_conditional_panel_20261003_v1/publication.json','895b1d0f71fb3f4b1175845c3390f3d286c672519fa4aa2c0a13bb930f6a2a9d'),
 'readback':('data/cache/research/new_cutoff_raw_readback_20260923_v1/completed102.json','7c03247919319c8e1a1a12be2fd8ccdba59aec20e0d9ee6634e69cc85fd0d53b'),
 'bridge':('data/cache/research/new_cutoff_event_policy_20260923_v1/bridge.json','d2f7824197cb30c119eb8297d6dda784e33ff2589010e36f63d4e9850267d7bd'),
 'panel_audit_report':('DYNAMIC_BULK_CONDITIONAL_PANEL_INDEPENDENT_READBACK_20261003.md','8a432b70dfc3393850242873b700eb54097bec9981c8f488cc88bd578295c879'),
 'panel_audit_reader':('scripts/ndx_bulk_conditional_panel_independent_review_20261003.py','5a3d35ba39e6a719dfafaa3e4e348f065c5cd297c403a08e087c78f02c5c1b0b')}
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
CONTRACT=dict(decision_cutoff='2026-09-21',fit_return_rows=126,evaluation_return_rows=126,rolling_step_rows=21,price_window_lengths=[253,505])
FLAGS=('http_performed','raw_decoding_reperformed','raw_quote_numerics_reaudited','old_audit_repeated','prices_reconstructed','returns_computed','fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','identity_interval_extended','complete_corporate_actions_verified','volume_unit_verified','provider_binding_verified','exchange_calendar_certified','future_oos_evaluation_performed','full_transitive_source_closure_reverified','formal_input_ready')

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def reference(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and type(r['sha256']) is str and len(r['sha256'])==64,'Saved reference shape')
def canonical(day):require(type(day) is str and date.fromisoformat(day).isoformat()==day,'Canonical observed date')
def loads(blob):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'Duplicate JSON key');result[k]=v
        return result
    def invalid(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)

def project_inputs(documents,references):
    pdoc=documents['panel'];p=pdoc['panel'];readback=documents['readback'];bridge=documents['bridge'];receipt=documents['panel_publication']
    require(pdoc['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and p['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','Saved bulk panel schema')
    require(receipt['panel_reference']==references['panel'] and receipt['status']=='PUBLISHED_CONDITIONAL_PANEL_ONLY','Panel publication binding');exact(receipt['source_hashes'],pdoc['source_hashes'],'Panel publication source map')
    for obj in (pdoc,p):require(all(obj[k] is False for k in ('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','formal_input_ready')),'Panel conditional boundaries')
    require(p['cutoff']==CONTRACT['decision_cutoff'],'Saved panel cutoff')
    u=p['universe'];require(u['type']=='dataframe' and u['index_kind']=='RangeIndex' and u['index']==list(range(77)) and len(u['data'])==77 and len(u['columns'])==len(set(u['columns']))==len(u['dtypes']) and all(len(r)==len(u['columns']) for r in u['data']),'Complete77 typed universe')
    universe=[dict(zip(u['columns'],r)) for r in u['data']];tickers=[r['ticker'] for r in universe]
    require(len(set(tickers))==len({r['security_id'] for r in universe})==77 and len({r['issuer_id'] for r in universe})==76,'77SID/76issuer exact')
    gaps=p['observed_provenance_and_missing'];require(len(gaps)==101 and len({r['ticker'] for r in gaps})==101,'Full101 provenance');gap_by={r['ticker']:r for r in gaps}
    require(readback['schema']=='NEW_CUTOFF_INDEPENDENT_RAW_READBACK_V1' and type(readback['attempted_prefix_count']) is int and readback['attempted_prefix_count']==102 and readback['queue_count']==104 and len(readback['rows'])==102,'Saved102/104 raw readback scope')
    require(bridge['candidate_cutoff']==CONTRACT['decision_cutoff'] and len(bridge['rows'])==101,'Full101 event bridge')
    for obj in (readback,bridge):require(all(obj[k] is False for k in ('prices_reconstructed','complete_corporate_actions_verified','legal_training_input_admitted','point_in_time_verified','promotion_allowed','volume_unit_verified')),'Saved source boundaries')
    channels={row['ticker']:(i,row) for i,row in enumerate(readback['rows'])};policies={row['ticker']:(i,row) for i,row in enumerate(bridge['rows'])}
    require(len(channels)==102 and set(policies)==set(gap_by) and set(tickers)<=set(policies) and 'AAPL' in channels,'Source ticker denominators')
    observations={}
    for item in universe:
        ticker=item['ticker'];ci,channel=channels[ticker];bi,br=policies[ticker];obs=channel['observation'];gap=gap_by[ticker]
        require(channel['http_status']==200 and channel['readback_status']=='RAW_CHANNEL_READBACK_ONLY' and obs['ticker']==ticker and obs['raw_provider_meta']['symbol']==ticker,'Saved provider ticker binding')
        require(gap['included_in_conditional_panel'] is True and gap['coordinate_assumption']['security_id']==item['security_id'] and gap['coordinate_assumption']['issuer_id']==item['issuer_id'] and gap['risk_assumption']['risk_chain']==item['risk_chain'],'Selected universe matches conditional gap evidence')
        window=gap['coordinate_assumption']['assumed_window'];exact(window,dict(first='2026-03-20',last=CONTRACT['decision_cutoff']),'Original identity window remains unchanged')
        rawref=br['new_raw_reference'];receiptreference=br['new_receipt_reference'];reference(rawref);reference(receiptreference)
        require(receiptreference['sha256']==channel['receipt_sha256'] and br['new_decoded_sha256']==obs['decoded_sha256'],'Saved receipt/decoded linkage')
        for r in (rawref,receiptreference):require(readback['source_hashes'].get(r['path'])==r['sha256'] and bridge['source_hashes'].get(r['path'])==r['sha256'],'Parent assertions reference same raw/receipt bytes')
        require(br['new_returned_splits']==obs['raw_returned_events'].get('splits',{}),'Original event payload linkage')
        rows=[];excluded=[];days=[];canonical(channel['receipt_new_york_day'])
        for ri,row in enumerate(obs['rows']):
            day=row['new_york_date'];canonical(day);require(type(row['excluded_receipt_day_or_later']) is bool and row['excluded_receipt_day_or_later']==(day>=channel['receipt_new_york_day']),'Receipt-day exclusion preserved')
            require(type(row['missing_fields']) is list and len(row['missing_fields'])==len(set(row['missing_fields'])) and set(row['missing_fields'])<= {'open','high','low','close','volume','adjclose'},'Saved missing-field metadata')
            days.append(day);projected=dict(session=day,missing_fields=deepcopy(row['missing_fields']),source_json_pointer=f'/rows/{ci}/observation/rows/{ri}')
            if day>CONTRACT['decision_cutoff'] or row['excluded_receipt_day_or_later']:excluded.append(projected)
            else:rows.append(projected)
        require(days==sorted(set(days)) and rows,'All original ordered observation dates retained without completeness filter')
        observations[ticker]=dict(observation_rows=rows,raw_reference=deepcopy(rawref),receipt_reference=deepcopy(receiptreference),decoded_sha256=obs['decoded_sha256'],bridge_reference=dict(references['bridge'],json_pointer=f'/rows/{bi}'),event_policy_bridge=deepcopy(br['event_policy_bridge']),identity_assumed_window=deepcopy(window),complete_bridge_row=deepcopy(br),complete_coordinate_assumption=deepcopy(gap['coordinate_assumption']),complete_risk_assumption=deepcopy(gap['risk_assumption']),returned_events=deepcopy(obs['raw_returned_events']),original_observation_reference=dict(references['readback'],json_pointer=f'/rows/{ci}'),excluded_after_cutoff_or_receipt_day=excluded,receipt_new_york_day=channel['receipt_new_york_day'],quote_price_unit=obs['quote_price_unit'],volume_unit=obs['volume_unit'],all_original_observation_row_count=len(days),historical_raw_source_bytes_reverified=False,raw_quote_values_projected=False)
    # AAPL dates come from the same sealed observation, not a certified exchange calendar.
    if 'AAPL' in observations:caldates=[r['session'] for r in observations['AAPL']['observation_rows']]
    else:raise ValueError('AAPL reference channel must be represented')
    ai=channels['AAPL'][0];calendar=dict(ticker='AAPL',dates=caldates,source_reference=dict(references['readback'],json_pointer=f'/rows/{ai}/observation/rows'))
    sidecars={name:deepcopy(pdoc[name]) for name in SIDECARS}
    args=dict(universe=universe,observed_provenance_and_missing=deepcopy(gaps),reference_calendar=calendar,ticker_observations=observations,window_contract=deepcopy(CONTRACT))
    evidence=dict(input_references=deepcopy(references),complete_panel_sidecars=sidecars,sidecar_references={name:dict(references['panel'],json_pointer='/'+name) for name in SIDECARS},observed_security_denominator=101,typed_security_count=77,typed_issuer_count=76,raw_attempted_channel_count=102,capture_queue_count=104,reference_calendar_basis='SEALED_AAPL_PROVIDER_OBSERVATIONS_NOT_EXCHANGE_CALENDAR',original_identity_assumed_window=dict(first='2026-03-20',last='2026-09-21'),source_assertions_reused_without_transitive_raw_reaudit=True)
    return args,evidence

def validate_result(value,args):
    require(value['schema']=='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1' and value['status']=='HISTORICAL_REQUIREMENTS_ONLY_NOT_TRAINING_ADMISSION','Requirements-only result')
    for key in ('source_bytes_authenticated','reference_calendar_exchange_certified','prices_computed','returns_computed','fit_performed','identity_interval_verified','risk_interval_verified','complete_corporate_actions_verified','provider_binding_verified','volume_unit_verified','point_in_time_verified','timely_availability_verified','legal_training_input_admitted','historical_six_input_training_ready','formal_dual_benchmark_ready','promotion_allowed','execution_authorized','future_independent_oos_recovered','benchmark_qualified','evaluation_executed'):
        require(value[key] is False,'Result authority remains false')
    for key in ('universe','observed_provenance_and_missing','reference_calendar','window_contract'):exact(value[key],args[key],'Pure preserved projection '+key)
    exact(value['ticker_observations_preserved'],args['ticker_observations'],'Pure preserved full77 metadata')
    require(len(value['scenarios'])==2,'Two explicit length scenarios')
    for scenario,length,count in zip(value['scenarios'],(253,505),(1,13)):
        require(type(scenario['price_window_length']) is int and scenario['price_window_length']==length and type(scenario['expected_rolling_window_count']) is int and scenario['expected_rolling_window_count']==count,'Window count contract')
        require(len(scenario['security_rows'])==77 and scenario['dates_intersected_or_compressed'] is False and scenario['all_security_windows_retained'] is True,'No survivor filtering')
    body={k:v for k,v in value.items() if k!='content_sha256'};require(sha(encoded(body))==value['content_sha256'],'Pure content checksum')

def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift '+path)
def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64,'Core pin pending')
    sources={str(SOURCE):LOADED_SHA};docs={};refs={}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;blob=path.read_bytes();require(sha(blob)==h,'Hard source SHA');refs[role]=dict(path=str(path),sha256=h);sources[str(path)]=h
        if role not in ('panel_audit_report','panel_audit_reader'):docs[role]=loads(blob)
    folder=Path(refs['panel']['path']).parent;require({p.name for p in folder.iterdir()}=={'started.json','panel.json','publication.json'},'Panel namespace is complete')
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Core source SHA');sources[str(CORE)]=CORE_SHA;guard(sources)
    module=types.ModuleType('_fresh_history_requirements');module.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),module.__dict__)
    return docs,refs,sources,module

def save(path,value):
    blob=encoded(value)
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Output bytes readback');return dict(path=str(path),sha256=sha(blob))
def run():
    require(not OUTPUT.exists(),'Immutable requirements namespace exists');docs,refs,sources,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,retry_allowed=False,**dict.fromkeys(FLAGS,False)))
        args,evidence=project_inputs(docs,refs);result=core.prepare_history_requirements(**args);validate_result(result,args)
        value=dict(schema='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1',requirements=result,projection_evidence=evidence,source_hashes=sources,**dict.fromkeys(FLAGS,False));guard(sources)
        out=save(OUTPUT/'requirements.json',value);guard(sources);receipt=save(OUTPUT/'publication.json',dict(schema='BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=out,source_hashes=sources,**dict.fromkeys(FLAGS,False)))
        guard(sources);require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(receipt['path']).read_bytes())==receipt['sha256'],'Final readback');require({p.name for p in OUTPUT.iterdir()}=={'started.json','requirements.json','publication.json'},'Exact result namespace');return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(exc),retry_allowed=False));raise

if __name__=='__main__':print(json.dumps(run()))
