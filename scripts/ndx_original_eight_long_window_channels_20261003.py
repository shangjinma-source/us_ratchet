"""Reuse seven sealed 253-date channels; reconstruct only the TSM control channel."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_bulk_long_window_channels_research.py'
CORE_SHA='419c8c36b8720609211910347f4c088a9a1a6e3bd874cd3a72f62d8a9fecbd40'
OUTPUT=ROOT/'data/cache/research/original_eight_long_window_channels_20261003_v1'
NY_SOURCE=Path(r'D:\python\Lib\site-packages\tzdata\zoneinfo\America\New_York')
NY_SHA='d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9'
BOUND={
 'channels':('data/cache/research/bulk_long_window_channels_20261003_v1/channels.json','0f13e2cca5979608d742bfe1bf7a04c46ee9ca4396e5f45f22741420ee540516'),
 'channels_publication':('data/cache/research/bulk_long_window_channels_20261003_v1/publication.json','b6c172eb6916361e9a701b8aed31f0caacb7161d6fdf1056d6c6127183343731'),
 'channels_audit':('DYNAMIC_BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_20261003.json','3b7b35a3574757c9cdd12c74e701366979e490f5aadebcf0019da97349f4da65'),
 'channels_audit_report':('DYNAMIC_BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_20261003.md','bbc0457b8e91b8215a30084402dae96a51dd7c63d614b1bd414239166f164c0d'),
 'channels_audit_reader':('scripts/ndx_bulk_long_window_channels_independent_review_20261003.py','7227e3705b12782c9514d39df7b23f12b1ae10e8da775f7364796d7c83ddcc99'),
 'requirements':('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/requirements.json','95461ba7b298347d969fe65cb3b93aa5632fecfdf331f1ba7a42af6abdee1c47'),
 'requirements_publication':('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/publication.json','bf9290f263f92523d7bd2001d138321ef429705aa96ec494e665ec15dead8766'),
 'requirements_audit_report':('DYNAMIC_BULK_LONG_WINDOW_BENCHMARK_INDEPENDENT_READBACK_20261003.md','803803bebc421a49b48755a6b22ea4b810bbfdbd88f1eca41582c5c5b2820655'),
 'requirements_audit_reader':('scripts/ndx_bulk_long_window_benchmark_independent_review_20261003.py','eaecf87e9c119a618ece888ffb9c1ce6270f4ee4e987e1393cfe45b8aa7b98d9'),
 'old_tsm_basis':('data/cache/research/current_tsm_raw_capture_20260919_v1/conditional_nominal_quotes_20260919.json','b51abeb8b9ef5b1b5cf6f9b8b2a6aaf797091ec02a65f5297d7326c4f7fbc2a3'),
}
TICKERS=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
CONTRACT=dict(cutoff='2026-09-21',fit_return_count=126,evaluation_return_count=126,receipt_exclusion_date='2026-09-23')
FLAGS=('http_performed','fit_performed','account_simulation_performed','old_producer_called','old_audit_repeated','seven_reused_channels_recomputed','weights_normalized','weights_reoptimized','holdings_or_quotes_converted','identity_interval_extended','historical_identity_verified','historical_risk_verified','complete_corporate_actions_verified','provider_binding_verified','point_in_time_verified','legal_training_input_admitted','execution_authorized','promotion_allowed','formal_benchmark_evaluation_performed','full_transitive_source_closure_reverified','benchmark_qualified','fx_equivalence_verified','nav_publication_verified','future_independent_oos','untouched_holdout')
CHANNEL_FALSE=('source_bytes_authenticated','provider_price_unit_verified','identity_interval_verified','point_in_time_verified','exchange_calendar_verified','complete_corporate_actions_verified','dividend_cash_flows_included','volume_unit_verified','liquidity_qualified','legal_training_input_admitted','benchmark_qualified','promotion_allowed','execution_authorized','fit_performed','old_outputs_spliced','missing_values_filled','historical_timely_availability_verified')

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(blob):return hashlib.sha256(blob).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(value):raise ValueError('Nonfinite JSON literal')
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)
def merge(sources,path,h):require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h
def no_authority(value,keys):require(all(value[k] is False for k in keys),'No input authority upgrade')

def prepare(docs,refs):
    """Metadata and exact sealed-row linking; no old arithmetic or raw decoding."""
    saved=docs['channels'];audit=docs['channels_audit'];reqdoc=docs['requirements'];req=reqdoc['requirements']
    require(saved['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1' and reqdoc['schema']=='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1' and req['schema']=='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1','Parent schemas')
    for role,status,schema,field in [('channels','PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_INDEPENDENT_READBACK','BULK_LONG_WINDOW_CHANNELS_PUBLICATION_V1','channels_reference'),('requirements','PUBLISHED_REQUIREMENTS_ONLY','BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1','requirements_reference')]:
        publication=docs[role+'_publication'];require(publication['status']==status and publication['schema']==schema,'Successful parent publication');exact(publication[field],refs[role],'Parent receipt reference');exact(publication['source_hashes'],docs[role]['source_hashes'],'Parent receipt sources')
        no_authority(publication,('fit_performed','account_simulation_performed','point_in_time_verified','promotion_allowed','execution_authorized','legal_training_input_admitted'))
    require(audit['schema']=='BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['channels_sha256']==refs['channels']['sha256'] and audit['publication_sha256']==refs['channels_publication']['sha256'] and audit['reader_sha256']==refs['channels_audit_reader']['sha256'],'External77 independent readback')
    for item in (saved,reqdoc,audit):no_authority(item,('fit_performed','account_simulation_performed','point_in_time_verified','legal_training_input_admitted'))
    require(saved['evaluation_interval_previously_used_for_fitting'] is True and saved['future_independent_oos'] is False and saved['untouched_holdout'] is False,'Previously consumed evaluation interval')
    dates=req['reference_calendar']['dates'];exact(dates,saved['calendar253'],'Same253 benchmark/candidate dates')
    require(len(dates)==253 and dates==sorted(set(dates)) and dates[0]=='2025-09-18' and dates[126]=='2026-03-20' and dates[127]=='2026-03-23' and dates[-1]=='2026-09-21','Fixed historical window')
    exact(req['training_return_end_dates'],dates[1:127],'Training126');exact(req['evaluation_return_end_dates'],dates[127:],'Evaluation126')
    control=req['original_control_preserved'];securities=control['securities'];exact(req['original_control_order'],TICKERS,'Original8 order');exact([r['ticker'] for r in securities],TICKERS,'Original8 securities')
    exact(control['complete_original_definition']['securities'],securities,'Original weights unchanged');exact(control['complete_original_manifest']['definition'],control['complete_original_definition'],'Complete original control')
    require(control['new_execution_contract_frozen'] is False and len({r['security_id'] for r in securities})==8 and len({r['issuer_id'] for r in securities})==8,'Distinct original8, no new execution contract')
    require(len(saved['rows'])==77 and len(audit['per_channel'])==77 and len(saved['original_provenance_and_missing'])==101 and len(saved['preserved_evidence_sidecars'])==7,'Full parent denominators')
    by={r['coordinate']['ticker']:(i,r) for i,r in enumerate(saved['rows'])};audits={r['ticker']:(i,r) for i,r in enumerate(audit['per_channel'])};require(len(by)==len(audits)==77 and set(by)==set(audits) and 'TSM' not in by,'77unique nonTSM channels')
    rows=[];metadata=req['stock_metadata_preserved'];require(set(metadata)==set(TICKERS),'All8 metadata')
    for i,security in enumerate(securities):
        ticker=security['ticker'];meta=metadata[ticker];exact(meta['complete_original_control_security'],security,'Original security metadata');require(meta['security_id']==security['security_id'] and meta['shares_or_prices_converted'] is False,'No class conversion')
        row=dict(original_control_security=deepcopy(security),original_control_security_reference=dict(refs['requirements'],json_pointer=f'/requirements/original_control_preserved/securities/{i}'),benchmark_metadata_reference=dict(refs['requirements'],json_pointer='/requirements/stock_metadata_preserved/'+ticker),complete_benchmark_metadata=deepcopy(meta))
        if ticker!='TSM':
            index,parent=by[ticker];ai,ar=audits[ticker];channel=parent['channel']
            for key in ('security_id','issuer_id','risk_chain','ticker'):require(parent['coordinate'][key]==security[key],'Selected ticker/SID/issuer/risk mismatch')
            require(channel['status']=='CONDITIONAL_NUMERIC_RESULT' and channel['ticker']==ticker,'Reused numeric channel');no_authority(channel,CHANNEL_FALSE);exact(channel['calendar'],dates,'Reused complete calendar')
            for key in ('raw_reference','receipt_reference'):exact(channel[key],meta[key],'Same underlying capture');exact(ar[key],channel[key],'Independent capture reference')
            for field in ('quote_rows','training_returns','evaluation_returns'):require(channel[field+'_sha256']==ar[field+'_sha256']==sha(encoded(channel[field])),'Sealed row and independent payload linkage')
            require(len(channel['quote_rows'])==253 and len(channel['return_rows'])==252 and len(channel['training_returns'])==len(channel['evaluation_returns'])==126,'Saved numerical shapes')
            row.update(mode='EXACT_SEALED_CHANNEL_REUSE_NO_ARITHMETIC',channel_reference=dict(refs['channels'],json_pointer=f'/rows/{index}/channel'),complete_parent_row=deepcopy(parent),independent_readback_reference=dict(refs['channels_audit'],json_pointer=f'/per_channel/{ai}'),channel=deepcopy(channel))
        else:
            require(security['security_id']=='security:incumbent_overlay:TSM' and security['issuer_id']=='issuer:0001046179' and meta['control_only_overlay'] is True,'Original TSM overlay retained')
            sidecar=meta['complete_identity_sidecar'];require(sidecar['ticker']=='TSM' and sidecar['security_id']==security['security_id'] and sidecar['issuer_id']==security['issuer_id'] and sidecar['cusip']=='874039100' and sidecar['security_class']=='American Depositary Shares' and type(sidecar['ordinary_shares_per_ads']) is int and sidecar['ordinary_shares_per_ads']==5,'TSM conditional ADS facts')
            no_authority(sidecar,('historical_2023_identity_interval_verified','point_in_time_verified','ndx_membership_verified','price_identity_verified','holdings_conversion_performed','promotion_allowed'))
            old=docs['old_tsm_basis'];reconstruction=old['reconstruction'];require(old['schema']=='INCUMBENT_TSM_FIXED_CUTOFF_CONDITIONAL_NOMINAL_QUOTE_V1' and old['ticker']=='TSM','Old conditional TSM basis')
            require(reconstruction['quote_field_basis']=='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS' and reconstruction['basis_was_supplied_not_authenticated'] is True and reconstruction['provider_split_events']==[],'Explicit old conditional unit assumption')
            no_authority(old,('zero_returned_splits_proves_no_actions','complete_actions_verified','quote_basis_independently_authenticated','point_in_time_verified','promotion_allowed'))
            require(old['all_returned_raw_events'].get('splits',{})=={} and meta['returned_events'].get('splits',{})=={},'Only exact empty returned split policies eligible for this TSM adapter')
            bridge=dict(ticker='TSM',new_raw_reference=deepcopy(meta['raw_reference']),new_receipt_reference=deepcopy(meta['receipt_reference']),new_decoded_sha256=meta['decoded_sha256'],new_returned_splits={},event_policy_bridge=dict(events=[],regular_floor=None),basis_assumption='SPLIT_ADJUSTED_QUOTE_OPEN_CLOSE_EXCLUDES_DIVIDENDS',old_basis_reference=dict(refs['old_tsm_basis'],json_pointer='/reconstruction/quote_field_basis'),old_returned_events_reference=dict(refs['old_tsm_basis'],json_pointer='/all_returned_raw_events'),new_returned_events_reference=dict(refs['requirements'],json_pointer='/requirements/stock_metadata_preserved/TSM/returned_events'),empty_returned_splits_is_not_action_completeness=True,complete_corporate_actions_verified=False,provider_price_unit_verified=False)
            row.update(mode='ONE_NEW_TSM_RAW_RECONSTRUCTION',channel_reference=None,complete_parent_row=None,independent_readback_reference=None,channel=None,conditional_event_policy_bridge=bridge)
        rows.append(row)
    return dict(rows=rows,calendar253=deepcopy(dates))

def validate_new_channel(value,request,tzif_bytes):
    meta=request['complete_benchmark_metadata'];require(value['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1' and value['ticker']=='TSM' and value['status'] in ('CONDITIONAL_NUMERIC_RESULT','BLOCKED_PRICE_INPUT'),'New TSM state');no_authority(value,CHANNEL_FALSE)
    for key in ('raw_reference','receipt_reference'):exact(value[key],meta[key],'New TSM source')
    exact(value['bridge_row_preserved'],request['conditional_event_policy_bridge'],'New explicit TSM conditional policy');exact(value['window_contract'],CONTRACT,'New TSM window');require(value['tzif_sha256']==sha(tzif_bytes) and value['decoded_sha256']==meta['decoded_sha256'],'Consumed timezone/decoded source')
    if value['status']=='BLOCKED_PRICE_INPUT':require(bool(value['reasons']) and all(value[k] is None for k in ('quote_rows','return_rows','training_returns','evaluation_returns')),'Blocked TSM no invented prices')
    else:
        require(value['reasons']==[] and len(value['quote_rows'])==253 and len(value['return_rows'])==252 and len(value['training_returns'])==len(value['evaluation_returns'])==126,'TSM253/252/126 dimensions')
        exact(value['return_rows'][:126],value['training_returns'],'TSM training slice');exact(value['return_rows'][126:],value['evaluation_returns'],'TSM evaluation slice')
        for field in ('quote_rows','training_returns','evaluation_returns'):require(value[field+'_sha256']==sha(encoded(value[field])),'TSM payload checksum')

def assemble(prepared,raw_bytes,receipt_bytes,tzif_bytes,core,docs,refs):
    rows=deepcopy(prepared['rows']);require([r['original_control_security']['ticker'] for r in rows]==TICKERS,'Ordered8');target=rows[4];meta=target['complete_benchmark_metadata']
    require(sha(raw_bytes)==meta['raw_reference']['sha256'] and sha(receipt_bytes)==meta['receipt_reference']['sha256'],'Consumed TSM transport/receipt bytes');receipt=loads(receipt_bytes);exact(receipt,meta['original_receipt'],'Original TSM receipt immutable')
    value=core.reconstruct_long_channel(raw_bytes=raw_bytes,raw_reference=deepcopy(meta['raw_reference']),receipt=receipt,receipt_reference=deepcopy(meta['receipt_reference']),bridge_row=deepcopy(target['conditional_event_policy_bridge']),calendar253=deepcopy(prepared['calendar253']),tzif_bytes=tzif_bytes,window_contract=deepcopy(CONTRACT))
    validate_new_channel(value,target,tzif_bytes);exact(value['calendar'],prepared['calendar253'],'TSM full calendar');target['channel']=value
    req=docs['requirements']['requirements'];saved=docs['channels']
    return dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',rows=rows,original_control_order=deepcopy(TICKERS),original_control_preserved=deepcopy(req['original_control_preserved']),original_target_weight_sum_exact=req['original_target_weight_sum_exact'],original_benchmark_requirements_reference=deepcopy(refs['requirements']),complete_benchmark_requirements_preserved=deepcopy(req),calendar253=deepcopy(prepared['calendar253']),window_contract=deepcopy(CONTRACT),security_count=8,issuer_count=8,new_raw_channel_reconstruction_count=1,sealed_channel_reuse_count=7,conditional_numeric_channel_count=sum(r['channel']['status']=='CONDITIONAL_NUMERIC_RESULT' for r in rows),blocked_price_channel_count=sum(r['channel']['status']=='BLOCKED_PRICE_INPUT' for r in rows),original_candidate_provenance=deepcopy(saved['original_provenance_and_missing']),preserved_candidate_evidence_sidecars=deepcopy(saved['preserved_evidence_sidecars']),evaluation_interval_previously_used_for_fitting=True,evaluation_prior_fit_overlap_evidence=deepcopy(saved['evaluation_prior_fit_overlap_evidence']),tsm_same_evaluation_calendar_not_claimed_prior_candidate_fit=True,new_tsm_independent_arithmetic_readback_completed=False,reuse_scope='SEVEN_COMPLETE_NEW_253_CHANNELS_ONLY_NOT_OLD_127_OUTPUT_SPLICING',input_references=deepcopy(refs),**dict.fromkeys(FLAGS,False))

def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source drift')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift '+path)
def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64 and all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'All external audit/source pins required before IO')
    docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;blob=path.read_bytes();require(sha(blob)==h,'Hard parent source bytes');merge(sources,str(path),h);refs[role]=dict(path=str(path),sha256=h)
        if not role.endswith(('_reader','_report')):docs[role]=loads(blob)
    for role,filename in [('channels','channels.json'),('requirements','requirements.json')]:require({p.name for p in Path(refs[role]['path']).parent.iterdir()}=={'started.json',filename,'publication.json'},'Successful parent namespace without failure')
    prepared=prepare(docs,refs);meta=prepared['rows'][4]['complete_benchmark_metadata'];blobs=[]
    for key in ('raw_reference','receipt_reference'):
        ref=meta[key];blob=Path(ref['path']).read_bytes();require(sha(blob)==ref['sha256'],'TSM source reference bytes');merge(sources,ref['path'],ref['sha256']);blobs.append(blob)
    tzif=NY_SOURCE.read_bytes();require(sha(tzif)==NY_SHA,'Locked NY bytes');merge(sources,str(NY_SOURCE),NY_SHA)
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Frozen numerical core');merge(sources,str(CORE),CORE_SHA);guard(sources)
    core=types.ModuleType('_fresh_original8_long_channel');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,prepared,*blobs,tzif,core
def save(path,value):
    blob=encoded(value)
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Durable output bytes');return dict(path=str(path),sha256=sha(blob))
def run():
    require(not OUTPUT.exists(),'Immutable original8 namespace exists');docs,refs,sources,prepared,raw,receipt,tzif,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,input_references=refs,planned_new_raw_channel_count=1,planned_sealed_channel_reuse_count=7,retry_allowed=False,**dict.fromkeys(FLAGS,False)))
        value=assemble(prepared,raw,receipt,tzif,core,docs,refs);value['source_hashes']=sources;guard(sources);out=save(OUTPUT/'channels.json',value);guard(sources)
        publication=save(OUTPUT/'publication.json',dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_CHANNELS_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK',channels_reference=out,source_hashes=sources,**dict.fromkeys(FLAGS,False)))
        guard(sources);require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(publication['path']).read_bytes())==publication['sha256'],'Final output readback');require({p.name for p in OUTPUT.iterdir()}=={'started.json','channels.json','publication.json'},'Exact output namespace');return out
    except Exception as exc:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(exc),retry_allowed=False));raise

if __name__=='__main__':print(json.dumps(run()))
