"""Read-only registration gates for conditional paper operation, not PIT certification.

All trust starts at the caller's externally approved raw request digest. Receipt
publication and shared locking belong to the caller. No account or file writes.
"""
from copy import deepcopy
from datetime import datetime, time
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from backtest.current_quantity_v2_simulated_settlement import _rebuild
from data.quantity_v2_simulation_account_binding import validate_account_binding

NY=ZoneInfo('America/New_York')

def need(ok, reason):
    if not ok: raise ValueError(reason)

def stamp(value):
    value=datetime.fromisoformat(value) if isinstance(value,str) else value
    need(isinstance(value,datetime) and value.tzinfo is not None and value.utcoffset() is not None,'AWARE_TIME_REQUIRED')
    return value

def path_at(root,value):
    path=Path(value)
    path=(root/path).resolve() if not path.is_absolute() else path.resolve()
    need(path.is_relative_to(root),'PATH_OUTSIDE_ROOT')
    return path

def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def _validate(*,root,request_path,expected_request_sha256,now):
    root=Path(root).resolve();now=stamp(now)
    raw=path_at(root,request_path).read_bytes()
    need(sha256(raw).hexdigest()==expected_request_sha256,'REQUEST_HASH_MISMATCH')
    request=json.loads(raw)
    need(request.get('schema')=='REGISTERED_PAPER_REQUEST_V1','REGISTRATION_SCHEMA')
    need(request.get('external_flow_policy')=='FORBID','EXTERNAL_FLOW_POLICY_REQUIRED')
    need(request.get('calendar_policy')=='EXPLICIT_AUTHORIZED_CONDITIONAL','CALENDAR_POLICY_REQUIRED')
    for key in ('registration_id','output_directory'):
        need(type(request.get(key)) is str and bool(request[key].strip()),'REGISTRATION_FIELD_REQUIRED')
    path_at(root,request['output_directory'])
    identity=request['identity'];evaluation=request['evaluation']
    for key in ('account_id','simulation_id','database_path'):
        need(type(identity.get(key)) is str and bool(identity[key].strip()),'IDENTITY_REQUIRED')
    database=path_at(root,identity['database_path'])
    need(identity.get('currency')=='USD' and Fraction(identity['initial_cash'])>0,'INITIAL_CASH_REQUIRED')
    pins={};seen=set()
    def bind(path,expected):
        resolved=path_at(root,path)
        need(type(expected) is str and len(expected)==64,'INVALID_SOURCE_HASH')
        need(resolved not in pins or pins[resolved]==expected,'CONFLICTING_SOURCE_PINS')
        pins[resolved]=expected
        blob=resolved.read_bytes();need(sha256(blob).hexdigest()==expected,'SOURCE_HASH_MISMATCH')
        return resolved,blob
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            if 'path' in value and 'sha256' in value:
                read(value)
            for key,item in value.items():
                if key in ('source_hashes','original_source_hashes','fixed_source_hashes'):
                    need(isinstance(item,dict),'SOURCE_PINS_REQUIRED')
                    for p,h in item.items():bind(p,h)
                else:walk(item)
    def read(ref,required_json=False):
        resolved,blob=bind(ref['path'],ref['sha256'])
        if not required_json and resolved.suffix.lower()!='.json':return None
        value=json.loads(blob)
        if resolved not in seen:
            seen.add(resolved);walk(value)
        return value
    refs=request['refs']
    need(set(refs)=={'protocol','authorization','bootstrap','daily','calendar','calendar_authorization'},'REGISTRATION_REFS_REQUIRED')
    documents={key:read(ref,required_json=True) for key,ref in refs.items()}
    walk({'source_hashes':request['source_hashes']})
    need(bool(request['source_hashes']),'SOURCE_PINS_REQUIRED')
    bootstrap=documents['bootstrap'];daily=documents['daily'];calendar=documents['calendar']
    for config in (bootstrap,daily):
        need(path_at(root,config['root'])==root,'CONFIG_ROOT_MISMATCH')
        need(path_at(root,config['database_path'])==database,'CONFIG_DATABASE_MISMATCH')
        need(config['simulation_id']==identity['simulation_id'],'CONFIG_SIMULATION_MISMATCH')
    need(bootstrap['account_id']==identity['account_id'],'CONFIG_ACCOUNT_MISMATCH')
    if 'account_id' in daily:need(daily['account_id']==identity['account_id'],'CONFIG_ACCOUNT_MISMATCH')
    need(Fraction(bootstrap['initial_cash'])==Fraction(identity['initial_cash']),'CONFIG_CASH_MISMATCH')
    need(bootstrap['schedule']==refs['calendar'],'CONFIG_CALENDAR_MISMATCH')
    need(daily['schedule_path']==refs['calendar']['path'] and daily['schedule_sha256']==refs['calendar']['sha256'],'CONFIG_CALENDAR_MISMATCH')
    need(bootstrap['fees']=={'path':daily['fees_path'],'sha256':daily['fees_sha256']},'CONFIG_FEES_MISMATCH')
    need(bootstrap.get('pullback')==daily.get('pullback') and bootstrap.get('pullback') is not None,'CONFIG_BUY_POLICY_MISMATCH')
    # Path-only runtime input must have an externally approved explicit pin.
    if 'identity_manifest_path' in bootstrap:
        need(path_at(root,bootstrap['identity_manifest_path']) in pins,'IDENTITY_MANIFEST_UNBOUND')
    for name in ('authorization','calendar_authorization'):
        approval=documents[name]
        need(approval.get('registration_id')==request['registration_id'] and approval.get('authorized') is True,'EXPLICIT_AUTHORIZATION_REQUIRED')
    approval=documents['authorization']
    need(approval.get('identity')==identity and approval.get('evaluation')==evaluation and approval.get('protocol_sha256')==refs['protocol']['sha256'],'AUTHORIZATION_SCOPE_MISMATCH')
    need(documents['calendar_authorization'].get('calendar_sha256')==refs['calendar']['sha256'],'CALENDAR_AUTHORIZATION_MISMATCH')
    sessions=calendar['sessions'];dates=[row['date'] for row in sessions]
    need(dates==sorted(set(dates)) and dates==calendar['calendar'],'CALENDAR_SESSION_MISMATCH')
    for row in sessions:
        opening=stamp(row['open_at']);closing=stamp(row['close_at'])
        need(opening<closing and opening.astimezone(NY).date().isoformat()==row['date']==closing.astimezone(NY).date().isoformat(),'INVALID_SESSION_TIMES')
    start=evaluation['start_session'];end=evaluation['end_session']
    need(start in dates and end in dates and start<=end,'EVALUATION_CALENDAR_COVERAGE')
    first=datetime.combine(datetime.fromisoformat(start).date(),time(10),NY)
    first_session=sessions[dates.index(start)]
    need(stamp(first_session['open_at'])<=first<stamp(first_session['close_at']),'FIRST_DECISION_OUTSIDE_SESSION')
    return dict(request=deepcopy(request),request_sha256=expected_request_sha256,root=str(root),
        first_decision_at=first.isoformat(),end_close_at=sessions[dates.index(end)]['close_at'],
        database_path=str(database),calendar=deepcopy(calendar),documents=documents,
        verified_source_hashes={str(p):h for p,h in pins.items()},account_writes=False,
        scope='CONDITIONAL_OPERATION_BINDING_NOT_PIT_OR_INDEPENDENT_OOS_CERTIFICATION')

