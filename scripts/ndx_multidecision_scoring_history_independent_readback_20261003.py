"""Independent saved77 source readback; invokes only a pinned arithmetic inspector."""
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
PARENT=ROOT/'data/cache/research/multidecision_scoring_history_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_scoring_history_independent_readback_20261003_v1'
INDEX_SHA='ce4fd8a1a8f7f0c9c1ddd20cd4136c1c078e4aae81b37e61c9a1b0aae981ff2d'
PUBLICATION_SHA='e413e1cb7c10b543042fb7cbc34eafda48c93cfab3f25cd4e5b9f798249e88b9'
PRODUCER=ROOT/'scripts/ndx_multidecision_scoring_history_20261003.py'
PRODUCER_SHA='19d930450ecb80de44254566927fc3d2629daf7f2102bc41390fe608fa3e7ab5'
INSPECTOR=ROOT/'backtest/ndx_multidecision_scoring_history_inspection_research.py'
INSPECTOR_SHA='196694b29e723929569c2367c2e7debbfd332aa18cdd7a112983d6ea7538ff2b'
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

def ref(path,h):return dict(path=str(path),sha256=h)

def take(r,sources):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and type(r['sha256']) is str and len(r['sha256'])==64,'Exact byte reference')
    b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Byte identity '+r['path']);merge(sources,r['path'],r['sha256']);return b


