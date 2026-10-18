"""Offline follow-up evidence inspection; not fills, returns or unit certification.

No boolean or caller-authored continuity assertion can unlock price calculations.
"""
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo
from data.current_quantity_v2_touch_review import review_generated_reference
from data.current_research_saved_quote import read_saved_quote
from data.current_quantity_v2_followup_actions import review_interval_actions,check_known_actions

CALENDAR_PATH='tmp/official_session_closes_20261016_v1/session_close_times.json'
CALENDAR_SHA='325751c9c0273c516a6fe2b272f85b9e83eb43b7f754cf675807dc7040630f7b'
FORWARD_PATH='tmp/review_regular_calendar_20261016_v1/schedule.json'
FORWARD_SHA='6a4ff44105f4006fbc068d72c403bdc1e801893a234406adbf303fc6f04bf44e'
NY=ZoneInfo('America/New_York')


def review_reference_followup(*,root,binding,event_path,files,source_hashes,
                              daily_observations,now,action_evidence=None,trusted_chain_sources=None):
    """Server-owned inputs only. Does not discover, fetch, write or mutate events.

    Daily descriptors bind SID/ticker/date, relative_directory and the original
    raw/receipt/decoded triple pins. No trade-status input is accepted: execution
    evidence needs a separate authenticated ledger adapter.
    """
    root=Path(root).resolve()
    def require(ok,reason):
        if not ok:raise ValueError(reason)
    def read(relative,expected):
        require(type(relative)is str and not Path(relative).is_absolute(),'UNSAFE_PATH')
        path=(root/relative).resolve();require(path.is_relative_to(root),'OUTSIDE_ROOT')
        with path.open('rb') as stream:raw=stream.read(32*1024*1024+1)
        require(len(raw)<=32*1024*1024 and sha256(raw).hexdigest()==expected,'SOURCE_HASH_MISMATCH')
        return json.loads(raw)
    require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
    raw=files[event_path];require(type(raw)is bytes and len(raw)<=1024*1024 and sha256(raw).hexdigest()==source_hashes[event_path],'EVENT_HASH_MISMATCH')
    event=json.loads(raw);context=event['research_context']
    require(set(binding)=={'decision_id','research_version','available_cash_exact'},'EXACT_BINDING_REQUIRED')
    require(event['decision_id']==binding['decision_id'] and context['research_id']==binding['decision_id'][:24]
        and all(context[key]==binding[key] for key in ('research_version','available_cash_exact')),'EVENT_BINDING_MISMATCH')
    require(event.get('generated_not_confirmed_displayed')is True and event.get('actual_fill_inferred')is False,'EVENT_SEMANTICS_MISMATCH')
    observed=datetime.fromisoformat(event['observed_at'])
    require(observed.tzinfo is not None and observed<=now,'INVALID_EVENT_TIME')
    session=observed.astimezone(NY).date().isoformat()
    diagnostic=review_generated_reference(event_path=event_path,subsequent_event_paths=[],files=files,source_hashes=source_hashes,trusted_chain_sources=trusted_chain_sources)
    require(diagnostic['status']=='DIAGNOSTIC' and len(diagnostic['orders'])==len(event['orders'])
        and all(row.get('reason') in (None,'INCOMPLETE_MINUTE_COVERAGE') for row in diagnostic['orders']),'ORIGINAL_REFERENCE_UNVERIFIED')
    pins=dict(diagnostic['source_hashes']);calendar=None;calendar_error=None
    try:
        try:
            calendar=read(CALENDAR_PATH,CALENDAR_SHA);pins[CALENDAR_PATH]=CALENDAR_SHA
            require(calendar['schema']=='OFFICIAL_SCHEDULED_US_EQUITY_CLOSES_V1','CALENDAR_SCHEMA')
        except (OSError,ValueError,KeyError,TypeError):calendar=None
        if calendar is None or session not in calendar['session_dates']:
            forward=read(FORWARD_PATH,FORWARD_SHA);pins[FORWARD_PATH]=FORWARD_SHA
            require(forward['schema']=='SCHEDULED_REGULAR_SESSIONS_V1'
                and [r['date'] for r in forward['sessions']]==forward['calendar'],'FORWARD_CALENDAR_SCHEMA')
            closes={}
            for row in forward['sessions']:
                opened=datetime.fromisoformat(row['open_at']);closed=datetime.fromisoformat(row['close_at'])
                require(opened.tzinfo is not None and closed.tzinfo is not None and opened<closed
                    and row['timezone']=='America/New_York'
                    and opened.astimezone(NY).date().isoformat()==row['date']
                    and closed.astimezone(NY).date().isoformat()==row['date'],'FORWARD_SESSION_INVALID')
                closes[row['date']]=closed.astimezone(NY).isoformat()
            # Each admitted calendar must cover the whole window; never splice gaps.
            calendar=dict(session_dates=forward['calendar'],closes=closes,source_hashes=forward['source_hashes'])
        dates=calendar['session_dates'];require(dates==sorted(set(dates)) and session in dates,'REFERENCE_SESSION_NOT_IN_CALENDAR')
        for path,digest in calendar['source_hashes'].items():
            target=(root/path).resolve();require(target.is_relative_to(root),'OUTSIDE_ROOT')
            with target.open('rb') as stream:content=stream.read(32*1024*1024+1)
            require(len(content)<=32*1024*1024 and sha256(content).hexdigest()==digest,'CALENDAR_SOURCE_CHANGED')
            pins[path]=digest
        for day in dates:
            close=datetime.fromisoformat(calendar['closes'][day])
            require(close.tzinfo is not None and close.astimezone(NY).date().isoformat()==day
                and close.utcoffset()==close.astimezone(NY).utcoffset(),'CALENDAR_CLOSE_OFFSET_INVALID')
    except (OSError,ValueError,KeyError,TypeError):calendar=None;calendar_error='PENDING_VERIFIED_CALENDAR'
    require(type(daily_observations)is list and len(daily_observations)<=2000,'OBSERVATION_LIMIT')
    descriptors={}
    for item in daily_observations:
        key=(item['security_id'],item['date']);require(key not in descriptors,'DUPLICATE_OBSERVATION')
        descriptors[key]=item
    orders=[]
    for order in event['orders']:
        sid=order['security_id'];matches=[row for row in event['rows'] if row['security_id']==sid]
        require(len(matches)==1,'REFERENCE_ROW_NOT_UNIQUE')
        row=matches[0];ticker=row['ticker']
        require(row['security_id']==sid and row['reference']['session']==session
            and Fraction(row['limit_price'])==Fraction(order['limit_price']),'REFERENCE_IDENTITY_MISMATCH')
        results=[]
        for horizon in (1,5,20):
            result=dict(sessions_after_reference=horizon,status=calendar_error or 'PENDING_BARS',
                price_change_vs_reference=None,execution_status='NOT_PROVIDED',actual_fill_inferred=False)
            results.append(result)
            if calendar is None:continue
            index=dates.index(session);window=dates[index+1:index+horizon+1]
            if len(window)!=horizon:result['status']='PENDING_CALENDAR_HORIZON';continue
            result['target_session']=window[-1]
            if datetime.fromisoformat(calendar['closes'][window[-1]])>now:
                result['status']='PENDING_SESSION_CLOSE';continue
            try:
                daily_closes={};latest_daily_capture=datetime.fromisoformat(calendar['closes'][window[-1]])
                for day in window:
                    item=descriptors.get((sid,day))
                    if item is None:raise ValueError('PENDING_BARS')
                    require(item['ticker']==ticker,'BLOCKED_SECURITY_IDENTITY')
                    for suffix,key in (('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')):
                        path=(Path(item['relative_directory'])/(ticker+suffix)).as_posix()
                        require(source_hashes.get(path)==item['entry'][key],'BLOCKED_UNADMITTED_DAILY_SOURCE')
                    value=read_saved_quote(root=root,ticker=ticker,expected_security_type='EQUITY',entry=item['entry'],
                        relative_directory=item['relative_directory'],decision_date=day,decision_session_close_at=calendar['closes'][day])
                    require(datetime.fromisoformat(value['received_at'])<=now,'BLOCKED_FUTURE_CAPTURE')
                    latest_daily_capture=max(latest_daily_capture,datetime.fromisoformat(value['received_at']))
                    pins.update(value['source_hashes'])
                    daily_closes[day]=value['ohlc']['close']
                    check_known_actions(value['raw_returned_events'],start=observed,
                        end=datetime.fromisoformat(calendar['closes'][window[-1]]),captured=datetime.fromisoformat(value['received_at']))
                action_review=review_interval_actions(files=files,pins=source_hashes,
                    evidence=(action_evidence or {}).get(sid),security_id=sid,ticker=ticker,start=observed,
                    end=datetime.fromisoformat(calendar['closes'][window[-1]]),now=now,daily_closes=daily_closes,latest_daily_capture=latest_daily_capture)
                pins.update(action_review['source_hashes'])
                result.update(status='CONDITIONAL_PRICE_CHANGE',action_review=action_review,
                    closing_price=daily_closes[window[-1]],price_change_vs_reference=str(Fraction(daily_closes[window[-1]])/Fraction(order['limit_price'])-1))
            except (OSError,ValueError,KeyError,TypeError,OverflowError,ET.ParseError) as error:
                result['status']=str(error) if str(error) in ('PENDING_BARS','PENDING_INTERVAL_ACTION_SOURCES','BLOCKED_ACTION_SOURCE_VALIDATION','BLOCKED_INTERVAL_PRICE_COORDINATE_MISMATCH','BLOCKED_OFFICIAL_ACTION_CANDIDATE','BLOCKED_SECURITY_IDENTITY','BLOCKED_UNADMITTED_DAILY_SOURCE','BLOCKED_FUTURE_CAPTURE','BLOCKED_KNOWN_CORPORATE_ACTION','BLOCKED_POST_HORIZON_UNIT_CHANGE','BLOCKED_ACTION_INTERVAL_BEFORE_PRICE_CAPTURE') else 'BLOCKED_DAILY_SOURCE_VALIDATION'
        orders.append(dict(security_id=sid,ticker=ticker,side=order['side'],reference_limit=order['limit_price'],horizons=results))
    return dict(schema='V2_REFERENCE_FOLLOWUP_EVIDENCE_V1',status='EVIDENCE_REVIEW_ONLY',binding=dict(binding),orders=orders,
        reference_session=session,source_hashes=pins,actual_fill_inferred=False,performance_computed=False,
        bounded_unit_adapter_implemented=True,source_authenticated=False,
        limitations=['Generated reference is not an order or fill; price deviation is not trading return.',
            'Bounded interval daily events and saved visible official alerts checked; unknown actions may be missed.',
            'Price change is conditional, not certified nominal continuity or total return.'])
