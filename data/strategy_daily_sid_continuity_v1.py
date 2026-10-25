"""One-security continuity review before one full-domain account rebind."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical,require
from data.strategy_daily_session_capture import stamp
from data.current_quantity_v2_paper_action_sources import daily_url
from data.strategy_account_notice_review import review_notices
from scripts.current_research_official_alert_capture import parse_official_feed,URL


def review_sid_continuity(*,security_id,parent_receipt_bytes,trusted_parent_sha256,parent_files,
                          calendar_bytes,calendar_reference,capture_files,now):
    """Only server-hash-admitted previous-session parent packets are accepted."""
    current=stamp(now);sid=security_id
    require(sha256(parent_receipt_bytes).hexdigest()==trusted_parent_sha256,'SID_PARENT_HASH')
    parent=json.loads(parent_receipt_bytes)
    require(parent['schema']=='SERVER_REVIEWED_DAILY_EVIDENCE_V1' and parent['normalization_reviewed'] is True
            and parent['unresolved_units']==[] and parent['pending_rights']==[],'SID_PARENT_REVIEW')
    require(set(parent_files)==set(parent['source_sha256']) and
            all(sha256(raw).hexdigest()==parent['source_sha256'][name] for name,raw in parent_files.items()),
            'SID_PARENT_CLOSURE')
    require(0<len(parent_files)<=2000 and sum(map(len,parent_files.values()))<=32*1024*1024,'SID_PARENT_BUDGET')
    calendar=json.loads(calendar_bytes)
    require(sha256(calendar_bytes).hexdigest()==calendar_reference['sha256']
            and calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1','SID_CALENDAR_HASH')
    sessions=calendar['sessions'];dates=[row['date'] for row in sessions]
    require(dates==sorted(set(dates)),'SID_CALENDAR_DATES')
    today=current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(today in dates and dates.index(today)>=21,'SID_CALENDAR_COVERAGE')
    index=dates.index(today);session=sessions[index];previous=sessions[index-1];window=sessions[index-20:index]
    require(parent['execution_session']['date']==previous['date'] and
            all(stamp(parent['execution_session'][key])==stamp(previous[key]) for key in ('open','close')),
            'SID_EXACT_PREVIOUS_SESSION')
    require(stamp(parent['source_received_at'])<=stamp(parent['available_at'])<stamp(previous['close'])<=current
            <stamp(session['close']),'SID_PARENT_TIME')
    old_inputs=json.loads(parent_files[parent['normalized_inputs_path']])
    require(old_inputs['signal_date']==sessions[index-2]['date'] and
            stamp(parent['market_asof'])==stamp(sessions[index-2]['close']),'SID_PARENT_ASOF')
    history=old_inputs['histories'][sid];units=history['units']
    require(units['schema']=='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1' and units['currency']=='USD'
            and units['unit_asof']==old_inputs['signal_date'],'SID_PARENT_UNIT')
    source=json.loads(parent_files[history['source_reference']])['chart']['result'][0]
    meta=source['meta'];ticker=meta['symbol']
    require(meta['currency']=='USD' and meta['exchangeName']=='NMS' and meta['instrumentType']=='EQUITY',
            'SID_PARENT_IDENTITY')
    require(set(capture_files)=={'daily.response.bin','daily.receipt.json','official.response.bin','official.receipt.json'},
            'SID_CAPTURE_DOMAIN')
    receipts={}
    for name in ('daily','official'):
        body=capture_files[name+'.response.bin'];receipt=json.loads(capture_files[name+'.receipt.json'])
        started,received=stamp(receipt['started_at']),stamp(receipt['received_at'])
        require(receipt['status']=='CAPTURED' and receipt['attempts']==1 and receipt['http_status']==200
                and receipt['stored_bytes']==len(body) and receipt['raw_sha256']==sha256(body).hexdigest(),
                'SID_CAPTURE_RECEIPT')
        require(stamp(previous['close'])<=started<=received<=current and
                received.astimezone(ZoneInfo('America/New_York')).date().isoformat()==today,'SID_CAPTURE_TIME')
        require(receipt['url']==(daily_url(ticker,stamp(window[0]['open'])-timedelta(days=1),started)
                if name=='daily' else URL),'SID_CAPTURE_URL')
        receipts[name]=receipt
    chart=json.loads(capture_files['daily.response.bin'])['chart']
    require(chart.get('error')is None and len(chart['result'])==1,'SID_SERIES_COUNT')
    row=chart['result'][0]
    require(all(row['meta'].get(k)==meta[k] for k in ('symbol','currency','exchangeName','instrumentType')),
            'SID_IDENTITY_CHANGED')
    require(not any(row.get('events',{}).values()),'SID_KNOWN_ACTION')
    prices={};timestamps=row['timestamp'];closes=row['indicators']['quote'][0]['close'];adjusted=row['indicators']['adjclose'][0]['adjclose']
    require(len(timestamps)==len(closes)==len(adjusted),'SID_ARRAY_LENGTH')
    for ts,price,adj in zip(timestamps,closes,adjusted):
        day=datetime.fromtimestamp(ts,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if day not in dates[index-20:index]:continue
        require(day not in prices and type(price)is not bool and price==adj and Fraction(str(price))>0,'SID_PRICE_UNIT')
        prices[day]=str(price)
    require(sorted(prices)==dates[index-20:index],'SID_TWENTY_SESSIONS')
    old={row['date']:row['close'] for row in history['closes']}
    overlap=set(old)&set(prices)
    require(len(overlap)==19 and all(Fraction(old[d])==Fraction(prices[d]) for d in overlap),'SID_CONTINUITY')
    feed=parse_official_feed(capture_files['official.response.bin'],observed_at=stamp(receipts['official']['received_at']))
    names=[row['meta'][k] for k in ('longName','shortName') if isinstance(row['meta'].get(k),str)]
    require(not feed['channel']['future_publication'] and not any(item['future_publication'] for item in feed['items'])
            and not review_notices(capture_files['official.response.bin'],ticker=ticker,issuer_names=names)['blocking'],
            'SID_OFFICIAL_REVIEW')
    files=deepcopy(parent_files);prefix='sid-continuity/'+sid.replace(':','_')+'/'+today+'/'
    def include(name,raw):
        require(name not in files or files[name]==raw,'SID_SOURCE_COLLISION')
        files[name]=raw
        require(len(files)<=2000 and sum(map(len,files.values()))<=32*1024*1024,'SID_SOURCE_BUDGET')
    include('sid-parents/'+trusted_parent_sha256+'.json',parent_receipt_bytes)
    include(calendar_reference['path'],calendar_bytes)
    for name,body in capture_files.items():include(prefix+name,body)
    unit_path=prefix+'units.json'
    include(unit_path,canonical(dict(status='CONDITIONAL_MACHINE_CONTINUITY_CHECKED',
        parent_review_sha256=trusted_parent_sha256,overlap_exact_dates=sorted(overlap),
        source_authenticated=False,coverage_complete=False,policy_approved=False)))
    inputs=deepcopy(old_inputs)
    inputs.update(signal_date=previous['date'],observed_at=previous['close'],session_dates=dates[:index],
        session_close_times=dict(review_reference=calendar_reference['path'],
            closes={r['date']:r['close'] for r in sessions[:index]}))
    units=deepcopy(units);units.update(unit_asof=previous['date'],review_reference=unit_path)
    inputs['histories']={sid:dict(units=units,source_reference=prefix+'daily.response.bin',
        closes=[dict(date=r['date'],close=prices[r['date']],completed_at=r['close']) for r in window])}
    normalized_name=prefix+'normalized.json';include(normalized_name,canonical(inputs))
    receipt=deepcopy(parent)
    receipt.update(normalized_inputs_path=normalized_name,market_asof=previous['close'],
        source_received_at=max(stamp(r['received_at']) for r in receipts.values()).isoformat(),
        available_at=current.isoformat(),valid_from=max(current,stamp(session['open'])).isoformat(),
        valid_until=session['close'],execution_session=session,source_authenticated=False,coverage_complete=False,
        raw_source_paths=[prefix+n+'.response.bin' for n in ('daily','official')],
        source_sha256={name:sha256(raw).hexdigest() for name,raw in files.items()})
    return dict(receipt=receipt,files=files,status='SID_CONTINUITY_REVIEWED_POLICY_UNCHANGED')