def validate_registration_request(*,root,request_path,expected_request_sha256,now):
    result=_validate(root=root,request_path=request_path,expected_request_sha256=expected_request_sha256,now=now)
    need(stamp(now)<stamp(result['first_decision_at']),'REGISTRATION_WOULD_BACKFILL')
    database=Path(result['database_path'])
    need(not any(Path(str(database)+suffix).exists() for suffix in ('','-wal','-shm','-journal')),'NEW_REGISTRATION_DATABASE_EXISTS')
    return result

def validate_registration(*,root,request_path,expected_request_sha256,receipt,now):
    result=_validate(root=root,request_path=request_path,expected_request_sha256=expected_request_sha256,now=now)
    need(receipt.get('schema')=='REGISTERED_PAPER_RECEIPT_V1' and receipt.get('request_sha256')==expected_request_sha256,'REGISTRATION_RECEIPT_MISMATCH')
    need(stamp(receipt['registered_at'])<stamp(result['first_decision_at']) and stamp(receipt['registered_at'])<=stamp(now),'REGISTRATION_WOULD_BACKFILL')
    result['registered_at']=receipt['registered_at']
    return result

def validate_decision_time(*,validated,now):
    local=stamp(now).astimezone(NY);evaluation=validated['request']['evaluation']
    need(evaluation['start_session']<=local.date().isoformat()<=evaluation['end_session'],'OUTSIDE_EVALUATION_DECISION_PERIOD')
    need(local.date().isoformat() in validated['calendar']['calendar'] and (local.hour,local.minute)==(10,0),'OUTSIDE_DECISION_WINDOW')
    row=next(x for x in validated['calendar']['sessions'] if x['date']==local.date().isoformat())
    need(stamp(row['open_at'])<=stamp(now)<stamp(row['close_at']),'OUTSIDE_SESSION')
    return True

