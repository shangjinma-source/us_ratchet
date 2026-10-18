"""Bounded paper-model rights derivation, not a broker entitlement certificate.

Proofs contain a fixed baseline and source bytes, never the current chain itself.
The caller supplies the exact chain prefix during deterministic ledger replay.
"""
import base64
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
import re
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_quantity_v2_difference_service import document
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_paper_ledger import digest,initial,apply
from data.current_quantity_v2_monthly_bounded_review import _json
from data.current_research_ohlc_panel import parse_provider_ohlc
from scripts.current_research_official_alert_capture import parse_official_feed,URL

SCHEMA='QUANTITY_V2_DERIVED_PAPER_REVIEW_V1'
POLICY='BOUNDED_PUBLIC_PAPER_RIGHTS_DERIVATION_V1'
STATUS='NO_KNOWN_PENDING_RIGHTS_IN_PAPER_MODEL'
ERROR='PAPER_REVIEW_EVIDENCE_REQUIRED'
CANDIDATE='PAPER_REVIEW_ACTION_CANDIDATE'
MAX_BYTES=128*1024*1024


def _checked(package):
    require(type(package)is dict and set(package)=={'files','source_hashes','documents'},ERROR)
    files=package['files'];pins=package['source_hashes']
    require(type(files)is dict and set(files)==set(pins) and len(files)<=2000,ERROR)
    total=0
    for path,raw in files.items():
        CurrentQuantityV2CurrentCashSources._path(path)
        require(type(raw)is bytes and len(raw)<=32*1024*1024 and sha256(raw).hexdigest()==pins[path],ERROR)
        total+=len(raw);require(total<=MAX_BYTES,ERROR)
    return files


def _freeze(package):
    if package is None:return None
    _checked(package)
    return dict(source_hashes=deepcopy(package['source_hashes']),documents=deepcopy(package['documents']),
        files={p:base64.b64encode(v).decode() for p,v in package['files'].items()})


def _thaw(value):
    if value is None:return None
    require(type(value)is dict and set(value)=={'files','source_hashes','documents'} and len(value['files'])<=2000,ERROR)
    require(sum(len(v) for v in value['files'].values())<=4*((MAX_BYTES+2)//3),ERROR)
    files={}
    for p,text in value['files'].items():
        raw=base64.b64decode(text,validate=True);require(base64.b64encode(raw).decode()==text,ERROR);files[p]=raw
    package=dict(files=files,source_hashes=value['source_hashes'],documents=value['documents']);_checked(package);return package


def _securities(ledger):
    p=ledger.get('active_monthly_acceptance',ledger['acceptance'])['proposal']
    return p.get('securities',p['causal_inputs'].get('securities',{}))


def review_request(state,baseline_package=None,*,_verified_prefix=False):
    from data.current_quantity_v2_paper_chain import review_chain,accept_into,accept_month_into
    require(len(canonical(state))<=64*1024*1024 and len(state['operations'])<=1000,ERROR)
    state=deepcopy(state) if _verified_prefix else review_chain(state)
    baseline_index=0;automatic=baseline_package is None
    if automatic:
        g=state['genesis'];p=g['acceptance']['proposal'];a=g['acceptance']['account_state']
        require(p.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION' and a['shares']=={}
            and a['pending_rights']==[],'PAPER_BASELINE_REQUIRED')
        start=stamp(g['acceptance']['accepted_at']);baseline_hash=digest(g['acceptance'])
    else:
        files=_checked(baseline_package);docs=baseline_package['documents'];require(set(docs)=={'chain','review'},ERROR)
        baseline=review_chain(document(files[docs['chain']]));r=document(files[docs['review']])
        baseline_index=len(baseline['operations']);b=baseline['ledger']
        require(baseline['genesis']==state['genesis'] and state['operations'][:baseline_index]==baseline['operations'],'PAPER_BASELINE_NOT_ANCESTOR')
        require(set(r)=={'schema','account_id','state_revision','chain_sha256','pending_rights','reviewed_at','source_references'}
            and r['schema']=='EXPLICIT_PAPER_RIGHTS_BASELINE_V1' and r['account_id']==b['account_id']
            and r['state_revision']==b['revision'] and r['chain_sha256']==digest(baseline) and r['pending_rights']==[]
            and r['source_references'] and all(p in files for p in r['source_references']),ERROR)
        require(max(stamp(b['last_recorded_at']),stamp(b['last_effective_at']))<=stamp(r['reviewed_at']),ERROR)
        start=min(stamp(b['last_recorded_at']),stamp(b['last_effective_at']));baseline_hash=digest(baseline_package['source_hashes'])
    ledger=initial(state['genesis']['acceptance']);securities={};domain=set()
    def observe():
        current=_securities(ledger)
        for sid,q in ledger['shares'].items():
            if q:
                require(sid in current,ERROR);domain.add(sid)
                if sid in securities:
                    require(all(securities[sid].get(k)==current[sid].get(k) for k in ('ticker','issuer_id')),'PAPER_REVIEW_IDENTITY_CHANGED')
                securities[sid]=deepcopy(current[sid])
    if automatic:observe()
    for event in state['genesis']['events']:
        apply(ledger,deepcopy(event))
        if automatic:observe()
    for i,operation in enumerate(state['operations']):
        if i==baseline_index and not automatic:observe()
        if operation['kind']=='EVENT':
            event=operation['event']
            if i>=baseline_index and event['type']=='FILL':start=min(start,stamp(event['executed_at']))
            apply(ledger,deepcopy(event))
        elif operation['kind']=='ACCEPT':accept_into(ledger,operation)
        elif operation['kind']=='MONTHLY_RETARGET':accept_month_into(ledger,operation)
        else:raise ValueError('PAPER_REVIEW_UNSUPPORTED_OPERATION')
        if i>=baseline_index:observe()
    if not automatic and baseline_index==len(state['operations']):observe()
    require(ledger==state['ledger'],'CHAIN_REPLAY_MISMATCH')
    current=_securities(ledger)
    for sid,q in ledger['target_quantities'].items():
        if q:
            if sid in securities:require(all(securities[sid].get(k)==current[sid].get(k) for k in ('ticker','issuer_id')),'PAPER_REVIEW_IDENTITY_CHANGED')
            domain.add(sid);securities[sid]=deepcopy(current[sid])
    floor=max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))
    return dict(account_id=ledger['account_id'],state_revision=ledger['revision'],window_start=start.isoformat(),observed_floor=floor.isoformat(),
        securities={sid:securities[sid] for sid in sorted(domain)},current_target_quantities=deepcopy(ledger['target_quantities']),
        baseline_hash=baseline_hash,baseline_kind='VERIFIED_NEW_CASH_PAPER_GENESIS' if automatic else 'PINNED_EXPLICIT_ANCESTOR',
        chain_sha256=digest(state),ledger_sha256=digest(ledger),operation_prefix_sha256=digest(state['operations']))


