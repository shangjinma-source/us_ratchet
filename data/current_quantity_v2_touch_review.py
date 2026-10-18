"""Pure saved-byte diagnostics for generated V2 references, never execution evidence."""
import json
import math
import re
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from data.current_research_intraday_execution import decode_intraday_reference
from data.current_research_intraday_touch_review import _complete_bars, _time


def review_generated_reference(*, event_path, subsequent_event_paths, files, source_hashes, trusted_chain_sources=None):
    """Server supplies original journal receipt hashes; no discovery, fetching or fills.

    Subsequent events supply their original quote receipt/capture pairs. Hashes bind
    local bytes only; neither external authenticity nor delivery is certified.
    """
    consumed={}
    def read(path):
        raw=files.get(path)
        if type(raw)is not bytes or len(raw)>32*1024*1024 or sha256(raw).hexdigest()!=source_hashes.get(path):
            raise ValueError('SOURCE_EVIDENCE_MISSING')
        consumed[path]=source_hashes[path]
        if sum(len(files[p]) for p in consumed)>128*1024*1024:raise ValueError('SOURCE_LIMIT')
        return raw
    def event(path):
        value=json.loads(read(path))
        if value.get('schema')!='V2_GENERATED_PREVIEW_OBSERVATION_V1':raise ValueError('EVENT_SCHEMA')
        return value
    def capture(value,sid,ticker):
        refs=value.get('captures',[])
        raw=[r for r in refs if r.get('security_id')==sid and r.get('role')=='ORIGINAL_QUOTE']
        receipts=[r for r in refs if r.get('security_id')==sid and r.get('role')=='ORIGINAL_QUOTE_RECEIPT']
        if len(raw)!=1 or len(receipts)!=1:raise ValueError('SOURCE_EVIDENCE_MISSING')
        r,q=raw[0],receipts[0];payload=read(r['path']);receipt_raw=read(q['path']);receipt=json.loads(receipt_raw)
        if (r['sha256']!=sha256(payload).hexdigest() or q['sha256']!=sha256(receipt_raw).hexdigest()
            or r['ticker']!=ticker or q['ticker']!=ticker or receipt['ticker']!=ticker or receipt['security_id']!=sid
            or receipt['raw_sha256']!=r['sha256'] or receipt['raw_path']!=r['original_source_path']
            or receipt['captured_at']!=r['captured_at'] or receipt['captured_at']!=q['captured_at']):raise ValueError('CAPTURE_BINDING_MISMATCH')
        return payload,_time(receipt['captured_at'])
    result=dict(scope='HYPOTHETICAL_GENERATED_REFERENCE',orders=[],actual_fill_inferred=False,
                future_price_evaluation='NOT_EVALUATED',source_authenticated=False)
    try:
        if len(subsequent_event_paths)>1000:raise ValueError('SOURCE_LIMIT')
        original=event(event_path);start=_time(original['observed_at']);end=_time(original['reference_valid_until'])
        if end<=start or (end-start).total_seconds()>120:raise ValueError('INVALID_REFERENCE_WINDOW')
        expected=list(range(math.ceil(start.timestamp()/60)*60,math.floor(end.timestamp()/60)*60,60))
        later=[event(p) for p in subsequent_event_paths]
        for order in original['orders']:
            item=dict(security_id=order['security_id'],status='UNKNOWN',reason=None,coverage_complete=False,
                      window_start=start.isoformat(),window_end=end.isoformat(),edge_intervals_not_evaluated=True,
                      leading_edge=[start.isoformat(),datetime.fromtimestamp(math.ceil(start.timestamp()/60)*60,timezone.utc).isoformat()] if start.timestamp()%60 else None,
                      trailing_edge=[datetime.fromtimestamp(math.floor(end.timestamp()/60)*60,timezone.utc).isoformat(),end.isoformat()] if end.timestamp()%60 else None)
            result['orders'].append(item)
            try:
                sid=order['security_id'];rows=[r for r in original['rows'] if r['security_id']==sid]
                if len(rows)!=1:raise ValueError('ORIGINAL_ORDER_BINDING')
                row=rows[0];ticker=row['ticker'];session=row['reference']['session'];limit=Fraction(order['limit_price'])
                if limit<=0 or order['side'] not in ('BUY','SELL') or Fraction(row['limit_price'])!=limit:raise ValueError('ORIGINAL_ORDER_BINDING')
                raw,captured=capture(original,sid,ticker)
                if captured>start:raise ValueError('ORIGINAL_CAPTURE_AFTER_OBSERVATION')
                reference=decode_intraday_reference(raw,ticker=ticker,now=captured,captured_at=captured)
                saved_reference=row['reference']
                if 'pullback' in saved_reference:
                    from data.current_quantity_v2_pullback_sources import candidate_from_yahoo_bytes
                    from data.current_quantity_v2_pullback_entry import VERSION
                    pullback=saved_reference['pullback']
                    expected_policy=dict(version=VERSION,rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120)
                    if pullback.get('policy')!=expected_policy or pullback.get('status')!='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED':
                        raise ValueError('ORIGINAL_PULLBACK_POLICY_UNSUPPORTED')
                    from data.current_quantity_v2_pullback_chain_review import ARCHIVE_PATH, ARCHIVE_SHA256, verify_chain
                    chain_source=(trusted_chain_sources or {}).get(pullback['cap_record_hash'])
                    if chain_source is None and ARCHIVE_PATH in files:
                        chain_source=dict(path=ARCHIVE_PATH,sha256=ARCHIVE_SHA256)
                    authenticated = chain_source is not None
                    if authenticated:
                        if set(chain_source)!={'path','sha256'} or source_hashes.get(chain_source['path']) != chain_source['sha256']:
                            raise ValueError('ORIGINAL_PULLBACK_ARCHIVE_UNTRUSTED')
                        candidate = verify_chain(read(chain_source['path']), pullback['cap_record_hash'], raw, pullback, observed_at=start.isoformat())
                    else:
                        if pullback.get('prior_cap') is not None:
                            raise ValueError('ORIGINAL_PULLBACK_PRIOR_EVIDENCE_REQUIRED')
                        candidate=candidate_from_yahoo_bytes(raw=raw,expected_sha256=sha256(raw).hexdigest(),
                            security_id=sid,ticker=ticker,session=reference['session'],
                            session_open=reference['session_open'],session_close=reference['session_close'],
                            captured_at=captured.isoformat(),checked_at=captured.isoformat(),now=captured.isoformat(),
                            rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120,previous_cap=None)['candidate']
                        if set(pullback)!=set(candidate)|{'prior_cap','status','cap_record_hash'}:
                            raise ValueError('ORIGINAL_PULLBACK_FIELDS_MISMATCH')
                        # checked_at was not journaled by early versions. Recompute all
                        # economic fields, but explicitly do not certify its input digest
                        # or server cap-record hash from their declarations alone.
                        if any(pullback[key]!=value for key,value in candidate.items() if key!='input_digest'):
                            raise ValueError('ORIGINAL_PULLBACK_REPLAY_MISMATCH')
                        if any(type(pullback[key]) is not str or re.fullmatch('[a-f0-9]{64}',pullback[key]) is None for key in ('input_digest','cap_record_hash')):
                            raise ValueError('ORIGINAL_PULLBACK_PROVENANCE_FORMAT')
                    reference['refresh_by']=min(_time(reference['refresh_by']),_time(candidate['reference_valid_until'])).isoformat()
                    if {k:v for k,v in saved_reference.items() if k!='pullback'}!=reference:
                        raise ValueError('ORIGINAL_REFERENCE_MISMATCH')
                    if order['side']=='BUY' and limit!=Fraction(candidate['limit_price']):
                        raise ValueError('ORIGINAL_PULLBACK_LIMIT_MISMATCH')
                    item.update(original_rule_verification=('PINNED_LOCAL_CAP_PREFIX_REPLAYED' if authenticated else 'RAW_MINUTES_FIXED_POLICY_NO_PRIOR_CAP_RECOMPUTED'),
                        cap_history_authenticated=authenticated,input_digest_authenticated=authenticated)
                elif reference!=saved_reference:raise ValueError('ORIGINAL_REFERENCE_MISMATCH')
                if _time(reference['refresh_by'])<end:raise ValueError('ORIGINAL_REFERENCE_MISMATCH')
                if order['side']=='BUY' and limit>Fraction(reference['observed_cap']):raise ValueError('ORIGINAL_LIMIT_ABOVE_CAP')
                bars={};conflicts=set()
                for value in later:
                    if not any(r.get('security_id')==sid for r in value.get('captures',[])):continue
                    raw,captured=capture(value,sid,ticker)
                    if captured>_time(value['observed_at']):raise ValueError('CAPTURE_AFTER_OBSERVATION')
                    for stamp,bar in _complete_bars(raw,ticker=ticker,session=session,captured=captured).items():
                        if stamp not in expected:continue
                        if stamp in bars and bars[stamp]!=bar:conflicts.add(stamp)
                        bars[stamp]=bar
                item.update(expected_minutes=len(expected),covered_minutes=len(bars),conflicting_minutes=sorted(conflicts),
                            coverage_complete=bool(expected) and set(expected)==set(bars) and not conflicts)
                if conflicts:raise ValueError('CONFLICTING_MINUTE')
                touched=any(Fraction(bar[2])<=limit if order['side']=='BUY' else Fraction(bar[1])>=limit for bar in bars.values())
                if touched:item['status']='TOUCH_IN_COMPLETE_MINUTE'
                elif item['coverage_complete']:item['status']='NO_TOUCH_IN_COMPLETE_MINUTES'
                else:item['reason']='INCOMPLETE_MINUTE_COVERAGE'
            except (ValueError,KeyError,TypeError,AttributeError,ArithmeticError) as error:item['reason']=str(error)
        result['status']='DIAGNOSTIC'
    except (ValueError,KeyError,TypeError,AttributeError) as error:result.update(status='UNKNOWN',reason=str(error))
    result['source_hashes']=dict(consumed)
    return result
