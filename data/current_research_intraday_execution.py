"""Fresh intraday conservative BUY reference, never an order or timing claim."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal,ROUND_FLOOR
from fractions import Fraction
from threading import RLock, Lock
from urllib.parse import quote
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo
import json
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_snapshot_resolver import read_known_research_snapshot
from data.current_top1_portfolio_research import METHOD as TOP1_METHOD,RESEARCH_VERSION as TOP1_VERSION

NY=ZoneInfo('America/New_York')
MAX_AGE_SECONDS=120
RULE='MIN_FRESH_LAST_AND_COMPLETED_1M_LOW_FLOOR_CENT_NONINCREASING_SESSION_CAP'

def fetch_intraday_chart(ticker):
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker,safe='')+'?interval=1m&range=1d'
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=10) as response:
        raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('QUOTE_RESPONSE_TOO_LARGE')
    return raw

def _require(ok,reason):
    if not ok:raise ValueError(reason)

def _number(value):
    _require(not isinstance(value,bool) and value is not None,'INVALID_NUMERIC_QUOTE')
    result=Decimal(str(value));_require(result.is_finite(),'NONFINITE_QUOTE');return result

def _stamp(value):
    number=_number(value);_require(number==number.to_integral_value(),'NONINTEGER_TIMESTAMP')
    return int(number)

def _iso(stamp):return datetime.fromtimestamp(stamp,timezone.utc).isoformat()

def _money(value):
    cents=value*100
    _require(cents.denominator==1 and cents>=0,'SUBCENT_CASH_NOT_SUPPORTED')
    n=int(cents);return f'{n//100}.{n%100:02d}'

def decode_intraday_reference(payload, *, ticker, now, captured_at=None):
    _require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
    captured_at=now if captured_at is None else captured_at
    _require(isinstance(captured_at,datetime) and captured_at.tzinfo is not None and captured_at<=now,'CAPTURE_TIME_INVALID')
    completed_through=Decimal(str(captured_at.timestamp()))
    data=json.loads(payload,parse_float=Decimal) if isinstance(payload,(bytes,str)) else payload
    chart=data['chart'];_require(chart.get('error') is None and len(chart['result'])==1,'INVALID_CHART_RESULT')
    result=chart['result'][0];meta=result['meta'];current=Decimal(str(now.timestamp()))
    _require(meta['symbol']==ticker and meta['currency']=='USD' and meta.get('exchangeTimezoneName')=='America/New_York','QUOTE_IDENTITY_CURRENCY_MISMATCH')
    _require(meta.get('dataGranularity')=='1m','NOT_ONE_MINUTE_DATA')
    regular=meta['currentTradingPeriod']['regular'];opening=_stamp(regular['start']);closing=_stamp(regular['end'])
    _require(opening<=current<closing and opening<closing,'OUTSIDE_REGULAR_SESSION')
    session=now.astimezone(NY).date().isoformat()
    _require(datetime.fromtimestamp(opening,NY).date().isoformat()==session and datetime.fromtimestamp(closing,NY).date().isoformat()==session,'SESSION_DATE_MISMATCH')
    last=_number(meta['regularMarketPrice']);last_at=_stamp(meta['regularMarketTime'])
    _require(last>0 and opening<=last_at<closing,'INVALID_LAST_QUOTE')
    _require(current-last_at<=MAX_AGE_SECONDS,'LAST_QUOTE_STALE')
    timestamps=result['timestamp'];quotes=result['indicators']['quote']
    _require(len(quotes)==1,'AMBIGUOUS_MINUTE_QUOTES');q=quotes[0]
    _require(all(len(q[k])==len(timestamps) for k in ('open','high','low','close','volume')),'MINUTE_ARRAY_LENGTH_MISMATCH')
    seen=set();eligible=[]
    for i,t in enumerate(timestamps):
        ts=_stamp(t);_require(ts not in seen,'DUPLICATE_MINUTE');seen.add(ts)
        # Partial minute and provider non-minute snapshots are never full bars.
        if ts%60 or ts<opening or ts+60>closing or ts+60>completed_through:continue
        if any(q[k][i] is None for k in ('open','high','low','close','volume')):continue
        volume=_number(q['volume'][i])
        if volume<=0:continue
        o,h,l,c=(_number(q[k][i]) for k in ('open','high','low','close'))
        _require(0<l<=o<=h and l<=c<=h,'INVALID_MINUTE_OHLC')
        eligible.append((ts,l))
    _require(eligible,'NO_COMPLETED_VALID_MINUTE')
    ts,low=max(eligible)
    _require(current-(ts+60)<=MAX_AGE_SECONDS,'COMPLETED_MINUTE_STALE')
    cap=min(last,low).quantize(Decimal('0.01'),rounding=ROUND_FLOOR)
    _require(cap>0,'NONPOSITIVE_CENT_LIMIT')
    _require(last_at<=current,'LAST_QUOTE_FUTURE')
    return dict(session=session,last_price=str(last),last_at=_iso(last_at),minute_low=str(low),minute_start=_iso(ts),minute_end=_iso(ts+60),
        observed_cap=str(cap),refresh_by=_iso(min(last_at+MAX_AGE_SECONDS,ts+60+MAX_AGE_SECONDS,closing)),
        source='YAHOO_CHART_REGULAR_LAST_AND_COMPLETED_1M',session_open=_iso(opening),session_close=_iso(closing))

class IntradayExecutionService:
    def __init__(self, *, snapshot_reader=read_known_research_snapshot, fetch=fetch_intraday_chart, clock=lambda:datetime.now(timezone.utc), journal=None, cap_store=None):
        self.cap_store=cap_store
        self.journal=journal;self.process_boot_id=uuid4().hex;self.source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()
        self.snapshot_reader=snapshot_reader;self.fetch=fetch;self.clock=clock;self.caps={};self.cap_events={};self.observation_sequence=0;self.pending_responses={};self.last_valid_responses={};self.fetch_gates={};self.lock=RLock()
        self.reference_attempt_sequence=0;self.current_attempts={}
    def preview(self,research_id):
        # Attempt authority begins before snapshot validation, fetch, or publication.
        _require(isinstance(research_id,str) and research_id,'RESEARCH_ID_REQUIRED')
        with self.lock:
            self.reference_attempt_sequence+=1;token=self.reference_attempt_sequence
            self.current_attempts[research_id]=dict(token=token,status='PENDING',started_at=None,finished_at=None,result=None,reason=None)
        try:
            started=self.clock()
            with self.lock:
                if self.current_attempts[research_id]['token']==token:self.current_attempts[research_id]['started_at']=started.isoformat()
            response=self._preview(research_id)
        except Exception as error:
            with self.lock:
                if self.current_attempts[research_id]['token']==token:
                    self.current_attempts[research_id].update(status='UNAVAILABLE',finished_at=self.clock().isoformat(),reason=str(error),result=None)
            raise
        with self.lock:
            if self.current_attempts[research_id]['token']==token:
                self.current_attempts[research_id].update(status='FINISHED',finished_at=self.clock().isoformat(),result=deepcopy(response))
        return response

    def current_reference(self,research_id):
        """Read only this process's latest attempt, without any HTTP or recovery.

        A SAVED receipt is a local reference, not independent source certification.
        Consumers must replay the receipt/raw closure before constructing orders.
        """
        _require(isinstance(research_id,str) and research_id,'RESEARCH_ID_REQUIRED')
        with self.lock:
            entry=self.current_attempts.get(research_id)
            output=dict(schema='CURRENT_INTRADAY_EXECUTION_REFERENCE_V1',research_id=research_id,process_boot_id=self.process_boot_id,
                attempt_token=None,attempt_started_at=None,attempt_finished_at=None,observation_sequence=None,
                current_receipt=None,response=None,status='NO_CURRENT_REFERENCE',reason='NO_ATTEMPT_IN_THIS_PROCESS',
                research_only=True,execution_blocked=True)
            if entry is None:return output
            output.update(attempt_token=entry['token'],attempt_started_at=entry['started_at'],attempt_finished_at=entry['finished_at'])
            if entry['status']=='PENDING':
                output.update(status='PENDING',reason='LATEST_ATTEMPT_PENDING');return output
            response=entry['result']
            if response is None:
                output.update(status='UNAVAILABLE',reason=entry['reason']);return output
            output['observation_sequence']=response.get('observation_sequence')
            receipt=response.get('observation_record')
            output['current_receipt']=deepcopy(receipt) if isinstance(receipt,dict) and receipt.get('status')=='SAVED' else None
            try:
                _require(response.get('process_boot_id')==self.process_boot_id and response.get('research_id')==research_id,'CURRENT_RESPONSE_BINDING_MISMATCH')
                _require(response.get('status')=='AVAILABLE' and response.get('stocks') and all(row.get('status')=='AVAILABLE' for row in response['stocks']),
                    'LATEST_ATTEMPT_UNAVAILABLE:'+str(next((row.get('reason') for row in response.get('stocks',[]) if row.get('status')!='AVAILABLE'),'')))
                _require(isinstance(receipt,dict) and receipt.get('status')=='SAVED' and all(isinstance(receipt.get(k),str) and receipt[k] for k in ('event_id','event_path','event_sha256')),'CURRENT_OBSERVATION_NOT_SAVED')
                now=self.clock();_require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
                _require(datetime.fromisoformat(entry['finished_at'])<=now,'CURRENT_ATTEMPT_FINISH_IN_FUTURE')
                for row in response['stocks']:
                    checked=datetime.fromisoformat(row['checked_at']);deadline=datetime.fromisoformat(row['refresh_by'])
                    _require(checked<=now<deadline,'CURRENT_REFERENCE_EXPIRED_OR_FUTURE')
                    _require(row['session']==now.astimezone(NY).date().isoformat(),'CURRENT_REFERENCE_SESSION_CHANGED')
                output.update(status='AVAILABLE',reason=None,response=deepcopy(response))
            except (ValueError,KeyError,TypeError) as error:
                output.update(status='UNAVAILABLE',reason=str(error))
            return deepcopy(output)

    def _preview(self,research_id):
        request_id=uuid4().hex;started=self.clock();captures=[];frozen_publication=None
        snapshot=self.snapshot_reader(research_id)
        _require(snapshot.get('research_id')==research_id and snapshot.get('research_only') is True and snapshot.get('execution_blocked') is True,'INVALID_RESEARCH_SNAPSHOT')
        _require(snapshot.get('method')==TOP1_METHOD and snapshot.get('research_version')==TOP1_VERSION,'CURRENT_TOP1_METHOD_REQUIRED')
        identity=snapshot['budget_identity_exact']
        values={}
        for key in ('entered_cash','stock_notional','fees','residual_cash'):
            _require(not isinstance(identity[key],bool),'INVALID_EXACT_BUDGET')
            values[key]=Fraction(str(identity[key]))
            _require(values[key]>=0,'INVALID_EXACT_BUDGET')
        cash=values['entered_cash']
        _require(cash>0 and values['fees']==0 and values['stock_notional']+values['fees']+values['residual_cash']==cash
                 and not isinstance(snapshot['budget'],bool) and Fraction(str(snapshot['budget']))==cash,'EXACT_BUDGET_IDENTITY_MISMATCH')
        _money(cash)
        selected=snapshot['selected_security']
        _require(selected['security_id']==snapshot['selected_ranking_security_id'],'SELECTED_SECURITY_MISMATCH')
        stocks=snapshot['stocks']
        _require(isinstance(stocks,list) and len(stocks)<=1,'TOP1_STOCK_DOMAIN_MISMATCH')
        _require(all(s['security_id']==selected['security_id'] and s['ticker']==selected['ticker'] for s in stocks),'TOP1_STOCK_DOMAIN_MISMATCH')
        if not stocks:
            _require(snapshot.get('status')=='ALL_CASH' and values['stock_notional']==0,'INVALID_ALL_CASH_SNAPSHOT')
            stocks=[dict(selected,units=0,close=None)]
        def response_for(rows):
            available=sum(row['status']=='AVAILABLE' for row in rows)
            return dict(status='ALL_CASH' if not rows else 'AVAILABLE' if available==len(rows) else 'PARTIAL' if available else 'UNAVAILABLE',
                research_id=research_id,stocks=deepcopy(rows),research_only=True,execution_blocked=True,
                execution_rule=RULE,method_scope='ENGINEERING_EXECUTION_REFERENCE_NOT_BACKTESTED_IMPROVEMENT',
                notes=['Buy reference only; limit may never fill. No automatic order or recorded fill.',
                       'Session cap decreases within the configured persistence scope; see cap_persistence. A different research identity or session has a separate cap.',
                       'Provider session metadata is a cross-check, not an official exchange-calendar certification.',
                       'Zero commission does not certify other costs as zero. Historical Close is displayed separately and never used as fallback.'],
                process_boot_id=self.process_boot_id,observation_sequence=sequence)
        def event_for(response):
            return dict(schema='INTRADAY_OBSERVATION_V1',event_id=request_id,observation_sequence=sequence,
                process_boot_id=self.process_boot_id,service_source_sha256=self.source_sha256,
                service_version='INTRADAY_EXECUTION_OBSERVATIONS_V1',research_id=research_id,
                delivery_status='NOT_ATTESTED',purpose='OBSERVED_BEFORE_DELIVERY',
                research_binding={key:deepcopy(snapshot.get(key)) for key in (
                    'research_version','method','as_of','budget_identity_exact','selected_security','stocks','sources')},
                request_started_at=started.isoformat(),request_finished_at=self.clock().isoformat(),response=deepcopy(response))
        def row_for(evidence,cap,persistence,base,units):
            limit=Fraction(cap);fresh_units=int(cash//limit);notional=fresh_units*limit
            fresh=dict(cash=_money(cash),quantity=fresh_units,limit_price=str(cap),notional=_money(notional),
                commission='0.00',residual_cash=_money(cash-notional),research_id=research_id,
                other_fees_known=False,source_budget='snapshot.budget_identity_exact.entered_cash',
                assumption='FRESH_CASH_BUILD_ONLY_NOT_ADDITIONAL_SHARES_FOR_EXISTING_HOLDINGS',other_charges='UNCONFIRMED')
            return dict(base,**evidence,status='AVAILABLE',limit_price=str(cap),cap_locked_below_observed=cap<Decimal(evidence['observed_cap']),
                fresh_cash_reference=fresh,sealed_target_units=units,cap_rule=RULE,cap_persistence=persistence,
                quantity_policy='SEALED_TARGET_PRESERVED_FRESH_CASH_SIZE_SEPARATE_NOT_AN_ORDER')
        rows=[]
        ticker=stocks[0]['ticker']
        with self.lock:
            gate=self.fetch_gates.setdefault(ticker,Lock())
        owns_gate=gate.acquire(blocking=False)
        fetch_error=None;payload=None;fetch_captured_at=None
        try:
            if owns_gate:
                try:
                    _require(type(stocks[0]['units']) is int and stocks[0]['units']>=0,'INVALID_FROZEN_QUANTITY')
                    if self.cap_store is not None and self.journal is not None:
                        self.cap_store.recover(self.journal,research_id=research_id,security_id=selected['security_id'],ticker=ticker,session=started.astimezone(NY).date().isoformat())
                    payload=self.fetch(ticker)
                    fetch_captured_at=self.clock()
                    captures.append(dict(ticker=ticker,role='FETCHED',captured_at=fetch_captured_at.isoformat(),payload=deepcopy(payload)))
                except Exception as error:
                    fetch_error=error
            else:
                fetch_error=ValueError('FETCH_IN_PROGRESS')
            with self.lock:
                self.observation_sequence+=1;sequence=self.observation_sequence
                for stock in stocks:
                    ticker=stock['ticker'];units=stock['units']
                    base=dict(ticker=ticker,units=units,historical_reference=dict(as_of=snapshot.get('as_of'),close=stock.get('close')))
                    now=self.clock()
                    try:
                        _require(type(units) is int and units>=0,'INVALID_FROZEN_QUANTITY')
                        if fetch_error is not None:raise fetch_error
                        captured=fetch_captured_at;origin='NEW_FETCH'
                        used_payload=payload
                        try:
                            evidence=decode_intraday_reference(payload,ticker=ticker,now=now,captured_at=captured)
                        except ValueError as error:
                            if str(error)!='LAST_QUOTE_FUTURE':raise
                            previous=self.pending_responses.get(ticker)
                            self.pending_responses[ticker]=(deepcopy(payload),fetch_captured_at)
                            candidates=[(previous,'PENDING_RESPONSE_NOW_VALID'),
                                        (self.last_valid_responses.get(ticker),'VERIFIED_RESPONSE_STILL_FRESH')]
                            seen=[];failure=error
                            for candidate,candidate_origin in candidates:
                                if candidate is None:continue
                                candidate_payload,candidate_capture=candidate
                                if any(candidate_payload==prior for prior in seen):continue
                                seen.append(candidate_payload)
                                try:
                                    candidate_evidence=decode_intraday_reference(candidate_payload,ticker=ticker,now=now,captured_at=candidate_capture)
                                except (ValueError,KeyError,TypeError) as candidate_error:
                                    failure=candidate_error;continue
                                evidence=candidate_evidence;captured=candidate_capture
                                origin=candidate_origin;used_payload=candidate_payload
                                break
                            else:raise failure
                        self.last_valid_responses[ticker]=(deepcopy(used_payload),captured)
                        captures.append(dict(ticker=ticker,role='USED',captured_at=captured.isoformat(),payload=deepcopy(used_payload)))
                        evidence.update(quote_response_origin=origin,quote_response_captured_at=captured.astimezone(timezone.utc).isoformat(),quote_response_age_seconds=(now-captured).total_seconds())
                        key=(research_id,selected['security_id'],ticker,evidence['session']);observed=Decimal(evidence['observed_cap'])
                        if self.cap_store is not None and self.journal is not None:
                            prepared_rows=[]
                            def prepare_publication(metadata):
                                checked=self.clock()
                                decode_intraday_reference(used_payload,ticker=ticker,now=checked,captured_at=captured)
                                _require(checked.timestamp()<datetime.fromisoformat(evidence['refresh_by']).timestamp(),'REFERENCE_EXPIRED_BEFORE_CAP_COMMIT')
                                frozen_evidence=dict(evidence,**{k:v for k,v in metadata.items() if k!='cap'},
                                    cap_history_verification='FOLLOW_EVENT_RECEIPTS_TRANSACTIONAL_OUTBOX',checked_at=checked.isoformat(),
                                    quote_response_age_seconds=(checked-captured).total_seconds())
                                row=row_for(frozen_evidence,Decimal(metadata['cap']),'TRANSACTIONAL_LOCAL_SQLITE_MIN_ACROSS_RESTARTS',base,units)
                                package=self.journal.prepare(event_for(response_for([row])),captures)
                                self.journal.validate_prepared(package)
                                prepared_rows.append(row)
                                return package
                            saved=self.cap_store.lower_with_outbox(research_id=research_id,security_id=selected['security_id'],ticker=ticker,
                                session=evidence['session'],observed_cap=str(observed),event_id=request_id,prepare_callback=prepare_publication)
                            frozen_publication=saved['publication'];rows.append(prepared_rows[0])
                        else:
                            if self.cap_store is not None:
                                saved=self.cap_store.lower(research_id=research_id,security_id=selected['security_id'],ticker=ticker,
                                    session=evidence['session'],observed_cap=str(observed),event_id=request_id)
                                cap=Decimal(saved.pop('cap'));evidence.update(saved)
                                persistence='TRANSACTIONAL_LOCAL_SQLITE_MIN_ACROSS_RESTARTS'
                            else:
                                previous_cap=self.caps.get(key);prior_cap_event_id=self.cap_events.get(key);cap=min(observed,self.caps.get(key,observed));self.caps[key]=cap
                                if previous_cap is None or cap<previous_cap:self.cap_events[key]=request_id
                                evidence.update(cap_before=None if previous_cap is None else str(previous_cap),prior_cap_event_id=prior_cap_event_id,cap_origin_event_id=self.cap_events[key])
                                persistence='PROCESS_MEMORY_ONLY_RESET_ON_RESTART'
                            final_now=self.clock()
                            decode_intraday_reference(used_payload,ticker=ticker,now=final_now,captured_at=captured)
                            _require(final_now.timestamp()<datetime.fromisoformat(evidence['refresh_by']).timestamp(),'REFERENCE_EXPIRED_AFTER_CAP_COMMIT')
                            evidence.update(cap_history_verification='FOLLOW_EVENT_RECEIPTS_PRIOR_EVENT_MAY_HAVE_FAILED_TO_SAVE',checked_at=final_now.isoformat(),quote_response_age_seconds=(final_now-captured).total_seconds())
                            rows.append(row_for(evidence,cap,persistence,base,units))
                    except Exception as error:
                        rows.append(dict(base,checked_at=self.clock().isoformat(),status='UNAVAILABLE',reason=str(error),limit_price=None,refresh_by=None))
        finally:
            if owns_gate:gate.release()
        response=response_for(rows)
        if frozen_publication is not None:
            try:
                self.cap_store.recover(self.journal,research_id=research_id,security_id=selected['security_id'],ticker=ticker,session=rows[0]['session'])
                response['observation_record']=dict(frozen_publication['receipt'])
                # Original observation bytes/time never change during publication or recovery.
                delivered_at=self.clock()
                decode_intraday_reference(used_payload,ticker=ticker,now=delivered_at,captured_at=captured)
                _require(delivered_at.timestamp()<datetime.fromisoformat(rows[0]['refresh_by']).timestamp(),'REFERENCE_EXPIRED_AFTER_PUBLICATION')
            except Exception as error:
                response.update(status='UNAVAILABLE',stocks=[dict(base,checked_at=self.clock().isoformat(),status='UNAVAILABLE',reason=str(error),limit_price=None,refresh_by=None)])
                if 'observation_record' not in response:
                    response['observation_record']=dict(status='FAILED',event_id=request_id,reason=str(error),recovery='COMMITTED_ORIGINAL_BYTES_PENDING_PUBLICATION')
        elif self.journal is None:
            response['observation_record']=dict(status='NOT_CONFIGURED')
        else:
            try:
                response['observation_record']=self.journal.record(event_for(response),captures)
            except Exception as error:
                response['observation_record']=dict(status='FAILED',event_id=request_id,reason=str(error))

        return response

SERVICE=IntradayExecutionService(journal=IntradayObservationJournal(
    Path(__file__).resolve().parents[1]/'data/cache/research/intraday_execution_observations'),
    cap_store=PersistentIntradayCapStore(Path(__file__).resolve().parents[1]/'data/cache/research/intraday_execution_caps.sqlite3'))
def preview_intraday_execution(research_id):return SERVICE.preview(research_id)
