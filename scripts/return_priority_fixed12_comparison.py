"""Register then value 36 fixed comparisons once; never call quantity search."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.return_priority_top1_baselines import select_top1

OUTPUT=ROOT/'tmp/fixed12_comparison_20261014_v1'
TRAINING='tmp/fixed12_training_prepare_20261014_v6/prepared.json'
TRAINING_SHA='226210854041216e8ace37fb52395809d6cff64e45e2f125197da9e2f7047606'
HOLDING='tmp/fixed12_holding_prepare_20261014_v3/prepared.json'
HOLDING_SHA='0b9cbe607710ba7fcfd0b395ea55e539c7f5d014c74bfe653aa349a352429dc1'
SEARCH='tmp/fixed12_quantity_search_20261014_v1'
ENGINES={'backtest/return_priority_holding_entitlement_outcome.py':'ebc9539009683258650b5c56bf997d682b33dfe25905c35a2414e077ad547415',
 'backtest/return_priority_cash_stock_entitlements.py':'7aece5075df20b76e1a39e8cc0f5cfb14f6987a72968e3b5a853ff1823d4be59',
 'backtest/return_priority_frozen_nominal_outcome.py':'0494a78bdd36b00a6009c9f02e73098104f75c6db57f1e0e6bd805099e68bf70',
 'backtest/return_priority_fresh_cash_quantity_search.py':'756a16a83735279db24332d096aa149b54fc7ff4e91cb807410b3f33f425b588'}
PROTECTED=['data/state.json','data/broker_positions.json','config/config.yaml','api/server.py','web/index.html',
           'web/selected_stock_charts.js','data/current_cash_portfolio_research.py','data/current_quantity_portfolio_research.py']
MODES=('QUANTITY','TOP1_SAME_PROJECTION','QQQ')


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    raw=json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode('utf-8')
    with Path(path).open('xb') as f:f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def guards():return {name:digest(ROOT/name) for name in PROTECTED}


def frozen_weights(arguments,selected):
    """Check frozen search accounting; do not scale or optimize its positions."""
    if selected is None:raise ValueError('No frozen quantity selection')
    cash=Fraction(arguments['entered_cash'])
    if cash!=20000 or Fraction(arguments['fee_bps']) or Fraction(arguments['minimum_cash_buffer']):raise ValueError('Protocol differs')
    quantities=selected['quantities'];weights={}
    for sid,q in quantities.items():
        if isinstance(q,bool) or not isinstance(q,int) or q<=0 or sid not in arguments['prices']:raise ValueError('Invalid selected quantity')
        weights[sid]=str(q*Fraction(arguments['prices'][sid])/cash)
    if set(weights)!=set(selected['actual_weights']) or any(Fraction(weights[s])!=Fraction(selected['actual_weights'][s]) for s in weights):raise ValueError('Frozen weight accounting differs')
    notional=sum((Fraction(v)*cash for v in weights.values()),Fraction(0))
    if notional!=Fraction(selected['notional']) or notional+Fraction(selected['residual_cash'])!=cash or Fraction(selected['fees']):raise ValueError('Frozen budget does not conserve cash')
    if len(weights)!=selected['actual_k']:raise ValueError('Frozen k differs')
    issuers=[arguments['metadata'][s]['issuer_id'] for s in weights]
    if len(set(issuers))!=len(issuers):raise ValueError('Multiple classes per issuer')
    return weights


def construct_books(training,holding,selected):
    args=training['search_arguments'];weights=frozen_weights(args,selected)
    top=select_top1(args)
    topweight=top['modes']['TOP1_SAME_PROJECTION']
    targets={'QUANTITY':weights,'TOP1_SAME_PROJECTION':{top['security_id']:topweight} if Fraction(topweight)>0 else {}}
    books=[]
    for mode in MODES:
        if mode=='QQQ':outcome=deepcopy(holding['qqq_reference']['outcome_arguments'])
        else:
            outcome=deepcopy(holding['outcome_arguments_without_target_weights'])
            outcome['target_weights']=targets[mode]
        if outcome['decision_date']!=training['decision_cutoff'] or outcome['entered_cash']!='20000' or Fraction(outcome['fee_bps']):raise ValueError('Holding protocol differs')
        dates=outcome['session_dates']
        if len(dates)!=22 or dates!=sorted(set(dates)) or dates[0]!=outcome['decision_date'] or dates[-1]!=outcome['end_date']:raise ValueError('Expected decision plus next21 sessions')
        if any(s not in outcome['metadata'] for s in outcome['target_weights']):raise ValueError('Frozen selection missing holding metadata')
        books.append(dict(book_id=training['decision_cutoff']+'_'+mode,decision_cutoff=training['decision_cutoff'],mode=mode,
            outcome_arguments=outcome,frozen_selection=deepcopy(selected) if mode=='QUANTITY' else (top if mode=='TOP1_SAME_PROJECTION' else None),
            price_gaps_retained=holding['price_gaps'] if mode!='QQQ' else holding['qqq_reference']['missing_dates'],
            no_outcome_filtering_or_substitution=True))
    return books


def prepare():
    if OUTPUT.exists():raise ValueError('Create-only output already exists')
    pins={}
    def read(name,expected=None):
        path=ROOT/name;raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest()
        if expected and h!=expected:raise ValueError('Source changed: '+name)
        pins[name]=h
        return json.loads(raw)
    training=read(TRAINING,TRAINING_SHA);holding=read(HOLDING,HOLDING_SHA)
    for payload in (training,holding):
        for name,h in payload['source_hashes'].items():
            if digest(ROOT/name)!=h:raise ValueError('Source closure changed: '+name)
            pins[name]=h
    reg=read(SEARCH+'/registration.json')
    if reg['input_sha256']!=TRAINING_SHA:raise ValueError('Search uses different training')
    result=read(SEARCH+'/result.json');after=read(SEARCH+'/protected_after.json')
    if result['search_calls']!=12 or not after['unchanged']:raise ValueError('Incomplete search or protected change')
    for name,h in ENGINES.items():
        if digest(ROOT/name)!=h:raise ValueError('Reviewed implementation changed: '+name)
        pins[name]=h
    for name in ('scripts/return_priority_top1_baselines.py','scripts/return_priority_fixed12_holding_prepare.py',str(Path(__file__).resolve())):pins[name]=digest(ROOT/name)
    tw=training['windows'];hw={w['decision_cutoff']:w for w in holding['windows']};sw={w['decision_cutoff']:w for w in result['windows']}
    if len(tw)!=12 or len(hw)!=12 or set(hw)!=set(sw) or set(hw)!={w['decision_cutoff'] for w in tw}:raise ValueError('All twelve windows required')
    books=[]
    for w in tw:
        d=w['decision_cutoff'];saved=read(SEARCH+'/'+d+'/search.json');search_input=read(SEARCH+'/'+d+'/inputs.json')
        if search_input['search_arguments']!=w['search_arguments'] or saved['selected']!=sw[d]['selected']:raise ValueError('Frozen per-window selection differs')
        books.extend(construct_books(w,hw[d],saved['selected']))
    if len(books)!=36:raise ValueError('Exactly36 registered comparisons required')
    OUTPUT.mkdir()
    prepared_sha=save(OUTPUT/'prepared.json',dict(books=books,source_hashes=pins,book_calls=0,search_calls=0))
    registration=dict(prepared_sha256=prepared_sha,runner_sha256=digest(__file__),source_hashes=pins,protected_before=guards(),
        maximum_book_calls=36,maximum_search_calls=0,modes=MODES,windows=12,
        fixed_denominator_per_mode=12,independent_fresh_cash_accounts=True,independent_oos=False,promotion_allowed=False,
        limitations=['Conditional parent-price returns; no dividends.','ANSS completion rights are economic receivables, not paid cash or delivered tradable shares.','Blocked books stay in denominator; no substitutions or winner promotion.'])
    print(save(OUTPUT/'registration.json',registration))


def run(registration_sha):
    if digest(OUTPUT/'registration.json')!=registration_sha:raise ValueError('Registration differs')
    if {p.name for p in OUTPUT.iterdir()}!={'registration.json','prepared.json'}:raise ValueError('Already started: inspect, never rerun')
    reg=json.loads((OUTPUT/'registration.json').read_bytes())
    if digest(__file__)!=reg['runner_sha256'] or digest(OUTPUT/'prepared.json')!=reg['prepared_sha256']:raise ValueError('Prepared implementation/input differs')
    for name,h in reg['source_hashes'].items():
        if digest(ROOT/name)!=h:raise ValueError('Source changed: '+name)
    if guards()!=reg['protected_before']:raise ValueError('Protected files changed')
    from backtest.return_priority_holding_entitlement_outcome import frozen_holding_with_entitlements
    payload=json.loads((OUTPUT/'prepared.json').read_bytes())
    save(OUTPUT/'started.json',dict(registration_sha256=registration_sha,maximum_book_calls=36,automatic_retry_allowed=False))
    summary=[]
    try:
        for book in payload['books']:
            directory=OUTPUT/book['book_id'];directory.mkdir()
            save(directory/'intent.json',dict(maximum_calls=1,mode=book['mode'],target_weights=book['outcome_arguments']['target_weights']))
            try:outcome=frozen_holding_with_entitlements(**book['outcome_arguments'])
            except (KeyError,ValueError,TypeError,ZeroDivisionError) as error:
                outcome=dict(status='BLOCKED',blocked_reason=dict(type=type(error).__name__,detail=str(error)),return_fraction=None,maximum_drawdown=None,daily_ledger=[],research_only=True)
            save(directory/'outcome.json',outcome)
            summary.append(dict(book_id=book['book_id'],decision_cutoff=book['decision_cutoff'],mode=book['mode'],status=outcome['status'],
                return_fraction=outcome.get('return_fraction'),maximum_drawdown=outcome.get('maximum_drawdown'),blocked_reason=outcome.get('blocked_reason')))
        save(OUTPUT/'result.json',dict(books=summary,book_calls=len(summary),search_calls=0,denominator_per_mode=12,independent_oos=False,promotion_allowed=False))
    finally:
        after=guards();save(OUTPUT/'protected_after.json',dict(hashes=after,unchanged=after==reg['protected_before']))
        if after!=reg['protected_before']:raise ValueError('Protected mutation detected')


if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--prepare',action='store_true');group.add_argument('--run',action='store_true');parser.add_argument('--registration-sha');args=parser.parse_args()
    if args.prepare:prepare()
    elif args.registration_sha:run(args.registration_sha)
    else:raise ValueError('Reviewed registration SHA required')