def validate_start_receipt(*,validated,receipt,simulation,now):
    request=validated['request'];identity=request['identity']
    need(receipt.get('schema')=='REGISTERED_PAPER_START_V1' and receipt.get('request_sha256')==validated['request_sha256'],'START_RECEIPT_MISMATCH')
    started=stamp(receipt['started_at']);need(started<=stamp(now),'FUTURE_START_RECEIPT')
    validate_decision_time(validated=validated,now=started)
    need(started.astimezone(NY).date().isoformat()==request['evaluation']['start_session'],'START_BACKFILL_OR_LATE')
    rebuilt,_,last_at=_rebuild(simulation)
    need(stamp(last_at)<=stamp(now),'SIMULATION_FROM_FUTURE')
    bootstrap=validated['documents']['bootstrap']
    need(rebuilt['model']==bootstrap['model'],'SIMULATION_MODEL_MISMATCH')
    expected_dates=[d for d in validated['calendar']['calendar'] if d>=request['evaluation']['start_session']]
    actual_calendar=rebuilt.get('valuation',{}).get('registration',{}).get('calendar',{})
    expected_closes={r['date']:r['close_at'] for r in validated['calendar']['sessions'] if r['date'] in expected_dates}
    need(actual_calendar.get('session_dates')==expected_dates,'VALUATION_CALENDAR_MISMATCH')
    need(set(actual_calendar.get('closes',{}))==set(expected_closes) and all(stamp(actual_calendar['closes'][d])==stamp(v) for d,v in expected_closes.items()),'VALUATION_CLOSES_MISMATCH')
    need(actual_calendar.get('source_references')==[request['refs']['calendar']['path']],'VALUATION_CALENDAR_SOURCE_MISMATCH')
    for batch in rebuilt['batches']:
        if batch.get('kind')=='ACCEPTANCE':
            validate_decision_time(validated=validated,now=batch['request']['accepted_at'])
        elif batch.get('kind')=='CLOSE_VALUATION':
            need(request['evaluation']['start_session']<=batch['request']['session']<=request['evaluation']['end_session'],'VALUATION_OUTSIDE_EVALUATION')
    # Continuation/monthly acceptance replaces the order set. Check each fee
    # against that batch's pre-execution chain, never the final order set.
    from scripts.run_current_quantity_v2_simulation import _fees
    from backtest.current_quantity_v2_simulated_settlement import (
        create_simulation, _configure_valuation, _accept, _execute, _record_close)
    replay=create_simulation(chain=rebuilt['origin'],simulation_id=rebuilt['simulation_id'],model=rebuilt['model'])
    _configure_valuation(replay,rebuilt['valuation']['registration'])
    for batch in rebuilt['batches']:
        item=batch['request']
        if batch.get('kind')=='ACCEPTANCE':
            replay['chain']=_accept(replay['chain'],item)
        elif batch.get('kind')=='CLOSE_VALUATION':
            _record_close(replay,item)
        else:
            approved_fees=_fees(validated['documents']['daily'],Path(validated['root']),replay)
            for oid,evidence in item['evidence'].items():
                need(oid in approved_fees and Fraction(evidence['fees'])==Fraction(approved_fees[oid]),'SETTLEMENT_FEE_POLICY_MISMATCH')
            replay['chain'],_=_execute(replay['chain'],replay,item)
        replay['batches'].append(deepcopy(batch))
    need(replay['chain']==rebuilt['chain'],'FEE_AUDIT_REPLAY_MISMATCH')
    validate_account_binding(bootstrap=identity,simulation=rebuilt)
    origin=rebuilt['origin']['ledger']
    need(stamp(origin['acceptance']['accepted_at'])==started,'ORIGIN_START_MISMATCH')
    need(Fraction(origin['cash'])==Fraction(identity['initial_cash']) and not any(origin['shares'].values()),'ORIGIN_CAPITAL_MISMATCH')
    need(receipt.get('origin_sha256')==digest(rebuilt['origin']),'ORIGIN_RECEIPT_MISMATCH')
    # _rebuild replays only supported settlement/acceptance/valuation batches;
    # manual cash mutation or external-flow batches are rejected by that replay.
    return dict(status='START_AND_REPLAY_BOUND',account_writes=False)

