"""One separately registered TOP1 repair; never rerun completed quantity."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import return_priority_next12_monthly_comparison as base
SELECTOR='backtest/return_priority_monthly_top1_selector.py'
SELF='scripts/return_priority_next12_top1_pin_repair.py'

def derive_input(prepared, registration):
    result=deepcopy(prepared)
    if SELECTOR in result['source_hashes']:raise ValueError('REPAIR_NOT_REQUIRED_OR_ALREADY_APPLIED')
    value=registration['source_hashes'][SELECTOR]
    if not isinstance(value,str) or len(value)!=64:raise ValueError('INVALID_REGISTERED_SELECTOR_PIN')
    result['source_hashes'][SELECTOR]=value
    return result

def inspect_original(directory, registration_sha):
    directory=base.absolute(directory)
    if base.digest(directory/'registration.json')!=registration_sha:raise ValueError('ORIGINAL_REGISTRATION_CHANGED')
    reg=base.load(directory/'registration.json');base.verify(reg['source_hashes'])
    if base.guards()!=reg['protected_before']:raise ValueError('ORIGINAL_PROTECTION_CHANGED')
    basefile=base.absolute(reg['input_path'])
    if base.digest(basefile)!=reg['input_sha256']:raise ValueError('ORIGINAL_INPUT_CHANGED')
    quantity=base.load(directory/'quantity/result.json')
    top=base.load(directory/'top1/outcome.json')
    tr=base.load(directory/'top1/result.json')
    cb=base.load(directory/'top1/callback_2025-07-31.json')['response']
    whole=base.load(directory/'result.json')
    after=base.load(directory/'protected_after.json')
    if quantity['core_calls']!=12 or not quantity['metrics']['complete_full_period'] or quantity['method']!='quantity':raise ValueError('QUANTITY_NOT_COMPLETED')
    if whole['methods']!=[quantity,tr] or whole['book_calls']!=2:raise ValueError('ORIGINAL_FINAL_RESULT_MISMATCH')
    if (top['status']!='BLOCKED' or top['reason']!='ORDER_PROVIDER_NOT_READY' or top['daily_ledger'] or top['order_log'] or top['shares'] or top['cash']!='20000'):raise ValueError('TOP1_ALREADY_EXECUTED_OR_DIFFERENT_FAILURE')
    if (cb['status']!='BLOCKED' or cb['reason'].get('detail')!='Selector source pin required' or cb['selection'] is not None or cb['orders'] or cb['capital_decision_attempts']!=1 or tr['core_calls']!=0):raise ValueError('NOT_SELECTOR_PIN_FAILURE')
    if not after['unchanged'] or after['hashes']!=reg['protected_before']:raise ValueError('ORIGINAL_PROTECTION_FAILED')
    files={str(p):base.digest(p) for p in directory.rglob('*') if p.is_file()}
    return reg,base.load(basefile),files

def prepare(original, original_sha, output):
    output=base.absolute(output)
    if output.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    reg,old,oldfiles=inspect_original(original,original_sha)
    derived=derive_input(old,reg);base.validate(derived)
    pins=dict(reg['source_hashes']);pins[SELF]=base.digest(SELF)
    protected=base.guards()
    output.mkdir(parents=True)
    base.save(output/'derived_prepared.json',derived)
    receipt=dict(schema='NEXT12_TOP1_PIN_REPAIR_V1',original_directory=str(base.absolute(original)),original_registration_sha256=original_sha,
        original_artifact_hashes=oldfiles,source_hashes=pins,protected_before=protected,
        derived_input_sha256=base.digest(output/'derived_prepared.json'),methods=['top1'],maximum_book_calls=1,
        maximum_selector_attempts=12,maximum_quantity_core_calls=0,automatic_retry=False,monthly_cash_reset=False,
        initial_cash='20000',changed_input_field='source_hashes.'+SELECTOR,
        original_failure_preserved=True,independent_oos=False,adoption_allowed=False)
    base.save(output/'registration.json',receipt)
    return base.digest(output/'registration.json')

def run(output, registration_sha):
    output=base.absolute(output)
    if base.digest(output/'registration.json')!=registration_sha:raise ValueError('REPAIR_REGISTRATION_CHANGED')
    if {p.name for p in output.iterdir()}!={'registration.json','derived_prepared.json'}:raise ValueError('ALREADY_STARTED_NO_RETRY')
    r=base.load(output/'registration.json');base.verify(r['source_hashes']);base.verify(r['original_artifact_hashes'])
    if base.guards()!=r['protected_before']:raise ValueError('PROTECTED_CHANGED')
    if r['methods']!=['top1'] or r['maximum_book_calls']!=1 or r['maximum_quantity_core_calls']!=0 or r['maximum_selector_attempts']!=12 or r['automatic_retry'] is not False:raise ValueError('REPAIR_SCOPE_CHANGED')
    original,old,_=inspect_original(r['original_directory'],r['original_registration_sha256'])
    data=base.load(output/'derived_prepared.json')
    if base.digest(output/'derived_prepared.json')!=r['derived_input_sha256'] or data!=derive_input(old,original):raise ValueError('DERIVED_INPUT_CHANGED')
    assembled=base.validate(data)
    base.save(output/'started.json',dict(registration_sha256=registration_sha,maximum_books=1,quantity_core_calls=0,no_retry=True))
    try:
        result=base.execute_method('top1',data,assembled,output/'top1')
        if result['core_calls']!=0 or result['book_calls']>1:raise ValueError('REPAIR_CALL_LIMIT_VIOLATION')
        base.save(output/'result.json',dict(original_run=r['original_directory'],original_failure_preserved=True,
            recovery=result,quantity_reused_not_rerun=True,quantity_core_calls=0,denominator_repaired=1,independent_oos=False))
    finally:
        current=base.guards();unchanged=current==r['protected_before']
        base.save(output/'protected_after.json',dict(hashes=current,unchanged=unchanged))
        base.verify(r['original_artifact_hashes'])
        if not unchanged:raise ValueError('PROTECTED_CHANGED')

if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--original');parser.add_argument('--original-registration-sha');parser.add_argument('--output',required=True);parser.add_argument('--registration-sha')
    args=parser.parse_args()
    if args.prepare:
        if not args.original or not args.original_registration_sha:raise ValueError('EXPLICIT_ORIGINAL_REQUIRED')
        print(prepare(args.original,args.original_registration_sha,args.output))
    else:
        if not args.registration_sha:raise ValueError('EXPLICIT_REPAIR_REGISTRATION_REQUIRED')
        run(args.output,args.registration_sha)
