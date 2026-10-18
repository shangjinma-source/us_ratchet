"""Capture a declared full domain through the existing small-batch collector.

Default is read-only preflight. Membership observations are not PIT certification;
successful collection is not training admission, optimization or account mutation.
"""
from datetime import date,datetime
from pathlib import Path
import argparse
import json
from scripts.current_research_close_capture import (
    ROOT,NY,_path,_clock,_json,require,digest,save,capture_saved_close,default_fetch,utc_now)

SCHEMA='MONTHLY_FULL_DOMAIN_CAPTURE_PLAN_V1'


def prepare(plan_path,plan_sha256,*,root=ROOT,clock=utc_now):
    root=Path(root).resolve();raw=_path(root,plan_path).read_bytes()
    require(digest(raw)==plan_sha256,'FULL_DOMAIN_PLAN_CHANGED');plan=_json(raw)
    require(set(plan)=={'schema','membership_path','membership_source_hashes','calendar_path','calendar_source_hashes',
        'session','history_start_date','securities','output_directory'} and plan['schema']==SCHEMA,'FULL_DOMAIN_PLAN_FIELDS')
    verified={}
    for path_key,pins_key in (('membership_path','membership_source_hashes'),('calendar_path','calendar_source_hashes')):
        pins=plan[pins_key];require(type(pins)is dict and plan[path_key] in pins,'FULL_DOMAIN_SOURCE_PIN_REQUIRED')
        for name,expected in pins.items():
            content=_path(root,name).read_bytes()
            require(digest(content)==expected,'FULL_DOMAIN_SOURCE_CHANGED')
            verified[name]=content
    membership=_json(verified[plan['membership_path']])
    members=membership['observed_symbols']
    require(membership.get('schema')=='ndx_current_quote_list_observation_v1'
        and membership.get('point_in_time_membership_verified') is False
        and type(members)is list and 1<=len(members)<=200 and len(set(members))==len(members)
        and membership['observed_security_count']==len(members),'FULL_DOMAIN_MEMBERSHIP_INVALID')
    securities=plan['securities'];require(type(securities)is list and len(securities)==len(members),'FULL_DOMAIN_INCOMPLETE')
    import re
    require(all(type(s)is dict and set(s)=={'ticker','security_id','security_type'}
        and type(s['ticker'])is str and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',s['ticker'])
        and s['security_type']=='EQUITY' and (s['security_id'] is None or (type(s['security_id'])is str and s['security_id'].strip())) for s in securities),'FULL_DOMAIN_SECURITY_INVALID')
    known_ids=[s['security_id'] for s in securities if s['security_id'] is not None]
    require({s['ticker'] for s in securities}==set(members)
        and len(set(known_ids))==len(known_ids),'FULL_DOMAIN_DUPLICATE_OR_MISSING')
    session=plan['session'];history=plan['history_start_date']
    require(date.fromisoformat(session).isoformat()==session and date.fromisoformat(history).isoformat()==history<=session,'INVALID_CAPTURE_DATES')
    calendar=_json(verified[plan['calendar_path']])
    require(calendar['schema']=='SCHEDULED_REGULAR_SESSIONS_V1' and calendar['source_hashes']
        and all(plan['calendar_source_hashes'].get(p)==h for p,h in calendar['source_hashes'].items()),'CALENDAR_CLOSURE_UNBOUND')
    days=calendar['calendar'];sessions=calendar['sessions'];byday={s['date']:s for s in sessions}
    require(days==sorted(set(days)) and len(byday)==len(sessions) and set(days)==set(byday) and session in byday,'SESSION_CALENDAR_MISMATCH')
    schedule=byday[session];opening=datetime.fromisoformat(schedule['open_at']);closing=datetime.fromisoformat(schedule['close_at'])
    require(schedule['timezone']=='America/New_York' and all(t.tzinfo is not None and t.date().isoformat()==session
        and t.astimezone(NY).date().isoformat()==session and t.utcoffset()==t.astimezone(NY).utcoffset() for t in (opening,closing)) and opening<closing,'INVALID_SESSION_TIMES')
    output=_path(root,plan['output_directory']);require(output!=root,'OUTPUT_CANNOT_BE_ROOT')
    now=_clock(clock)
    return plan,dict(schema='MONTHLY_FULL_DOMAIN_CAPTURE_PREFLIGHT_V1',plan_sha256=plan_sha256,
        session=session,session_close_at=closing.isoformat(),checked_at=now.isoformat(),ready_after_close=now>=closing,
        declared_count=len(securities),known_identity_count=len(known_ids),unresolved_identity_count=len(securities)-len(known_ids),
        batch_count=(len(known_ids)+4)//5,http_calls=0,account_writes=False,
        registration_performed=False,point_in_time_membership_verified=False,training_admitted=False)


