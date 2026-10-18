"""Read-only explicit observation preparation and opt-in create-only export.

Calendar conversion records a conditional human admission, not new certification
of official hours or absence of emergency closure. No fetching or account writes.
"""
from copy import deepcopy
from datetime import datetime
import hashlib,json
from pathlib import Path
from data.current_research_observation_registry import PlanObservationLoader,SCHEMA,require,NY
from data.current_research_fill_ledger import review_paper_ledger
from data.current_research_saved_quote import read_saved_quote


def encoded(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def prepare_observation_input(state, *, root, raw_sources, source_hashes, unit_continuity,
                              admission, calendar_path, now, output_directory):
    review_paper_ledger(state)
    loader=PlanObservationLoader(root=root);pins=deepcopy(source_hashes);plan=state['plan'];day=plan['active_date']
    output=loader._path(output_directory)
    require(not output.is_relative_to(loader.root/'data/research_paper'), 'REAL_REGISTRY_EXPORT_FORBIDDEN')
    require(not output.exists(), 'CREATE_ONLY_OUTPUT_EXISTS')
    require(isinstance(now,datetime) and now.tzinfo is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
    require(isinstance(pins,dict) and calendar_path in pins, 'CALENDAR_SOURCE_NOT_PINNED')
    for p,h in pins.items():loader._read(p,h)
    def refs(v):require(isinstance(v,list) and v and all(k in pins for k in v), 'UNPINNED_EVIDENCE')
    schedule=json.loads(loader._read(calendar_path,pins[calendar_path]))
    require(schedule.get('schema')=='SCHEDULED_REGULAR_SESSIONS_V1', 'INVALID_SCHEDULE_SCHEMA')
    evidence=schedule.get('source_hashes',{})
    require(evidence and all(pins.get(k)==v for k,v in evidence.items()), 'CALENDAR_EVIDENCE_PIN_MISMATCH')
    sessions=schedule['sessions'];calendar=schedule['calendar']
    require(calendar==sorted(set(calendar)) and [s['date'] for s in sessions]==calendar, 'INVALID_SCHEDULE_DATES')
    match=[s for s in sessions if s['date']==day];require(len(match)==1, 'ACTIVE_SESSION_MISSING')
    session=match[0];market=plan['causal_inputs']['research_snapshot']['market_session']
    require(all(session.get(k)==market.get(k) for k in ['date','timezone','open_at','close_at']), 'CALENDAR_PLAN_MISMATCH')
    if 'source_references' not in session and 'source' not in session:
        # Some saved calendars pin evidence at document level only.
        refs([calendar_path]+list(evidence))
    else:
        if 'source_references' in session:refs(session['source_references'])
        if 'source' in session:
            require(isinstance(session['source'],str) and bool(session['source']), 'UNPINNED_EVIDENCE')
            refs([session['source']])
    require(admission.get('status')=='ACCEPTED_CONDITIONAL_OBSERVATION' and admission.get('reviewer') and admission.get('limitations'), 'EXPLICIT_REVIEW_REQUIRED')
    refs(admission.get('evidence_references'))
    close=datetime.fromisoformat(session['close_at']);opening=datetime.fromisoformat(session['open_at']);reviewed=datetime.fromisoformat(admission['reviewed_at'])
    require(all(t.tzinfo is not None for t in [close,opening,reviewed]) and opening<close<=reviewed<=now, 'SESSION_NOT_COMPLETED_OR_REVIEW_TIME_INVALID')
    require(session['timezone']=='America/New_York' and all(t.astimezone(NY).date().isoformat()==day and t.date().isoformat()==day and t.utcoffset()==t.astimezone(NY).utcoffset() for t in [opening,close]), 'SESSION_COORDINATE_INVALID')
    required={o['security_id'] for o in plan['orders']}
    require(isinstance(raw_sources,dict) and required==set(raw_sources)==set(unit_continuity) and required, 'ACTIVE_ORDER_SOURCE_DOMAIN_MISMATCH')
    observations=[]
    for sid,source in raw_sources.items():
        quote=plan['causal_inputs']['quotes'][sid];decl=unit_continuity[sid]
        require(source['ticker']==plan['causal_inputs']['securities'][sid] and source['price_basis']==quote['price_basis'], 'SOURCE_SECURITY_OR_BASIS_MISMATCH')
        require(decl.get('status')=='NO_UNPROCESSED_ACTIONS' and decl.get('from_date')==plan['causal_inputs']['decision_date'] and decl.get('to_date')==day and decl.get('price_basis')==quote['price_basis'], 'UNIT_CONTINUITY_INVALID')
        refs(decl.get('source_references'))
        directory=source['relative_directory'];loader._path(directory)
        for suffix,key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]:
            p=(Path(directory)/(source['ticker']+suffix)).as_posix()
            require(pins.get(p)==source['entry'][key], 'RAW_SOURCE_NOT_PINNED')
        decoded=read_saved_quote(root=root,ticker=source['ticker'],expected_security_type=source['expected_security_type'],entry=source['entry'],relative_directory=directory,decision_date=day,decision_session_close_at=close.isoformat())
        require(datetime.fromisoformat(decoded['received_at'])<=reviewed<=now, 'CAPTURE_AFTER_REVIEW')
        require(not any(plan['causal_inputs']['decision_date']<e['session']<=day and e['kind']!='dividends' for e in decoded['event_details']), 'UNPROCESSED_CORPORATE_ACTION')
        observations.append(dict(security_id=sid,ticker=source['ticker'],expected_security_type=source['expected_security_type'],relative_directory=directory,entry=deepcopy(source['entry']),observation_date=day,session_close_at=close.isoformat()))
    prefix=output.relative_to(loader.root).as_posix()
    derived=dict(status='REVIEWED_OFFICIAL_SESSION_CALENDAR',sessions={day:deepcopy(session)},source_references=[calendar_path]+list(evidence),original_calendar_path=calendar_path,conversion_basis='EXPLICIT_CONDITIONAL_HUMAN_ADMISSION_NOT_NEW_CALENDAR_CERTIFICATION',limitations=deepcopy(admission['limitations']))
    derived_path=prefix+'/calendar.json';pins[derived_path]=digest(derived)
    bundle=dict(account_id=state['account_id'],plan_id=plan['plan_id'],research_id=plan['research_id'],active_date=day,observed_through=day,calendar_path=derived_path,source_hashes=pins,observations=observations,unit_continuity=deepcopy(unit_continuity),admission=deepcopy(admission))
    entry={k:bundle[k] for k in ['account_id','plan_id','research_id','active_date']};entry.update(bundle_path=prefix+'/bundle.json',sha256=digest(bundle))
    registry=dict(schema=SCHEMA,entries=[entry])
    return dict(bundle=bundle,derived_calendar=derived,registry=registry,registry_sha256=digest(registry),output_directory=prefix,bundle_sha256=digest(bundle),calendar_sha256=digest(derived),selector_calls=0)


def export_observation_input(prepared, state, *, root, now):
    loader=PlanObservationLoader(root=root);output=loader._path(prepared['output_directory'])
    require(not output.is_relative_to(loader.root/'data/research_paper'), 'REAL_REGISTRY_EXPORT_FORBIDDEN')
    require(not output.exists(), 'CREATE_ONLY_OUTPUT_EXISTS')
    require(digest(prepared['bundle'])==prepared['bundle_sha256'] and digest(prepared['derived_calendar'])==prepared['calendar_sha256'], 'PREPARED_CONTENT_CHANGED')
    require(digest(prepared['registry'])==prepared['registry_sha256'], 'PREPARED_REGISTRY_CHANGED')
    prefix=output.relative_to(loader.root).as_posix();bundle=prepared['bundle'];entries=prepared['registry']['entries']
    require(len(entries)==1 and entries[0]['bundle_path']==prefix+'/bundle.json'
            and entries[0]['sha256']==prepared['bundle_sha256']
            and bundle['calendar_path']==prefix+'/calendar.json'
            and bundle['source_hashes'].get(prefix+'/calendar.json')==prepared['calendar_sha256'], 'PREPARED_ARTIFACT_LINK_MISMATCH')
    for key,expected in [('account_id',state['account_id']),('plan_id',state['plan']['plan_id']),('research_id',state['plan']['research_id']),('active_date',state['plan']['active_date'])]:
        require(entries[0].get(key)==bundle.get(key)==expected, 'PREPARED_BINDING_MISMATCH')
    output.mkdir(parents=True,exist_ok=False)
    stage=output/'validation.pending.json'
    try:
        for name,value in [('calendar.json',prepared['derived_calendar']),('bundle.json',prepared['bundle']),('validation.pending.json',prepared['registry'])]:
            with (output/name).open('xb') as f:f.write(encoded(value))
        result=PlanObservationLoader(root=root,registry_path=stage.relative_to(loader.root).as_posix()).review(state,now=now)
        require(result is not None, 'EXPORT_REGISTRY_NOT_BOUND')
        with (output/'registry.json').open('xb') as f:f.write(encoded(prepared['registry']))
        return dict(registry_path=(output/'registry.json').relative_to(loader.root).as_posix(),bundle_sha256=prepared['bundle_sha256'],review=result)
    finally:
        if stage.exists():stage.unlink()
