"""Bounded public-source screening, never a complete corporate-action certificate."""
import base64
from datetime import datetime, timezone
from hashlib import sha256
import json
import html
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from data.current_quantity_v2_current_cash_plan import canonical, BASIS
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_research_intraday_execution import decode_intraday_reference
from scripts.current_research_official_alert_capture import fetch_official_feed, parse_official_feed, URL, MAX_BYTES

POLICY='BOUNDED_PUBLIC_KNOWN_ACTIONS_V1'
STATUS='NO_KNOWN_UNIT_CHANGE_UNDER_BOUNDED_PUBLIC_REVIEW'
LIMITATIONS=['公开来源可能漏报，未发现不代表不存在单位变化', '发行人名称来自当前行情；缺名称时仅匹配证券代码']


def _files(evidence):
    encoded=evidence['files'];pins=evidence['source_hashes']
    require(type(encoded)is dict and set(encoded)==set(pins) and len(encoded)<=8,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
    require(sum(len(v) for v in encoded.values())<=16*1024*1024,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
    result={}
    for p,v in encoded.items():
        require(type(p)is str and p and "\\" not in p and ":" not in p and not PurePosixPath(p).is_absolute() and all(x not in ("..",".","") for x in p.split("/")),"BOUNDED_PUBLIC_REVIEW_UNAVAILABLE")
        raw=base64.b64decode(v,validate=True)
        require(base64.b64encode(raw).decode()==v and sha256(raw).hexdigest()==pins[p],'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
        result[p]=raw
    return result


def _quote(files,pins,security,captured,now,fresh):
    require(pins and all(p in files and sha256(files[p]).hexdigest()==h for p,h in pins.items()),'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
    receipts=[]
    for p in pins:
        value=json.loads(files[p])
        if isinstance(value,dict) and 'raw_path' in value:receipts.append(value)
    require(len(receipts)==1,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE');receipt=receipts[0]
    require(receipt['ticker']==security['ticker'] and receipt['security_id']==security['security_id'] and stamp(receipt['captured_at'])==captured,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
    raw=files[receipt['raw_path']]
    require(sha256(raw).hexdigest()==receipt['raw_sha256'],'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
    chart=json.loads(raw)['chart']['result'][0];meta=chart['meta']
    require(meta['symbol']==security['ticker'] and meta['currency']=='USD' and meta['instrumentType']=='EQUITY','BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
    require(not any(v for k,v in chart.get('events',{}).items() if k!='dividends'),'BOUNDED_UNIT_CHANGE_CANDIDATE')
    if fresh:
        ref=decode_intraday_reference(raw,ticker=security['ticker'],now=now,captured_at=captured)
        require(stamp(ref['last_at'])<=captured and now<stamp(ref['refresh_by']),'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
    return meta, (ref if fresh else None)


def replay_bounded_review(unit,*,security,origin,current,now):
    """Recompute from frozen bytes; local hashes do not authenticate outside sources."""
    try:
        now=stamp(now);e=unit['bounded_evidence'];files=_files(e)
        require(e['policy']==POLICY and e['security']==security,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
        old=stamp(origin['captured_at']);new=stamp(current['captured_at'])
        require(old<=new<=now,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
        _quote(files,origin['source_hashes'],security,old,now,False)
        meta,decoded=_quote(files,current['source_hashes'],security,new,now,True)
        if 'last_price' in current:
            for key in ('last_price','minute_low','last_at','minute_start','minute_end','session'):
                require(current[key]==decoded[key],'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
        receipt=json.loads(files[e['rss_receipt_path']]);raw=files[e['rss_raw_path']]
        received=stamp(receipt['received_at']);started=stamp(receipt['started_at'])
        require(receipt['url']==URL and receipt['http_status']==200 and receipt['raw_sha256']==sha256(raw).hexdigest()
            and receipt['stored_bytes']==len(raw) and new<=started<=received<=now
            and (now-received).total_seconds()<120,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
        parsed=parse_official_feed(raw,observed_at=received)
        require(not parsed['channel']['publication_time_issue']
            and parsed['channel']['future_publication'] is not True
            and all(not item['publication_time_issue'] and item['future_publication'] is False
                    for item in parsed['items']),'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
        names=[meta[k].strip() for k in ('longName','shortName') if isinstance(meta.get(k),str) and len(meta[k].strip())>=2]
        def normalized(value):
            return ' '.join(re.sub(r'<[^>]*>', ' ', html.unescape(value)).split())
        terms=list(map(normalized,[security['ticker']]+names))
        # Parser already rejected entities/DOCTYPE; do not screen only truncated summaries.
        items=[node for node in ET.fromstring(raw).iter() if node.tag.rsplit('}',1)[-1]=='item']
        for item in items:
            text=normalized(' '.join(item.itertext()))
            require(not any(re.search(r'(?<![A-Za-z0-9])'+re.escape(term)+r'(?![A-Za-z0-9])',text,re.I) for term in terms),'BOUNDED_UNIT_CHANGE_CANDIDATE')
        return dict(policy=POLICY,coverage_complete=False,source_authenticated=False,retention_unknown=True,
            limited_name_coverage=not bool(names),limitations=LIMITATIONS)
    except ValueError as error:
        if str(error) in ('BOUNDED_UNIT_CHANGE_CANDIDATE','BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):raise
        raise ValueError('BOUNDED_PUBLIC_REVIEW_UNAVAILABLE') from error
    except Exception as error:raise ValueError('BOUNDED_PUBLIC_REVIEW_UNAVAILABLE') from error


class BoundedPublicUnitReview:
    policy=POLICY
    def __init__(self,*,fetch=fetch_official_feed,clock=None):
        self.fetch=fetch;self.clock=clock or (lambda:datetime.now(timezone.utc))

    def __call__(self,snapshot):
        try:
            started=stamp(self.clock());response=self.fetch();received=stamp(self.clock())
            raw=response['body']
            require(type(raw)is bytes and 0<len(raw)<=MAX_BYTES and response['status']==200,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
            token=sha256(raw+received.isoformat().encode()).hexdigest()
            prefix='bounded-review/'+token+'/'
            rawpath=prefix+'rss.xml';receiptpath=prefix+'receipt.json'
            files={rawpath:raw,receiptpath:canonical(dict(url=URL,http_status=200,started_at=started.isoformat(),received_at=received.isoformat(),raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw)))}
            units={}
            for sid,current in snapshot['current_receipts'].items():
                security=snapshot['securities'][sid];origin=snapshot['origins'][sid]
                needed=set(origin['source_hashes'])|set(current['source_hashes'])
                source={**snapshot['origin_files'],**snapshot['quote_files']}
                subset={**files,**{p:source[p] for p in needed}}
                evidence=dict(policy=POLICY,security=security,rss_raw_path=rawpath,rss_receipt_path=receiptpath,
                    files={p:base64.b64encode(v).decode() for p,v in subset.items()},source_hashes={p:sha256(v).hexdigest() for p,v in subset.items()})
                unit=dict(security_id=sid,ticker=security['ticker'],security_class=security['security_class'],price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',initial_price_basis=BASIS,status=STATUS,
                    initial_execution_target_id=snapshot['execution_target_id'],initial_reference_source_hashes=origin['source_hashes'],reference_source_hashes=current['source_hashes'],
                    covered_from=origin['captured_at'],covered_through=current['captured_at'],reviewed_at=received.isoformat(),source_references=[rawpath,receiptpath],bounded_evidence=evidence)
                replay_bounded_review(unit,security=security,origin=origin,current=current,now=received);units[sid]=unit
            path=prefix+'units.json';files[path]=canonical(units)
            return dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},unit_continuity_path=path)
        except ValueError as error:
            if str(error) in ('BOUNDED_UNIT_CHANGE_CANDIDATE','BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):raise
            raise ValueError('BOUNDED_PUBLIC_REVIEW_UNAVAILABLE') from error
        except Exception as error:raise ValueError('BOUNDED_PUBLIC_REVIEW_UNAVAILABLE') from error

