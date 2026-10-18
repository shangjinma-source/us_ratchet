"""Explicit fixed experimental domain; never a new index membership observation."""
from datetime import date, datetime
from pathlib import Path
import argparse
import json
import re

from scripts.current_research_close_capture import (
    ROOT, NY, _path, _clock, _json, require, digest, save,
    capture_saved_close, default_fetch, utc_now)

SCHEMA='EXPERIMENTAL_FULL_DOMAIN_CAPTURE_PLAN_V1'


def prepare(plan_path,plan_sha256,*,root=ROOT,clock=utc_now):
    root=Path(root).resolve();files={};pins={};total=0
    def read(path,expected):
        nonlocal total
        target=_path(root,path)
        require(target.stat().st_size<=32*1024*1024,'EXPERIMENTAL_SOURCE_TOO_LARGE')
        with target.open('rb') as stream:raw=stream.read(32*1024*1024+1)
        total+=len(raw)
        require(len(raw)<=32*1024*1024 and total<=128*1024*1024 and digest(raw)==expected,'EXPERIMENTAL_SOURCE_CHANGED')
        require(path not in pins or pins[path]==expected,'EXPERIMENTAL_SOURCE_CONFLICT')
        files[path]=raw;pins[path]=expected;return raw
    plan=_json(read(plan_path,plan_sha256))
    require(set(plan)=={'schema','status','domain_path','domain_source_hashes','calendar_path','calendar_source_hashes',
        'session','history_start_date','securities','output_directory','previous_manifest_path','previous_manifest_sha256'}
        and plan['schema']==SCHEMA,'EXPERIMENTAL_PLAN_FIELDS')
    for pathkey,pinkey in (('domain_path','domain_source_hashes'),('calendar_path','calendar_source_hashes')):
        require(type(plan[pinkey])is dict and plan[pathkey] in plan[pinkey],'EXPERIMENTAL_SOURCE_PIN_REQUIRED')
        for path,h in plan[pinkey].items():read(path,h)
    domain=_json(files[plan['domain_path']])
    require(domain['schema']=='EXPERIMENTAL_DERIVED_DOMAIN_V1' and domain['point_in_time_membership_verified'] is False
            and domain['new_membership_observation'] is False and domain['production_replacement'] is False,
            'EXPERIMENTAL_DOMAIN_REQUIRED')
    require(all(pins.get(p)==h for p,h in domain['source_hashes'].items()),'EXPERIMENTAL_DOMAIN_SOURCE_UNBOUND')
    observed=_json(read(domain['original_observation_path'],domain['original_observation_sha256']))
    require(observed['schema']=='ndx_current_quote_list_observation_v1'
            and observed['point_in_time_membership_verified'] is False,'ORIGINAL_OBSERVATION_REQUIRED')
    symbols=observed['observed_symbols'];members=domain['members'];securities=domain['securities']
    require(len(symbols)==len(set(symbols))==domain['original_observed_count']==observed['observed_security_count']
            and len(members)==len(set(members))==len(securities)==domain['fixed_security_count']
            and set(members)<set(symbols),'EXPERIMENTAL_DOMAIN_COUNTS')
    removed=domain['exclusions']
    require(len(removed)==len({r['ticker'] for r in removed}) and {r['ticker'] for r in removed}==set(symbols)-set(members)
            and all(type(r.get('reason'))is str and r['reason'].strip() for r in removed),'EXPERIMENTAL_EXCLUSIONS_REQUIRED')
    current=_json(read(domain['fixed_input_path'],domain['fixed_input_sha256']));arguments=current['search_arguments'];metadata=arguments['metadata']
    require(set(arguments['prices'])==set(metadata) and len(metadata)==len(securities),'FIXED_INPUT_DOMAIN_MISMATCH')
    require(len({s['security_id'] for s in securities})==len(securities) and {s['security_id'] for s in securities}==set(metadata)
            and {s['ticker'] for s in securities}==set(members),'FIXED_INPUT_DOMAIN_MISMATCH')
    for security in securities:
        require(set(security)=={'ticker','security_id','issuer_id','security_type'}
                and security['security_type']=='EQUITY' and type(security['security_id'])is str and security['security_id']
                and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',security['ticker'])
                and all(security[k]==metadata[security['security_id']][k] for k in ('ticker','issuer_id')),'FIXED_INPUT_IDENTITY_MISMATCH')
    require(plan['securities']==[{k:s[k] for k in ('ticker','security_id','security_type')} for s in securities],
            'EXPERIMENTAL_PLAN_DOMAIN_MISMATCH')
    previous=_json(read(plan['previous_manifest_path'],plan['previous_manifest_sha256']))
    require(previous['members']==members and len(previous['candidates'])==len(securities)
            and {r['security_id'] for r in previous['candidates']}==set(metadata)
            and all(all(r[k]==metadata[r['security_id']][k] for k in ('ticker','issuer_id')) for r in previous['candidates'])
            and previous['membership_observation_asof']==domain['membership_observation_date']
            and previous['decision_date']==arguments['decision_date'],'EXPERIMENTAL_PREVIOUS_MANIFEST_MISMATCH')
    session,history=plan['session'],plan['history_start_date']
    require(date.fromisoformat(session).isoformat()==session and date.fromisoformat(history).isoformat()==history
            and history<=previous['training_dates'][0] and previous['decision_date']<session,'INVALID_EXPERIMENTAL_DATES')
    calendar=_json(files[plan['calendar_path']]);days=calendar['calendar'];sessions=calendar['sessions'];byday={s['date']:s for s in sessions}
    require(calendar['schema']=='SCHEDULED_REGULAR_SESSIONS_V1' and calendar['source_hashes']
            and all(pins.get(p)==h for p,h in calendar['source_hashes'].items())
            and days==sorted(set(days)) and len(byday)==len(sessions) and set(days)==set(byday) and session in byday,
            'EXPERIMENTAL_CALENDAR_UNBOUND')
    row=byday[session];opening=datetime.fromisoformat(row['open_at']);closing=datetime.fromisoformat(row['close_at'])
    require(row['timezone']=='America/New_York' and all(t.tzinfo is not None and t.date().isoformat()==session
            and t.astimezone(NY).date().isoformat()==session and t.utcoffset()==t.astimezone(NY).utcoffset()
            for t in (opening,closing)) and opening<closing,'INVALID_SESSION_TIMES')
    require(_path(root,plan['output_directory'])!=root,'OUTPUT_CANNOT_BE_ROOT')
    now=_clock(clock)
    # Existing preparation calls this key for source-byte closure only. The
    # referenced document remains EXPERIMENTAL_DERIVED_DOMAIN, not an observation.
    plan['membership_source_hashes']=dict(plan['domain_source_hashes'])
    return plan,dict(schema='EXPERIMENTAL_DOMAIN_CAPTURE_PREFLIGHT_V1',plan_sha256=plan_sha256,session=session,
        session_close_at=closing.isoformat(),checked_at=now.isoformat(),ready_after_close=now>=closing,
        declared_count=len(securities),known_identity_count=len(securities),unresolved_identity_count=0,
        batch_count=(len(securities)+4)//5,http_calls=0,account_writes=False,registration_performed=False,
        point_in_time_membership_verified=False,new_membership_observation=False,training_admitted=False)


