"""Strict publication boundary around the sealed independent numerical reader."""
import argparse,copy,hashlib,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_all_k_completed_independent_audit_20260919 as old
OLD_SOURCE=Path(old.__file__).resolve()
OLD_SHA='ed2e6200b80ea572b6e7e6cf15d7e053e2e55aae68bbc4a5559b377a0f9b7d7a'
if hashlib.sha256(OLD_SOURCE.read_bytes()).hexdigest()!=OLD_SHA:raise ValueError('Frozen independent reader differs')
SCHEMA='LATEST_ALL_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V2'
LOADED=dict(old.LOADED);old.archive.merge(LOADED,{str(OLD_SOURCE):OLD_SHA,str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
EXTRA_FALSE=('alias_equivalence_verified','solver_called','owner_check_result_called','constrained_projection_optimality_independently_verified')
CHECKS=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')

def validate_report(value,plan,index):
    if value.get('schema')!=SCHEMA or value.get('numerical_reader_schema')!='LATEST_ALL_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1':raise ValueError('Exact independent publication schema required')
    if any(value.get(k) is not False for k in (*old.FALSE,*EXTRA_FALSE)):raise ValueError('Independent report scope cannot be upgraded')
    for key in ('all_original_126_matrices_verified','all_seven_parameters_and_five_risks_verified'):
        if value.get(key) is not True:raise ValueError('Complete independent numerical checks required')
    if value['prefix_completion_evidence']!='CALLER_OBSERVED_BOUNDED_RUN_EXIT_NOT_INDEPENDENT_PROCESS_ATTESTATION' or value['risk_boundary_policy']!='DECIMAL_AT_ORIGINAL_1E_MINUS9_TOLERANCE_DISAGREEMENT_WITH_SAVED_BINARYFLOAT_VERDICT_FAILS_CLOSED_NO_RESIGNING':raise ValueError('Evidence/Decimal boundary differs')
    entries=index['entries'];count=len(entries)
    expected=dict(planned=764,completed=count,pending=764-count,alias_count=382,aliases_independently_fitted=0)
    if not 1<=count<=764 or any(type(value.get(k)) is not int or value[k]!=v for k,v in expected.items()):raise ValueError('Exact completed denominator required')
    pref=dict(path=str(old.PLAN),sha256=old.PLAN_SHA)
    if not old.exact(value['plan_reference'],pref) or not old.exact(index['plan_reference'],pref):raise ValueError('Hard plan identity differs')
    if index['schema']!='LATEST_ALL_K_BOUNDED_INDEX_V1' or type(index['completed']) is not int or index['completed']!=count or type(index['planned']) is not int or index['planned']!=764 or index['status']!=('COMPLETE' if count==764 else 'PARTIAL') or any(index[k] is not False for k in old.FALSE):raise ValueError('External prefix index differs')
    tasks=plan['canonical_tasks'][:count];details=value['details']
    if len(details)!=count or [d['task_id'] for d in details]!=[t['task_id'] for t in tasks] or [e['task_id'] for e in entries]!=[t['task_id'] for t in tasks]:raise ValueError('Exact completed task prefix required')
    for detail,entry,task in zip(details,entries,tasks):
        if not old.exact(detail['checkpoint_reference'],dict(path=entry['path'],sha256=entry['sha256'])):raise ValueError('Task checkpoint differs')
        if detail['weight_spec']!=task['weight_spec'] or type(detail['holding_count']) is not int or detail['holding_count']!=len(task['selected']) or type(detail['issuer_count']) is not int or detail['issuer_count']!=len(task['selected']):raise ValueError('Actual task dimensions differ')
        checks=detail['five_risk_checks']
        if set(checks)!=set(CHECKS) or any(type(v) is not bool for v in checks.values()) or detail['risk_pass'] is not all(checks.values()) or detail['risk_failures']!=[k for k in CHECKS if not checks[k]]:raise ValueError('Detail risk diagnostics differ')
        if detail['constrained_projection_optimality_independently_verified'] is not False or detail['equal_weight_exact_verified'] is not (task['weight_spec']=='equal_weight'):raise ValueError('Detail scope differs')
    passed=sum(d['risk_pass'] for d in details)
    if type(value['risk_pass_count']) is not int or value['risk_pass_count']!=passed or type(value['risk_fail_count']) is not int or value['risk_fail_count']!=count-passed or not old.exact(value['completed_weight_specs'],dict(Counter(d['weight_spec'] for d in details))):raise ValueError('Risk/spec summary differs')

def verify(value):
    sources=value['historical_expected_source_hashes'];required=dict(LOADED)
    if any(sources.get(p)!=h for p,h in required.items()):raise ValueError('Publisher/reader source omitted')
    if value.get('schema')!=SCHEMA or any(value.get(k) is not False for k in (*old.FALSE,*EXTRA_FALSE)):raise ValueError('Publication boundary differs')
    ref=value['index_reference']
    expected=build(ref['path'],ref['sha256'],completed_prefix_confirmed=True)
    if not old.exact(value,expected):raise ValueError('Entire independent report/source closure does not reproduce')

def build(index_path,index_sha256,*,completed_prefix_confirmed=False):
    value=copy.deepcopy(old.build(index_path,index_sha256,completed_prefix_confirmed=completed_prefix_confirmed))
    value.update(schema=SCHEMA,numerical_reader_schema='LATEST_ALL_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1')
    old.archive.merge(value['historical_expected_source_hashes'],LOADED)
    value['archive_resolution']=old.archive.verify_expected_sources(value['historical_expected_source_hashes'],old.archive.load_contract())
    return value

def publish_verified(path,value):
    verify(value);saved=old.exclusive_publish(path,value);verify(value);return saved

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--index',required=True);p.add_argument('--index-sha256',required=True);p.add_argument('--completed-prefix-confirmed',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(publish_verified(a.output,build(a.index,a.index_sha256,completed_prefix_confirmed=a.completed_prefix_confirmed))))
