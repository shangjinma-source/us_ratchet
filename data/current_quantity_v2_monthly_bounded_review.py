"""Replayable monthly bounded public screening; not complete action certification."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import gzip
import io
from hashlib import sha256
import json
from threading import RLock
from zoneinfo import ZoneInfo
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_bounded_unit_review import (
    _files, replay_bounded_review, POLICY as CASH_POLICY, STATUS,
    fetch_official_feed, MAX_BYTES, URL)

POLICY='MONTHLY_BOUNDED_PUBLIC_KNOWN_ACTIONS_V1'
ERROR='MONTHLY_BOUNDED_REVIEW_UNAVAILABLE'


def _json(raw):
    require(type(raw)is bytes and len(raw)<=16*1024*1024,ERROR)
    if raw[:2]==b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:raw=source.read(16*1024*1024+1)
    require(len(raw)<=16*1024*1024,ERROR)
    return json.loads(raw,parse_float=Decimal)


def _events(chart, start, end, *, date_only=False):
    for kind, events in chart.get('events',{}).items():
        if kind=='dividends' or not events:continue
        require(isinstance(events,dict),ERROR)
        for event in events.values():
            require(isinstance(event,dict) and type(event.get('date')) in (int,float),ERROR)
            at=datetime.fromtimestamp(event['date'],timezone.utc)
            relevant=(at.astimezone(ZoneInfo('America/New_York')).date().isoformat()>=start if date_only else at>=stamp(start))
            require(not (relevant and at<=stamp(end)),'BOUNDED_UNIT_CHANGE_CANDIDATE')


def _origin_chart(files,pins,security,origin):
    receipts=[]
    for path in pins:
        value=_json(files[path])
        if isinstance(value,dict) and 'raw_path' in value:receipts.append(value)
    require(len(receipts)==1,ERROR);r=receipts[0]
    require(r['security_id']==security['security_id'] and r['ticker']==security['ticker']
        and stamp(r['captured_at'])==stamp(origin['captured_at']) and r['raw_path'] in pins
        and sha256(files[r['raw_path']]).hexdigest()==r['raw_sha256'],ERROR)
    chart=_json(files[r['raw_path']])['chart']['result'][0];m=chart['meta']
    require(m['symbol']==security['ticker'] and m['currency']=='USD' and m['instrumentType']=='EQUITY',ERROR)
    return chart,r


def replay_monthly_review(unit,*,security,current,source_hashes,now,capital_decision=None,origin=None,held_capital_decision=None):
    """Validate outer pins and independently replay both evidence coordinates."""
    try:
        e=unit['bounded_evidence'];files=_files(e);now=stamp(now)
        require(e['policy']==POLICY and unit['status']==STATUS,ERROR)
        expected=({'security_id','ticker','price_basis','capital_decision_id','status','reference_source_hashes','valuation_source_references','source_references','covered_from_date','covered_through','reviewed_at','bounded_evidence'} if capital_decision is not None else {'prior_revision','security_id','prior_reference_source_hashes','reference_source_hashes','prior_active_proposal_id','prior_price_basis','price_basis','security_class','covered_from','covered_through','reviewed_at','status','source_references','bounded_evidence'})
        require(set(unit)==expected,ERROR)
        require(unit.get('ticker',security['ticker'])==security['ticker'] and unit['price_basis']=='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS'
            and stamp(current['captured_at'])<=stamp(unit['covered_through'])<=stamp(unit['reviewed_at'])<=now,ERROR)
        require(not (set(unit)&{'known_actions','pending_actions'}),ERROR)
        require(all(source_hashes.get(p)==h for p,h in e['source_hashes'].items()),ERROR)
        require(e['rss_raw_path'] in unit['source_references'] and e['rss_receipt_path'] in unit['source_references'],ERROR)
        sec=dict(security,security_id=unit['security_id'])
        require(e['security']==sec and unit['reference_source_hashes']==current['source_hashes'],ERROR)
        require(all(e['source_hashes'].get(p)==h for p,h in current['source_hashes'].items()),ERROR)
        # Reuse current-quote + RSS screen without manufacturing a daily intraday receipt.
        # Current reference is both endpoints only for this current-source screen; origin
        # daily/held verification below is independent and cannot be bypassed by it.
        screen=deepcopy(e);screen['policy']=CASH_POLICY
        summary=replay_bounded_review({'bounded_evidence':screen},security=sec,origin=current,current=current,now=now)
        if capital_decision is not None:
            b=capital_decision['binding'];q=b['valuation_quotes'][unit['security_id']]
            require(e['kind']=='VALUATION' and unit['capital_decision_id']==capital_decision['decision_id']
                and unit['valuation_source_references']==q['source_references']
                and e['valuation_quote']==q and e['decision_date']==b['decision_date'],ERROR)
            matches=[]
            for path in q['source_references']:
                require(path in files and e['source_hashes'][path]==source_hashes[path],ERROR)
                try:chart=_json(files[path])['chart']['result'][0]
                except (KeyError,TypeError,IndexError,ValueError):continue
                from data.current_research_ohlc_panel import parse_provider_ohlc
                parse_provider_ohlc(files[path],sec['ticker'])
                meta=chart['meta']
                if meta.get('symbol')!=sec['ticker']:continue
                require(meta.get('currency')=='USD' and meta.get('instrumentType')=='EQUITY',ERROR)
                closes=chart['indicators']['quote'][0]['close'];times=chart['timestamp']
                require(len(closes)==len(times),ERROR)
                selected=[closes[i] for i,t in enumerate(times) if datetime.fromtimestamp(t,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()==b['decision_date']]
                if len(selected)==1 and selected[0] is not None and Fraction(str(selected[0]))==Fraction(q['price']):
                    _events(chart,b['decision_date'],current['captured_at'],date_only=True);matches.append(path)
            require(len(matches)==1 and e['daily_raw_path']==matches[0],ERROR)
        else:
            require(e['kind']=='HELD' and e['origin']==origin and origin is not None,ERROR)
            require(all(e['source_hashes'].get(p)==h for p,h in origin['source_hashes'].items()),ERROR)
            require(stamp(origin['captured_at'])<=stamp(current['captured_at']),ERROR)
            chart,_=_origin_chart(files,origin['source_hashes'],sec,origin)
            _events(chart,origin['captured_at'],current['captured_at'])
            from data.current_research_ohlc_panel import parse_provider_ohlc
            require(held_capital_decision is not None,ERROR)
            valuation=held_capital_decision['binding']['valuation_quotes'][unit['security_id']]
            daily=e['daily_raw_path']
            require(daily in valuation['source_references'] and e['valuation_quote']==valuation
                and e['decision_date']==held_capital_decision['decision_date'],ERROR)
            daily_chart=_json(files[daily])['chart']['result'][0]
            parse_provider_ohlc(files[daily],sec['ticker'])
            close_values=[v for t,v in zip(daily_chart['timestamp'],daily_chart['indicators']['quote'][0]['close'])
                if datetime.fromtimestamp(t,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()==held_capital_decision['decision_date']]
            require(len(close_values)==1 and close_values[0] is not None and Fraction(str(close_values[0]))==Fraction(valuation['price']),ERROR)
            _events(daily_chart,origin['captured_at'],current['captured_at'])
        receipt=json.loads(files[e['rss_receipt_path']])
        require(stamp(unit['reviewed_at'])==stamp(receipt['received_at']) and stamp(unit['covered_through'])==stamp(current['captured_at']),ERROR)
        if capital_decision is not None:require(unit['covered_from_date']==capital_decision['decision_date'],ERROR)
        else:require(stamp(unit['covered_from'])==stamp(origin['captured_at']),ERROR)
        summary['policy']=POLICY
        summary['limitations']=summary['limitations']+['Incomplete public event coverage; dividends and rights require separate account review']
        return summary
    except ValueError as error:
        if str(error) in (ERROR,'BOUNDED_UNIT_CHANGE_CANDIDATE','BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):raise
        raise ValueError(ERROR) from error
    except Exception as error:raise ValueError(ERROR) from error


def _identity(snapshot):
    def convert(value):
        if isinstance(value,bytes):return {'byte_sha256':sha256(value).hexdigest()}
        if isinstance(value,dict):return {k:convert(v) for k,v in value.items()}
        if isinstance(value,list):return [convert(v) for v in value]
        return value
    return sha256(canonical(convert(snapshot))).hexdigest()


class MonthlyBoundedUnitReview:
    policy=POLICY
    def __init__(self,*,account_review_reader,origin_reader=None,fetch=fetch_official_feed,clock=None):
        self.account_review_reader=account_review_reader;self.origin_reader=origin_reader
        self.fetch=fetch;self.clock=clock or (lambda:datetime.now(timezone.utc))
        self._lock=RLock();self._saved=None

    def capture(self,snapshot):
        with self._lock:
            self._saved=None
            result,account=self._capture(snapshot)
            self._saved=(_identity(snapshot),deepcopy(result),deepcopy(account))
            return deepcopy(result)

    def read(self,snapshot):
        with self._lock:
            require(self._saved is not None and self._saved[0]==_identity(snapshot),ERROR)
            result=deepcopy(self._saved[1]);account=deepcopy(self._saved[2])
        if callable(getattr(self.account_review_reader,'capture',None)):
            require(callable(getattr(self.account_review_reader,'read',None)),ERROR)
            require(self.account_review_reader.read(snapshot,frozen_package=account)==account,ERROR)
        self._validate(snapshot,result,stamp(self.clock()))
        return result

    __call__=read

    def _capture(self,s):
        from data.current_quantity_v2_monthly_retarget import active_proposal
        ledger=s['state']['ledger'];decision=s['capital_decision'];old=active_proposal(ledger)
        securities=s['identities']['securities'];current=s['current_receipts']
        files={};pins={}
        def merge(fs,ps):
            require(set(fs)==set(ps),ERROR)
            for p,v in fs.items():
                require(type(v)is bytes and sha256(v).hexdigest()==ps[p] and (p not in files or files[p]==v),ERROR)
                files[p]=v;pins[p]=ps[p]
        merge(s['base_files'],s['base_source_hashes'])
        merge(s['quote_files'],{p:sha256(v).hexdigest() for p,v in s['quote_files'].items()})
        if self.origin_reader:
            extra=self.origin_reader(s);merge(extra['files'],extra.get('source_hashes',extra.get('pins')))
        if callable(getattr(self.account_review_reader,'capture',None)):
            require(callable(getattr(self.account_review_reader,'read',None)),ERROR)
            account=self.account_review_reader.capture(s)
        else:account=self.account_review_reader(s)
        merge(account['files'],account.get('source_hashes',account.get('pins')))
        accountpath=account.get('account_review_path') or account['documents']['account_review']
        require(accountpath in files,ERROR)
        output={p:files[p] for p in account['files']}
        units={};held={};rss={}
        received=stamp(self.clock())
        shared=account.get('shared_rss')
        if shared is not None and shared.get('raw_path') is not None:
            rp=shared['raw_path'];cp=shared['receipt_path']
            require(rp in account['files'] and cp in account['files'],ERROR)
            receipt=json.loads(files[cp]);received=stamp(receipt['received_at'])
            require(received<=stamp(self.clock()) and all(stamp(ref['captured_at'])<=received for ref in current.values()),ERROR)
            rss={rp:files[rp],cp:files[cp]};output.update(rss)
            prefix='monthly-bounded/'+sha256(files[rp]+received.isoformat().encode()).hexdigest()+'/'
        elif current:
            started=received;response=self.fetch();received=stamp(self.clock());raw=response['body']
            require(response['status']==200 and type(raw)is bytes and 0<len(raw)<=MAX_BYTES,ERROR)
            prefix='monthly-bounded/'+sha256(raw+received.isoformat().encode()).hexdigest()+'/'
            rp=prefix+'rss.xml';cp=prefix+'receipt.json'
            rss={rp:raw,cp:canonical(dict(url=URL,http_status=200,started_at=started.isoformat(),received_at=received.isoformat(),raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw)))}
            merge(rss,{p:sha256(v).hexdigest() for p,v in rss.items()});output.update(rss)
        else:prefix='monthly-bounded/'+_identity(s)+'/'
        for sid,ref in current.items():
            sec=dict(securities[sid],security_id=sid);q=decision['binding']['valuation_quotes'][sid]
            def evidence(kind,paths,**extra):
                subset={p:files[p] for p in set(paths)|set(ref['source_hashes'])|set(rss)}
                return dict(policy=POLICY,kind=kind,security=sec,rss_raw_path=rp,rss_receipt_path=cp,
                    files={p:base64.b64encode(v).decode() for p,v in subset.items()},source_hashes={p:pins[p] for p in subset},**extra)
            candidates=[]
            for p in q['source_references']:
                try:
                    if _json(files[p])['chart']['result'][0]['meta']['symbol']==sec['ticker']:candidates.append(p)
                except (KeyError,ValueError,TypeError,IndexError):pass
            require(len(candidates)==1,ERROR)
            u=dict(security_id=sid,ticker=sec['ticker'],price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                capital_decision_id=decision['decision_id'],status=STATUS,reference_source_hashes=ref['source_hashes'],
                valuation_source_references=q['source_references'],source_references=list(rss),
                covered_from_date=decision['decision_date'],covered_through=ref['captured_at'],reviewed_at=received.isoformat(),
                bounded_evidence=evidence('VALUATION',q['source_references'],valuation_quote=q,decision_date=decision['decision_date'],daily_raw_path=candidates[0]))
            units[sid]=u
            if ledger['shares'].get(sid,0):
                prior=(next(row for row in old['rows'] if row['security_id']==sid) if old.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION' else old['causal_inputs']['execution_references'][sid])
                origin={k:prior[k] for k in ('captured_at','source_hashes')}
                oldsecs=old.get('securities',old['causal_inputs'].get('securities'))
                held[sid]=dict(prior_revision=ledger['revision'],security_id=sid,prior_reference_source_hashes=prior['source_hashes'],
                    reference_source_hashes=ref['source_hashes'],prior_active_proposal_id=old['proposal_id'],
                    prior_price_basis='PROVIDER_CURRENT_REGULAR_NOMINAL_QUOTE' if old.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION' else prior['price_basis'],
                    price_basis=u['price_basis'],security_class=oldsecs[sid].get('security_class'),covered_from=prior['captured_at'],
                    covered_through=ref['captured_at'],reviewed_at=received.isoformat(),status=STATUS,source_references=list(rss),
                    bounded_evidence=evidence('HELD',set(prior['source_hashes'])|set(q['source_references']),origin=origin,daily_raw_path=candidates[0],valuation_quote=q,decision_date=decision['decision_date']))
        documents={'account_review':accountpath}
        for key,value in [('unit_continuity',units),('held_unit_continuity',held)]:
            path=prefix+key+'.json';output[path]=canonical(value);documents[key]=path
        # Include origin bytes if supplied separately, for the outer package closure.
        for values in (units,held):
            for unit in values.values():
                for p in unit['bounded_evidence']['source_hashes']:output[p]=files[p]
        result=dict(files=output,source_hashes={p:sha256(v).hexdigest() for p,v in output.items()},documents=documents)
        self._validate(s,result,stamp(self.clock()))
        return result,account

    def _validate(self,s,result,now):
        pins={**s['base_source_hashes'],**result['source_hashes'],**{p:sha256(v).hexdigest() for p,v in s['quote_files'].items()}}
        for key in ('unit_continuity','held_unit_continuity'):
            for sid,unit in json.loads(result['files'][result['documents'][key]]).items():
                replay_monthly_review(unit,security=s['identities']['securities'][sid],current=s['current_receipts'][sid],
                    source_hashes=pins,now=now,capital_decision=s['capital_decision'] if key=='unit_continuity' else None,
                    origin=unit['bounded_evidence'].get('origin'),held_capital_decision=s['capital_decision'] if key=='held_unit_continuity' else None)


BoundedMonthlyUnitReview=MonthlyBoundedUnitReview
