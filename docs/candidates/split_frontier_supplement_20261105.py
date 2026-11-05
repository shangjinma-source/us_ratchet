"""Isolated actual gzip-capture review and split-aware overlap into daily risk.
Original receipts are immutable. Parent normalization uses only its own clock;
later unit projection is explicit derived accounting, never publication evidence.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from docs.candidates.split_monthly_raw_history_20261105 import normalize_monthly_raw
from data.strategy_rss_gzip_capture_v1 import validate_capture
from data.saved_frontier_first_window_v1 import review_future_notice_scope


def review_generation(*, capture, request, binding, inputs, identities, reviews, now):
    """Review capture content against already admitted identity/unit history.

    The caller must authenticate those original inputs and the capture location.
    This conditional review never grants policy authority or complete action coverage.
    """
    from core.strategy_account_ledger import canonical, require
    from data.current_quantity_v2_paper_action_sources import daily_url, stamp
    from data.strategy_account_notice_review import review_notices
    from scripts.current_research_official_alert_capture import parse_official_feed, URL
    validate_capture(capture)
    current=stamp(now)
    require(capture['status']=='CAPTURED_REVIEW_REQUIRED' and capture['binding']==binding and
        capture['capture_id']==sha256(canonical(dict(binding=binding,request=request))).hexdigest(),
        'SUPPLEMENT_REVIEW_BINDING')
    require(request['account_id']==binding['account_id'] and request['state_revision']==binding['account_revision'],
        'SUPPLEMENT_REVIEW_ACCOUNT')
    require(current.astimezone(ZoneInfo('America/New_York')).date().isoformat()==binding['session'] and
        stamp(capture['finished_at'])<=current,'SUPPLEMENT_REVIEW_TIME')
    files=capture['files'];pins=capture['source_hashes']
    require(set(files)==set(pins) and sum(map(len,files.values()))<=128*1024*1024,'SUPPLEMENT_REVIEW_FILES')
    for name,raw in files.items():require(sha256(raw).hexdigest()==pins[name],'SUPPLEMENT_REVIEW_HASH')
    documents=capture['documents'];sources={};hashes={};metas={};starts=[]
    require(request['observed_floor']<=capture['finished_at'],'SUPPLEMENT_OBSERVED_FLOOR')
    require(set(documents['action_receipts'])==set(identities)==set(inputs['histories']), 'SUPPLEMENT_REVIEW_DOMAIN')
    closes=inputs['session_close_times']['closes']
    for sid,path in documents['action_receipts'].items():
        receipt=json.loads(files[path]);ticker=identities[sid]['ticker']
        raw=files[receipt['raw_path']];received=stamp(receipt['received_at'])
        started=stamp(receipt['requested_through']);starts.append(started)
        require(stamp(request['observed_floor'])<=started<=received<=stamp(capture['finished_at']) and (stamp(capture['finished_at'])-started).total_seconds()<120,'SUPPLEMENT_DAILY_CAPTURE_CLOCK')
        require(receipt['security_id']==sid and receipt['ticker']==ticker and receipt['http_status']==200 and
            receipt['body_truncated'] is False and receipt['transport_error'] is None and
            receipt['raw_sha256']==sha256(raw).hexdigest(),'SUPPLEMENT_REVIEW_RECEIPT')
        require(stamp(request['window_start'])<=stamp(closes[inputs['base_target']['monthly_decision_date']]) and
            stamp(receipt['requested_from'])<=stamp(request['window_start']) and
            stamp(closes[inputs['signal_date']])<=stamp(receipt['requested_through'])<=received<=stamp(capture['finished_at']),
            'SUPPLEMENT_REVIEW_WINDOW')
        require(receipt['url']==daily_url(ticker,stamp(receipt['requested_from']),stamp(receipt['requested_through'])) and
            receipt['interval']=='1d' and set(receipt['events_requested'])=={'dividends','splits'},'SUPPLEMENT_REVIEW_URL')
        series=json.loads(raw)['chart']['result'][0]
        require(all(datetime.fromtimestamp(t,timezone.utc)<=received for t in series['timestamp']), 'SUPPLEMENT_FUTURE_BAR')
        require(reviews[sid]['captured_at']==receipt['received_at'], 'SPLIT_BASIS_RECEIPT_CLOCK')
        require(receipt['request_period1']==int(stamp(receipt['requested_from']).timestamp()) and receipt['request_period2']==int(stamp(receipt['requested_through']).timestamp())+1,'SUPPLEMENT_REQUEST_EPOCH')
        metas[sid]=series['meta'];sources[sid]=raw;hashes[sid]=sha256(raw).hexdigest()
    rss=files[documents['rss_raw']];rss_receipt=json.loads(files[documents['rss_receipt']])
    require(rss_receipt['url']==URL and rss_receipt['http_status']==200 and
        rss_receipt['raw_sha256']==sha256(rss).hexdigest() and rss_receipt['stored_bytes']==len(rss) and
        stamp(rss_receipt['started_at'])<=stamp(rss_receipt['received_at'])<=stamp(capture['finished_at']), 'SUPPLEMENT_RSS_RECEIPT')
    require(stamp(request['observed_floor'])<=stamp(rss_receipt['started_at']) and (stamp(capture['finished_at'])-min(starts)).total_seconds()<120,'SUPPLEMENT_CAPTURE_CLOCK')
    feed=parse_official_feed(rss,observed_at=stamp(rss_receipt['received_at']))
    future_notice_scope = {}
    for sid,meta in metas.items():
        names=[meta[k] for k in ('longName','shortName') if isinstance(meta.get(k),str)]
        future_notice_scope[sid] = review_future_notice_scope(rss, feed=feed,
            ticker=identities[sid]['ticker'], issuer_names=names)
    normalized=deepcopy(inputs);normalized['observed_at']=current.isoformat()
    result=normalize_monthly_raw(inputs=normalized,sources=sources,expected_hashes=hashes,identities=identities,reviews=reviews)
    return dict(result,status='CONDITIONAL_MONTHLY_SOURCE_REVIEW',capture_id=capture['capture_id'],
        policy_approved=False,coverage_complete=False,future_notice_scope=future_notice_scope)


def prepare_request(*, state, target, proposal, risk_state, calendar, identities, now):
    """Fixed server calendar/domain; no ticker, cash, or quote supplied by browser."""
    from core.strategy_account_ledger import canonical,require
    from core.strategy_account_split_v1 import replay
    from core.saved_monthly_frontier_proposal import build_frontier_proposal
    from data.monthly_risk_epoch import validate_monthly_epoch
    from data.strategy_daily_session_capture import stamp
    require(replay(state['account_id'],[r['payload'] for r in state['events']])==state,'SPLIT_REQUEST_REPLAY')
    require(target['target_id']==sha256(canonical(target['payload'])).hexdigest() and
        target['payload']['account_id']==state['account_id'] and proposal==build_frontier_proposal(target=target),'SPLIT_REQUEST_TARGET')
    require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ','SUPPLEMENT_CALENDAR_SCHEMA')
    sessions=calendar['sessions'];dates=[r['date'] for r in sessions];current=stamp(now)
    require(dates==sorted(set(dates)),'SUPPLEMENT_CALENDAR_DATES')
    today=current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(today in dates,'WAIT_SUPPLEMENT_SESSION');index=dates.index(today);session=sessions[index]
    require(stamp(session['open'])<=current<stamp(session['close']),'WAIT_SUPPLEMENT_SESSION')
    require(risk_state['account_id']==state['account_id'] and risk_state['target_month']==target['payload']['target_month'],'FRONTIER_RISK_ACCOUNT')
    decision=risk_state['decision_date'];validate_monthly_epoch(decision_date=decision,target_month=target['payload']['target_month'],session_dates=dates)
    require(index>=20 and dates.index(decision)<index,'SUPPLEMENT_MONTHLY_WINDOW')
    quantities=proposal['payload']['proposed_target_quantities']
    needed={s for s,q in quantities.items() if q}|set(risk_state['peaks'])|set(risk_state['exited'])
    needed|={s for s,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN' and o['remaining_quantity']>0}
    require(0<len(needed)<=250 and needed==set(identities),'SUPPLEMENT_REQUEST_DOMAIN')
    binding=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],session=today)
    request=dict(account_id=state['account_id'],state_revision=state['revision'],window_start=sessions[min(index-20,dates.index(decision))]['open'],observed_floor=session['open'],securities={s:dict(ticker=identities[s]['ticker']) for s in sorted(needed)},current_target_quantities={s:quantities.get(s,0) for s in sorted(needed)})
    return dict(request=request,binding=binding,review_binding=dict(binding,proposal_id=proposal['proposal_id'],risk_state_sha256=sha256(canonical(risk_state)).hexdigest()),calendar_sha256=sha256(canonical(calendar)).hexdigest())


def review_pair(*, parent, current, identities, action, trusted_pair_sha256, now):
    """Each generation has its own receipt/basis. Projection is explicitly later."""
    from core.strategy_account_ledger import canonical,require
    from data.strategy_split_history_projection_v1 import project_history_units
    descriptor={key:{k:v for k,v in generation.items() if k!='capture'}|dict(capture={k:v for k,v in generation['capture'].items() if k!='files'}) for key,generation in [('parent',parent),('current',current)]}
    descriptor['action']=action
    require(sha256(canonical(descriptor)).hexdigest()==trusted_pair_sha256,'SPLIT_PAIR_REVIEW_HASH')
    old=review_generation(**parent,identities=identities,now=parent['capture']['finished_at'])
    new=review_generation(**current,identities=identities,now=now)
    require(parent['binding']['account_id']==current['binding']['account_id'] and parent['binding']['target_id']==current['binding']['target_id'],'SPLIT_PAIR_ACCOUNT_TARGET')
    require(parent['inputs']['base_target']['monthly_decision_date']==current['inputs']['base_target']['monthly_decision_date'],'SPLIT_PAIR_EPOCH')
    require(datetime.fromisoformat(parent['capture']['finished_at'])<datetime.fromisoformat(action['effective_at'])<=datetime.fromisoformat(current['capture']['finished_at']),'SPLIT_PAIR_CLOCK_ORDER')
    # No future action is inserted into the old raw review or receipt.
    projected=project_history_units(observations=old['observations'],action=action,expected_sessions=[r['session_date'] for r in old['observations']])
    oldrows={r['session_date']:r for r in projected['payload']['normalized_observations']};newrows={r['session_date']:r for r in new['observations']}
    overlap=sorted(set(oldrows)&set(newrows));require(overlap and set(oldrows)<=set(newrows),'SPLIT_PAIR_OVERLAP_MISSING')
    for day in overlap:
        require(oldrows[day]['unit_ids']==newrows[day]['unit_ids'] and oldrows[day]['closes']==newrows[day]['closes'],'SPLIT_PAIR_PRICE_CONTINUITY')
    return dict(parent=old,current=new,history_projection=projected,overlap_dates=overlap,source_authenticated=False)


def apply_capture_pair(*, parent, current, trusted_pair_sha256, reader_arguments, read_binding, now):
    """Use reviewed transport bytes as the actual daily-reader source, then risk."""
    from core.strategy_account_ledger import canonical,require
    from docs.candidates.split_saved_frontier_daily_evidence_20261105 import project_split_frontier_daily
    args=deepcopy(reader_arguments);state=args['state'];review=json.loads(args['review_bytes']);files=args['files']
    identities=json.loads(files[review['documents']['identities']])['securities']
    from contextlib import closing
    import sqlite3
    from docs.candidates.split_saved_frontier_daily_evidence_20261105 import verify_transition_ancestry
    from data.saved_frontier_policy_archive import read_saved_frontier_policy
    with closing(sqlite3.connect(args['risk_path'].as_uri()+'?mode=ro',uri=True)) as con:
        raw,digest=con.execute('SELECT payload,digest FROM split_preparation WHERE singleton=1').fetchone()
    require(sha256(raw.encode()).hexdigest()==digest,'SPLIT_PREPARATION_CHANGED')
    prep=json.loads(raw);transition=prep['transition'];archive=read_saved_frontier_policy(research_root=args['research_root'],target_id=args['target_id'])
    verify_transition_ancestry(state=state,transition=transition,risk_before=prep['original_risk_state'],target=archive['target'],proposal_id=archive['proposal']['proposal_id'])
    from data.monthly_peak_exit_store import MonthlyPeakExitStore
    current_risk=MonthlyPeakExitStore(args['risk_path']).read(state['account_id'])
    planned=prepare_request(state=state,target=archive['target'],proposal=archive['proposal'],risk_state=current_risk,
        calendar=json.loads(files[review['documents']['calendar']]),identities=identities,now=now)
    require(current['request']==planned['request'] and current['binding']==planned['binding'],'SPLIT_CURRENT_REQUEST_CHANGED')
    matches=[r['payload'] for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED' and r['payload']['action_id']==transition['payload']['action_id']]
    require(len(matches)==1,'SPLIT_CAPTURE_ACTION_REQUIRED');action=matches[0]
    require(read_binding()==current['binding'] and state['revision']==current['binding']['account_revision'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    checked=review_pair(parent=parent,current=current,identities=identities,action=action,trusted_pair_sha256=trusted_pair_sha256,now=now)
    # Reader's separately trusted review must already bind the exact received raw,
    # normalization and clock. Never mint source approval from a successful fetch.
    received_map={}
    for sid,path in current['capture']['documents']['action_receipts'].items():
        receipt=json.loads(current['capture']['files'][path]);raw=current['capture']['files'][receipt['raw_path']]
        require(files[review['documents']['raw_by_security'][sid]]==raw,'SPLIT_CAPTURE_READER_RAW_MISMATCH')
        unit=json.loads(files[review['documents']['unit_reviews'][sid]])
        require(unit['raw_normalization']==current['reviews'][sid],'SPLIT_CAPTURE_READER_REVIEW_MISMATCH')
        received_map[sid]=receipt['received_at']
    require(review.get('source_received_by_security')==received_map and review['source_received_at']==max(received_map.values(),key=datetime.fromisoformat),'SPLIT_CAPTURE_RECEIVED_SUMMARY')
    require(json.loads(files[review['documents']['normalized_inputs']])==checked['current']['inputs'],'SPLIT_CAPTURE_READER_INPUT_MISMATCH')
    require(read_binding()==current['binding'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    result=project_split_frontier_daily(**dict(args,now=now))
    require(read_binding()==current['binding'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    return dict(result,supplement_pair=checked,capture_id=current['capture']['capture_id'],automatic_source_approval=False,review_binding=planned['review_binding'])
