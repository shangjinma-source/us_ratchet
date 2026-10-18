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
PARENT=ROOT/'data/cache/research/original_eight_tsm_scoring_history_20261003_v1'
OUTPUT=ROOT/'data/cache/research/tsm_scoring_history_independent_readback_20261003_v1'
CHANNEL_SHA='85779cc0bdca5ed70a496626c697d157089064a314e51b27b74b5e412c021a93'
PUBLICATION_SHA='6011dd0df112123c81c3c17e6db9437c08ac68d04853a157f9a451430785e033'
PRODUCER=ROOT/'scripts/ndx_original_eight_tsm_scoring_history_20261003.py'
PRODUCER_SHA='94239f91d0fd2a072ec05b89f60e542c5b6745c456da246843c21bf15698e8f1'
INSPECTOR=ROOT/'backtest/ndx_tsm_scoring_history_inspection_research.py'
INSPECTOR_SHA='8f95a2c9c786c972d449a15cf424788932414291d886dcbd9d20867de942a5b7'
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


def inspect_evidence(document,publication,started,docs,refs,producer_sources):
    require(document['schema']=='TSM_CONTROL_SCORING_HISTORY_DOCUMENT_V1' and publication['schema']=='TSM_CONTROL_SCORING_HISTORY_PUBLICATION_V1' and started['schema']=='TSM_CONTROL_SCORING_HISTORY_STARTED_V1','Output schemas')
    for x in (document,publication):
        require(x['status']=='PUBLISHED_CONTROL_NUMBERS_PENDING_INDEPENDENT_READBACK','Pending numerical audit state')
        exact(x['input_references'],refs,'All direct input references');exact(x['source_hashes'],producer_sources,'Independent producer source closure')
        require(all(x[k] is False for k in FLAGS),'All output permissions')
    exact(started['input_references'],refs,'Started refs');exact(started['source_hashes'],producer_sources,'Started closure')
    require(type(started['planned_raw_decode_count']) is int and started['planned_raw_decode_count']==1 and started['retry_allowed'] is False,'One planned decode')
    require(document['role']==ROLE and type(document['raw_decode_count']) is int and document['raw_decode_count']==1,'Control single decode')
    for k in ('other_seven_channels_recomputed','new_independent_numeric_readback_completed','score_computed'):require(document[k] is False,'No extra work')
    req=docs['requirements']['requirements'];metadata=req['stock_metadata_preserved']['TSM'];control=req['original_control_preserved'];securities=docs['control']['definition']['securities']
    exact(control['complete_original_manifest'],docs['control'],'Full original manifest');exact(control['complete_original_definition'],docs['control']['definition'],'Original definition');exact(control['securities'],securities,'Fixed weights');exact(document['original_control_preserved'],control,'Preserved control');exact(document['complete_tsm_metadata'],metadata,'Preserved TSM metadata')
    exact([s['ticker'] for s in securities],ORDER,'Full original eight order')
    side=metadata['complete_identity_sidecar'];require(side['ticker']=='TSM' and side['security_id']=='security:incumbent_overlay:TSM' and side['issuer_id']=='issuer:0001046179' and side['cusip']=='874039100' and side['security_class']=='American Depositary Shares' and type(side['ordinary_shares_per_ads']) is int and side['ordinary_shares_per_ads']==5,'Conditional ADS identity')
    for k in ('historical_2023_identity_interval_verified','point_in_time_verified','ndx_membership_verified','price_identity_verified','holdings_conversion_performed','promotion_allowed'):require(side[k] is False,'No identity promotion')
    require(metadata['control_only_overlay'] is True and metadata['shares_or_prices_converted'] is False and metadata['security_id']==securities[4]['security_id']==side['security_id'],'Control overlay metadata')
    parent=docs['original_channels'];row=parent['rows'][4]
    require(parent['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1','Original eight schema')
    exact(parent['original_control_preserved'],control,'Parent control');exact(row['complete_benchmark_metadata'],metadata,'Parent TSM evidence');exact(row['original_control_security'],securities[4],'Parent TSM coordinate')
    bridge=row['conditional_event_policy_bridge'];exact(bridge,row['channel']['bridge_row_preserved'],'Sealed policy bridge')
    require(bridge['new_returned_splits']==metadata['returned_events'].get('splits',{})=={} and bridge['event_policy_bridge']==dict(events=[],regular_floor=None),'Saved TSM empty action basis not certification')
    for role,field,status,schema,parentkey in [('history','requirements_reference','PUBLISHED_REQUIREMENTS_ONLY','BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1','history'),('requirements','requirements_reference','PUBLISHED_REQUIREMENTS_ONLY','BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1','requirements'),('original','channels_reference','PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK','ORIGINAL_EIGHT_LONG_WINDOW_CHANNELS_PUBLICATION_V1','original_channels')]:
        pub=docs[role+'_publication'];require(pub['schema']==schema and pub['status']==status,'Parent publication');exact(pub[field],refs[parentkey],'Parent publication identity');exact(pub['source_hashes'],docs[parentkey]['source_hashes'],'Parent claims')
    for key,field,source,pub,reader in [('history_audit','requirements_sha256','history','history_publication','history_audit_reader'),('original_audit','channels_sha256','original_channels','original_publication','original_reader')]:
        a=docs[key];require(a['status']=='PASS' and a[field]==refs[source]['sha256'] and a['publication_sha256']==refs[pub]['sha256'] and a['reader_sha256']==refs[reader]['sha256'],'Parent audit binding')
    for x in (docs['history'],docs['requirements'],parent):require(all(x[k] is False for k in ('point_in_time_verified','fit_performed','execution_authorized','promotion_allowed','legal_training_input_admitted')),'Conditional parent')
    cal=docs['history']['requirements']['reference_calendar'];require(cal['ticker']=='AAPL' and len(cal['dates'])==1183,'AAPL1183')
    exact([x['session'] for x in metadata['observation_rows']],cal['dates'],'Original observations')
    for k,b in [('raw_reference','new_raw_reference'),('receipt_reference','new_receipt_reference')]:exact(metadata[k],bridge[b],'Bridge original byte ref');exact(docs['original_audit'][k],metadata[k],'Audit original byte ref')
    require(bridge['new_decoded_sha256']==metadata['decoded_sha256'],'Original decoded hash')
    return dict(raw_reference=deepcopy(metadata['raw_reference']),receipt_reference=deepcopy(metadata['receipt_reference']),receipt=deepcopy(metadata['original_receipt']),bridge_row=deepcopy(bridge),reference_calendar=deepcopy(cal['dates']),window_contract=deepcopy(CONTRACT),original_control_contract=dict(role=ROLE,control_reference=deepcopy(refs['control']),securities=deepcopy(securities),selected_security_id=metadata['security_id'],identity_evidence=deepcopy(metadata['identity_evidence']),risk_evidence=deepcopy(metadata['risk_evidence'])))


def take(path,h,sources):
    require(not (path.parent/'failure.json').exists(),'Source namespace failure')
    raw=path.read_bytes();require(sha(raw)==h,'Bound source bytes '+str(path));merge(sources,str(path),h);return raw


def guard(sources):
    require({p.name for p in PARENT.iterdir()}=={'started.json','channel.json','publication.json'},'Exact successful producer namespace')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded reader drift')
    for path,h in sources.items():
        p=Path(path);require(not (p.parent/'failure.json').exists(),'Source failure marker');require(sha(p.read_bytes())==h,'Source drift')


def save(path,value):
    b=encoded(value)
    with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==b,'Saved report');return dict(path=str(path),sha256=sha(b))