def run(plan_path,plan_sha256,*,root=ROOT,capture=False,fetch=default_fetch,clock=utc_now):
    root=Path(root).resolve();plan,preflight=prepare(plan_path,plan_sha256,root=root,clock=clock)
    if not capture:return preflight
    require(preflight['ready_after_close'],'SESSION_NOT_CLOSED_ZERO_HTTP')
    output=_path(root,plan['output_directory']);require(not output.exists(),'CAPTURE_OUTPUT_EXISTS_NO_RETRY')
    output.mkdir(parents=True,exist_ok=False)
    save(output/'plan.json',plan);save(output/'started.json',preflight)
    batches=[];entries=[]
    known=[s for s in plan['securities'] if s['security_id'] is not None]
    unresolved=[s for s in plan['securities'] if s['security_id'] is None]
    for number,start in enumerate(range(0,len(known),5)):
        # Recheck all input bytes and clock before each bounded batch.
        current,checked=prepare(plan_path,plan_sha256,root=root,clock=clock)
        require(current==plan and checked['ready_after_close'],'FULL_DOMAIN_PLAN_CHANGED')
        manifest=dict(schema='SAVED_CLOSE_CAPTURE_MANIFEST_V1',session=plan['session'],history_start_date=plan['history_start_date'],
            calendar_path=plan['calendar_path'],calendar_source_hashes=plan['calendar_source_hashes'],
            securities=known[start:start+5],output_directory=(output/f'batch-{number:03d}').relative_to(root).as_posix())
        path=output/f'batch-{number:03d}.json';pin=save(path,manifest)
        result=capture_saved_close(path.relative_to(root).as_posix(),pin,root=root,capture=True,fetch=fetch,clock=clock)
        index_path=output/f'batch-{number:03d}'/'completion_index.json'
        batches.append(dict(path=index_path.relative_to(root).as_posix(),sha256=digest(index_path.read_bytes())))
        entries.extend(dict(entry,relative_directory=manifest['output_directory']) for entry in result['entries'])
    for security in unresolved:
        from scripts.current_research_unresolved_close_capture import capture_unresolved_close
        current,checked=prepare(plan_path,plan_sha256,root=root,clock=clock)
        require(current==plan and checked['ready_after_close'],'FULL_DOMAIN_PLAN_CHANGED')
        directory=(output/('unresolved-'+security['ticker'])).relative_to(root).as_posix()
        entry=capture_unresolved_close(security,root=root,output_directory=directory,session=plan['session'],
            history_start_date=plan['history_start_date'],session_close_at=checked['session_close_at'],fetch=fetch,clock=clock,capture=True)
        entries.append(dict(entry,relative_directory=directory))
    current,checked=prepare(plan_path,plan_sha256,root=root,clock=clock)
    require(current==plan and checked['ready_after_close'],'FULL_DOMAIN_PLAN_CHANGED')
    require(len(entries)==len(plan['securities']) and {e['ticker'] for e in entries}=={s['ticker'] for s in plan['securities']},'FULL_DOMAIN_RESULT_MISMATCH')
    validated=sum(e['status']=='SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED' for e in entries)
    unresolved_saved=sum(e['status']=='TRANSPORT_SAVED_UNRESOLVED_NOT_ADMITTED' for e in entries)
    status='INCOMPLETE_NOT_ADMITTED'
    if validated+unresolved_saved==len(entries):
        status='DECLARED_DOMAIN_CAPTURED_IDENTITY_UNRESOLVED_NOT_ADMITTED' if unresolved_saved else 'DECLARED_DOMAIN_CAPTURED_NOT_ADMITTED'
    result=dict(schema='MONTHLY_FULL_DOMAIN_CAPTURE_INDEX_V1',status=status,
        plan_sha256=plan_sha256,declared_count=len(entries),attempted_count=len(entries),validated_count=validated,
        unresolved_identity_count=len(unresolved),unresolved_transport_saved_count=unresolved_saved,
        session=plan['session'],entries=entries,batches=batches,http_calls=len(entries),account_writes=False,registration_performed=False,
        point_in_time_membership_verified=False,training_admitted=False,completed_at=_clock(clock).isoformat())
    save(output/'completion_index.json',result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256',required=True);parser.add_argument('--capture',action='store_true')
    args=parser.parse_args();print(json.dumps(run(args.plan,args.plan_sha256,capture=args.capture),indent=2))


if __name__=='__main__':main()
