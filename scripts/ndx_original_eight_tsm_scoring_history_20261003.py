"""TSM control-only505; reuse saved metadata, one new raw decode, no score or fit."""
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
CORE=ROOT/'backtest/ndx_original_eight_tsm_scoring_history_research.py';CORE_SHA='d5a085f054aea5d55535bdb20522a147d779bfe84d73efea82cb3e6547ff7e7b'
OUTPUT=ROOT/'data/cache/research/original_eight_tsm_scoring_history_20261003_v1'
NY_SOURCE=Path(r'D:\python\Lib\site-packages\tzdata\zoneinfo\America\New_York')
NY_SHA='d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9'
BOUND={'history': ('data/cache/research/bulk_history_requirements_20261003_v1/requirements.json', 'f3a317fd00800fe025003479358a6798cd893d4305511bcb1c39eb73ae94e2f5'), 'history_publication': ('data/cache/research/bulk_history_requirements_20261003_v1/publication.json', '171f4218d2ec3997b53d21d9e0e4c6081425ae963f79e7b7d0b3c5fa2ea5d13d'), 'history_audit': ('DYNAMIC_BULK_HISTORY_REQUIREMENTS_INDEPENDENT_READBACK_20261003.json', '22928d8aaa756f11bd7071f7ef4544cfaeca2e17206b46f7dc273a4c6f0ded9d'), 'history_audit_report': ('DYNAMIC_BULK_HISTORY_REQUIREMENTS_INDEPENDENT_READBACK_20261003.md', 'fcd9f8f97bd15dd255e7fdb497af034cee69e86564345f85078205618ab60217'), 'history_audit_reader': ('scripts/ndx_bulk_history_requirements_independent_review_20261003.py', '64652e1966f2f97fbfd3cd02d23018875b36a83fb06cf6657fddb4ff8154ddbd'), 'requirements': ('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/requirements.json', '95461ba7b298347d969fe65cb3b93aa5632fecfdf331f1ba7a42af6abdee1c47'), 'requirements_publication': ('data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1/publication.json', 'bf9290f263f92523d7bd2001d138321ef429705aa96ec494e665ec15dead8766'), 'requirements_audit_report': ('DYNAMIC_BULK_LONG_WINDOW_BENCHMARK_INDEPENDENT_READBACK_20261003.md', '803803bebc421a49b48755a6b22ea4b810bbfdbd88f1eca41582c5c5b2820655'), 'requirements_audit_reader': ('scripts/ndx_bulk_long_window_benchmark_independent_review_20261003.py', 'eaecf87e9c119a618ece888ffb9c1ce6270f4ee4e987e1393cfe45b8aa7b98d9'), 'control': ('data/cache/research/ndx_original_8_control_v1/manifest.json', '2ca955ce951061a2aa89242c53c645775f36a658e2f51db1dc3732582317a260'), 'original_channels': ('data/cache/research/original_eight_long_window_channels_20261003_v1/channels.json', '67d433ae92acb0755a1ffdabf090e6c20706b4d1ba893637673e96a047acc372'), 'original_publication': ('data/cache/research/original_eight_long_window_channels_20261003_v1/publication.json', '836622bff616370375539490c441fbb5b988d5dab8b661b202991288bcbf05e1'), 'original_audit': ('DYNAMIC_ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_20261003.json', '182e901ad1554292444142c51ace220da2f1912b361d048d78b499d5aeaeb988'), 'original_reader': ('scripts/ndx_original_eight_long_window_independent_review_20261003.py', '738e876b8e03cc2d2892a34b2c254c4ea8cc91e191e03acca55d15110b4bd469')}
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


ROLE='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE'
ORDER=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']

