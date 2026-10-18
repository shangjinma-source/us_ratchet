"""Long-window benchmark requirements only, with immutable direct sources."""
from copy import deepcopy
import csv
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import types
from urllib.parse import urlparse

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_long_window_benchmark_requirements_research.py';CORE_SHA='eef682a2570860dc6eaf42e4beb9b871c98d53b09eb1090a3fda3b78e0b7be49'
OUTPUT=ROOT/'data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1'
BOUND={'control': ('data/cache/research/ndx_original_8_control_v1/manifest.json', '2ca955ce951061a2aa89242c53c645775f36a658e2f51db1dc3732582317a260'), 'readback': ('data/cache/research/new_cutoff_raw_readback_20260923_v1/completed102.json', '7c03247919319c8e1a1a12be2fd8ccdba59aec20e0d9ee6634e69cc85fd0d53b'), 'index': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/completion_index_102.json', '59e8573257a2d55aa80c8a2788e48fe756b7f2fd96eabc672f2d97f5789140fb'), 'nav_csv': ('data/cache/research/new_cutoff_nav_snapshot_20260923_v1/nav.csv', '020f3e636c732259dedb796606de49b89a0ee7df0263442ddae5f3e73dc76d1f'), 'nav_manifest': ('data/cache/research/new_cutoff_nav_snapshot_20260923_v1/original_manifest.json', 'dcb18867c3b4f75192927ca66f05ad972490bbf6b45f0aea275af4547575ae38'), 'nav_snapshot': ('data/cache/research/new_cutoff_nav_snapshot_20260923_v1/snapshot.json', '7b2303f0ab5618ef35790d24637681e8ce58463f846ef303bf62acf7fa681061'), 'wiring': ('data/cache/research/bulk_conditional_wiring_20261003_v1/wiring.json', 'e4f4328043254667ff334ebc7aaf0fe530d451339f5b9d4b1ba0a20c37b9b8a5'), 'tsm': ('data/cache/research/tsm_incumbent_identity_20261002_v1/identity.json', '0bf3f51697fbf09966d6f20454c3a70552e97cbfe8f8bbbe6ad729f304eafbe9'), 'tsm_publication': ('data/cache/research/tsm_incumbent_identity_20261002_v1/publication.json', 'a0dc16ce41f0930ed408b3aba0f4d63a37febec871dc8c14c7c49d281bcda236'), 'asml': ('data/cache/research/asml_incumbent_identity_20261002_v1/identity.json', '85cdde6403d93a544679886c5b85b7c68fb9fd8e7657ad84ea8ac5c9591d544d'), 'asml_publication': ('data/cache/research/asml_incumbent_identity_20261002_v1/publication.json', '87836bfddc6fe331db194b23df308c51e460c062b4c2d34ee4e67c0786001784'), 'currency_listing': ('data/cache/research/fund_012922_currency_source_20261002_v1/issuer_listing.html', '89f8a7a02aa843193bbfab8acd3a273ff7053d69fcc4256f242eb453dc43d292'), 'currency_manifest': ('data/cache/research/fund_012922_currency_source_20261002_v1/manifest.json', 'ff4f51f7463f0c805f6ae0542aea46883ba2476b416364d293d93d7026a5b284'), 'receipt_NVDA': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/NVDA.receipt.json', 'e501263328699a9e1ebb6fdf4b7f7a34432b13555832ff3a4c636ea91ebbc532'), 'receipt_TXN': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/TXN.receipt.json', '5511bddc51f6f61b62826eb9af01adcd6d74a89975d0ac7893dbac7bda958bd1'), 'receipt_ASML': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/ASML.receipt.json', 'bb7a6b7292360b6db86dabec5e0380489142f5011ea063ebb23c7507c4e1fda0'), 'receipt_CDNS': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/CDNS.receipt.json', 'e3131ca192aca3d965f1a6947a1234fa15fe3de733a088df4820bfa2bf9c8377'), 'receipt_TSM': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/TSM.receipt.json', '5c8e30012c5a7c03dd0739d5cc0b4382fd79a61ca5067cb5d5155bd2851ac604'), 'receipt_MU': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/MU.receipt.json', 'ce6e5c91e8af018fe4b60c8a1a7d2bb3599e09abb878c1f8ec147b5cee1782ef'), 'receipt_MSFT': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/MSFT.receipt.json', 'cc2fa41b702b1f275906c5f873d5d72c5f73a0d93c798b34701ded6d023c11af'), 'receipt_GOOG': ('data/cache/research/new_cutoff_raw_capture_20260923_v1/GOOG.receipt.json', '675d08417f68a788014426014fc01da31204cdfb76d5a424fa19d49a4488a6cf'), 'source_contract': ('DYNAMIC_BULK_LONG_WINDOW_BENCHMARK_INPUTS_20261003.md', '099ce5232e0548eb1e6f748065b346ad4b928334cfc913cc58e89274137a423d')}
TICKERS=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
FLAGS=('http_performed','prices_reconstructed','raw_decoding_reperformed','old_audit_repeated','returns_computed','account_simulation_performed','fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','benchmark_qualified','evaluation_executed','historical_identity_verified','historical_currency_verified','fx_equivalence_verified','nav_publication_verified','full_transitive_source_closure_reverified')
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def canonical(d):require(type(d) is str and date.fromisoformat(d).isoformat()==d,'Canonical date')
def reference(r):require(type(r) is dict and {'path','sha256'}<=set(r)<= {'path','sha256','json_pointer'} and type(r['sha256']) is str and len(r['sha256'])==64,'Explicit source reference')
def loads(blob):
    def pairs(items):
        result={}
        for k,v in items:require(k not in result,'Duplicate JSON key');result[k]=v
        return result
    def invalid(v):raise ValueError('Nonfinite JSON '+v)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=invalid)

