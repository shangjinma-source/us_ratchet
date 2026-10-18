"""Scoped current-cache capture; preserve prior failed capture unchanged."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/forward_source_capture_scoped_20261003_v1'
PINS={
 'frontier':('data/cache/research/observation_gap_frontier_20261002_v1/frontier.json','a463539f706db1925c52cab0f8d1a4da34eb36b62e915b1842e9cbe229062170'),
 'frontier_publication':('data/cache/research/observation_gap_frontier_20261002_v1/publication.json','36c99f365a545f3c508795a8a1db39ed9afcddf4120dd4aa7ad73ad1b50abe44'),
 'baseline_QQQ':('data/cache/research/observation_gap_classification_20261002_v1/QQQ.csv','a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 'baseline_SPY':('data/cache/research/observation_gap_classification_20261002_v1/SPY.csv','dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf'),
 'tzif':('D:/python/Lib/site-packages/tzdata/zoneinfo/America/New_York','d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9'),
 'base_core':('backtest/ndx_forward_source_capture_research.py','30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'),
 'core':('backtest/ndx_forward_source_capture_scoped_research.py','9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee')}
FLAGS=dict.fromkeys(('old_calendar_mutated','old_calendar_full_validation_reexecuted','gap_ledger_validation_reexecuted',
 'classifier_reexecuted','candidate_generator_called','candidate_seal_allowed','cohort_registration_allowed',
 'canonical_calendar_append_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed',
 'network_quote_refresh_performed','oos_recovery_completed','full_transitive_source_closure_reverified'),False)
PLAN_FALSE=('candidate_seal_allowed','cohort_registration_allowed','decision_eligible','canonical_calendar_append_allowed',
 'source_price_execution_verified','exchange_holidays_verified','early_closes_verified','authentic_clock_verified',
 'point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed',
 'historical_first_observation_claimed','fresh_observation')


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def validate_parent(frontier,receipt,refs):
    require(frontier['schema']=='OBSERVATION_GAP_FRONTIER_RESEARCH_V1'
        and receipt['schema']=='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1'
        and receipt['status']=='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY'
        and receipt['frontier_reference']==refs['frontier']
        and receipt['source_hashes']==frontier['source_hashes'],'Frontier publication differs')
    require(frontier['last_observed_session']=='2026-09-24'
        and frontier['last_accounted_gap_session']==frontier['last_accounted_session']=='2026-10-01'
        and len(frontier['known_accounted_rows'])==65 and frontier['unaccounted_source_dates']==[],
        'Sealed frontier boundary differs')
    for flag in ('candidate_seal_allowed','cohort_registration_allowed','canonical_calendar_append_allowed',
                 'point_in_time_verified','promotion_allowed','oos_recovery_completed'):
        require(frontier[flag] is False and receipt[flag] is False,'Parent authority differs')
    for ticker in ('QQQ','SPY'):
        require(frontier['input_references'][ticker]==refs['baseline_'+ticker],'Baseline bytes not bound to frontier')


def write_bytes(path,raw):
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output readback differs')
    return sha(raw)


def write_json(path,value):
    return write_bytes(path,(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())


def validate_result(result,frontier,current,raw,started,observed):
    require(result['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1','Scoped schema differs')
    require(result['frozen_capture_source_sha256']==PINS['base_core'][1]
        and result['full_original_bytes_preserved'] is True,'Frozen engine or original bytes preservation differs')
    for key in ('frozen_capture_consumed_full_original_csv','out_of_scope_ohlc_anomalies_repaired','scope_chosen_from_prices',
                'source_bytes_authenticated_by_this_module','old_failed_namespace_modified','original_calendar_reverified',
                'source_price_execution_verified','historical_first_observation_claimed','fresh_observation','decision_eligible',
                'candidate_seal_allowed','cohort_registration_allowed','canonical_calendar_append_allowed',
                'point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed'):
        require(result[key] is False,'Scoped authority differs: '+key)
    require(result['scope_start']==frontier['known_accounted_rows'][0]['session'],'Scope must come from sealed frontier')
    require(result['original_source_sha256']=={ticker:sha(value) for ticker,value in current.items()}
        and result['original_baseline_sha256']=={ticker:sha(raw['baseline_'+ticker]) for ticker in ('QQQ','SPY')},
        'Original source byte hashes differ')
    for role,originals in [('source',current),('baseline',{ticker:raw['baseline_'+ticker] for ticker in ('QQQ','SPY')})]:
        for ticker,original in originals.items():
            evidence=result['csv_scope_evidence'][role][ticker]
            derived=evidence['scoped_csv_utf8'].encode('utf-8')
            require(base64.b64decode(evidence['original_csv_bytes_base64'],validate=True)==original
                and evidence['original_sha256']==sha(original)
                and type(evidence['original_byte_count']) is int and evidence['original_byte_count']==len(original),
                'Full original bytes evidence differs')
            require(evidence['scoped_sha256']==sha(derived)==result['scoped_'+role+'_sha256'][ticker]
                and type(evidence['scoped_byte_count']) is int and evidence['scoped_byte_count']==len(derived)
                and type(evidence['original_row_count']) is int and evidence['original_row_count']==len(evidence['original_rows']),
                'Derived CSV byte linkage differs')
    plan=result['capture_plan']
    require(plan['schema']=='FORWARD_SOURCE_CAPTURE_PLANNING_V1','Plan schema differs')
    require(plan['capture_started_at_utc']==started and plan['observed_at_utc']==observed,'Capture interval changed')
    require(plan['source_sha256']==result['scoped_source_sha256']
        and plan['baseline_sha256']==result['scoped_baseline_sha256']
        and plan['tzif_sha256']==sha(raw['tzif']),'Consumed scoped/TZif bytes differ')
    require(plan['accounted_prefix_dates']==[row['session'] for row in frontier['known_accounted_rows']]
        and plan['last_observed_session_unchanged']==frontier['last_observed_session']
        and plan['last_accounted_session_unchanged']==frontier['last_accounted_session'],'Frontier state changed')
    require(plan['month_first_semantics']=='UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE','Sealed frontier semantics changed')
    for row in [plan]+plan['classifications']+([plan['timeliness_candidate']] if plan['timeliness_candidate'] is not None else []):
        require(all(row[key] is False for key in PLAN_FALSE),'Capture cannot grant eligibility')


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    sources={str(SOURCE):LOADED_SHA}; refs={}; raw={}
    for role,(relative,digest) in PINS.items():
        require(len(digest)==64,'Pending source pin'); path=ROOT/relative; data=path.read_bytes()
        require(sha(data)==digest,'Source mismatch: '+role)
        raw[role]=data; refs[role]={'path':str(path),'sha256':digest}; sources[str(path)]=digest
    frontier=json.loads(raw['frontier']); receipt=json.loads(raw['frontier_publication'])
    require({p.name for p in Path(refs['frontier']['path']).parent.iterdir()}=={'started.json','frontier.json','publication.json'},
            'Incomplete frontier namespace')
    validate_parent(frontier,receipt,refs)
    name='backtest.ndx_forward_source_capture_scoped_research'
    require(name not in sys.modules and 'backtest.ndx_forward_source_capture_research' not in sys.modules,'Fresh CLI required')
    module=importlib.import_module(name)
    require(Path(module.__file__).resolve()==Path(refs['core']['path']).resolve(),'Core path differs')
    require(Path(sys.modules['backtest.ndx_forward_source_capture_research'].__file__).resolve()==Path(refs['base_core']['path']).resolve(),'Base core path differs')
    started=datetime.now(timezone.utc).isoformat()
    current={ticker:(ROOT/'data/cache'/f'{ticker}.csv').read_bytes() for ticker in ('QQQ','SPY')}
    observed=datetime.now(timezone.utc).isoformat()
    for ticker,data in current.items():
        path=ROOT/'data/cache'/f'{ticker}.csv'; refs['current_'+ticker]={'path':str(path),'sha256':sha(data)}
        sources[str(path)]=sha(data)
    def guard():
        require(all(sha(Path(path).read_bytes())==digest for path,digest in sources.items()),'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_json(OUTPUT/'started.json',{'capture_started_at_utc':started,'observed_at_utc':observed,
            'source_hashes':sources,'retry_allowed':False,**FLAGS})
        guard(); artifacts={}
        for ticker,data in current.items():
            filename=ticker+'.csv'; artifacts[ticker]={'path':str(OUTPUT/filename),'sha256':write_bytes(OUTPUT/filename,data)}
        artifacts['tzif']={'path':str(OUTPUT/'New_York.tzif'),'sha256':write_bytes(OUTPUT/'New_York.tzif',raw['tzif'])}
        result=module.plan_scoped_forward_source_capture(frontier=frontier,source_csv_bytes=current,
            baseline_csv_bytes={ticker:raw['baseline_'+ticker] for ticker in ('QQQ','SPY')},
            tzif_bytes=raw['tzif'],capture_started_at_utc=started,observed_at_utc=observed)
        validate_result(result,frontier,current,raw,started,observed)
        capture={'schema':'FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1','plan':result,
            'capture_started_at_utc':started,'observed_at_utc':observed,'clock_captured_by_runner':True,
            'external_clock_attestation_verified':False,'source_hashes':sources,'input_references':refs,
            'captured_artifacts':artifacts,'quote_source_type':'EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
            'timezone_resource_metadata':{'zone':'America/New_York','package_version_at_implementation':'2025.1',
                'bytes_sha256':refs['tzif']['sha256'],'current_exchange_rules_certified':False},**FLAGS}
        digest=write_json(OUTPUT/'capture.json',capture); guard()
        publication=write_json(OUTPUT/'publication.json',{'schema':'FORWARD_SOURCE_CAPTURE_SCOPED_PUBLICATION_V1',
            'status':'PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND',
            'capture_reference':{'path':str(OUTPUT/'capture.json'),'sha256':digest},'source_hashes':sources,**FLAGS})
        guard()
        require(sha((OUTPUT/'capture.json').read_bytes())==digest
            and sha((OUTPUT/'publication.json').read_bytes())==publication
            and all(sha(Path(ref['path']).read_bytes())==ref['sha256'] for ref in artifacts.values()),'Final capture readback differs')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'},
                'Unexpected capture namespace')
        return {'path':str(OUTPUT/'capture.json'),'sha256':digest,'publication_sha256':publication,
                'capture_started_at_utc':started,'observed_at_utc':observed}
    except Exception as error:
        write_json(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
