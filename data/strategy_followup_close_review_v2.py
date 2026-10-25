"""Conditional post-advice price observation; not a fill or strategy return."""
from datetime import datetime,timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from core.strategy_account_difference import require,timestamp
from data.strategy_followup_price_basis_v2 import review_price_basis
from data.strategy_account_notice_review import review_notices
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.current_research_official_alert_capture import parse_official_feed,URL


def review_close(*,observation,baseline_inputs,baseline_files,daily_bytes,daily_receipt,
                 official_bytes,official_receipt,now):
    require(now.tzinfo is not None,'FOLLOWUP_REVIEW_CLOCK')
    sid=observation['security_id'];ticker=observation['ticker']
    baseline=review_price_basis(baseline_inputs,baseline_files, monthly=observation.get('policy_id')=='SAVED_FRONTIER_CAP50_EXIT20_V1')['securities'][sid]
    require(baseline['ticker']==ticker,'FOLLOWUP_BASELINE_TICKER')
    require(baseline_inputs['signal_date']<=observation['reference_session']<observation['observation_session'],
            'FOLLOWUP_SESSION_ORDER')
    close_at=timestamp(observation['observation_close'])
    require(close_at.astimezone(ZoneInfo('America/New_York')).date().isoformat()==observation['observation_session'],
            'FOLLOWUP_CLOSE_DATE')
    for body,receipt in ((daily_bytes,daily_receipt),(official_bytes,official_receipt)):
        require(receipt['http_status']==200 and receipt['stored_bytes']==len(body) and
            receipt['raw_sha256']==sha256(body).hexdigest(),'FOLLOWUP_CAPTURE_HASH')
        require(close_at<=timestamp(receipt['started_at'])<=timestamp(receipt['received_at'])<=now,
                'FOLLOWUP_CAPTURE_TIME')
    require(daily_receipt['security_id']==sid and daily_receipt['ticker']==ticker,'FOLLOWUP_CAPTURE_IDENTITY')
    require(daily_receipt['url']==daily_url(ticker,timestamp(daily_receipt['requested_from']),timestamp(daily_receipt['requested_through'])),
            'FOLLOWUP_CAPTURE_URL')
    require(official_receipt['url']==URL and timestamp(daily_receipt['received_at'])<=timestamp(official_receipt['started_at']),
            'FOLLOWUP_OFFICIAL_ORDER')
    feed=parse_official_feed(official_bytes,observed_at=timestamp(official_receipt['received_at']))
    require(not feed['channel']['publication_time_issue'] and feed['channel']['future_publication'] is False and
        all(not i['publication_time_issue'] and i['future_publication'] is False and not i['description_truncated'] for i in feed['items']),
        'FOLLOWUP_OFFICIAL_INVALID')
    chart=json.loads(daily_bytes)['chart']
    require(chart.get('error') is None and len(chart['result'])==1,'FOLLOWUP_DAILY_SERIES')
    source=chart['result'][0];meta=source['meta']
    require(meta['symbol']==ticker and meta['currency']=='USD' and meta['exchangeName']=='NMS' and
        meta['instrumentType']=='EQUITY','FOLLOWUP_DAILY_IDENTITY')
    require(not any(source.get('events',{}).values()),'FOLLOWUP_CORPORATE_ACTION_REVIEW_REQUIRED')
    names=[meta[k] for k in ('longName','shortName') if isinstance(meta.get(k),str)]
    require(not review_notices(official_bytes,ticker=ticker,issuer_names=names)['blocking'], 'FOLLOWUP_OFFICIAL_CANDIDATE')
    expected={r['date']:Fraction(r['close']) for r in baseline_inputs['histories'][sid]['closes']}
    target=observation['observation_session'];needed=set(expected)|{target}
    times=source['timestamp'];prices=source['indicators']['quote'][0]['close'];adjusted=source['indicators']['adjclose'][0]['adjclose']
    require(len(times)==len(prices)==len(adjusted),'FOLLOWUP_DAILY_ARRAYS')
    seen={}
    for stamp,price,adj in zip(times,prices,adjusted):
        day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if day not in needed:continue
        require(day not in seen and type(price) in (int,float) and type(adj) in (int,float),'FOLLOWUP_DAILY_PRICE')
        value=Fraction(str(price));require(value>0 and value==Fraction(str(adj)),'FOLLOWUP_DAILY_ADJUSTMENT')
        seen[day]=value
    require(set(seen)==needed,'FOLLOWUP_MISSING_BARS')
    require(all(seen[d]==v for d,v in expected.items()),'FOLLOWUP_BASELINE_REVISED')
    reference=Fraction(observation['reference_limit']);require(reference>0,'FOLLOWUP_REFERENCE_PRICE')
    return dict(status='CONDITIONAL_PRICE_OBSERVATION',observation_id=observation['observation_id'],
        security_id=sid,ticker=ticker,side=observation['side'],observation_session=target,
        reference_limit=str(reference),closing_price=str(seen[target]),price_change_vs_reference=str(seen[target]/reference-1),
        daily_sha256=sha256(daily_bytes).hexdigest(),official_sha256=sha256(official_bytes).hexdigest(),
        baseline_overlap_sessions=len(expected),actual_fill_inferred=False,performance_computed=False,
        source_authenticated=False,coverage_complete=False)
