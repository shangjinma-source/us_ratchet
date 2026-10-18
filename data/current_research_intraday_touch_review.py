"""Saved future minute touch diagnostics only: never fills or performance."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json
import math
from data.current_research_intraday_review import review_intraday_session

NY=ZoneInfo('America/New_York')


def _time(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('NAIVE_TIME')
    return result


def _require(value,reason):
    if not value:raise ValueError(reason)


def _number(value):
    _require(value is not None and not isinstance(value,bool),'INVALID_BAR_NUMBER')
    result=Decimal(str(value));_require(result.is_finite(),'NONFINITE_BAR')
    return result


def _stamp(value):
    number=_number(value);_require(number==number.to_integral_value(),'NONINTEGER_TIMESTAMP')
    return int(number)


def _complete_bars(raw, *, ticker, session, captured):
    """Do not mature partial bars using the time at which the review is run."""
    chart=json.loads(raw,parse_float=Decimal)['chart']
    _require(chart.get('error') is None and len(chart['result'])==1,'INVALID_CHART')
    result=chart['result'][0];meta=result['meta']
    _require(meta['symbol']==ticker and meta['currency']=='USD' and meta.get('exchangeTimezoneName')=='America/New_York'
             and meta.get('dataGranularity')=='1m','SOURCE_IDENTITY_OR_GRANULARITY_MISMATCH')
    regular=meta['currentTradingPeriod']['regular'];opening=_stamp(regular['start']);closing=_stamp(regular['end'])
    _require(opening<closing and all(datetime.fromtimestamp(t,NY).date().isoformat()==session for t in (opening,closing)), 'SOURCE_SESSION_MISMATCH')
    timestamps=result['timestamp'];quotes=result['indicators']['quote'];_require(len(quotes)==1,'AMBIGUOUS_QUOTES');q=quotes[0]
    _require(all(len(q[key])==len(timestamps) for key in ('open','high','low','close','volume')),'ARRAY_LENGTH_MISMATCH')
    bars={};seen=set()
    for i,value in enumerate(timestamps):
        ts=_stamp(value);_require(ts not in seen,'DUPLICATE_BAR_TIMESTAMP');seen.add(ts)
        if ts%60 or ts<opening or ts+60>closing or datetime.fromtimestamp(ts+60,timezone.utc)>captured:continue
        if any(q[key][i] is None for key in ('open','high','low','close','volume')):continue
        volume=_number(q['volume'][i])
        if volume<=0:continue
        o,h,l,c=(_number(q[key][i]) for key in ('open','high','low','close'))
        _require(0<l<=o<=h and l<=c<=h,'INVALID_BAR_OHLC')
        bars[ts]=tuple(str(value) for value in (o,h,l,c))
    return bars


def review_intraday_touches(journal_root, session, *, expected_event_hashes=None):
    base=review_intraday_session(journal_root,session,expected_event_hashes=expected_event_hashes)
    root=Path(journal_root).resolve();loaded={};pins={};diagnostics=[]
    for record in base['records']:
        if 'event_id' not in record or record['issues']:
            diagnostics.append(dict(path=record['path'],reason='BASE_EVENT_REVIEW_INVALID',issues=record['issues']))
            continue
        try:
            raw=(root/record['path']).read_bytes()
            _require(sha256(raw).hexdigest()==record['event_sha256'],'EVENT_CHANGED_DURING_REVIEW')
            loaded[record['event_id']]=(json.loads(raw),record)
            pins[record['path']]=record['event_sha256']
        except Exception as error:diagnostics.append(dict(path=record['path'],reason=str(error)))
    results=[]
    for identifier,(event,record) in loaded.items():
        for row in event['response']['stocks']:
            if row['status']!='AVAILABLE':continue
            item=dict(event_id=identifier,process_boot_id=event['process_boot_id'],observation_sequence=event['observation_sequence'],
                      research_id=event['research_id'],ticker=row['ticker'],limit_price=row['limit_price'],status='UNKNOWN',
                      reasons=[],evidence=[],coverage_complete=False,conflicting_minutes=[])
            results.append(item)
            try:
                _require(not record['issues'] and not base['missing_receipts'] and not diagnostics,'ORIGINAL_REVIEW_OR_INVENTORY_INCOMPLETE')
                start=_time(event['request_finished_at']);end=_time(row['refresh_by']);cutoffs=[]
                # Observed server response boundaries only, not browser receipt or broker cancellations.
                for other_id,(other,other_record) in loaded.items():
                    if other_id==identifier:continue
                    matching=other['research_id']==event['research_id'] and any(r['ticker']==row['ticker'] for r in other['response']['stocks'])
                    if other['process_boot_id']!=event['process_boot_id'] and _time(other['request_started_at'])>_time(event['request_started_at']):
                        boundary=_time(other['request_started_at']);kind='OBSERVED_OTHER_BOOT_REQUEST_START'
                    elif matching and other['process_boot_id']==event['process_boot_id'] and other['observation_sequence']>event['observation_sequence']:
                        boundary=_time(other['request_finished_at']);kind='SUBSEQUENT_SERVER_RESPONSE'
                    else:continue
                    if boundary<end:
                        end=boundary;cutoffs.append(dict(event_id=other_id,time=boundary.isoformat(),kind=kind))
                item.update(window_start=start.isoformat(),window_end=end.isoformat(),cutoffs=cutoffs)
                expected=list(range(math.ceil(start.timestamp()/60)*60,math.floor(end.timestamp()/60)*60,60)) if end>start else []
                item['partial_edge_exclusions']=dict(
                    start_partial_until=datetime.fromtimestamp(math.ceil(start.timestamp()/60)*60,timezone.utc).isoformat() if start.second or start.microsecond else None,
                    end_partial_from=datetime.fromtimestamp(math.floor(end.timestamp()/60)*60,timezone.utc).isoformat() if end.second or end.microsecond else None,
                    scope='EXCLUDED_PARTIAL_EDGE_INTERVALS_NOT_EVIDENCE_OF_NO_TOUCH')
                item['expected_complete_minute_starts']=[datetime.fromtimestamp(t,timezone.utc).isoformat() for t in expected]
                _require(expected,'NO_FULL_MINUTE_IN_OBSERVED_VALIDITY_WINDOW')
                original_hashes={c['sha256'] for c in event['captures']}
                variants={};invalid=[]
                for other_id,(other,other_record) in loaded.items():
                    if other_id==identifier or _time(other['request_finished_at'])<=start:continue
                    for capture in other['captures']:
                        if capture['role']!='FETCHED' or capture['ticker']!=row['ticker']:continue
                        captured=_time(capture['captured_at'])
                        if captured<=start or capture['sha256'] in original_hashes:continue
                        try:
                            _require(not other_record['issues'],'LATER_EVENT_REVIEW_INVALID')
                            source=root/capture['path'];raw=source.read_bytes()
                            _require(sha256(raw).hexdigest()==capture['sha256'],'RAW_CHANGED_DURING_REVIEW')
                            bars=_complete_bars(raw,ticker=row['ticker'],session=session,captured=captured)
                            pins[capture['path']]=capture['sha256']
                            for ts in expected:
                                if ts not in bars:continue
                                values=tuple(Fraction(v) for v in bars[ts])
                                evidence=dict(source_event_id=other_id,raw_path=capture['path'],raw_sha256=capture['sha256'],
                                              captured_at=capture['captured_at'],encoding=capture['encoding'],minute_start=datetime.fromtimestamp(ts,timezone.utc).isoformat(),
                                              minute_end=datetime.fromtimestamp(ts+60,timezone.utc).isoformat(),ohlc=list(bars[ts]))
                                variants.setdefault(ts,{}).setdefault(values,[]).append(evidence)
                        except Exception as error:invalid.append(dict(source_event_id=other_id,reason=str(error)))
                item['source_issues']=invalid
                conflicts=[ts for ts,v in variants.items() if len(v)>1]
                item['conflicting_minutes']=[datetime.fromtimestamp(t,timezone.utc).isoformat() for t in conflicts]
                item['missing_minutes']=[datetime.fromtimestamp(t,timezone.utc).isoformat() for t in expected if t not in variants]
                item['coverage_complete']=len(variants)==len(expected) and not conflicts and not invalid
                for ts in sorted(variants):
                    for evidence in variants[ts].values():item['evidence'].extend(evidence)
                _require(not conflicts,'CONFLICTING_LATER_OHLC_NO_PRICE_SELECTION')
                _require(not invalid,'INVALID_LATER_SOURCE_EVIDENCE')
                touched=[ts for ts,v in variants.items() if next(iter(v))[2]<=Fraction(row['limit_price'])]
                item['touch_minutes']=[datetime.fromtimestamp(t,timezone.utc).isoformat() for t in touched]
                if touched:item['status']='OBSERVED_TOUCH'
                elif item['coverage_complete']:item['status']='NO_TOUCH_IN_COMPLETE_OBSERVED_WINDOW'
                else:item['reasons'].append('INCOMPLETE_LATER_MINUTE_COVERAGE')
            except Exception as error:item['reasons'].append(str(error))
    results.sort(key=lambda r:(r['process_boot_id'],r['observation_sequence'],r['ticker']))
    return dict(schema='INTRADAY_SAVED_TOUCH_REVIEW_V1',session=session,base_review_status=base['status'],
                base_events_with_issues=base['events_with_issues'],
                saved_inventory=[dict({key:r.get(key) for key in ('path','event_sha256','event_id','process_boot_id','observation_sequence','status','issues')},
                                      rows=[{key:row.get(key) for key in ('ticker','status','reason','checked_at')} for row in r['observations']]) for r in base['records']],
                saved_event_count=base['event_count'],
                saved_response_counts={status:sum(r.get('status')==status for r in base['records']) for status in ('AVAILABLE','PARTIAL','UNAVAILABLE','ALL_CASH')},
                source_diagnostics=diagnostics,observations=results,source_hashes=pins,
                reviewer_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                limitations=['Observed touch is not an order, fill, broker acknowledgement, or return.',
                             'Only fully contained complete minutes count; partial edge intervals and missing captures remain unobserved.',
                             'Server response and first observed restart boundaries are conservative observation cutoffs, not proven browser receipt times.',
                             'Local file hashes are not independently trusted timestamps; prior receipts only verify agreement when explicitly supplied.',
                             'No network, account changes, backfills, or strategy evaluation.'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--journal-root',required=True);parser.add_argument('--session',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();report=review_intraday_touches(args.journal_root,args.session)
    with Path(args.output).open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(observations=len(report['observations']),statuses={s:sum(r['status']==s for r in report['observations']) for s in ('OBSERVED_TOUCH','NO_TOUCH_IN_COMPLETE_OBSERVED_WINDOW','UNKNOWN')})))

if __name__=='__main__':main()