def readback(*,execute=False):
    require(execute is True,'Explicit execute')
    require(all(type(x) is str and len(x)==64 for x in (CHANNEL_SHA,PUBLICATION_SHA,PRODUCER_SHA,INSPECTOR_SHA)),'Future external anchors before IO')
    require(not OUTPUT.exists(),'Immutable audit namespace');require({p.name for p in PARENT.iterdir()}=={'started.json','channel.json','publication.json'},'Exact successful producer namespace')
    sources={};docs={};refs={};base={str(PRODUCER):PRODUCER_SHA,str(CORE):CORE_SHA,str(NY_SOURCE):NY_SHA}
    for role,(relative,h) in BOUND.items():
        p=ROOT/relative;b=take(p,h,sources);refs[role]=dict(path=str(p),sha256=h);base[str(p)]=h
        if not role.endswith(('_reader','_report')):docs[role]=loads(b)
    for path,h in ((PRODUCER,PRODUCER_SHA),(CORE,CORE_SHA)):take(path,h,sources)
    tzif=take(NY_SOURCE,NY_SHA,sources)
    meta=docs['requirements']['requirements']['stock_metadata_preserved']['TSM'];raw=take(Path(meta['raw_reference']['path']),meta['raw_reference']['sha256'],sources);receipt=loads(take(Path(meta['receipt_reference']['path']),meta['receipt_reference']['sha256'],sources))
    for k in ('raw_reference','receipt_reference'):merge(base,meta[k]['path'],meta[k]['sha256'])
    exact(receipt,meta['original_receipt'],'Consumed receipt object')
    document=loads(take(PARENT/'channel.json',CHANNEL_SHA,sources));publication=loads(take(PARENT/'publication.json',PUBLICATION_SHA,sources))
    # Started is authenticated by same-read hash, not an external standalone anchor.
    sb=(PARENT/'started.json').read_bytes();merge(sources,str(PARENT/'started.json'),sha(sb));started=loads(sb)
    exact(publication['channel_reference'],dict(path=str(PARENT/'channel.json'),sha256=CHANNEL_SHA),'Publication channel reference')
    args=inspect_evidence(document,publication,started,docs,refs,base)
    code=take(INSPECTOR,INSPECTOR_SHA,sources);merge(sources,str(SOURCE),LOADED_SHA);guard(sources)
    private=types.ModuleType('_private_tsm_inspector');exec(compile(code,str(INSPECTOR),'exec'),private.__dict__)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        own_started=save(OUTPUT/'started.json',dict(schema='TSM_CONTROL_SCORING_HISTORY_READBACK_STARTED_V1',source_hashes=sources))
        arithmetic=private.inspect_tsm_control_history(saved_channel=document['channel'],raw_bytes=raw,tzif_bytes=tzif,**args)
        guard(sources)
        out=save(OUTPUT/'independent_readback.json',dict(schema='TSM_CONTROL_SCORING_HISTORY_INDEPENDENT_READBACK_V1',status='PASS',channel_reference=dict(path=str(PARENT/'channel.json'),sha256=CHANNEL_SHA),publication_reference=dict(path=str(PARENT/'publication.json'),sha256=PUBLICATION_SHA),reader_sha256=LOADED_SHA,arithmetic=arithmetic,source_hashes=sources,started_external_anchor_available=False,other_seven_channels_recomputed=False,**dict.fromkeys(FLAGS,False)))
        guard(sources);require(all(sha(Path(r['path']).read_bytes())==r['sha256'] for r in (own_started,out)) and {p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Final audit output')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),retry_allowed=False));raise


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
