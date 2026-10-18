"""Bind the user's gap-month choice to saved typed dates, without sealing."""
import argparse
from copy import deepcopy
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
OUTPUT=ROOT/'data/cache/research/gap_monthly_policy_20261002_v1'
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
PINS={
 'frontier':('data/cache/research/observation_gap_frontier_20261002_v1/frontier.json','a463539f706db1925c52cab0f8d1a4da34eb36b62e915b1842e9cbe229062170'),
 'publication':('data/cache/research/observation_gap_frontier_20261002_v1/publication.json','36c99f365a545f3c508795a8a1db39ed9afcddf4120dd4aa7ad73ad1b50abe44'),
 'user_choice':('DYNAMIC_GAP_MONTHLY_POLICY_USER_DECISION_20261002.md','f661616a86dca8e80aa3e8bcea1b55c29b97760e993948049327fe1a38d84906'),
 'core':('backtest/ndx_gap_monthly_observation_policy_research.py','aab44a1cd8c41be42ace2061b788865d90f83e9c678f6daa59560809edfc7e1b')}
FLAGS=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified',
 'promotion_allowed','live_mutation_allowed','oos_recovery_completed','old_calendar_mutated',
 'old_generator_modified','existing_frontier_rewritten','full_transitive_source_closure_reverified',
 'input_timeliness_verified','old_calendar_full_validation_reexecuted'),False)


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def prepare(frontier,reference):
    require(frontier['schema']=='OBSERVATION_GAP_FRONTIER_RESEARCH_V1'
        and frontier['last_observed_session']=='2026-09-24'
        and frontier['last_accounted_session']=='2026-10-01'
        and frontier['month_first_semantics']=='UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE',
        'Saved unresolved frontier differs')
    rows=frontier['known_accounted_rows']; require(len(rows)==65,'Full saved65 required')
    require([row['kind'] for row in rows]==['SEALED_PARENT_OBSERVED_SESSION']*60+['MISSED_OBSERVATION']*5,
            'Preserve sixty observed and five missed types')
    prepared=[]
    for index,row in enumerate(rows):
        if row['kind']=='MISSED_OBSERVATION':
            require(row['counts_as_observed_session'] is False and row['decision_eligible'] is False,'Gap authority differs')
        prepared.append({'sequence':index+1,'session':row['session'],'kind':row['kind'],
            'evidence_reference':dict(reference,json_pointer=f'/known_accounted_rows/{index}'),
            'seal_status':'NOT_ATTEMPTED' if row['kind']=='MISSED_OBSERVATION' else 'UNKNOWN'})
    return {'policy_id':POLICY,'known_rows':prepared,'new_prospective_observations':[]}


def assemble(frontier,refs,project):
    inputs=prepare(frontier,refs['frontier']); result=project(**inputs)
    require(result['schema']=='GAP_MONTHLY_OBSERVATION_POLICY_RESEARCH_V1' and result['policy_id']==POLICY
        and len(result['rows'])==65 and type(result['new_prospective_observation_count']) is int
        and result['new_prospective_observation_count']==0 and type(result['known_row_count']) is int
        and result['known_row_count']==65,'Policy result differs')
    require(all(type(row['monthly_coordinate_eligible']) is bool and row['candidate_seal_allowed'] is False
        and row['cohort_registration_allowed'] is False and row['seal_outcome_used_to_select_coordinate'] is False
        for row in result['rows']),'Strict coordinate types and permissions required')
    require(all(type(month['observed_count']) is int and type(month['missed_count']) is int for month in result['months']),
            'Strict month counts required')
    require([row['input_row'] for row in result['rows']]==inputs['known_rows'],'Typed row evidence changed')
    october=[month for month in result['months'] if month['month']=='2026-10']
    require(october==[{'month':'2026-10','first_observed_session':None,'observed_count':0,'missed_count':1}],
            'No actual October observation exists')
    for flag in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed',
                 'live_mutation_allowed','oos_recovery_completed','input_timeliness_verified','user_choice_authenticity_verified'):
        require(result[flag] is False,'Policy projection authority differs')
    require(result['complete_sequence_independently_verified'] is False
        and result['caller_source_evidence_not_verified'] is True,'Caller evidence must not become certified')
    return {'schema':'SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1','policy_id':POLICY,'projection':result,
        'projection_inputs':inputs,'user_choice_reference':refs['user_choice'],'frontier_reference':refs['frontier'],
        'user_choice_recorded_from_explicit_reply':True,'cryptographic_user_signature_claimed':False,
        'preserved_old_frontier_month_semantics':frontier['month_first_semantics'],
        'prospective_decision_not_before':'2026-10-01','prospective_monthly_coordinate_count':sum(
            row['monthly_coordinate_eligible'] and row['input_row']['session']>='2026-10-01' for row in result['rows']),
        'new_observation_count':0,'saved_frontier_rows':deepcopy(frontier['known_accounted_rows']),**FLAGS}


def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output differs'); return sha(raw)


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry')
    sources={str(SOURCE):LOADED_SHA}; refs={}; raw={}
    for role,(relative,digest) in PINS.items():
        path=ROOT/relative; data=path.read_bytes(); require(sha(data)==digest,'Source mismatch: '+role)
        raw[role]=data; refs[role]={'path':str(path),'sha256':digest}; sources[str(path)]=digest
    frontier=json.loads(raw['frontier']); receipt=json.loads(raw['publication'])
    require({p.name for p in Path(refs['frontier']['path']).parent.iterdir()}=={'started.json','frontier.json','publication.json'},
            'Frontier namespace incomplete')
    require(receipt['schema']=='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1'
        and receipt['status']=='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY'
        and receipt['frontier_reference']==refs['frontier'] and receipt['source_hashes']==frontier['source_hashes'],
        'Frontier receipt differs')
    name='backtest.ndx_gap_monthly_observation_policy_research'; require(name not in sys.modules,'Fresh CLI required')
    module=importlib.import_module(name); require(Path(module.__file__).resolve()==Path(refs['core']['path']).resolve(),'Core path differs')
    def guard():
        require(all(sha(Path(path).read_bytes())==digest for path,digest in sources.items()),'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'source_hashes':sources,'retry_allowed':False,**FLAGS})
        result=assemble(frontier,refs,module.monthly_observation_coordinates)
        result.update(source_hashes=sources,input_references=refs); guard()
        digest=write_new(OUTPUT/'policy.json',result); guard()
        pubsha=write_new(OUTPUT/'publication.json',{'schema':'GAP_MONTHLY_POLICY_PUBLICATION_V1',
            'status':'PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL',
            'policy_reference':{'path':str(OUTPUT/'policy.json'),'sha256':digest},'source_hashes':sources,**FLAGS}); guard()
        require(sha((OUTPUT/'policy.json').read_bytes())==digest and sha((OUTPUT/'publication.json').read_bytes())==pubsha
            and {p.name for p in OUTPUT.iterdir()}=={'started.json','policy.json','publication.json'},'Publication readback differs')
        return {'path':str(OUTPUT/'policy.json'),'sha256':digest,'publication_sha256':pubsha}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False}); raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
