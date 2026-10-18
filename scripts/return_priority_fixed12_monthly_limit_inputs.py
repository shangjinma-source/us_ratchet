"""Prepare continuous whole-source monthly replay inputs; no book or search."""
import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
CONTRACT='research_contracts/fixed12_monthly_limit_execution_20261014_v1.json'
TRAINING='tmp/fixed12_training_prepare_20261014_v6/prepared.json'
COMPARISON='tmp/fixed12_comparison_20261014_v1/prepared.json'
MODE_MAP={'QUANTITY':'QUANTITY_FROZEN_WEIGHT_REPLAY','TOP1_SAME_PROJECTION':'TOP1_SAME_PROJECTION_FROZEN_WEIGHT_REPLAY','QQQ':'QQQ_FULL_WEIGHT'}
FIELDS=('open','high','low','close')


def prepare():
    pins={}
    def read(name,expected=None):
        raw=(ROOT/name).read_bytes();h=hashlib.sha256(raw).hexdigest()
        if expected and h!=expected:raise ValueError('Source changed: '+name)
        pins[name]=h
        return raw
    def document(name,expected=None):
        p=json.loads(read(name,expected))
        for path,h in p.get('source_hashes',{}).items():read(path,h)
        return p
    contract=document(CONTRACT)
    training=document(TRAINING,'226210854041216e8ace37fb52395809d6cff64e45e2f125197da9e2f7047606')
    reg=document('tmp/fixed12_comparison_20261014_v1/registration.json','35e67af034339025214be72b06449b96190a3133a1f29197395d3686cbfb23af')
    comparison=document(COMPARISON,reg['prepared_sha256'])
    sources={}

    def source(path,ticker):
        if path in sources:return sources[path]
        raw=read(path)
        if path.endswith('.csv'):
            rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
            data={r['Date']:{k:r[k.title()] for k in FIELDS} for r in rows}
            if len(data)!=len(rows):raise ValueError('Duplicate archive dates')
            events=[]
        elif path.endswith('.response.bin'):
            receipt=json.loads(read(path.replace('.response.bin','.receipt.json')))
            if hashlib.sha256(raw).hexdigest()!=receipt['raw_sha256']:raise ValueError('Receipt mismatch')
            decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            if receipt.get('decoded_sha256') and hashlib.sha256(decoded).hexdigest()!=receipt['decoded_sha256']:raise ValueError('Decoded mismatch')
            p=json.loads(decoded)['chart']['result'][0]
            if p['meta']['symbol']!=ticker or p['meta']['currency']!='USD':raise ValueError('Wrong source identity')
            zone=ZoneInfo(p['meta']['exchangeTimezoneName'])
            date=lambda t:datetime.fromtimestamp(t,zone).date().isoformat()
            days=[date(t) for t in p['timestamp']];q=p['indicators']['quote'][0]
            if len(set(days))!=len(days) or any(len(q[k])!=len(days) for k in FIELDS):raise ValueError('Malformed source timeline')
            data={d:{k:str(q[k][i]) for k in FIELDS if q[k][i] is not None} for i,d in enumerate(days)}
            events=[dict(event_date=date(e['date']),factor=str(Fraction(str(e['numerator']))/Fraction(str(e['denominator']))),provider_event=e) for e in p.get('events',{}).get('splits',{}).values()]
        else:raise ValueError('Whole source unsupported')
        sources[path]=(data,events)
        return data,events

    qqq_path='data/cache/research/current_raw_capture_20261013_v1/QQQ.response.bin'
    qqq,qqq_events=source(qqq_path,'QQQ')
    if qqq_events:raise ValueError('QQQ coordinate action requires review')
    calendar=sorted(d for d in qqq if contract['start_close']<=d<=contract['end_close'])
    if calendar[0]!=contract['start_close'] or calendar[-1]!=contract['end_close'] or not set(contract['decision_dates'])<=set(calendar):raise ValueError('Calendar boundary differs')
    training_by_date={w['decision_cutoff']:w for w in training['windows']}
    modes=[]
    for old_mode,mode in MODE_MAP.items():
        books=sorted((b for b in comparison['books'] if b['mode']==old_mode),key=lambda b:b['decision_cutoff'])
        if [b['decision_cutoff'] for b in books]!=contract['decision_dates']:raise ValueError('Monthly decision schedule differs')
        decisions=[];first={};metadata={}
        for book in books:
            d=book['decision_cutoff'];weights=book['outcome_arguments']['target_weights']
            if sum(Fraction(v) for v in weights.values())>1:raise ValueError('Frozen weights exceed one')
            decisions.append(dict(decision_date=d,target_weights=weights,source_book_id=book['book_id'],
                information_cutoff=d,weight_policy='FROZEN_WEIGHTS_REPLAY_ON_EVOLVED_INVESTABLE_EQUITY_NO_NEW_SEARCH'))
            for sid in weights:
                if Fraction(weights[sid])<=0:raise ValueError('Nonpositive selected weight')
                first.setdefault(sid,d);meta=book['outcome_arguments']['metadata'][sid]
                if sid in metadata and meta!=metadata[sid]:raise ValueError('SID metadata conflict')
                metadata[sid]=meta
        prices={};actions=[];provenance={};gaps=[];not_exposed_actions=[]
        for sid,start in first.items():
            ticker=metadata[sid]['ticker']
            if ticker=='QQQ':
                path=qqq_path;factor=Fraction(1);reviewed=[];baseline=None
            else:
                baseline=next(r for r in training_by_date[start]['candidates'] if r['security_id']==sid)
                path=baseline['training_source'];factor=Fraction(baseline['decision_cost_factor'])
                reviewed=[r['event'] for r in baseline.get('cost_restoration_evidence',[]) if r['event']['event_date']>start]
                matching=[r for w in training['windows'] for r in w['candidates'] if r['security_id']==sid]
                if any(r['training_source']!=path for r in matching):raise ValueError('Continuous SID must use one whole source')
            raw_rows,events=source(path,ticker)
            if not path.endswith('.csv'):
                if {(e['event_date'],Fraction(e['factor'])) for e in events if e['event_date']>start}!={(e['event_date'],Fraction(e['factor'])) for e in reviewed}:raise ValueError('Unreviewed subsequent coordinate event')
            if baseline and Fraction(raw_rows[start]['close'])*factor!=Fraction(baseline['decision_cost']):raise ValueError('First decision nominal bridge differs')
            required=[d for d in calendar if d>=start];prices[sid]={}
            for d in required:
                multiplier=factor
                for event in reviewed:
                    if event['event_date']<=d:multiplier/=Fraction(event['factor'])
                r=raw_rows.get(d,{})
                values={k:str(Fraction(r[k])*multiplier) for k in FIELDS if k in r}
                valid=len(values)==4 and all(Fraction(v)>0 for v in values.values())
                if valid:
                    op,hi,lo,cl=(Fraction(values[k]) for k in FIELDS)
                    valid=lo<=min(op,cl)<=max(op,cl)<=hi
                if not valid:gaps.append(dict(security_id=sid,ticker=ticker,date=d,reason='MISSING_OR_INVALID_WHOLE_SOURCE_OHLC'))
                prices[sid][d]=values
            for e in reviewed:
                if start<e['event_date']<=calendar[-1]:
                    f=Fraction(e['factor'])
                    actions.append(dict(type='split',date=e['event_date'],security_id=sid,new_shares=f.numerator,old_shares=f.denominator,source_references=[path,TRAINING]))
            not_exposed_actions.extend(dict(ticker=ticker,security_id=sid,event=e,reason='ON_OR_BEFORE_FIRST_SELECTION_NO_INITIAL_HOLDINGS') for e in events if calendar[0]<e['event_date']<=start)
            provenance[sid]=dict(ticker=ticker,whole_source=path,required_from=start,required_to=calendar[-1],row_count=len(required),
                decision_factor=str(factor),reviewed_coordinate_events=reviewed,price_basis='CONDITIONAL_HISTORICAL_NOMINAL_UNIT_COORDINATE_NOT_CERTIFIED',
                identity_evidence=baseline['identity_evidence'] if baseline else None,identity_bridge=baseline.get('identity_bridge') if baseline else None)
        modes.append(dict(mode=mode,monthly_decisions=decisions,metadata=metadata,ohlc=prices,actions=actions,
            initial_cash=contract['initial_cash'],initial_shares={},fee_bps='0',price_gaps=gaps,
            status='BLOCKED_SOURCE' if gaps else 'READY_CONDITIONAL',source_provenance=provenance,
            unexposed_observed_actions=not_exposed_actions,unpaid_rights_in_target_sizing=False))
    read('backtest/return_priority_limit_book.py')
    read(__file__)
    for name,h in list(pins.items()):read(name,h)
    return dict(status='PREPARED_CONTINUOUS_INPUTS_NO_EXECUTION',session_dates=calendar,modes=modes,
        contract=contract,source_hashes=pins,search_calls=0,book_calls=0,
        independent_oos=False,point_in_time_certified=False,whole_source_not_concatenated_books=True,
        selected_names_removed_for_future_price_gaps=False,
        limitations=['Each selected SID remains covered from first selection close through final close, including every possible unsold residual session.',
            'No initial shares: unselected pre-first-selection price history is neither fabricated nor needed.',
            'No ANSS exposure in either frozen stock mode; mixed-merger execution is not claimed tested.',
            'SMCI first selected 2024-10-31 under post-split SID; no old-SID residual exists to migrate.',
            'Retrospective fixed weights are replayed on evolved capital; integer search is not rerun.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    path=args.output.resolve()
    if path.exists() or (ROOT/'tmp').resolve() not in path.parents:raise ValueError('Create-only tmp output required')
    result=prepare();path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    draft=dict(status='DRAFT_NOT_EXECUTABLE_PROVIDER_AND_RUNNER_PINS_PENDING',input_path=str(path),input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        maximum_book_calls=3,maximum_search_calls=0,modes=[m['mode'] for m in result['modes']],
        initial_cash_per_independent_mode='20000',monthly_cash_reset=False,create_only=True,automatic_retry_allowed=False,
        source_hashes=result['source_hashes'])
    with (path.parent/'registration_draft.json').open('x',encoding='utf-8') as f:json.dump(draft,f,indent=2)
    print(json.dumps(dict(input_sha256=draft['input_sha256'],sessions=len(result['session_dates']),modes=[dict(mode=m['mode'],securities=len(m['metadata']),gaps=len(m['price_gaps']),actions=len(m['actions'])) for m in result['modes']])))
