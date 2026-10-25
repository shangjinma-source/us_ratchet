"""Bounded raw research capture; never admits observations or updates accounts."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import require
from data.current_quantity_v2_paper_action_sources import fetch_daily_actions,daily_url
from scripts.current_research_official_alert_capture import fetch_official_feed,parse_official_feed,URL


def capture(*,plan_bytes,plan_sha256,output,clock=None,daily_fetch=None,official_fetch=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    daily_fetch=daily_fetch or fetch_daily_actions;official_fetch=official_fetch or fetch_official_feed
    require(sha256(plan_bytes).hexdigest()==plan_sha256,'GROUP_CAPTURE_PLAN_CHANGED')
    plan=json.loads(plan_bytes);groups=plan['groups'];began=clock()
    require(began.tzinfo is not None,'GROUP_CAPTURE_CLOCK')
    require(plan['schema']=='DAILY_FOLLOWUP_CAPTURE_GROUPS_V1' and 0<len(groups)<=100,'GROUP_CAPTURE_DOMAIN')
    require(len({g['security_id'] for g in groups})==len(groups) and
            len({g['ticker'] for g in groups})==len(groups),'GROUP_CAPTURE_DUPLICATE')
    for group in groups:
        require(bool(group['observations']) and bool(group['sessions']),'GROUP_CAPTURE_EMPTY')
        for close in group['sessions'].values():
            value=datetime.fromisoformat(close)
            require(value.tzinfo is not None and value<=began,'GROUP_CAPTURE_NOT_CLOSED')
    output=Path(output).absolute()
    require(not output.is_symlink() and not any(p.is_symlink() for p in output.parents),'GROUP_CAPTURE_SYMLINK')
    output.mkdir(parents=True,exist_ok=False)
    def save(name,body):
        with (output/name).open('xb') as stream:stream.write(body)
        return sha256(body).hexdigest()
    def document(name,value):return save(name,json.dumps(value,sort_keys=True,separators=(',',':')).encode())
    save('plan.json',plan_bytes);receipts=[]
    document('started.json',dict(started_at=began.isoformat(),plan_sha256=plan_sha256))
    try:
        for ordinal,group in enumerate(groups):
            started=clock();left=datetime.fromisoformat(group['earliest_reference_session']).replace(tzinfo=ZoneInfo('America/New_York'))-timedelta(days=45)
            response=daily_fetch(group['ticker'],left,started);received=clock()
            raw=response['body'];name=f'daily-{ordinal:03d}.bin'
            require(type(raw)is bytes and len(raw)<=4*1024*1024,'GROUP_CAPTURE_BYTES')
            digest=save(name,raw)
            receipt=dict(kind='daily',security_id=group['security_id'],ticker=group['ticker'],
                requested_from=left.isoformat(),requested_through=started.isoformat(),
                url=daily_url(group['ticker'],left,started),started_at=started.isoformat(),received_at=received.isoformat(),
                http_status=response['status'],raw_path=name,raw_sha256=digest,stored_bytes=len(raw))
            document(f'daily-{ordinal:03d}.receipt.json',receipt);receipts.append(receipt)
            require(began<=started<=received and response['status']==200,'GROUP_CAPTURE_TRANSPORT')
            chart=json.loads(raw)['chart']
            require(chart.get('error') is None and len(chart['result'])==1 and
                    chart['result'][0]['meta']['symbol']==group['ticker'],'GROUP_CAPTURE_DAILY_BODY')
        started=clock();response=official_fetch();received=clock();raw=response['body']
        require(type(raw)is bytes and len(raw)<=2*1024*1024,'GROUP_CAPTURE_BYTES')
        digest=save('official.bin',raw)
        receipt=dict(kind='official',url=URL,started_at=started.isoformat(),received_at=received.isoformat(),
            http_status=response['status'],raw_path='official.bin',raw_sha256=digest,stored_bytes=len(raw))
        document('official.receipt.json',receipt);receipts.append(receipt)
        require(all(datetime.fromisoformat(r['received_at'])<=started for r in receipts[:-1]) and
                started<=received and response['status']==200,'GROUP_CAPTURE_OFFICIAL_TRANSPORT')
        feed=parse_official_feed(raw,observed_at=received)
        require(not feed['channel']['publication_time_issue'] and feed['channel']['future_publication'] is False and
            all(not i['publication_time_issue'] and i['future_publication'] is False and not i['description_truncated'] for i in feed['items']),
            'GROUP_CAPTURE_OFFICIAL_TIME_OR_CONTENT')
        result=dict(status='RAW_SOURCES_SAVED_NOT_REVIEWED',plan_sha256=plan_sha256,receipts=receipts,
            network_calls=len(receipts),capture_admitted=False,account_writes=False,performance_computed=False)
        document('complete.json',result);return result
    except Exception as error:
        document('failed.json',dict(status='CAPTURE_STOPPED',error_type=type(error).__name__,reason=str(error),
            saved_receipts=len(receipts),retry_allowed=False))
        raise
