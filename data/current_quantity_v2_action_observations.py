"""Read saved official alerts as positive candidates, never a no-action certificate."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
from scripts.current_research_official_alert_capture import parse_official_feed,URL,MAX_BYTES
from data.current_quantity_v2_current_cash_plan import parse,require,timestamp


def read_saved_action_observations(*,root,raw_path,raw_sha256,receipt_path,receipt_sha256,securities,now):
    """No HTTP/writes. Securities are caller-bound identities; matches are hints.

    securities[sid] = {ticker, issuer_aliases:[...]}. No parser result is promoted
    to verified entity, effective time, ratio or unit-continuity approval.
    """
    root=Path(root).resolve();current=timestamp(now) if isinstance(now,str) else now
    require(isinstance(current,datetime) and current.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
    def read(name,expected,limit):
        require(type(name)is str and name and '\\' not in name and ':' not in name
            and not PurePosixPath(name).is_absolute() and all(x not in ('','.','..') for x in name.split('/')),
            'ACTION_SOURCE_SAFE_PATH_REQUIRED')
        require(type(expected)is str and re.fullmatch('[a-f0-9]{64}',expected),'ACTION_SOURCE_HASH_REQUIRED')
        p=(root/name).resolve();require(p.is_relative_to(root),'ACTION_SOURCE_PATH_ESCAPE')
        with p.open('rb') as stream:data=stream.read(limit+1)
        require(len(data)<=limit and sha256(data).hexdigest()==expected,'ACTION_SOURCE_CHANGED_OR_OVERSIZE')
        return data
    raw=read(raw_path,raw_sha256,MAX_BYTES);receipt=parse(read(receipt_path,receipt_sha256,128*1024))
    require(receipt['url']==URL and receipt['http_status']==200 and receipt['body_truncated']is False
        and receipt.get('transport_error')is None and receipt['raw_sha256']==raw_sha256
        and receipt['stored_bytes']==len(raw),'ACTION_CAPTURE_INVALID')
    observed=timestamp(receipt['received_at_utc']);started=timestamp(receipt['request_started_at_utc'])
    require(started<=observed<=current,'ACTION_CAPTURE_TIME_INVALID')
    parsed=parse_official_feed(raw,observed_at=observed)
    require(type(securities)is dict and 0<len(securities)<=101,'ACTION_SECURITY_DOMAIN_REQUIRED')
    result={}
    for sid,security in securities.items():
        require(type(sid)is str and sid and type(security)is dict
            and set(security)=={'ticker','issuer_aliases'} and type(security['ticker'])is str
            and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',security['ticker'])
            and type(security['issuer_aliases'])is list and len(security['issuer_aliases'])<=20
            and all(type(x)is str and 2<=len(x)<=200 for x in security['issuer_aliases']),
            'ACTION_SECURITY_FIELDS')
        terms=[security['ticker'],*security['issuer_aliases']];candidates=[]
        for item in parsed['items']:
            text=item['title']+' '+item['description_summary']
            matches=[term for term in terms if re.search(r'(?<![A-Za-z0-9])'+re.escape(term)+r'(?![A-Za-z0-9])',text,re.I)]
            if not matches:continue
            candidates.append(dict(source_item_index=item['index'],notice_id=item['guid'] or item['link'],
                title=item['title'],url=item['link'],news_category=item['news_category'],
                published_at=item['published_at_utc'],publication_time_issue=item['publication_time_issue'],
                future_at_capture=item['future_publication'],
                future_publication_at_review=(timestamp(item['published_at_utc'])>current) if item['published_at_utc'] else None,
                usable_as_effective_action=False,observed_at=observed.isoformat(),
                summary=item['description_summary'],description_truncated=item['description_truncated'],
                matched_terms=matches,entity_match_status='UNCONFIRMED_TEXT_CANDIDATE',
                action_type=None,effective_at=None,effective_date=None,ratio=None,
                review_status='UNRESOLVED',reason='ENTITY_AND_ACTION_DETAILS_REQUIRE_SOURCE_REVIEW'))
        result[sid]=dict(ticker=security['ticker'],
            status='UNKNOWN_NEEDS_ENTITY_ACTION_REVIEW' if candidates else 'NO_MATCH_IN_OBSERVED_SOURCE_NOT_NO_ACTION',
            unresolved_candidates=candidates,confirmed_unit_events=[],unit_continuity_approved=False)
    return dict(schema='SAVED_OFFICIAL_POSITIVE_ACTION_OBSERVATIONS_V1',securities=result,
        source_received_at=observed.isoformat(),source_age_seconds=(current-observed).total_seconds(),
        total_feed_items=len(parsed['items']),channel=parsed['channel'],source_url=URL,
        source_hashes={raw_path:raw_sha256,receipt_path:receipt_sha256},
        coverage_from=None,coverage_through=None,coverage_complete=False,retention_unknown=True,
        source_authenticated=False,identity_verified=False,unit_continuity_approved=False,
        conditional_policy_enabled=False,network_calls=0,account_writes=0,
        limitations=['Only retained visible feed items are examined; no match is not absence of actions.',
            'Text matches, including future or undated items, remain unresolved; links are not fetched.',
            'Source age is reported without claiming current coverage; publication is not effective time.',
            'Local source hashes establish byte identity, not trusted historical timing.'])
