"""Offline monthly known-source screening. No fetch, publication or certification."""
import html,json,re,xml.etree.ElementTree as ET
from hashlib import sha256
from scripts.prepare_monthly_captured_training import build
from scripts.current_research_official_alert_capture import parse_official_feed,URL
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,stamp

POLICY_SCHEMA='MONTHLY_VISIBLE_OFFICIAL_FEED_SCREEN_V1'


def normalized_notice_text(value):
    # RSS descriptions commonly contain escaped HTML and non-breaking spaces.
    return ' '.join(re.sub(r'<[^>]*>', ' ', html.unescape(value)).split())


def review(*,preparation_arguments,feed_raw,feed_receipt_raw,policy_raw,evidence_prefix):
    """Rebuild verified capture/training; return bytes for caller create-only archival.

    Retention and name screening are bounded. This does not create identities,
    held-position close evidence, or a publish request.
    """
    require(type(policy_raw)is bytes and len(policy_raw)<=65536 and type(feed_receipt_raw)is bytes and len(feed_receipt_raw)<=65536 and type(feed_raw)is bytes and len(feed_raw)<=2*1024*1024,'SCREEN_EVIDENCE_SIZE_INVALID')
    now=stamp(preparation_arguments['clock']())
    manifest,compiled,report=build(**dict(preparation_arguments,clock=lambda:now))
    require(compiled['status']=='READY_CONDITIONAL','TRAINING_NOT_READY')
    require(type(evidence_prefix)is str and re.fullmatch(r'[A-Za-z0-9_/-]+',evidence_prefix)
            and not evidence_prefix.startswith('/') and '..' not in evidence_prefix,'INVALID_EVIDENCE_PREFIX')
    policy=json.loads(policy_raw)
    require(set(policy)=={'schema','authority','maximum_capture_age_seconds','matching','coverage','retention'}
            and policy['schema']==POLICY_SCHEMA and policy['authority']=='RESEARCH_BOUNDED_SOURCE_ASSUMPTION'
            and type(policy['maximum_capture_age_seconds'])is int and 0<policy['maximum_capture_age_seconds']<=86400
            and policy['matching']=='ALL_VISIBLE_ITEMS_EXACT_TICKER_OR_META_NAME'
            and policy['coverage']=='INCOMPLETE_MAY_OMIT_ACTIONS' and policy['retention']=='UNKNOWN','INVALID_MONTHLY_SCREEN_POLICY')
    paths={k:evidence_prefix+'/'+k for k in ('policy.json','feed.xml','feed_receipt.json','scan.json')}
    evidence={paths['policy.json']:policy_raw,paths['feed.xml']:feed_raw,paths['feed_receipt.json']:feed_receipt_raw}
    root=preparation_arguments['root'];from pathlib import Path
    files={};total=0
    for path,h in manifest['source_hashes'].items():
        p=Path(root)/path;require(not p.is_symlink() and p.is_file() and p.stat().st_size<=32*1024*1024,'SOURCE_UNAVAILABLE')
        raw=p.read_bytes();total+=len(raw);require(total<=128*1024*1024,'SCREEN_SOURCES_TOO_LARGE');require(sha256(raw).hexdigest()==h,'SOURCE_CHANGED');files[path]=raw
    plan=json.loads(files[preparation_arguments['plan_path']]);calendar=json.loads(files[plan['calendar_path']])
    session=next(s for s in calendar['sessions'] if s['date']==manifest['decision_date']);closing=stamp(session['close_at'])
    require(closing<=now,'SESSION_NOT_CLOSED')
    global_reasons=[];items=[];feed_summary=None
    try:
        rec=json.loads(feed_receipt_raw);started=stamp(rec['request_started_at_utc']);received=stamp(rec['received_at_utc'])
        require(rec['url']==URL and rec['http_status']==200 and rec['body_truncated'] is False
                and rec['transport_error'] is None and rec['raw_sha256']==sha256(feed_raw).hexdigest()
                and rec['stored_bytes']==len(feed_raw),'OFFICIAL_FEED_RECEIPT_INVALID')
        require(closing<=started<=received<=now and (now-received).total_seconds()<=policy['maximum_capture_age_seconds'],'OFFICIAL_FEED_TIME_INVALID')
        feed_summary=parse_official_feed(feed_raw,observed_at=received)
        require(not feed_summary['channel']['publication_time_issue'] and feed_summary['channel']['future_publication'] is not True
                and all(not r['publication_time_issue'] and r['future_publication'] is False for r in feed_summary['items']),'OFFICIAL_FEED_ITEM_TIME_UNRESOLVED')
        # Full item text, not parser's deliberately truncated display summaries.
        items=[normalized_notice_text(' '.join(i.itertext())) for i in ET.fromstring(feed_raw).find('channel').findall('item')]
    except (ValueError,KeyError,TypeError,ET.ParseError,UnicodeError):global_reasons.append('OFFICIAL_FEED_UNUSABLE_OR_TIME_UNRESOLVED')
    rows=[];unresolved=[]
    for member in manifest['candidates']:
        reasons=list(global_reasons);ticker=member['ticker'];sid=member['security_id'];matches=[];names=[]
        try:
            meta=json.loads(files[member['training_source']])['chart']['result'][0]['meta']
            require(meta['symbol']==ticker and meta['currency']=='USD' and meta['instrumentType']=='EQUITY','MEMBER_META_IDENTITY_CONFLICT')
            names=list(dict.fromkeys(meta[k].strip() for k in ('longName','shortName') if type(meta.get(k))is str and len(meta[k].strip())>=3))
            require(names,'MEMBER_META_NAME_MISSING')
            require(sid in compiled['input']['search_arguments']['metadata'] and compiled['input']['search_arguments']['metadata'][sid]['ticker']==ticker
                    and compiled['input']['search_arguments']['metadata'][sid]['issuer_id']==member.get('issuer_id'),'MEMBER_NOT_TRAINING_ELIGIBLE')
        except (KeyError,TypeError,ValueError):reasons.append('MEMBER_META_OR_ELIGIBILITY_UNRESOLVED')
        terms=[normalized_notice_text(term) for term in [ticker]+names]
        for index,text in enumerate(items):
            if any(re.search(r'(?<![A-Za-z0-9])'+re.escape(term)+r'(?![A-Za-z0-9])',text,re.I) for term in terms):matches.append(index)
        if matches:reasons.append('OFFICIAL_NOTICE_MATCH_REQUIRES_RESOLUTION')
        rows.append(dict(ticker=ticker,security_id=sid,names=names,matched_item_indexes=matches,reasons=reasons,training_source=member['training_source']))
        for reason in reasons:unresolved.append(dict(ticker=ticker,security_id=sid,issuer_id=member.get('issuer_id'),reason=reason,source_references=list(paths.values())))
    scan=dict(schema='MONTHLY_KNOWN_SOURCE_SCAN_EVIDENCE_V1',decision_date=manifest['decision_date'],reviewed_at=now.isoformat(),policy=policy,
        preparation_source_hashes=manifest['source_hashes'],preparation_report=report,rows=rows,feed_summary=feed_summary,
        evidence_hashes={p:sha256(raw).hexdigest() for p,raw in evidence.items()},coverage_complete=False,retention_unknown=True,
        source_authenticated=False,point_in_time_certified=False,action_completeness_certified=False,
        limitations=['Only visible saved official feed screened; actions and historical notices may be absent.','Names and ticker text matches are conservative candidates, not resolved actions.','Training checks inherit conditional identity/coordinate assumptions; not historical certification.','Held outside-domain marks and final publication request are not produced.'])
    evidence[paths['scan.json']]=canonical(scan)
    result=dict(schema='MONTHLY_KNOWN_SOURCE_REVIEW_V1',decision_date=manifest['decision_date'],reviewed_at=now.isoformat(),source_references=list(evidence),reviewed_members=[r['ticker'] for r in rows],unresolved=unresolved)
    return dict(status='UNRESOLVED' if unresolved else 'NO_MATCH_UNDER_BOUNDED_POLICY',review=result,evidence_files=evidence,source_hashes={p:sha256(raw).hexdigest() for p,raw in evidence.items()},account_writes=False,network_calls=0,publication=False)
