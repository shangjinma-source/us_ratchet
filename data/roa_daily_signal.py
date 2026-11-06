"""Recoverable daily market-state updates for the frozen November roster only."""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
from hashlib import sha256
import json
import gzip
from pathlib import Path
from threading import RLock
from urllib.request import Request, urlopen
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from data.roa_session_reader import CALENDAR, SHA, RoaSessionReader
from data.roa_current_signal import load_current_signal
from data.roa_monthly_loader import RoaMonthlySelectionLoader

SEED='tmp/roa_current_qqq_raw_20261106/QQQ.response.bin'
SEED_SHA='1edaa989155fc293d500965d986ffbbc1a1ee6bed3aae5f952b6c1e6577703e0'
NY=ZoneInfo('America/New_York')


def fetch_daily_qqq():
    url='https://query1.finance.yahoo.com/v8/finance/chart/QQQ?interval=1d&range=1mo'
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=10) as response:
        raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('DAILY_RESPONSE_TOO_LARGE')
    return raw


def daily_rows(raw, ticker='QQQ'):
    if isinstance(raw,bytes) and raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
    data=json.loads(raw);chart=data['chart']
    if chart.get('error') or len(chart['result'])!=1:raise ValueError('DAILY_RESULT_INVALID')
    result=chart['result'][0];meta=result['meta']
    if meta['symbol']!=ticker or meta['currency']!='USD' or meta['exchangeTimezoneName']!='America/New_York':
        raise ValueError('DAILY_IDENTITY_INVALID')
    if meta.get('dataGranularity')!='1d':raise ValueError('DAILY_GRANULARITY_INVALID')
    quotes=result['indicators']['quote']
    if len(quotes)!=1:raise ValueError('DAILY_QUOTES_AMBIGUOUS')
    q=quotes[0];ts=result['timestamp']
    if ts!=sorted(set(ts)) or any(len(q[k])!=len(ts) for k in ('open','high','low','close','volume')):
        raise ValueError('DAILY_ARRAY_INVALID')
    rows={}
    for i,t in enumerate(ts):
        day=datetime.fromtimestamp(t,NY).date().isoformat()
        if day in rows:raise ValueError('DAILY_DUPLICATE_SESSION')
        values=[q[k][i] for k in ('open','high','low','close','volume')]
        if any(v is None or isinstance(v,bool) for v in values):raise ValueError('DAILY_NULL_BAR')
        o,h,l,c,v=map(lambda x:F(str(x)),values)
        if not (0<l<=o<=h and l<=c<=h and v>0):raise ValueError('DAILY_INVALID_OHLC')
        rows[day]=str(c)
    return rows


def fetch_daily_stock(ticker):
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker,safe='')+'?interval=1d&range=5d&events=div,splits,capitalGains'
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=10) as response:
        raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('DAILY_RESPONSE_TOO_LARGE')
    return raw


def load_completed_close_prices(*, identity_map, session, now, session_reader, evidence_dir,
                                fetch=fetch_daily_stock):
    """Actual held SID map only. Returns marks and source receipts, not fills.

    Recent split/identity actions require separate corporate-action admission;
    this loader never silently re-denominates the user's actual share quantity.
    """
    if now.tzinfo is None:raise ValueError('AWARE_CLOCK_REQUIRED')
    if now<datetime.fromisoformat(session_reader(session)['close_at']):
        raise ValueError('WAIT_COMPLETED_SESSION')
    if len(identity_map)>20:raise ValueError('CLOSE_IDENTITY_DOMAIN_INVALID')
    if not identity_map:return dict(prices={},evidence={})
    def capture(item):
        sid,identity=item;ticker=identity['ticker'];raw=fetch(ticker)
        rows=daily_rows(raw,ticker)
        if session not in rows:raise ValueError('WAIT_MISSING_COMPLETED_CLOSE')
        decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
        result=json.loads(decoded)['chart']['result'][0]
        for event in result.get('events',{}).get('splits',{}).values():
            day=datetime.fromtimestamp(event['date'],NY).date().isoformat()
            if day>=session:raise ValueError('WAIT_CORPORATE_ACTION_CLOSE_ADMISSION')
        return sid,rows[session],raw
    with ThreadPoolExecutor(max_workers=4) as executor:
        captures=list(executor.map(capture,identity_map.items()))
    directory=Path(evidence_dir);directory.mkdir(parents=True,exist_ok=True)
    prices,evidence={},{}
    for sid,value,raw in captures:
        digest=sha256(raw).hexdigest();path=directory/(digest+'.response')
        if path.exists() and path.read_bytes()!=raw:raise ValueError('CLOSE_SOURCE_CONFLICT')
        path.write_bytes(raw);prices[sid]=value
        evidence[sid]=dict(ticker=identity_map[sid]['ticker'],session=session,raw_path=str(path.resolve()),
                           raw_sha256=digest,requested_at=now.isoformat(),price_basis='current')
    return dict(prices=prices,evidence=evidence)


