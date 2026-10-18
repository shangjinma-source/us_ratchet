"""Publish a separate missed-observation chain without modifying calendar v2."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/observation_gap_ledger_20261002_v1'
BASE='data/cache/research/ndx_observed_us_session_calendar_v2/'
CAPTURE='data/cache/research/observation_gap_classification_20261002_v1/'
PINS={
 'parent_manifest':(BASE+'manifest.json','68404f2b127e45a608a49010d8d8beead28c3957288e8276554b56ee72194e6a'),
 'parent_events':(BASE+'events.jsonl','8cca71da136f454f0f0c45096ab5b8723ebecdb385c4c64364d0e073f695be30'),
 'parent_sessions':(BASE+'sessions.csv','f78183b85d8e83b5037d3c4b77b2a8662af451def7a0411bbc26f82e1081f2e2'),
 'parent_receipt':(BASE+'committed_transactions/e8ed2218d97d085c55b2ed6066ac3391db545fb22776b5df6524f17439550a14.json','ebe462aff95a3c5fcc08f4470f7bda8cc4725da6f1dfa9213404ea67b9cef92c'),
 'classification':(CAPTURE+'classification.json','e75a930582fc70d49860a55d30d79063959d588ee068fb6bfb2ef411f23398fe'),
 'QQQ':(CAPTURE+'QQQ.csv','a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88'),
 'SPY':(CAPTURE+'SPY.csv','dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf'),
 'core':('backtest/ndx_observation_gap_ledger_research.py','115a0474f8d4d7d61c9084f3fcaff323dc70e81b437ee9d902cfb59c186fe899')}
DATES=['2026-09-25','2026-09-28','2026-09-29','2026-09-30','2026-10-01']
FLAGS=dict.fromkeys(('old_calendar_mutated','old_calendar_full_validation_reexecuted','classifier_reexecuted',
 'canonical_calendar_append_allowed','candidate_seal_allowed','cohort_registration_allowed','oos_recovery_completed',
 'source_price_rows_validated_for_execution','promotion_allowed','live_mutation_allowed','point_in_time_verified',
 'full_transitive_source_closure_reverified'),False)
LEDGER_FALSE=('observed_session_added','fresh_observation','decision_eligible','candidate_seal_allowed',
 'cohort_registration_allowed','first_observed_session_of_month','historical_timeliness_verified',
 'future_timeliness_granted','canonical_calendar_append_allowed','point_in_time_verified','promotion_allowed',
 'live_mutation_allowed','source_bytes_verified','system_clock_verified','oos_recovery_completed')


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def prepare(raw,refs):
    manifest=json.loads(raw['parent_manifest']); capture=json.loads(raw['classification'])
    receipt=json.loads(raw['parent_receipt'])
    require(receipt['planned_manifest']==manifest and receipt['transaction_id']==manifest['commit_transaction_id'],
            'Saved committed receipt binding differs')
    require(manifest['manifest_type']=='ndx_observed_us_session_calendar_v2'
            and manifest['event_count']==66 and manifest['session_count']==60
            and manifest['decision_eligible_session_count']==0 and manifest['latest_session_date']=='2026-09-24',
            'Pinned v2 boundary differs')
    for role,artifact in [('parent_events','event_ledger'),('parent_sessions','session_projection')]:
        require(manifest['artifacts'][artifact]['sha256']==refs[role]['sha256'],'Parent artifact binding differs')
    lines=raw['parent_events'].splitlines()
    require(len(lines)==66 and json.loads(lines[-1])['event_sha256']==manifest['latest_event_sha256'],
            'Parent exact prefix tail differs')
    sessions=list(csv.DictReader(io.StringIO(raw['parent_sessions'].decode('utf-8-sig'))))
    require(len(sessions)==60 and sessions[-1]['session_date']=='2026-09-24','Parent projection boundary differs')
    require(capture['schema']=='CURRENT_SOURCE_GAP_CLASSIFICATION_CAPTURE_V1'
            and capture['captured_using_system_clock'] is True,'Saved classification capture required')
    require(capture['parent_references']['calendar_manifest']==refs['parent_manifest']
            and capture['parent_references']['calendar_events']==refs['parent_events'],'Capture parent differs')
    classification=capture['classification']
    require([row['session'] for row in classification['pending_classifications']]==DATES
            and classification['timeliness_candidate'] is None and classification['missed_or_ineligible_row_count']==5,
            'Exact five missed dates required')
    for flag in ('calendar_append_allowed','candidate_seal_allowed','cohort_registration_allowed',
                 'old_calendar_mutated','source_price_rows_validated_for_execution','promotion_allowed','live_mutation_allowed'):
        require(capture[flag] is False,'Capture authority differs')
    for ticker in ('QQQ','SPY'):
        require(capture['captured_source_references'][ticker]==refs[ticker],'Captured CSV reference differs')
        rows=list(csv.DictReader(io.StringIO(raw[ticker].decode('utf-8-sig'))))
        dates=[row['Date'] for row in rows]
        require(dates==sorted(set(dates)),'Unique ordered captured CSV dates required')
        indexed={row['Date']:row for row in rows}
        require(capture['pending_source_rows'][ticker]=={day:indexed[day] for day in DATES},'Saved source rows differ')
    return {'parent_binding':{'manifest_reference':refs['parent_manifest'],'event_prefix_reference':refs['parent_events'],
        'session_projection_reference':refs['parent_sessions'],'event_count':66,'session_count':60,
        'last_session':'2026-09-24','event_tail_sha256':manifest['latest_event_sha256']},
        'classification_capture':capture,'classification_reference':refs['classification']}


def write_bytes(path,raw):
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Published bytes differ')
    return sha(raw)


def write_json(path,value):
    return write_bytes(path,(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())


def validate_result(ledger,prepared,recorded):
    require(ledger['schema']=='OBSERVATION_GAP_EVIDENCE_LEDGER_V1' and len(ledger['events'])==5,'Ledger result differs')
    require(ledger['parent_binding']==prepared['parent_binding']
            and ledger['old_last_observed_session_unchanged']=='2026-09-24','Parent output differs')
    require(type(ledger['missed_observation_count']) is int and ledger['missed_observation_count']==5,'Missed count differs')
    for key in ('observed_session_increment','fresh_session_increment','seal_increment','cohort_increment'):
        require(type(ledger[key]) is int and ledger[key]==0,'Gap cannot add sessions/seals/cohorts')
    for item in [ledger]+ledger['events']:
        require(all(item[key] is False for key in LEDGER_FALSE),'Gap output authority differs')
    require([event['session'] for event in ledger['events']]==DATES,'Gap output dates differ')
    require(all(event['event_recorded_at_utc']==recorded
        and event['classification_captured_at_utc']==prepared['classification_capture']['captured_at_utc']
        and event['historical_source_first_observed_at_utc'] is None for event in ledger['events']),
        'Recording time is not historical observation time')
    require(ledger['batches']==[{'classification_capture':prepared['classification_capture'],
        'classification_reference':prepared['classification_reference'],'recorded_at_utc':recorded}],
        'Original classification batch differs')


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    sources={str(SOURCE):LOADED_SHA}; raw={}; refs={}
    for role,(relative,digest) in PINS.items():
        require(len(digest)==64,'Pending source pin'); path=ROOT/relative; data=path.read_bytes()
        require(sha(data)==digest,'Source mismatch: '+role)
        raw[role]=data; refs[role]={'path':str(path),'sha256':digest}; sources[str(path)]=digest
    prepared=prepare(raw,refs)
    name='backtest.ndx_observation_gap_ledger_research'
    require(name not in sys.modules,'Fresh CLI required')
    module=importlib.import_module(name)
    require(Path(module.__file__).resolve()==Path(refs['core']['path']).resolve(),'Core module path differs')
    def guard():
        require(all(sha(Path(path).read_bytes())==digest for path,digest in sources.items()),'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        recorded=datetime.now(timezone.utc).isoformat()
        write_json(OUTPUT/'started.json',{'recorded_at_utc':recorded,'source_hashes':sources,'retry_allowed':False,**FLAGS})
        ledger=module.append_missed_observations(**prepared,recorded_at_utc=recorded)
        validate_result(ledger,prepared,recorded)
        guard(); artifacts={}
        for role,filename in [('parent_manifest','parent_manifest.json'),('parent_events','parent_events.jsonl'),
                              ('parent_sessions','parent_sessions.csv'),('parent_receipt','parent_receipt.json')]:
            artifacts[role]={'path':str(OUTPUT/filename),'sha256':write_bytes(OUTPUT/filename,raw[role])}
        artifacts['ledger']={'path':str(OUTPUT/'ledger.json'),'sha256':write_json(OUTPUT/'ledger.json',ledger)}
        event_raw=b''.join((json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode() for event in ledger['events'])
        artifacts['extension_events']={'path':str(OUTPUT/'extension_events.jsonl'),'sha256':write_bytes(OUTPUT/'extension_events.jsonl',event_raw)}
        guard()
        digest=write_json(OUTPUT/'publication.json',{'schema':'OBSERVATION_GAP_LEDGER_PUBLICATION_V1',
            'status':'PUBLISHED_MISSED_OBSERVATION_EVIDENCE_ONLY','source_hashes':sources,'input_references':refs,
            'artifacts':artifacts,'recorded_at_utc':recorded,'new_record_time_is_not_historical_observation':True,
            'parent_prefix_byte_identical_copy':True,'classification_reused_without_reexecution':True,**FLAGS})
        guard()
        require(sha((OUTPUT/'publication.json').read_bytes())==digest,'Final publication readback differs')
        require(all(sha(Path(ref['path']).read_bytes())==ref['sha256'] for ref in artifacts.values()),'Final artifact readback differs')
        require({path.name for path in OUTPUT.iterdir()}=={'started.json','publication.json','ledger.json','extension_events.jsonl',
            'parent_manifest.json','parent_events.jsonl','parent_sessions.csv','parent_receipt.json'},'Unexpected publication namespace')
        return {'ledger_reference':artifacts['ledger'],'publication_sha256':digest,'recorded_at_utc':recorded}
    except Exception as error:
        write_json(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