def project_inputs(docs,refs):
    control=docs['control'];securities=control['definition']['securities'];require([r['ticker'] for r in securities]==TICKERS and len({r['security_id'] for r in securities})==8 and len({r['issuer_id'] for r in securities})==8,'Original8 complete fixed order')
    require(control['promotion_allowed'] is False and type(control['live_mutation']) is dict and set(control['live_mutation'])=={'broker','config','orders','state','today_advice'} and all(v is False for v in control['live_mutation'].values()),'Research control')
    require(securities[4]['security_id']=='security:incumbent_overlay:TSM','Original overlay unchanged')
    readback=docs['readback'];require(readback['schema']=='NEW_CUTOFF_INDEPENDENT_RAW_READBACK_V1' and len(readback['rows'])==102,'Sealed102 observation source')
    observed={r['ticker']:(i,r) for i,r in enumerate(readback['rows'])};entries={r['ticker']:(i,r) for i,r in enumerate(docs['index']['entries'])};require(len(observed)==len(entries)==102,'Unique channel indexes')
    require(readback['index_path']==refs['index']['path'] and readback['index_sha256']==refs['index']['sha256'],'Readback index linkage')
    ai,aapl=observed['AAPL'];dates=[]
    for row in aapl['observation']['rows']:
        d=row['new_york_date'];canonical(d)
        if d<='2026-09-21' and row['excluded_receipt_day_or_later'] is False:dates.append(d)
    require(dates==sorted(set(dates)) and len(dates)>=253 and dates[-1]=='2026-09-21','Unfiltered complete AAPL calendar')
    dates=dates[-253:];require(dates[0]=='2025-09-18' and dates[126]=='2026-03-20' and dates[127]=='2026-03-23','Exact253/126 freeze and first evaluation predecessor')
    wire=docs['wiring'];wireby={r['ticker']:(i,r) for i,r in enumerate(wire['rows'])};require(len(wire['rows'])==len(wireby)==101,'Full conditional wiring')
    stock={}
    for i,security in enumerate(securities):
        t=security['ticker'];oi,ch=observed[t];ei,entry=entries[t];receipt=docs['receipt_'+t];obs=ch['observation'];rr=refs['receipt_'+t]
        require(entry['receipt_path']==rr['path'] and entry['receipt_sha256']==rr['sha256']==ch['receipt_sha256'],'Receipt index/readback binding')
        require(receipt['ticker']==t==obs['ticker']==obs['raw_provider_meta']['symbol'] and receipt['http_status']==ch['http_status']==200 and ch['readback_status']=='RAW_CHANNEL_READBACK_ONLY','Saved exact ticker status')
        require(urlparse(receipt['request_url']).path.endswith('/chart/'+t) and receipt['request_method']=='GET' and receipt['credentials_sent'] is False,'Original request ticker and method')
        require(receipt['point_in_time_verified'] is False and receipt['promotion_allowed'] is False,'Receipt does not grant PIT')
        rawref=dict(path=receipt['raw_path'],sha256=receipt['raw_sha256']);reference(rawref);require(readback['source_hashes'].get(rawref['path'])==rawref['sha256'],'Raw SHA agrees with sealed readback, no new decode')
        observations=[]
        for j,row in enumerate(obs['rows']):
            d=row['new_york_date'];canonical(d);require(type(row['excluded_receipt_day_or_later']) is bool and row['excluded_receipt_day_or_later']==(d>=ch['receipt_new_york_day']),'Receipt day exclusion')
            if d<='2026-09-21' and not row['excluded_receipt_day_or_later']:
                observations.append(dict(session=d,missing_fields=deepcopy(row['missing_fields']),source_json_pointer=f'/rows/{oi}/observation/rows/{j}'))
        require([r['session'] for r in observations]==sorted({r['session'] for r in observations}),'Original dates not compressed')
        identity=[];metadata={}
        if t!='TSM':
            wi,w=wireby[t];require(w['coordinate']['security_id']==security['security_id'] and w['coordinate']['issuer_id']==security['issuer_id'],'Conditional coordinate matches original control')
            identity.append(dict(refs['wiring'],json_pointer=f'/rows/{wi}'));metadata['complete_conditional_wiring_row']=deepcopy(w)
        if t in ('TSM','ASML'):
            role=t.lower();side=docs[role];publication=docs[role+'_publication'];require(publication['status']=='PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY' and publication['identity_reference']==refs[role] and publication['source_hashes']==side['source_hashes'],'Completed identity sidecar publication')
            require(side['ticker']==t and side['security_id']==security['security_id'] and side['issuer_id']==security['issuer_id'],'Sidecar conditional coordinate')
            require(side['point_in_time_verified'] is False and side['promotion_allowed'] is False,'Sidecar permission')
            identity.append(refs[role]);metadata['complete_identity_sidecar']=deepcopy(side);metadata['sidecar_publication_reference']=refs[role+'_publication']
        stock[t]=dict(security_id=security['security_id'],raw_reference=rawref,receipt_reference=deepcopy(rr),receipt_binding=dict(ticker=t,raw_reference=deepcopy(rawref)),observation_reference=dict(refs['readback'],json_pointer=f'/rows/{oi}'),observation_rows=observations,identity_evidence=identity,risk_evidence=[dict(refs['control'],json_pointer=f'/definition/securities/{i}')],complete_original_control_security=deepcopy(security),original_receipt=deepcopy(receipt),original_capture_index_entry=deepcopy(entry),decoded_sha256=obs['decoded_sha256'],returned_events=deepcopy(obs['raw_returned_events']),quote_price_unit=obs['quote_price_unit'],volume_unit=obs['volume_unit'],observed_provider_currency=obs['raw_provider_meta'].get('currency'),provider_currency_historical_continuity_verified=False,control_only_overlay=t=='TSM',shares_or_prices_converted=False,**metadata)
    snap=docs['nav_snapshot'];manifest=docs['nav_manifest'];require(snap['schema']=='NEW_CUTOFF_LOCAL_NAV_BYTES_SNAPSHOT_V1' and snap['dataset_key']=='012922','NAV snapshot')
    for name,role in [('nav.csv','nav_csv'),('original_manifest.json','nav_manifest')]:exact(snap['immutable_copies'][name],refs[role],'Immutable NAV copy')
    require(manifest['content_sha256']==refs['nav_csv']['sha256'] and manifest['publication_time_known'] is False and snap['nav_publication_time_verified'] is False,'NAV byte/publication binding')
    navrows=docs['nav_csv'];require(type(manifest['row_count']) is int and len(navrows)==manifest['row_count'],'Full original NAV row count')
    nav=[]
    for i,row in enumerate(navrows):canonical(row['Date']);nav.append(dict(date=row['Date'],row_index=i,source_reference=deepcopy(refs['nav_csv'])))
    require([r['date'] for r in nav]==sorted({r['date'] for r in nav}),'NAV chronological distinct rows')
    cm=docs['currency_manifest'];exact(cm['source_reference'],refs['currency_listing'],'Currency listing bytes');require(cm['nav_dataset_currency_binding_certified'] is False and cm['fx_rates_supplied'] is False and cm['point_in_time_verified'] is False,'Currency evidence remains current-only')
    args=dict(reference_calendar=dict(ticker='AAPL',dates=dates,source_reference=dict(refs['readback'],json_pointer=f'/rows/{ai}/observation/rows')),original_control=dict(source_reference=deepcopy(refs['control']),securities=deepcopy(securities),complete_original_definition=deepcopy(control['definition']),complete_original_manifest=deepcopy(control),new_execution_contract_frozen=False),stock_metadata=stock,nav_metadata=dict(source_reference=deepcopy(refs['nav_csv']),manifest_reference=deepcopy(refs['nav_manifest']),snapshot_reference=deepcopy(refs['nav_snapshot']),rows=nav,publication_time_known=False,selected_value_column='Close',selected_value_semantics='SAVED_UNIT_NAV_NOT_ACCUMULATED_NAV',complete_saved_manifest=deepcopy(manifest),complete_saved_snapshot=deepcopy(snap),current_currency_listing_reference=deepcopy(refs['currency_listing']),complete_currency_listing_manifest=deepcopy(cm),currency_manifest_reference=deepcopy(refs['currency_manifest'])),fx_metadata=dict(bound=False,source_reference=None,scope='NO_BOUND_HISTORICAL_USD_CNY_SEQUENCE_IN_THIS_REQUIREMENTS_DOCUMENT_NOT_REPOSITORY_ABSENCE_CLAIM',rates_computed=False,conversion_performed=False))
    return args

