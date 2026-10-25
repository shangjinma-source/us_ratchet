"""Read-only, explicit recovery request validation. No capture or publication API."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import re
from data.current_quantity_v2_followup_provider import canonical, parse, safe_path, read_bytes, STORAGE, MAX_FILES, MAX_TOTAL

CALENDAR = 'tmp/followup_capture_calendar_20261016_v1.json'
CALENDAR_SHA = 'fb9cce4e30f87864251fdd3e27608ff1c4fe1047dff0e0a0cc44cebdac5ed92b'
NY = ZoneInfo('America/New_York')


def preflight(*, root, request, observed_at=None):
    root = Path(root).resolve()
    observed = observed_at or datetime.now(timezone.utc)
    validated = {}
    def require(ok, reason):
        if not ok: raise ValueError(reason)
    def digest(raw): return sha256(raw).hexdigest()
    def hashed(name, expected, limit=32*1024*1024):
        require(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected), 'INVALID_EXPECTED_HASH')
        path=safe_path(root,name)
        # Reject aliases/reparse links even when they lead back inside the root.
        cursor=path
        while cursor != root:
            require(not cursor.is_symlink() and not (hasattr(cursor,'is_junction') and cursor.is_junction()), 'PATH_ALIAS_REJECTED')
            cursor=cursor.parent
        raw=read_bytes(path,limit);require(digest(raw)==expected,'SOURCE_CHANGED');validated[name]=expected
        return raw
    require(observed.tzinfo is not None and observed.utcoffset() is not None,'AWARE_CLOCK_REQUIRED')
    require(request.get('schema')=='FOLLOWUP_RECOVERY_REQUEST_V1','REQUEST_SCHEMA')
    target=request['target_session'];datetime.strptime(target,'%Y-%m-%d')
    require(re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',target),'TARGET_FORMAT')
    name=request['recovery_name'];require(isinstance(name,str) and re.fullmatch('[a-z][a-z0-9_-]{2,63}',name),'RECOVERY_NAME')
    refs=request['evidence'];require(set(refs)=={'event','started','failed','review','bundle'},'EVIDENCE_SET')
    loaded={key:parse(hashed(ref['path'],ref['sha256'])) for key,ref in refs.items()}
    event,started,failed,review,bundle=(loaded[k] for k in ('event','started','failed','review','bundle'))
    event_hash=refs['event']['sha256'];binding=request['binding']
    require(set(binding)=={'decision_id','research_version','available_cash_exact'},'BINDING_FIELDS')
    require(re.fullmatch('[0-9a-f]{64}',binding['decision_id']) and binding['research_version']=='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
        and isinstance(binding['available_cash_exact'],str) and re.fullmatch(r'[0-9]{1,20}(?:\.[0-9]{1,10})?(?:/[1-9][0-9]{0,20})?',binding['available_cash_exact']),'BINDING_FORMAT')
    start_time=datetime.fromisoformat(event['request_started_at']);event_time=datetime.fromisoformat(event['observed_at'])
    failure_time=datetime.fromisoformat(failed['at'])
    require(all(t.tzinfo is not None and t.utcoffset() is not None for t in (start_time,event_time,failure_time)) and start_time<=event_time<=failure_time<=observed,'EVENT_FAILURE_TIME')
    identifier=event['event_id'];require(re.fullmatch('[a-f0-9]{32}',identifier),'EVENT_ID')
    event_path=f"events/{start_time.astimezone(NY).date().isoformat()}/{identifier}.json"
    require(refs['event']['path']=='data/quantity_v2_observations/'+event_path,'EVENT_PATH_IDENTITY')
    context=event['research_context']
    require(event['schema']=='V2_GENERATED_PREVIEW_OBSERVATION_V1' and event['generated_not_confirmed_displayed'] is True
        and event['actual_fill_inferred'] is False and event['decision_id']==binding['decision_id']
        and context['research_id']==binding['decision_id'][:24]
        and all(context[k]==binding[k] for k in ('research_version','available_cash_exact')),'EVENT_BINDING')
    attempt=f'{STORAGE}/attempts/{event_hash}/{target}'
    for key in ('started','failed','review'):require(refs[key]['path']==attempt+'/'+key+'.json','ATTEMPT_IDENTITY')
    require(started['status']=='PREFLIGHT_ONLY' and started['session']==target and started['binding']==binding
        and started['event_sha256']==event_hash,'STARTED_BINDING')
    require(failed['status']=='BLOCKED' and failed['retry_allowed'] is False and failed['reason']=='MATURED_HORIZON_UNRESOLVED','SUPPORTED_FAILURE_REQUIRED')
    require(not safe_path(root,attempt+'/complete.json').exists(),'OLD_ATTEMPT_COMPLETED')
    pins=request['attempt_source_hashes']
    require(isinstance(pins,dict) and 3<=len(pins)<=MAX_FILES,'ATTEMPT_EVIDENCE_REQUIRED')
    actual={p.relative_to(root).as_posix() for p in safe_path(root,attempt).rglob('*') if p.is_file()}
    require(set(pins)==actual,'INCOMPLETE_ATTEMPT_EVIDENCE')
    total=0
    for path,h in pins.items():
        require(path.startswith(attempt+'/'),'ATTEMPT_SOURCE_ESCAPE')
        total+=len(hashed(path,h));require(total<=MAX_TOTAL,'EVIDENCE_SIZE_LIMIT')
    for key in ('started','failed','review'):require(pins[refs[key]['path']]==refs[key]['sha256'],'ATTEMPT_REF_CONFLICT')
    manifest_hash=refs['bundle']['sha256'];bundle_dir=f'{STORAGE}/bundles/{manifest_hash}'
    require(refs['bundle']['path']==bundle_dir+'/manifest.json','BUNDLE_PATH_IDENTITY')
    require(bundle['schema']=='V2_FOLLOWUP_BUNDLE_V1' and bundle['binding']==binding and bundle['event_path']==event_path
        and bundle['event_sha256']==event_hash and bundle['source_hashes'].get(event_path)==event_hash,'BUNDLE_IDENTITY')
    require(0<len(bundle['source_hashes'])<=MAX_FILES,'BUNDLE_SIZE_LIMIT')
    for path,h in bundle['source_hashes'].items():
        safe_path(Path('.'),path)
        total+=len(hashed(bundle_dir+'/sources/'+path,h));require(total<=MAX_TOTAL,'EVIDENCE_SIZE_LIMIT')
    for capture in event['captures']:
        path=capture['path'];require(path=='raw/'+capture['sha256']+'.bin','CAPTURE_IDENTITY')
        require(bundle['source_hashes'].get(path)==capture['sha256'],'CAPTURE_CLOSURE')
        hashed('data/quantity_v2_observations/'+path,capture['sha256'])
    require(review['status']=='EVIDENCE_REVIEW_ONLY' and review['binding']==binding
        and all(bundle['source_hashes'].get(p)==h for p,h in review['source_hashes'].items()),'OLD_REVIEW_BINDING')
    securities=[dict(security_id=o['security_id'],ticker=o['ticker'],security_type='EQUITY') for o in review['orders']]
    require(securities==started['securities'] and len({s['security_id'] for s in securities})==len(securities)
        and len({s['ticker'] for s in securities})==len(securities) and securities,'SECURITY_IDENTITY')
    calendar=parse(hashed(CALENDAR,CALENDAR_SHA))
    for path,h in calendar['source_hashes'].items():hashed(path,h)
    sessions=calendar['calendar'];reference=event_time.astimezone(NY).date().isoformat()
    require(reference in sessions and target in sessions and 0<sessions.index(target)-sessions.index(reference)<=20,'ORIGINAL_TARGET_WINDOW')
    closes=[r for r in calendar['sessions'] if r['date']==target];require(len(closes)==1,'TARGET_CALENDAR')
    require(datetime.fromisoformat(closes[0]['close_at'])<=observed,'TARGET_NOT_CLOSED')
    matured=[n for n in (1,5,20) if sessions.index(reference)+n<len(sessions) and sessions[sessions.index(reference)+n]<=target]
    require(matured and started['matured_horizons']==matured,'HORIZON_BINDING')
    require(review['reference_session']==reference,'REFERENCE_SESSION_BINDING')
    for order in review['orders']:
        require([h['sessions_after_reference'] for h in order['horizons']]==[1,5,20],'DUPLICATE_OR_MISSING_HORIZON')
        for horizon in order['horizons']:
            offset=horizon['sessions_after_reference'];position=sessions.index(reference)+offset
            require(position<len(sessions) and horizon['target_session']==sessions[position],'HORIZON_TARGET_BINDING')
    observations=bundle['daily_observations']
    require(len({(r['security_id'],r['date']) for r in observations})==len(observations),'DUPLICATE_DAILY_OBSERVATION')
    require(all(reference<r['date']<=target for r in observations),'BUNDLE_TARGET_DRIFT')
    horizons=[h for o in review['orders'] for h in o['horizons'] if h['sessions_after_reference'] in matured]
    require(any(h['status']!='CONDITIONAL_PRICE_CHANGE' for h in horizons),'ALREADY_COVERED')
    index=f'{STORAGE}/index/{digest(canonical(binding))}/{event_hash}.json';index_path=safe_path(root,index)
    expected_index=request['expected_index_sha256']
    actual_index=digest(hashed(index,expected_index,4096)) if index_path.exists() and expected_index is not None else digest(read_bytes(index_path,4096)) if index_path.exists() else None
    require(actual_index==expected_index,'INDEX_HASH_CONFLICT')
    pointer=parse(read_bytes(index_path,4096)) if index_path.exists() else None
    require((pointer or {}).get('manifest_sha256')==started['expected_manifest_sha256'],'INDEX_MANIFEST_CONFLICT')
    require(not index_path.with_suffix('.lock').exists() and not index_path.with_suffix('.pending').exists(),'INDEX_RECOVERY_REQUIRED')
    recovery_parent=f'{STORAGE}/recoveries/{event_hash}/{target}'
    parent=safe_path(root,recovery_parent)
    cursor=parent
    while cursor != root:
        require(not cursor.is_symlink() and not (hasattr(cursor,'is_junction') and cursor.is_junction()),'RECOVERY_PATH_ALIAS_REJECTED')
        cursor=cursor.parent
    require(not parent.exists() or not any(parent.iterdir()),'RECOVERY_ALREADY_EXISTS')
    output=recovery_parent+'/'+name;safe_path(root,output)
    return dict(status='RECOVERY_PREFLIGHT_ONLY_NOT_EXECUTED',request_sha256=digest(canonical(request)),
        recovery_directory=output,target_session=target,binding=binding,securities=securities,
        matured_horizons=matured,expected_index_sha256=expected_index,previous_manifest_sha256=started['expected_manifest_sha256'],
        evidence=refs,attempt_source_hashes=pins,validated_source_hashes=validated,http_calls=0,filesystem_writes=False,published=False,
        execution_available=False,requires_fresh_preflight_before_future_execution=True)
