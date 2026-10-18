"""Read-only saved successor observations -> reconstructed paper performance."""
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
import hashlib,json
from zoneinfo import ZoneInfo
from data.current_research_fill_ledger import (review_paper_ledger,initialize_paper_ledger,apply_paper_fill,apply_paper_order_event,activate_paper_plan)
from data.current_research_successor_inputs import SuccessorInputLoader,DEFAULT_REGISTRY,validate_successor_time_chain
from data.current_research_saved_quote import read_saved_quote
from data.current_research_paper_performance import compute_paper_performance


def build_saved_paper_performance(state, *, root, input_ids, calendar_path, calendar_source_hashes, through_date, now, registry_path=DEFAULT_REGISTRY):
    def require(ok,reason):
        if not ok:raise ValueError(reason)
    review_paper_ledger(state)
    require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_NOW_REQUIRED')
    loader=SuccessorInputLoader(root=root,registry_path=registry_path)
    pins=dict(calendar_source_hashes)
    require(calendar_path in pins,'CALENDAR_NOT_PINNED')
    for path,digest in pins.items():require(hashlib.sha256(loader._path(path).read_bytes()).hexdigest()==digest,'CALENDAR_SOURCE_CHANGED')
    calendar=json.loads(loader._path(calendar_path).read_bytes())
    require(calendar.get('schema')=='SCHEDULED_REGULAR_SESSIONS_V1','CALENDAR_SCHEMA_INVALID')
    require(calendar.get('source_hashes') and all(pins.get(p)==h for p,h in calendar['source_hashes'].items()),'CALENDAR_EVIDENCE_UNBOUND')
    days=calendar['calendar'];require(days==sorted(set(days)),'CALENDAR_ORDER_INVALID')
    sessions={s['date']:s for s in calendar['sessions']}
    require(len(sessions)==len(calendar['sessions']) and set(sessions)==set(days),'CALENDAR_SESSION_DOMAIN_MISMATCH')
    start=state['plans'][0]['causal_inputs']['decision_date']
    require(start in days and through_date in days and start<=through_date,'CALENDAR_RANGE_MISSING')
    selected_days=days[days.index(start):days.index(through_date)+1]
    for day in selected_days:
        s=sessions[day];opening=datetime.fromisoformat(s['open_at']);close=datetime.fromisoformat(s['close_at'])
        require(s['timezone']=='America/New_York' and all(t.tzinfo is not None and t.date().isoformat()==day and t.astimezone(ZoneInfo('America/New_York')).date().isoformat()==day and t.utcoffset()==t.astimezone(ZoneInfo('America/New_York')).utcoffset() for t in [opening,close]) and opening<close<=now,'CALENDAR_SESSION_NOT_COMPLETED')
    current=initialize_paper_ledger(state['plans'][0],state['account_id']);prefixes={current['revision']:current}
    for event in state['events']:
        kind=event.get('event_type','FILL')
        if kind=='FILL':current=apply_paper_fill(current,event)
        elif kind=='ACTIVATE_PLAN':current=activate_paper_plan(current,event['new_plan'],{k:v for k,v in event.items() if k!='new_plan'})
        else:current=apply_paper_order_event(current,event)
        prefixes[current['revision']]=current
    require(current==state,'PREFIX_REPLAY_MISMATCH')
    all_orders={(p['plan_id'],o['order_id']):o for p in state['plans'] for o in p['orders']}
    fills=[e for e in state['events'] if e.get('event_type','FILL')=='FILL']
    def held_on(sid, day, before=False):
        quantity=0
        for e in fills:
            if e['session']>day or (before and e['session']==day):continue
            order=all_orders[(e['plan_id'],e['order_id'])]
            if order['security_id']==sid:quantity+=(1 if order['side']=='BUY' else -1)*e['qty']
        return quantity
    marks={start:{}};audit=[];seen=set()
    require(isinstance(input_ids,list) and len(input_ids)==len(set(input_ids)),'DUPLICATE_INPUT_ID')
    for input_id in input_ids:
        bundle=loader(input_id);validate_successor_time_chain(bundle,root=root,now=now)
        require(bundle['account_id']==state['account_id'] and bundle['revision'] in prefixes,'BUNDLE_HISTORY_ACCOUNT_REVISION_MISMATCH')
        prefix=prefixes[bundle['revision']]
        require(prefix['plan']['plan_id']==bundle['parent_plan_id'],'BUNDLE_HISTORY_PARENT_MISMATCH')
        day=bundle['decision_date'];require(day in selected_days and day not in seen,'AMBIGUOUS_OR_OUTSIDE_REPORT_SESSION');seen.add(day)
        require(bundle['decision_session']==sessions[day],'BUNDLE_CALENDAR_SESSION_MISMATCH')
        require(bundle.get('quote_reference_policy')=='EXACT_RAW_DECISION_CLOSE_NO_ROUNDING','EXACT_RAW_POLICY_REQUIRED')
        quotes={q['security_id']:q for q in bundle['valuation_quotes']}
        require(len(quotes)==len(bundle['valuation_quotes']),'DUPLICATE_QUOTE_SECURITY')
        traded_today={all_orders[(e['plan_id'],e['order_id'])]['security_id'] for e in fills if e['session']==day}
        historical_sids={o['security_id'] for o in all_orders.values()}
        required_action_domain=traded_today|{sid for sid in historical_sids if held_on(sid,day,before=True)>0}
        require(required_action_domain<=set(quotes),'MISSING_OPENING_HELD_OR_TRADED_ACTION_EVIDENCE')
        observations=bundle['saved_quote_observations'];require(set(quotes)==set(observations),'OBSERVATION_DOMAIN_MISMATCH')
        historical={}
        for plan in prefix['plans']:
            for sid,ticker in plan['causal_inputs']['securities'].items():historical.setdefault(sid,set()).add(ticker)
        metadata=bundle.get('search_arguments',{}).get('metadata',{})
        daymarks={}
        for sid,quote in quotes.items():
            observation=observations[sid];ticker=quote['ticker']
            if sid in historical:require(historical[sid]=={ticker},'HISTORICAL_TICKER_MISMATCH')
            else:require(metadata.get(sid,{}).get('ticker')==ticker,'UNBOUND_NEW_SECURITY')
            require(observation['ticker']==ticker and quote['as_of']==day,'QUOTE_IDENTITY_DATE_MISMATCH')
            oldquote=prefix['plan']['causal_inputs']['quotes'].get(sid)
            if oldquote is not None:require(oldquote['price_basis']==quote['price_basis'],'QUOTE_UNIT_BASIS_CHANGED')
            sources=observation['source_hashes'];paths=[p for p in sources if p.endswith('/'+ticker+'.response.bin') or p==ticker+'.response.bin']
            require(len(paths)==1,'RAW_SOURCE_AMBIGUOUS')
            from pathlib import PurePosixPath
            directory=PurePosixPath(paths[0]).parent
            entry={key:bundle['source_hashes'][(directory/(ticker+suffix)).as_posix()] for suffix,key in [('.response.bin','raw_sha256'),('.receipt.json','receipt_sha256'),('.decoded.json','decoded_sha256')]}
            actual=read_saved_quote(root=root,ticker=ticker,expected_security_type=observation['security_type'],entry=entry,relative_directory=directory.as_posix(),decision_date=day,decision_session_close_at=sessions[day]['close_at'])
            require(Fraction(actual['ohlc']['close'])==Fraction(quote['price']),'RAW_CLOSE_QUOTE_MISMATCH')
            require(datetime.fromisoformat(actual['received_at'])<=datetime.fromisoformat(bundle['admission']['reviewed_at'])<=now,'CAPTURE_REVIEW_NOW_MISMATCH')
            exposed=sid in required_action_domain or prefix['shares'].get(sid,0)>0 or held_on(sid,day)>0
            if exposed:
                continuity=bundle['held_unit_continuity'].get(sid,{})
                require(continuity.get('status')=='NO_UNPROCESSED_ACTIONS' and continuity.get('from_date')==prefix['plan']['causal_inputs']['decision_date'] and continuity.get('to_date')==day and continuity.get('price_basis')==quote['price_basis'],'HELD_UNIT_CONTINUITY_MISSING')
            require(not any(start<e['session']<=day and e['kind']!='dividends'
                            and (held_on(sid,e['session'],before=True)>0 or any(f['session']==e['session'] and all_orders[(f['plan_id'],f['order_id'])]['security_id']==sid for f in fills))
                            for e in actual['event_details']),'UNPROCESSED_EXPOSED_RAW_ACTION_IN_REPORT_PERIOD')
            require(not any(start<e['session']<=day and e['kind']=='dividends'
                            and held_on(sid,e['session'],before=True)>0
                            for e in actual['event_details']),'UNPROCESSED_EXPOSED_DIVIDEND')
            daymarks[sid]=actual['ohlc']['close']
        marks[day]=daymarks
        audit.append(dict(input_id=input_id,session=day,prefix_revision=bundle['revision'],source_hashes=bundle['source_hashes']))
    result=compute_paper_performance(state,session_dates=selected_days,marks=marks,through_date=through_date)
    result.update(saved_source_audit=audit,calendar_source_hashes=pins,source_adapter='VERIFIED_SAVED_BYTES_AND_PREFIX_BINDING_NOT_MARKET_TRUTH',calendar_verified=False,source_verified=False,
                  return_scope='PRICE_AND_RECORDED_FILL_FEES_ONLY',total_return_certified=False,
                  dividend_coverage_complete=False)
    return result