def states(prices):
    dates=sorted(prices);state=False;previous=None;result={}
    for i,day in enumerate(dates):
        if i<199:continue
        above=F(prices[day])>sum(F(prices[d]) for d in dates[i-199:i+1])/200
        if previous is not None:
            if above==previous:state=above
            result[day]=state
        previous=above
    return result


class RoaDailySignalProvider:
    def __init__(self,*,root,path,expected_contract_hashes,clock=lambda:datetime.now(timezone.utc),fetch=fetch_daily_qqq,monthly_selections=None,base_input_root=None):
        self.root=Path(root).resolve();self.path=Path(path);self.contracts=expected_contract_hashes
        self.base_root=(self.root/base_input_root).resolve() if base_input_root is not None else self.root
        if not self.base_root.is_relative_to(self.root):raise ValueError('BASE_INPUT_ROOT_OUTSIDE_WORKSPACE')
        if not expected_contract_hashes:raise ValueError('APPROVED_CONTRACTS_REQUIRED')
        self.clock=clock;self.fetch=fetch;self.lock=RLock();self.calendar=RoaSessionReader(root)
        self.months=RoaMonthlySelectionLoader(root=self.root,registry=monthly_selections or {})

    def _base(self):
        return load_current_signal(as_of_date='2026-11-06',root=self.base_root,expected_contract_hashes=self.contracts)

    def frozen_roster(self):
        """Verified identity lookup, independent of today's signal readiness.

        This does not authorize continued selection after November.
        """
        session=self._execution_session(self.clock())
        if session[:7] in self.months.registry:return deepcopy(self.months(session)['securities'])
        return deepcopy(self._base()['securities'])

    def _execution_session(self,now):
        if now.tzinfo is None:raise ValueError('AWARE_CLOCK_REQUIRED')
        session=next((d for d in self._sessions() if datetime.fromisoformat(self.calendar(d)['close_at'])>now),None)
        if session is None:raise ValueError('WAIT_VERIFIED_CALENDAR')
        return session

    def _sessions(self):
        raw=(self.root/CALENDAR).read_bytes()
        if sha256(raw).hexdigest()!=SHA:raise ValueError('CALENDAR_SOURCE_CHANGED')
        return [r['date'] for r in json.loads(raw)['sessions']]

    def _read(self):
        raw=(self.base_root/SEED).read_bytes()
        if sha256(raw).hexdigest()!=SEED_SHA:raise ValueError('QQQ_SEED_CHANGED')
        prices=daily_rows(raw)
        if max(prices)!='2026-11-05':raise ValueError('QQQ_SEED_DATE')
        records=[]
        if self.path.exists():
            document=json.loads(self.path.read_text(encoding='utf8'))
            if document['base_signal_id']!=self._base()['signal_id']:raise ValueError('DAILY_BASE_CHANGED')
            for record in document['updates']:
                evidence=Path(record['raw_path'])
                if evidence.parent.resolve()!=self.path.parent.resolve():raise ValueError('DAILY_PATH_INVALID')
                payload=evidence.read_bytes()
                if sha256(payload).hexdigest()!=record['raw_sha256']:raise ValueError('DAILY_SOURCE_CHANGED')
                rows=daily_rows(payload);day=record['session']
                expected=next((d for d in self._sessions() if d>max(prices)),None)
                if day!=expected or rows[day]!=record['close']:raise ValueError('DAILY_CHAIN_INVALID')
                captured=datetime.fromisoformat(record['captured_at'])
                if captured.tzinfo is None or not datetime.fromisoformat(self.calendar(day)['close_at'])<=captured<=self.clock():
                    raise ValueError('DAILY_CAPTURE_BEFORE_CLOSE_OR_FUTURE')
                prices[day]=record['close'];records.append(record)
        return prices,records

    def refresh_completed(self):
        """Trusted backend call; only completed sequential calendar days admitted."""
        with self.lock:
            base=self._base();prices,records=self._read();now=self.clock()
            if now.tzinfo is None:raise ValueError('AWARE_CLOCK_REQUIRED')
            available=[d for d in self._sessions() if d>max(prices) and datetime.fromisoformat(self.calendar(d)['close_at'])<=now]
            if not available:return dict(status='WAIT_COMPLETED_SESSION',updated=[])
            payload=self.fetch();captured=self.clock();rows=daily_rows(payload)
            if captured.tzinfo is None or captured<now:raise ValueError('DAILY_CAPTURE_CLOCK_INVALID')
            for d,c in prices.items():
                if d in rows and F(rows[d])!=F(c):raise ValueError('QQQ_HISTORY_COORDINATE_CHANGED')
            additions=[]
            for day in available:
                if day not in rows:raise ValueError('WAIT_MISSING_COMPLETED_QQQ_SESSION:'+day)
                additions.append(dict(session=day,close=rows[day]))
            digest=sha256(payload).hexdigest();self.path.parent.mkdir(parents=True,exist_ok=True)
            evidence=self.path.parent/('qqq_daily_'+digest+'.json')
            if evidence.exists() and evidence.read_bytes()!=payload:raise ValueError('DAILY_EVIDENCE_CONFLICT')
            evidence.write_bytes(payload)
            for row in additions:row.update(raw_path=str(evidence.resolve()),raw_sha256=digest,captured_at=captured.isoformat())
            document=dict(schema='ROA_DAILY_SIGNAL_V1',base_signal_id=base['signal_id'],updates=records+additions)
            temporary=self.path.with_suffix(self.path.suffix+'.tmp')
            temporary.write_text(json.dumps(document,indent=2),encoding='utf8');temporary.replace(self.path)
            return dict(status='UPDATED',updated=[r['session'] for r in additions])

    def __call__(self):
        with self.lock:
            now=self.clock()
            session=self._execution_session(now)
            month=None
            if session[:7] in self.months.registry:month=self.months(session)
            elif session[:7]!='2026-11':raise ValueError('WAIT_NEW_MONTH_SIGNAL')
            self.calendar(session)
            base=self._base();prices,records=self._read();dates=self._sessions()
            previous=max(d for d in dates if d<session)
            if max(prices)!=previous:raise ValueError('WAIT_DAILY_MARKET_SIGNAL')
            result=deepcopy(base);result.update(signal_date=previous,risk_on=states(prices)[previous],
                execution_not_before_session=session,quote_inputs_asof=previous)
            if month is not None:
                result.update(decision_date=month['decision_date'],weights=deepcopy(month['weights']),
                    securities=deepcopy(month['securities']),financial_cutoff=month['financial_cutoff'],monthly_selection_id=month['selection_id'])
                result['source_hashes'].update(month['source_hashes'])
                spec=self.months.registry[session[:7]];result['source_hashes'][spec['path']]=spec['sha256']
            result['daily_updates']=records
            identity=dict(base=base['signal_id'],session=session,updates=records)
            if month is not None:identity['monthly_selection_id']=month['selection_id']
            result['signal_id']=sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            return result
