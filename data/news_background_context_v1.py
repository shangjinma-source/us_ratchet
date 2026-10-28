"""Server-pinned historical issuer context; never a discovery event or action evidence."""
from copy import deepcopy
from datetime import datetime, date, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

BACKGROUND_INSTRUCTION = ''' Historical background_sources are separate from current triggering sources. They are old quarterly context, NOT latest guidance and NOT new triggers. Their observation time cannot renew any event window. Only current sources may be cited in action evidence; background alone cannot justify an action. Preserve publication minute conflicts (null means unknown), reference periods, later-update gaps and all limitations. Different metrics, accounting scopes, units or reference periods are not interchangeable. Missing intervening guidance or ambiguous flattened tables means comparability is unknown; do not infer a guidance cut/raise. Background explanatory references are not separately quote-validated action evidence. A long-term financial framework does not replace a quarterly outlook for a different reference period. Historical model memory is not evidence. '''

def moment(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('BACKGROUND_AWARE_TIME_REQUIRED')
    return t

def verify_manifest(root,configuration):
    root=Path(root).resolve();path=(root/configuration['manifest_path']).resolve()
    if not path.is_relative_to(root):raise ValueError('BACKGROUND_PATH_OUTSIDE_ROOT')
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=configuration['manifest_sha256']:raise ValueError('BACKGROUND_MANIFEST_CHANGED')
    manifest=json.loads(raw)
    if manifest.get('events')!=[]:raise ValueError('BACKGROUND_CANNOT_CONTAIN_EVENTS')
    seen_paths={}
    for name,expected in manifest['source_hashes'].items():
        file=(root/name).resolve()
        canonical=str(file).casefold()
        if canonical in seen_paths and seen_paths[canonical] != expected:raise ValueError('BACKGROUND_CONFLICTING_PATH_PINS')
        seen_paths[canonical]=expected
        if not file.is_relative_to(root) or sha256(file.read_bytes()).hexdigest()!=expected:raise ValueError('BACKGROUND_SOURCE_CHANGED')
    return manifest

def attach_background(payload,background_sources,now=None):
    if not background_sources:return payload
    if not payload.get('sources'):raise ValueError('CURRENT_TRIGGER_REQUIRED_FOR_BACKGROUND')
    current=now or datetime.now(timezone.utc)
    trigger_by_sid={}
    for source in payload['sources']:
        for sid in source['security_ids']:trigger_by_sid.setdefault(sid,[]).append(moment(source['published_at']))
    admitted=[];seen={s['id'] for s in payload['sources']}
    for record in background_sources:
        row=deepcopy(record)
        if row.get('role')!='BACKGROUND' or row.get('eligible_as_new_trigger') is not False or row.get('may_refresh_event_window') is not False:raise ValueError('BACKGROUND_ROLE_REQUIRED')
        if row['id'] in seen:raise ValueError('BACKGROUND_SOURCE_ID_COLLISION')
        seen.add(row['id'])
        if row.get('content_kind')!='FULL_TEXT' or not row.get('text') or sha256(row['text'].encode()).hexdigest()!=row['text_sha256']:raise ValueError('BACKGROUND_FULL_BODY_HASH_REQUIRED')
        if moment(row['observed_at'])>current:raise ValueError('BACKGROUND_NOT_OBSERVED_AT_DECISION')
        # Unknown timezone date: global latest bound, never a fabricated minute.
        upper=datetime.combine(date.fromisoformat(row['publication_date'])+timedelta(days=1),datetime.min.time(),timezone.utc)+timedelta(hours=12)
        if not row.get('security_ids') or any(s not in trigger_by_sid or upper>=min(trigger_by_sid[s]) for s in row['security_ids']):raise ValueError('BACKGROUND_MUST_PRECEDE_CURRENT_TRIGGER')
        if 'CONFLICT' in row['publication_time_quality'] and row.get('published_at') is not None:raise ValueError('BACKGROUND_CONFLICT_MUST_REMAIN_UNKNOWN')
        admitted.append(row)
    result=deepcopy(payload)
    for source in result['sources']:source['role']='TRIGGER'
    result['background_sources']=admitted
    return result

def load_background(root,configuration,sources,positions,now):
    if not sources:return []
    manifest=verify_manifest(root,configuration)
    domain={p['security_id']:p['ticker'] for p in positions}
    trigger_ids={sid for s in sources for sid in s['security_ids']}
    result=[]
    for entry in manifest['background_sources']:
        ids=sorted(sid for sid,ticker in domain.items() if ticker==entry['ticker'] and sid in trigger_ids)
        if not ids:continue
        body=(Path(root).resolve()/entry['body_path']).resolve()
        if not body.is_relative_to(Path(root).resolve()) or not any((Path(root).resolve()/name).resolve()==body and value==entry['text_sha256'] for name,value in manifest['source_hashes'].items()):
            raise ValueError('BACKGROUND_BODY_NOT_PINNED_WITHIN_ROOT')
        text=body.read_text(encoding='utf-8')
        row={k:deepcopy(entry[k]) for k in ('id','role','title','url','ticker','issuer','observed_at','published_at','publication_date','publication_time_candidates','publication_time_quality','reference_period','limitations','eligible_as_new_trigger','may_refresh_event_window','text_sha256')}
        row.update(security_ids=ids,content_kind='FULL_TEXT',text=text,latest_known_later_context=deepcopy(entry.get('latest_known_later_context')))
        result.append(row)
    return attach_background({'sources':sources,'positions':positions},result,now).get('background_sources',[])