def validate_result(value,args):
    require(value['schema']=='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1' and value['status']=='BENCHMARK_INPUT_REQUIREMENTS_ONLY_NOT_EVALUATED','Pure requirements schema')
    for target,source in [('reference_calendar','reference_calendar'),('original_control_preserved','original_control'),('stock_metadata_preserved','stock_metadata'),('nav_metadata_preserved','nav_metadata'),('fx_metadata_preserved','fx_metadata')]:exact(value[target],args[source],'Complete preserved requirement inputs')
    require(type(value['stock_denominator']) is int and value['stock_denominator']==8 and value['stock_date_requirement_count']==2024 and value['nav_date_requirement_count']==253 and len(value['nav_date_mappings'])==253,'Complete 253x8/NAV scope')
    require(all(value[k] is False for k in ('promotion_allowed','evaluation_executed','benchmark_qualified','point_in_time_verified','legal_training_input_admitted','execution_authorized')),'Requirements do not qualify benchmark')
    require(value['content_sha256']==sha(encoded({k:v for k,v in value.items() if k!='content_sha256'})),'Pure output hash')


def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Direct source drift '+p)
def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64,'Pure core pin pending');docs={};refs={};sources={str(SOURCE):LOADED_SHA}
    for role,(relative,h) in BOUND.items():
        path=ROOT/relative;blob=path.read_bytes();require(sha(blob)==h,'Hard source bytes');sources[str(path)]=h;refs[role]=dict(path=str(path),sha256=h)
        if role=='nav_csv':
            reader=csv.DictReader(io.StringIO(blob.decode('utf-8-sig')));require(reader.fieldnames==['Date','UnitNav','AccumNav','DailyPct','Close'],'Saved NAV CSV columns');docs[role]=list(reader)
        elif role not in ('source_contract','currency_listing'):docs[role]=loads(blob)
    for role in ('tsm','asml'):
        require({p.name for p in Path(refs[role]['path']).parent.iterdir()}=={'identity.json','publication.json'},'Sidecar failed/incomplete namespace')
    blob=CORE.read_bytes();require(sha(blob)==CORE_SHA,'Frozen core bytes');sources[str(CORE)]=CORE_SHA;guard(sources)
    core=types.ModuleType('_fresh_benchmark_requirements');core.__file__=str(CORE);exec(compile(blob,str(CORE),'exec'),core.__dict__);return docs,refs,sources,core

def save(path,value):
    blob=encoded(value)
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Output bytes');return dict(path=str(path),sha256=sha(blob))
def run():
    require(not OUTPUT.exists(),'Immutable requirements namespace exists');docs,refs,sources,core=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(source_hashes=sources,retry_allowed=False,**dict.fromkeys(FLAGS,False)))
        args=project_inputs(docs,refs);result=core.prepare_benchmark_requirements(**args)
        validate_result(result,args)
        value=dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1',requirements=result,input_references=refs,source_hashes=sources,raw_price_responses_reopened=False,**dict.fromkeys(FLAGS,False));guard(sources);out=save(OUTPUT/'requirements.json',value);guard(sources)
        receipt=save(OUTPUT/'publication.json',dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=out,source_hashes=sources,**dict.fromkeys(FLAGS,False)))
        guard(sources);require(sha(Path(out['path']).read_bytes())==out['sha256'] and sha(Path(receipt['path']).read_bytes())==receipt['sha256'],'Final readback');return out
    except Exception as exc:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(exc),retry_allowed=False));raise

if __name__=='__main__':print(json.dumps(run()))