def validate_route_binding(*,validated,route_path,expected_route_sha256,simulation):
    raw=path_at(Path(validated['root']),route_path).read_bytes()
    need(sha256(raw).hexdigest()==expected_route_sha256,'ROUTE_APPROVAL_HASH_MISMATCH')
    route=json.loads(raw)
    identity=validated['request']['identity'];evaluation=validated['request']['evaluation']
    need(route.get('schema')=='REGISTERED_PAPER_ROUTE_V1' and route.get('request_sha256')==validated['request_sha256'],'ROUTE_REGISTRATION_MISMATCH')
    need(route.get('identity')==identity,'ROUTE_IDENTITY_MISMATCH')
    month=route['target_month'];need(len(month)==7 and evaluation['start_session'][:7]<=month<=evaluation['end_session'][:7],'ROUTE_MONTH_OUTSIDE_PERIOD')
    root=Path(validated['root']);ref=route['configuration']
    raw=path_at(root,ref['path']).read_bytes();need(sha256(raw).hexdigest()==ref['sha256'],'ROUTE_CONFIG_HASH_MISMATCH')
    config=json.loads(raw);base=validated['documents']['daily']
    need(set(config)==set(base),'ROUTE_CONFIG_FIELDS_CHANGED')
    need(all(config[k]==base[k] for k in base if k not in ('monthly','monthly_blob_root')),'ROUTE_FIXED_CONFIG_CHANGED')
    need(config.get('monthly') is not None,'ROUTE_MONTHLY_REQUIRED')
    from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
    monthly_ref=config['monthly']
    # This is only a selector for a saved month, not a simulated runtime clock.
    selector=datetime.fromisoformat(month+'-01T12:00:00').replace(tzinfo=NY)
    reader=MonthlyFileConfiguration(root=root,path=monthly_ref['path'],sha256_value=monthly_ref['sha256'],clock=lambda:selector.isoformat())
    package=reader.market_reader(simulation['chain'])
    rebuilt,_,_=_rebuild(simulation);validate_account_binding(bootstrap=identity,simulation=rebuilt)
    return dict(status='ROUTE_BOUND',configuration=config,account_writes=False,account_review_still_required=True)
