"""Initial BUY paper acceptance and exact replay; no store or broker integration."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import PurePosixPath
import base64
import json
import re
from data.current_research_intraday_buy_plan import build_intraday_initial_buy_proposal, _require, _time, _cash
from data.current_research_intraday_review import review_intraday_session
from data.current_research_intraday_journal import IntradayObservationJournal


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class _MemoryPath:
    """Minimal read-only path facade for the existing journal reviewer."""
    def __init__(self, files, path=''):self.files=files;self.path=PurePosixPath(path)
    def __truediv__(self, part):return _MemoryPath(self.files,str(self.path/part))
    def __lt__(self, other):return str(self.path)<str(other.path)
    def resolve(self):return self
    def is_relative_to(self, other):return self.path.is_relative_to(other.path)
    def relative_to(self, other):return self.path.relative_to(other.path)
    def as_posix(self):return self.path.as_posix()
    @property
    def stem(self):return self.path.stem
    def glob(self, pattern):return [self/f.name for p in self.files if (f:=PurePosixPath(p)).parent==self.path and f.match(pattern)]
    def read_bytes(self):return base64.b64decode(self.files[self.as_posix()],validate=True)


def _frozen_builder(files, **arguments):
    class Journal:
        def __init__(self, root):self.root=_MemoryPath(files)
        def read_event(self,path,expected_sha256=None):
            raw=(self.root/path).read_bytes()
            _require(expected_sha256 is None or sha256(raw).hexdigest()==expected_sha256,'EVENT_HASH_MISMATCH')
            event=json.loads(raw)
            for capture in event['captures']:
                _require(capture['path']=='raw/'+capture['sha256']+'.bin','RAW_PATH_INVALID')
                _require(sha256((self.root/capture['path']).read_bytes()).hexdigest()==capture['sha256'],'RAW_HASH_MISMATCH')
            return event
    return build_intraday_initial_buy_proposal(journal_root='',journal=Journal(''),**arguments)


def _capture(root, arguments):
    journal=IntradayObservationJournal(root); files={}
    folder=journal.root/'events'/arguments['session']
    for path in sorted(folder.glob('*.json')):
        relative=path.relative_to(journal.root).as_posix()
        raw=path.read_bytes(); event=journal.read_event(relative,expected_sha256=sha256(raw).hexdigest())
        files[relative]=base64.b64encode(raw).decode()
        for item in event['captures']:
            files[item['path']]=base64.b64encode((journal.root/item['path']).read_bytes()).decode()
    return files


def accept_intraday_proposal(proposal, *, journal_root, current_inputs, now):
    """Caller supplies current server account/research/calendar, never browser state.

    Returns an isolated paper state. No existing account is created or modified.
    """
    now=_time(now); causal=proposal['causal_inputs']
    arguments=deepcopy(current_inputs)
    _require(not {'journal_root','now','journal'} & set(arguments),'SERVER_INPUT_SCHEMA')
    files=_capture(journal_root,arguments)
    original_files={p:b for p,b in files.items() if p.startswith('raw/') or p in causal['reviewed_event_hashes']}
    original=deepcopy(arguments)
    original.update(research_snapshot=causal['research_snapshot'],available_cash=causal['available_cash'],shares=causal['shares'],reserved_cash=causal['reserved_cash'],open_orders=causal['open_orders'],account_id=causal['account_id'],account_revision=causal['account_revision'],expected_revision=causal['expected_revision'],market_session=causal['market_session'],source_hashes=causal['source_hashes'],session=causal['session'],event_path=causal['event_path'],expected_event_hashes=causal['reviewed_event_hashes'])
    rebuilt=_frozen_builder(original_files,**original,now=causal['proposal_created_at'])
    _require(rebuilt==proposal,'PROPOSAL_RECONSTRUCTION_MISMATCH')
    _require(now>=_time(proposal['proposal_created_at']),'ACCEPTANCE_BEFORE_PROPOSAL')
    current=_frozen_builder(files,**arguments,now=now)
    _require(current['status']=='READY','CURRENT_REFERENCE_NOT_READY:'+str(current.get('reason')))
    for field in ('research_snapshot','available_cash','shares','reserved_cash','open_orders','account_id','account_revision','expected_revision','market_session','source_hashes','event_path','event_sha256'):
        _require(current['causal_inputs'][field]==causal[field],'CURRENT_BINDING_CHANGED:'+field)
    _require(current['quantity']>0,'NO_BUY_QUANTITY')
    evidence=dict(proposal=deepcopy(proposal),original_inputs=original,current_inputs=arguments,
                  original_files=original_files,files=files,accepted_at=now.isoformat())
    return _initial(evidence)


def _initial(evidence):
    original=_frozen_builder(evidence['original_files'],**evidence['original_inputs'],now=evidence['proposal']['proposal_created_at'])
    _require(original==evidence['proposal'],'FROZEN_PROPOSAL_INVALID')
    current=_frozen_builder(evidence['files'],**evidence['current_inputs'],now=evidence['accepted_at'])
    _require(current['status']=='READY','FROZEN_ACCEPTANCE_INVALID')
    c=current['causal_inputs']; p=evidence['proposal']['causal_inputs']
    _require(_time(evidence['accepted_at'])>=_time(p['proposal_created_at']),'ACCEPTANCE_BEFORE_PROPOSAL')
    for field in ('research_snapshot','available_cash','shares','reserved_cash','open_orders','account_id','account_revision','expected_revision','market_session','source_hashes','event_path','event_sha256'):
        _require(c[field]==p[field],'FROZEN_BINDING_CHANGED')
    quantity=current['quantity'];_require(type(quantity) is int and quantity>0,'NO_BUY_QUANTITY')
    order=dict(side='BUY',security_id=current['security']['security_id'],quantity=quantity,limit=current['limit_price'],accepted_at=evidence['accepted_at'],session_close=c['market_session']['close_at'],time_in_force='DAY')
    acceptance_id=_hash(evidence);order['order_id']=acceptance_id+':BUY'
    return dict(schema='INTRADAY_INITIAL_BUY_PAPER_LEDGER_V1',research_only=True,execution_blocked=True,real_account=False,source_authenticated=False,account_id=c['account_id'],acceptance=deepcopy(evidence),acceptance_id=acceptance_id,order=order,cash=c['available_cash'],shares={},filled_quantity=0,reserved_cash=str(quantity*Fraction(order['limit'])),fees='0',closed=None,events=[],revision=_hash(dict(acceptance_id=acceptance_id,account_id=c['account_id'])),limitations=['Manual execution times are declarations, not proof of broker fills.','Reference refresh never cancels this accepted DAY order.','Closed orders reject even late-recorded fills; this does not prove no real execution occurred.','Only initial BUY is supported; no SELL, successor plan or company-action accounting.'])


def _apply(state,event):
    common={'event_id','kind','expected_revision','order_id','recorded_at'}
    kind=event.get('kind'); extra={'quantity','price','fees','executed_at'} if kind=='FILL' else {'cancelled_at'} if kind=='CANCEL' else set()
    _require(kind in ('FILL','CANCEL','EXPIRE') and set(event)==common|extra,'EVENT_SCHEMA')
    _require(isinstance(event['event_id'],str) and bool(event['event_id'].strip()),'EVENT_ID_REQUIRED')
    for old in state['events']:
        if old['event_id']==event['event_id']:
            _require(old==event,'CONFLICTING_EVENT_ID');return deepcopy(state)
    _require(event['expected_revision']==state['revision'] and event['order_id']==state['order']['order_id'],'STALE_OR_WRONG_ORDER')
    _require(state['closed'] is None and state['filled_quantity']<state['order']['quantity'],'ORDER_CLOSED_OR_FILLED')
    order=state['order']; recorded=_time(event['recorded_at']); accepted=_time(order['accepted_at']); close=_time(order['session_close'])
    _require(recorded>=accepted,'RECORDED_BEFORE_ACCEPTANCE')
    if state['events']:_require(recorded>=_time(state['events'][-1]['recorded_at']),'RECORDING_TIME_REGRESSED')
    result=deepcopy(state)
    if kind=='FILL':
        executed=_time(event['executed_at']);_require(accepted<=executed<close and executed<=recorded,'EXECUTION_TIME_INVALID')
        q=event['quantity'];_require(type(q) is int and 0<q<=order['quantity']-state['filled_quantity'],'OVERFILL_OR_INVALID_QUANTITY')
        price=_cash(event['price']);fees=_cash(event['fees']);_require(0<price<=Fraction(order['limit']),'PRICE_VIOLATES_LIMIT')
        cash=Fraction(state['cash'])-q*price-fees;remaining=order['quantity']-state['filled_quantity']-q
        reserve=remaining*Fraction(order['limit']);_require(cash>=reserve,'CASH_OR_REMAINING_RESERVATION_INVADED')
        result.update(cash=str(cash),reserved_cash=str(reserve),filled_quantity=state['filled_quantity']+q,fees=str(Fraction(state['fees'])+fees))
        result['shares'][order['security_id']]=result['filled_quantity']
    else:
        if kind=='CANCEL':
            cancelled=_time(event['cancelled_at']);_require(accepted<=cancelled<=recorded,'CANCEL_TIME_INVALID')
            prior=[_time(e['executed_at']) for e in state['events'] if e['kind']=='FILL']
            _require(not prior or cancelled>=max(prior),'CANCEL_BEFORE_RECORDED_EXECUTION')
        else:_require(recorded>=close,'SESSION_NOT_CLOSED')
        result.update(closed=kind,reserved_cash='0')
    result['events'].append(deepcopy(event));result['revision']=_hash(dict(previous=state['revision'],event=event))
    return result


def review_intraday_paper_ledger(state):
    rebuilt=_initial(state['acceptance'])
    for event in state['events']:rebuilt=_apply(rebuilt,event)
    _require(rebuilt==state,'PAPER_STATE_REPLAY_MISMATCH')
    return deepcopy(rebuilt)


def apply_intraday_paper_event(state,event,*,now):
    reviewed=review_intraday_paper_ledger(state)
    _require(_time(event['recorded_at'])<=_time(now),'FUTURE_RECORDING')
    return _apply(reviewed,event)