def _screen(request,package,now):
    files=_checked(package);docs=package['documents'];now=stamp(now)
    require(set(docs)=={'action_receipts','rss_raw','rss_receipt'} and set(docs['action_receipts'])==set(request['securities']),ERROR)
    require(stamp(request['observed_floor'])<=now,ERROR)
    if not request['securities']:
        require(docs['rss_raw'] is None and docs['rss_receipt'] is None and not files,ERROR);return False
    start_date=stamp(request['window_start']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    names={};latest=stamp(request['observed_floor'])
    for sid,security in request['securities'].items():
        r=document(files[docs['action_receipts'][sid]]);raw=files[r['raw_path']]
        received=stamp(r['received_at']);latest=max(latest,received)
        require(r['security_id']==sid and r['ticker']==security['ticker'] and r['raw_sha256']==sha256(raw).hexdigest()
            and r['http_status']==200 and r['body_truncated'] is False and r['transport_error'] is None
            and r['events_requested']==['dividends','splits'] and r['interval']=='1d'
            and stamp(r['requested_from'])<=stamp(request['window_start'])
            and stamp(request['observed_floor'])<=stamp(r['requested_through'])<=received<=now
            and (now-received).total_seconds()<120,ERROR)
        from data.current_quantity_v2_paper_action_sources import daily_url
        require(r['url']==daily_url(security['ticker'],stamp(r['requested_from']),stamp(r['requested_through']))
            and r['request_period1']==int(stamp(r['requested_from']).timestamp())
            and r['request_period2']==int(stamp(r['requested_through']).timestamp())+1,ERROR)
        chart=_json(raw)['chart']['result'][0];parsed=parse_provider_ohlc(raw,security['ticker'])
        require(parsed['dates'][0]<=start_date and parsed['dates'][-1]==received.astimezone(ZoneInfo('America/New_York')).date().isoformat(),ERROR)
        meta=chart['meta'];names[sid]=[meta[k].strip() for k in ('longName','shortName') if isinstance(meta.get(k),str) and len(meta[k].strip())>=2]
        for kind,events in chart.get('events',{}).items():
            require(kind in ('splits','dividends') and type(events)is dict,ERROR)
            for event in events.values():
                require(type(event)is dict and type(event.get('date'))is int,ERROR)
                day=datetime.fromtimestamp(event['date'],timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                # Conservative whole-domain date envelope includes cleared positions.
                require(day<start_date,CANDIDATE)
    receipt=document(files[docs['rss_receipt']]);raw=files[docs['rss_raw']]
    received=stamp(receipt['received_at'])
    require(receipt['url']==URL and receipt['http_status']==200 and receipt['raw_sha256']==sha256(raw).hexdigest()
        and receipt['stored_bytes']==len(raw) and latest<=stamp(receipt['started_at'])<=received<=now
        and (now-received).total_seconds()<120,ERROR)
    parse_official_feed(raw,observed_at=received)
    for node in ET.fromstring(raw).iter():
        if node.tag.rsplit('}',1)[-1]!='item':continue
        text=' '.join(node.itertext())
        for sid,security in request['securities'].items():
            require(not any(re.search(r'(?<![A-Za-z0-9])'+re.escape(term)+r'(?![A-Za-z0-9])',text,re.I)
                for term in [security['ticker']]+names[sid]),CANDIDATE)
    return any(not value for value in names.values())


def _screen_saved_actions(state,request):
    """Retain positive known events already frozen in accepted evidence."""
    start=stamp(request['window_start']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    tickers={v['ticker'] for v in request['securities'].values()};seen=set();total=0
    def scan(value,depth=0):
        nonlocal total
        require(depth<=80,ERROR)
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('files_base64','files') and isinstance(item,dict):
                    for encoded in item.values():
                        if not isinstance(encoded,str):continue
                        try:raw=base64.b64decode(encoded,validate=True)
                        except (ValueError,TypeError):continue
                        h=sha256(raw).hexdigest()
                        if h in seen:continue
                        seen.add(h);total+=len(raw);require(total<=MAX_BYTES,ERROR)
                        try:obj=_json(raw)
                        except (ValueError,KeyError,UnicodeError):continue
                        if not isinstance(obj,dict) or not isinstance(obj.get('chart'),dict):continue
                        results=obj['chart'].get('result') or []
                        for chart in results:
                            if chart.get('meta',{}).get('symbol') not in tickers:continue
                            for kind,events in chart.get('events',{}).items():
                                require(kind in ('splits','dividends') and isinstance(events,dict),ERROR)
                                for event in events.values():
                                    require(type(event.get('date'))is int,ERROR)
                                    day=datetime.fromtimestamp(event['date'],timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                                    require(day<start,CANDIDATE)
                else:scan(item,depth+1)
        elif isinstance(value,list):
            for item in value:scan(item,depth+1)
    scan(state)


def derive_paper_review(state,baseline_package,action_package,now,*,_verified_prefix=False):
    request=review_request(state,baseline_package,_verified_prefix=_verified_prefix);now=stamp(now)
    if baseline_package is not None:
        r=document(baseline_package['files'][baseline_package['documents']['review']]);require(stamp(r['reviewed_at'])<=now,ERROR)
    _screen_saved_actions(state,request)
    limited=_screen(request,action_package,now)
    evidence=dict(schema='PAPER_REVIEW_EVIDENCE_V1',request=request,baseline_package=_freeze(baseline_package),action_package=_freeze(action_package))
    return dict(schema=SCHEMA,status=STATUS,policy=POLICY,account_id=request['account_id'],state_revision=request['state_revision'],
        pending_rights=[],reviewed_at=now.isoformat(),source_references=sorted(action_package['source_hashes']),derived_evidence=evidence,
        coverage_complete=False,source_authenticated=False,limited_name_coverage=limited,
        limitations=['Conditional independent paper model, not broker rights certification','Public sources may omit events; all known dividends and unit changes in the conservative window pause review'])


def validate_review_ledger_binding(review,ledger,now):
    require(review.get('schema')==SCHEMA and review.get('status')==STATUS and review.get('policy')==POLICY
        and review['account_id']==ledger['account_id'] and review['state_revision']==ledger['revision']
        and review['pending_rights']==[] and review['coverage_complete'] is False and review['source_authenticated'] is False
        and review['derived_evidence']['request']['ledger_sha256']==digest(ledger)
        and max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))<=stamp(review['reviewed_at'])<=stamp(now),ERROR)


def validate_paper_review(review,state,now,*,_verified_prefix=False):
    e=review['derived_evidence'];require(e['schema']=='PAPER_REVIEW_EVIDENCE_V1',ERROR)
    rebuilt=derive_paper_review(state,_thaw(e['baseline_package']),_thaw(e['action_package']),review['reviewed_at'],_verified_prefix=_verified_prefix)
    require(rebuilt==review,'PAPER_REVIEW_REPLAY_MISMATCH')
    validate_review_ledger_binding(review,state['ledger'],now)
    _screen(e['request'],_thaw(e['action_package']),now)
    return deepcopy(review)