def run(plan_path,plan_sha256,*,root=ROOT,capture=False,fetch=default_fetch,clock=utc_now,plan_validator=None):
    validator=prepare if plan_validator is None else plan_validator
    require(callable(validator),'CAPTURE_PLAN_VALIDATOR_REQUIRED')
    root=Path(root).resolve();plan,preflight=validator(plan_path,plan_sha256,root=root,clock=clock)
    if not capture:return preflight
    require(preflight['ready_after_close'],'SESSION_NOT_CLOSED_ZERO_HTTP')
    output=_path(root,plan['output_directory']);require(not output.exists(),'CAPTURE_OUTPUT_EXISTS_NO_RETRY')
    output.mkdir(parents=True,exist_ok=False);save(output/'plan.json',plan);save(output/'started.json',preflight)
    batches=[];entries=[]
    for number,start in enumerate(range(0,len(plan['securities']),5)):
        current,checked=validator(plan_path,plan_sha256,root=root,clock=clock)
        require(current==plan and checked['ready_after_close'],'EXPERIMENTAL_PLAN_CHANGED')
        directory=(output/f'batch-{number:03d}').relative_to(root).as_posix()
        manifest=dict(schema='SAVED_CLOSE_CAPTURE_MANIFEST_V1',session=plan['session'],history_start_date=plan['history_start_date'],
            calendar_path=plan['calendar_path'],calendar_source_hashes=plan['calendar_source_hashes'],
            securities=plan['securities'][start:start+5],output_directory=directory)
        path=output/f'batch-{number:03d}.json';pin=save(path,manifest)
        result=capture_saved_close(path.relative_to(root).as_posix(),pin,root=root,capture=True,fetch=fetch,clock=clock)
        index=output/f'batch-{number:03d}'/'completion_index.json'
        batches.append(dict(path=index.relative_to(root).as_posix(),sha256=digest(index.read_bytes())))
        entries.extend(dict(entry,relative_directory=directory) for entry in result['entries'])
    current,checked=validator(plan_path,plan_sha256,root=root,clock=clock)
    require(current==plan and checked['ready_after_close'],'EXPERIMENTAL_PLAN_CHANGED')
    require(len(entries)==len(plan['securities']) and {e['ticker'] for e in entries}=={s['ticker'] for s in plan['securities']},'EXPERIMENTAL_RESULT_DOMAIN_MISMATCH')
    valid=sum(e['status']=='SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED' for e in entries)
    result=dict(schema='MONTHLY_FULL_DOMAIN_CAPTURE_INDEX_V1',status='EXPERIMENTAL_DOMAIN_CAPTURED_NOT_ADMITTED' if valid==len(entries) else 'INCOMPLETE_NOT_ADMITTED',
        plan_sha256=plan_sha256,declared_count=len(entries),attempted_count=len(entries),validated_count=valid,
        unresolved_identity_count=0,unresolved_transport_saved_count=0,session=plan['session'],entries=entries,batches=batches,
        http_calls=len(entries),account_writes=False,registration_performed=False,point_in_time_membership_verified=False,
        new_membership_observation=False,training_admitted=False,completed_at=_clock(clock).isoformat())
    save(output/'completion_index.json',result);return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--capture',action='store_true');args=parser.parse_args()
    result=run(args.plan,args.plan_sha256,capture=args.capture)
    print(json.dumps(result,indent=2));return 0 if result.get('status')!='INCOMPLETE_NOT_ADMITTED' else 1


if __name__=='__main__':raise SystemExit(main())
