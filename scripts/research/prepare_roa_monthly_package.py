"""Offline month-end generation -> immutable inputs -> verified registration proposal.

Never edits production config, schedules, caches or accounts. Dry-run is default.
"""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from data.roa_monthly_selection import generate_month_selection
from data.roa_monthly_loader import RoaMonthlySelectionLoader
from scripts.research.publish_roa_immutable_inputs import publish,verify,relative_name


def prepare(*,root,request,now,create=False):
    root=Path(root).resolve();pins={}
    if now.tzinfo is None:raise ValueError('AWARE_TIME_REQUIRED')
    def read(spec):
        name=relative_name(spec['path']);path=root/name
        if not path.resolve().is_relative_to(root):raise ValueError('SOURCE_OUTSIDE_ROOT')
        if not path.is_file():raise ValueError('WAIT_REQUIRED_MONTH_INPUT:'+name)
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=spec['sha256']:raise ValueError('PREPARATION_SOURCE_CHANGED:'+name)
        pins[name]=spec['sha256'];document=json.loads(raw)
        for source in document.get('source_references',[]):
            if isinstance(source,dict) and 'path' in source and 'sha256' in source:
                p=relative_name(source['path'])
                if sha256((root/p).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('CALENDAR_EVIDENCE_CHANGED')
                pins[p]=source['sha256']
        return document
    manifest=read(request['manifest']);day=manifest['decision_date']
    calendar=read(request['session_calendar'])
    if calendar['schema']!='FIXED_EXCHANGE_SESSIONS_V1':raise ValueError('SESSION_CALENDAR_SCHEMA')
    session_dates=[s['date'] for s in calendar['sessions']]
    if session_dates!=sorted(set(session_dates)):raise ValueError('SESSION_CALENDAR_ORDER_INVALID')
    matched=[s for s in calendar['sessions'] if s['date']==day]
    if len(matched)!=1:raise ValueError('WAIT_MONTH_END_SESSION_CALENDAR')
    closing=datetime.fromisoformat(matched[0]['close'])
    if closing.tzinfo is None or now<closing:raise ValueError('WAIT_COMPLETED_MONTH_END')
    training=read(request['training_calendar'])
    if training['schema'] not in ('FIXED_EXCHANGE_SESSIONS_V1','VERIFIED_SCHEDULE_DATES_V1'):raise ValueError('TRAINING_CALENDAR_SCHEMA')
    training_dates=[r['date'] for r in training['sessions']]
    execution_session=next((d for d in session_dates if d>day),None)
    training_next=next((d for d in training_dates if d>day),None)
    if execution_session is None:raise ValueError('WAIT_NEXT_SESSION_CALENDAR')
    if execution_session!=training_next:raise ValueError('MONTH_CALENDARS_NEXT_SESSION_CONFLICT')
    start=max(min(session_dates),min(training_dates));end=min(max(session_dates),max(training_dates))
    if [d for d in session_dates if start<=d<=end]!=[d for d in training_dates if start<=d<=end]:
        raise ValueError('MONTH_CALENDARS_OVERLAP_CONFLICT')
    artifact=generate_month_selection(root=root,manifest_path=request['manifest']['path'],manifest_sha256=request['manifest']['sha256'],
        calendar_sessions=[r['date'] for r in training['sessions']],completed_through=day)
    if artifact['effective_month']!=request['expected_month']:raise ValueError('WAIT_REQUESTED_MONTH_INPUTS')
    if artifact['first_execution_session']!=execution_session:raise ValueError('MONTH_EXECUTION_SESSION_CONFLICT')
    artifact['source_hashes'].update(pins)
    artifact.pop('selection_id');artifact['selection_id']=sha256(json.dumps(artifact,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    output=root/relative_name(request['output_directory'])
    if not output.resolve().is_relative_to(root) or any(p.is_symlink() for p in (output,*output.parents)):
        raise ValueError('MONTH_PACKAGE_OUTPUT_OUTSIDE_ROOT')
    if output.exists():raise ValueError('MONTH_PACKAGE_EXISTS')
    plan=publish(root=root,entrypoints=artifact['source_hashes'],destination=output/'input_bundle',dry_run=True,follow_references=False)
    summary=dict(status='DRY_RUN_READY_NOT_REGISTERED',month=artifact['effective_month'],decision_date=day,
        selected=[r['ticker'] for r in artifact['securities']],selection_id=artifact['selection_id'],
        input_files=plan['file_count'],input_bytes=plan['total_bytes'],account_writes=False,schedules_changed=False,
        pending=['Approve proposed registry in a controlled production release',
                 'Actual new-month market signal, quotes, existing holdings and executions remain separately validated'])
    if not create:return summary
    output.mkdir(parents=True)
    def save(path,value):
        raw=json.dumps(value,indent=2).encode()
        with path.open('xb') as stream:stream.write(raw)
        return sha256(raw).hexdigest()
    original=output/'selection.source.json';original_hash=save(original,artifact)
    inputs=dict(artifact['source_hashes']);inputs[str(original.relative_to(root))]=original_hash
    publish(root=root,entrypoints=inputs,destination=output/'input_bundle',follow_references=False)
    bundle=verify(output/'input_bundle');prefix=str((output/'input_bundle/inputs').relative_to(root)).replace('\\','/')
    runtime=dict(artifact)
    runtime['source_hashes']={prefix+'/'+relative_name(p):h for p,h in bundle['source_hashes'].items()}
    runtime['immutable_publication']=dict(path=str((output/'input_bundle/publication.json').relative_to(root)),
        sha256=sha256((output/'input_bundle/publication.json').read_bytes()).hexdigest(),scope=bundle['dependency_scope'])
    runtime['source_hashes'][runtime['immutable_publication']['path']]=runtime['immutable_publication']['sha256']
    runtime.pop('selection_id');runtime['selection_id']=sha256(json.dumps(runtime,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    runtime_path=output/'selection.runtime.json';runtime_hash=save(runtime_path,runtime)
    registry={artifact['effective_month']:dict(path=str(runtime_path.relative_to(root)),sha256=runtime_hash)}
    loaded=RoaMonthlySelectionLoader(root=root,registry=registry)(artifact['first_execution_session'])
    if loaded['weights']!=artifact['weights'] or loaded['selection']!=artifact['selection']:raise ValueError('IMMUTABLE_SELECTION_CHANGED')
    save(output/'registry.proposed.json',registry)
    summary.update(status='PREPARED_VERIFIED_NOT_REGISTERED',registry_proposal=str((output/'registry.proposed.json').relative_to(root)),
                   runtime_path=str(runtime_path.relative_to(root)),runtime_sha256=runtime_hash)
    save(output/'receipt.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--create',action='store_true')
    parser.add_argument('--report');args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    result=prepare(root=root,request=json.loads((root/args.request).read_bytes()),now=datetime.now(timezone.utc),create=args.create)
    if args.report:(root/args.report).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result))


if __name__=='__main__':main()