def inspect_inventory(index,publication,docs,refs):
    require(index['schema']=='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1' and publication['schema']=='MULTIDECISION_SCORING_HISTORY_PUBLICATION_V1','Aggregate schemas')
    for d in (index,publication):
        require(d['status']=='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK','Conditional published status')
        for k in FLAGS:require(d[k] is False,'Authority '+k)
        exact(d['input_references'],refs,'Fixed seven parent roles')
    for k in ('score_computed','unequal_window_pooling_allowed','full_ndx_universe_certified','new_independent_numeric_readback_completed'):require(index[k] is False,'Aggregate false '+k)
    require(index['historical_retrospective_only'] is True,'Retrospective scope')
    for k,n in dict(security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,raw_decode_count=77).items():require(type(index[k]) is int and index[k]==n,'Aggregate count '+k)
    h=docs['history'];hp=docs['history_publication'];ha=docs['history_audit'];hr=h['requirements'];p=docs['panel'];panel=p['panel'];bridge=docs['bridge']
    require(h['schema']=='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1' and hr['schema']=='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1','History schema')
    require(hp['schema']=='BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1' and hp['status']=='PUBLISHED_REQUIREMENTS_ONLY','History receipt')
    exact(hp['requirements_reference'],refs['history'],'History ref');exact(hp['source_hashes'],h['source_hashes'],'History claims')
    require(ha['status']=='PASS' and ha['requirements_sha256']==refs['history']['sha256'] and ha['publication_sha256']==refs['history_publication']['sha256'] and ha['reader_sha256']==refs['history_audit_reader']['sha256'],'History audit binding')
    require(p['schema']=='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and panel['schema']=='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','Conditional panel')
    for d in (h,p,panel):
        for k in ('fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted'):require(d[k] is False,'Parent authority')
    columns=panel['universe']['columns'];require(len(columns)==len(set(columns)),'Unique coordinate fields')
    require(all(len(r)==len(columns) for r in panel['universe']['data']),'Full coordinates')
    inventory=[dict(zip(columns,r)) for r in panel['universe']['data']]
    require(len(inventory)==77 and len({x['security_id'] for x in inventory})==77 and len({x['ticker'] for x in inventory})==77 and len({x['issuer_id'] for x in inventory})==76,'Independent77/76 inventory')
    exact(hr['universe'],inventory,'Inventory history join')
    provenance=panel['observed_provenance_and_missing'];require(len(provenance)==101,'All101')
    exact(hr['observed_provenance_and_missing'],provenance,'Original provenance');exact(index['original_provenance_and_missing'],provenance,'Published101')
    expected_sidecars={n:p[n] for n in SIDECARS}
    exact(index['preserved_evidence_sidecars'],expected_sidecars,'All seven sidecars');exact(h['projection_evidence']['complete_panel_sidecars'],expected_sidecars,'History sidecars')
    outer=dict(inventory_reference=dict(refs['panel'],json_pointer='/panel/universe'),security_count=77,issuer_count=76,observed_provenance_count=101,preserved_sidecar_references={n:dict(refs['panel'],json_pointer='/'+n) for n in SIDECARS})
    exact(index['outer_inventory_contract'],outer,'Outer exact evidence references');exact(index['window_contract'],CONTRACT,'Six505/13 contract')
    exact(index['reference_calendar'],hr['reference_calendar'],'Original full calendar')
    require(hr['reference_calendar']['ticker']=='AAPL','Reference provider');dates=hr['reference_calendar']['dates']
    require(type(dates) is list and dates==sorted(set(dates)) and all(date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in dates),'Canonical complete dates')
    require(dates[-1]=='2026-09-21' and all(d in dates and dates.index(d)>=504 for d in CUTOFFS),'Full505 per cutoff')
    exact(hr['original_identity_assumed_window'],dict(first='2026-03-20',last='2026-09-21'),'No identity extension')
    require(bridge['candidate_cutoff']=='2026-09-21' and len(bridge['rows'])==101,'Bridge101');by={x['ticker']:(i,x) for i,x in enumerate(bridge['rows'])};require(len(by)==101,'Unique bridge ticker')
    observations=hr['ticker_observations_preserved'];require(set(observations)=={x['ticker'] for x in inventory},'All77 raw metadata')
    require(type(index['rows']) is list and len(index['rows'])==77,'All77 ordered outputs');jobs=[]
    for i,(coordinate,row) in enumerate(zip(inventory,index['rows'])):
        require(type(row['index']) is int and row['index']==i,'Original row ordinal');exact(row['coordinate'],coordinate,'Original row coordinate')
        ticker=coordinate['ticker'];o=observations[ticker];bi,br=by[ticker]
        exact(o['complete_bridge_row'],br,'Full event bridge');exact(o['bridge_reference'],dict(refs['bridge'],json_pointer=f'/rows/{bi}'),'Bridge pointer')
        for k,bk in [('raw_reference','new_raw_reference'),('receipt_reference','new_receipt_reference')]:exact(o[k],br[bk],'Raw/receipt pointer')
        require(o['decoded_sha256']==br['new_decoded_sha256'],'Decoded binding')
        exact(row['history_observation_reference'],dict(refs['history'],json_pointer='/requirements/ticker_observations_preserved/'+ticker),'Metadata pointer')
        exact(row['original_identity_assumed_window'],o['identity_assumed_window'],'Identity assumption')
        require(row['channel_reference']['path']==str(PARENT/f'channel_{i:03d}.json'),'Fixed channel location')
        jobs.append(dict(row=row,raw_reference=o['raw_reference'],receipt_reference=o['receipt_reference'],bridge_row=br,reference_calendar=dates,outer_inventory_contract=outer))
    return jobs


def inspect_index_row(row,channel):
    require(row['status']==channel['status'] and row['regular_floor']==channel['regular_floor'],'Published blocking state')
    expected=[dict(cutoff=d['cutoff'],status=d['status'],complete_thirteen_window_numeric_supply=d['complete_thirteen_window_numeric_supply'],blocked_window_count=sum(w['status']=='BLOCKED_WINDOW' for w in d['windows'])) for d in channel['decisions']]
    exact(row['decision_coverage'],expected,'Every blocked13-window count')


def guard(sources,refs):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded reader changed')
    for path in [PARENT]+[Path(refs[k]['path']).parent for k in ('history','panel','bridge')]:require(not (path/'failure.json').exists(),'Failed parent')
    require({p.name for p in PARENT.iterdir()}=={'started.json','index.json','publication.json'}|{f'channel_{i:03d}.json' for i in range(77)},'Complete80-file parent namespace')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Final source drift '+p)


def load_inputs():
    pins=[INDEX_SHA,PUBLICATION_SHA,PRODUCER_SHA,CORE_SHA,INSPECTOR_SHA,NY_SHA]+[h for _,h in BOUND.values()]
    require(all(type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h) for h in pins),'Actual anchors pending')
    sources={str(SOURCE):LOADED_SHA};refs={};docs={};base={}
    for role,(relative,h) in BOUND.items():
        refs[role]=ref(ROOT/relative,h);b=take(refs[role],sources);merge(base,refs[role]['path'],h)
        if role not in ('history_audit_report','history_audit_reader'):docs[role]=loads(b)
    for path,h in ((PRODUCER,PRODUCER_SHA),(CORE,CORE_SHA),(NY_SOURCE,NY_SHA)):
        b=take(ref(path,h),sources);merge(base,str(path),h)
        if path==NY_SOURCE:tzif=b
    require(docs['bridge']['source_hashes'].get(str(NY_SOURCE))==NY_SHA,'Frozen timezone provenance')
    index_ref=ref(PARENT/'index.json',INDEX_SHA);pub_ref=ref(PARENT/'publication.json',PUBLICATION_SHA)
    index=loads(take(index_ref,sources));publication=loads(take(pub_ref,sources));exact(publication['index_reference'],index_ref,'External index publication')
    jobs=inspect_inventory(index,publication,docs,refs)
    expected=deepcopy(base)
    for job in jobs:
        for key in ('raw_reference','receipt_reference'):
            r=job[key];merge(expected,r['path'],r['sha256'])
    exact(index['source_hashes'],expected,'Independent full producer closure');exact(publication['source_hashes'],expected,'Receipt closure')
    started_path=PARENT/'started.json';b=started_path.read_bytes();merge(sources,str(started_path),sha(b));started=loads(b)
    require(started['schema']=='MULTIDECISION_SCORING_HISTORY_STARTED_V1' and type(started['planned_channel_count']) is int and started['planned_channel_count']==77 and started['retry_allowed'] is False,'Started contract')
    exact(started['input_references'],refs,'Started inputs');exact(started['source_hashes'],base,'Started frozen base')
    for k in FLAGS:require(started[k] is False,'Started permission')
    stamp=datetime.fromisoformat(started['started_at_utc']);require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds()==0,'Started UTC')
    blob=take(ref(INSPECTOR,INSPECTOR_SHA),sources)
    oracle=types.ModuleType('_private_independent_scoring_arithmetic');oracle.__file__=str(INSPECTOR);exec(compile(blob,str(INSPECTOR),'exec'),oracle.__dict__)
    guard(sources,refs)
    return refs,sources,jobs,tzif,oracle,index_ref,pub_ref,expected