def prepare(docs,refs):
    h=docs['history'];r=docs['requirements'];req=r['requirements'];saved=docs['original_channels']
    for role,schema,status,field in [('history','BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1','PUBLISHED_REQUIREMENTS_ONLY','requirements_reference'),('requirements','BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1','PUBLISHED_REQUIREMENTS_ONLY','requirements_reference'),('original','ORIGINAL_EIGHT_LONG_WINDOW_CHANNELS_PUBLICATION_V1','PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK','channels_reference')]:
        pub=docs[role+'_publication'];parent='original_channels' if role=='original' else role
        require(pub['schema']==schema and pub['status']==status,'Successful parent publication')
        exact(pub[field],refs[parent],'Parent reference');exact(pub['source_hashes'],docs[parent]['source_hashes'],'Parent source claims')
    a=docs['original_audit'];require(a['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_V1' and a['status']=='PASS' and a['channels_sha256']==refs['original_channels']['sha256'] and a['publication_sha256']==refs['original_publication']['sha256'] and a['reader_sha256']==refs['original_reader']['sha256'],'Saved TSM audit')
    ha=docs['history_audit'];require(ha['status']=='PASS' and ha['requirements_sha256']==refs['history']['sha256'] and ha['publication_sha256']==refs['history_publication']['sha256'] and ha['reader_sha256']==refs['history_audit_reader']['sha256'],'History audit')
    require(h['schema']=='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1' and r['schema']=='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1' and saved['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1','Saved schemas')
    for v in (h,r,saved):require(all(v[k] is False for k in ('fit_performed','point_in_time_verified','execution_authorized','promotion_allowed','legal_training_input_admitted')),'No authority upgrade')
    control=req['original_control_preserved'];exact(control['complete_original_manifest'],docs['control'],'Full original manifest');exact(control['complete_original_definition'],docs['control']['definition'],'Original definition')
    securities=control['securities'];exact(securities,docs['control']['definition']['securities'],'Original weights');exact([x['ticker'] for x in securities],ORDER,'Original8 order');exact(saved['original_control_preserved'],control,'Saved control')
    m=req['stock_metadata_preserved']['TSM'];row=saved['rows'][4]
    exact(row['original_control_security'],securities[4],'TSM row');exact(row['complete_benchmark_metadata'],m,'Original TSM metadata')
    require(m['security_id']=='security:incumbent_overlay:TSM' and m['control_only_overlay'] is True and m['shares_or_prices_converted'] is False,'Control overlay only')
    side=m['complete_identity_sidecar'];require(side['ticker']=='TSM' and side['issuer_id']=='issuer:0001046179' and side['security_id']==m['security_id'] and side['cusip']=='874039100' and side['security_class']=='American Depositary Shares' and type(side['ordinary_shares_per_ads']) is int and side['ordinary_shares_per_ads']==5,'ADS original identity')
    for k in ('historical_2023_identity_interval_verified','point_in_time_verified','ndx_membership_verified','price_identity_verified','holdings_conversion_performed','promotion_allowed'):require(side[k] is False,'Conditional identity only')
    bridge=row['conditional_event_policy_bridge'];exact(bridge,row['channel']['bridge_row_preserved'],'Sealed conditional bridge')
    for k,n in [('raw_reference','new_raw_reference'),('receipt_reference','new_receipt_reference')]:exact(m[k],bridge[n],'Source binding');exact(a[k],m[k],'Audit raw reference')
    require(bridge['new_decoded_sha256']==m['decoded_sha256'] and bridge['new_returned_splits']==m['returned_events'].get('splits',{})=={} and bridge['event_policy_bridge']==dict(events=[],regular_floor=None),'Saved empty split/floor basis only')
    dates=h['requirements']['reference_calendar'];require(dates['ticker']=='AAPL' and len(dates['dates'])==1183,'Full AAPL1183 provider calendar')
    exact([x['session'] for x in m['observation_rows']],dates['dates'],'Original full TSM observation calendar')
    return dict(raw_reference=deepcopy(m['raw_reference']),receipt_reference=deepcopy(m['receipt_reference']),bridge_row=deepcopy(bridge),reference_calendar=deepcopy(dates['dates']),window_contract=deepcopy(CONTRACT),original_control_contract=dict(role=ROLE,control_reference=deepcopy(refs['control']),securities=deepcopy(securities),selected_security_id=m['security_id'],identity_evidence=deepcopy(m['identity_evidence']),risk_evidence=deepcopy(m['risk_evidence'])))


def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper drift')
    for path,h in sources.items():
        p=Path(path);require(not (p.parent/'failure.json').exists(),'Source failure marker')
        require(sha(p.read_bytes())==h,'Source drift '+path)


def load_inputs():
    require(type(CORE_SHA) is str and len(CORE_SHA)==64 and all(type(h) is str and len(h)==64 for _,h in BOUND.values()),'Pending anchors before IO')
    sources={str(SOURCE):LOADED_SHA};docs={};refs={}
    for k,(relative,h) in BOUND.items():
        p=ROOT/relative;raw=p.read_bytes();require(sha(raw)==h,'Hard parent '+k);merge(sources,str(p),h);refs[k]=dict(path=str(p),sha256=h)
        if not k.endswith(('_reader','_report')):docs[k]=loads(raw)
    args=prepare(docs,refs)
    for field in ('raw_reference','receipt_reference'):
        r=args[field];b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Bound TSM bytes');merge(sources,r['path'],r['sha256'])
        args['raw_bytes' if field=='raw_reference' else 'receipt']=b if field=='raw_reference' else loads(b)
    exact(args['receipt'],docs['requirements']['requirements']['stock_metadata_preserved']['TSM']['original_receipt'],'Original receipt full')
    args['tzif_bytes']=NY_SOURCE.read_bytes();require(sha(args['tzif_bytes'])==NY_SHA,'TZif bytes');merge(sources,str(NY_SOURCE),NY_SHA)
    raw=CORE.read_bytes();require(sha(raw)==CORE_SHA,'Pure source');merge(sources,str(CORE),CORE_SHA);guard(sources)
    core=types.ModuleType('_private_tsm505');exec(compile(raw,str(CORE),'exec'),core.__dict__)
    return docs,refs,sources,args,core


def space(size):
    p=OUTPUT.parent
    while not p.exists():p=p.parent
    require(shutil.disk_usage(p).free>=5*1024**3+size,'Resource reserve plus bytes')


def save(path,value,failure=False):
    b=encoded(value)
    if not failure:space(len(b))
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved bytes');return dict(path=str(path),sha256=sha(b))


def run(*,execute=False):
    require(execute is True,'Explicit execute');require(not OUTPUT.exists(),'Immutable namespace')
    docs,refs,sources,args,core=load_inputs();space(0);OUTPUT.mkdir(parents=True,exist_ok=False);written=[]
    try:
        written.append(save(OUTPUT/'started.json',dict(schema='TSM_CONTROL_SCORING_HISTORY_STARTED_V1',input_references=refs,source_hashes=sources,planned_raw_decode_count=1,retry_allowed=False)))
        channel=core.materialize_tsm_control_history(**args)
        require(channel['schema']=='ORIGINAL_EIGHT_TSM_SCORING_HISTORY_CHANNEL_V1' and channel['role']==ROLE and channel['ticker']=='TSM','Only TSM output')
        for k in ('fit_performed','score_computed','source_bytes_authenticated','ndx_candidate_admitted','holdings_or_ads_converted','point_in_time_verified'):require(channel[k] is False,'No output authority')
        for k in ('raw_reference','receipt_reference','original_control_contract','window_contract'):exact(channel[k],args[k],'Output binding')
        exact(channel['bridge_row_preserved'],args['bridge_row'],'Output bridge');require(len(channel['decisions'])==6 and all(len(d['windows'])==13 for d in channel['decisions']),'All78 windows')
        guard(sources)
        result=dict(schema='TSM_CONTROL_SCORING_HISTORY_DOCUMENT_V1',status='PUBLISHED_CONTROL_NUMBERS_PENDING_INDEPENDENT_READBACK',role=ROLE,channel=channel,original_control_preserved=deepcopy(docs['requirements']['requirements']['original_control_preserved']),complete_tsm_metadata=deepcopy(docs['requirements']['requirements']['stock_metadata_preserved']['TSM']),input_references=refs,source_hashes=deepcopy(sources),raw_decode_count=1,other_seven_channels_recomputed=False,new_independent_numeric_readback_completed=False,score_computed=False,**dict.fromkeys(FLAGS,False))
        out=save(OUTPUT/'channel.json',result);written.append(out)
        written.append(save(OUTPUT/'publication.json',dict(schema='TSM_CONTROL_SCORING_HISTORY_PUBLICATION_V1',status=result['status'],channel_reference=out,input_references=refs,source_hashes=sources,**dict.fromkeys(FLAGS,False))))
        guard(sources);require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in written},'Exact output namespace')
        for r in written:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Output drift')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),saved_references=written,retry_allowed=False),failure=True);raise


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