def save(path,value,failure=False):
    blob=encoded(value)
    if not failure:require(shutil.disk_usage(OUTPUT.parent).free>=5*1024**3+len(blob),'5GiB plus report bytes')
    with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==blob,'Report persisted');return ref(path,sha(blob))


def readback(*,execute=False):
    require(execute is True,'Explicit execute required')
    # All pending anchors reject before even namespace inspection.
    require(all(type(h) is str and len(h)==64 for h in (INDEX_SHA,PUBLICATION_SHA,PRODUCER_SHA)),'Actual anchors pending')
    require(not OUTPUT.exists(),'Independent namespace exists; no retry')
    refs,sources,jobs,tzif,oracle,index_ref,pub_ref,expected=load_inputs();OUTPUT.mkdir(parents=True,exist_ok=False);reports=[]
    try:
        start=save(OUTPUT/'started.json',dict(schema='MULTIDECISION_SCORING_HISTORY_READBACK_STARTED_V1',index_reference=index_ref,publication_reference=pub_ref,reader_sha256=LOADED_SHA,retry_allowed=False))
        for job in jobs:
            raw=take(job['raw_reference'],sources);receipt=loads(take(job['receipt_reference'],sources));channel=loads(take(job['row']['channel_reference'],sources))
            result=oracle.inspect_scoring_history_channel(saved_channel=channel,raw_bytes=raw,raw_reference=job['raw_reference'],receipt=receipt,receipt_reference=job['receipt_reference'],bridge_row=job['bridge_row'],reference_calendar=job['reference_calendar'],tzif_bytes=tzif,window_contract=CONTRACT,outer_inventory_contract=job['outer_inventory_contract'])
            require(result['status']=='PASS' and result['window_count']==78,'Independent arithmetic acceptance')
            inspect_index_row(job['row'],channel)
            reports.append(dict(index=job['row']['index'],coordinate=job['row']['coordinate'],channel_reference=job['row']['channel_reference'],inspection=result,decision_coverage=job['row']['decision_coverage']))
            del raw,receipt,channel
        require(len(reports)==77,'All77 independently inspected');guard(sources,refs)
        report=dict(schema='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V1',status='PASS',index_reference=index_ref,publication_reference=pub_ref,reader_sha256=LOADED_SHA,inspector_reference=ref(INSPECTOR,INSPECTOR_SHA),producer_reference=ref(PRODUCER,PRODUCER_SHA),input_references=refs,source_hashes=sources,producer_source_hashes_verified=expected,rows=reports,security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,decision_count_per_security=6,window_count_per_security=78,started_bytes_externally_anchored=False,started_execution_time_attested=False,full_ndx_universe_certified=False,score_computed=False,independent_arithmetic_readback_completed=True,**dict.fromkeys(FLAGS,False))
        out=save(OUTPUT/'independent_readback.json',report);guard(sources,refs)
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact reader namespace')
        for r in (start,out):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Reader output drift')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),completed_channel_count=len(reports),remaining_channel_count=77-len(reports),retry_allowed=False),failure=True);raise


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args();print(json.dumps(readback(execute=a.execute)))
