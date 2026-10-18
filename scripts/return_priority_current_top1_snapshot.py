"""Create-only current TOP1 bootstrap registration; no account or book execution."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_top1_selector import select_top1_quantities

CODE_PATHS=[
    'scripts/return_priority_current_top1_snapshot.py',
    'scripts/return_priority_current_rebased_training.py',
    'backtest/return_priority_monthly_training_inputs.py',
    'backtest/return_priority_monthly_top1_selector.py',
    'data/current_research_capital_decision.py',
    'backtest/return_priority_fresh_cash_quantity_search.py',
]
LIMITATIONS=[
    'INITIAL_CURRENT_BOOTSTRAP: explicit 2026-10-13 research snapshot, not automatic within-month reselection.',
    'Conditional whole-source price scenarios, not certified nominal/PIT or total return; see input coordinate semantics.',
    'Exact single-stock training-product ranking is not a future-return forecast or global portfolio optimum.',
    'Fresh 20000 cash; existing holdings impose no constraint. No production or paper adoption.',
    'Zero commission is a research input; other charges are not certified zero.',
]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def save(path,value):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
def relative(path):return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
def verify(pins):
    if not pins:raise ValueError('SOURCE_PINS_REQUIRED')
    for name,expected in pins.items():
        p=Path(name)
        if p.is_absolute() or p.drive or '..' in p.parts or p.as_posix()!=name:raise ValueError('INVALID_SOURCE_PATH')
        resolved=(ROOT/p).resolve();resolved.relative_to(ROOT.resolve())
        if digest(resolved)!=expected:raise ValueError('SOURCE_CHANGED:'+name)
def validate(value):
    if value.get('status')!='READY_CONDITIONAL' or value.get('blocked_tickers'):raise ValueError('INPUT_NOT_READY')
    args=value['search_arguments']
    if args['decision_date']!='2026-10-13' or Fraction(args['entered_cash'])!=20000 or Fraction(args['fee_bps'])!=0 or Fraction(args['minimum_cash_buffer'])!=0:
        raise ValueError('BOOTSTRAP_CONSTANTS_CHANGED')
    if not args['prices'] or set(args['prices'])!=set(args['metadata']):raise ValueError('INVALID_DOMAIN')

def prepare(input_path,output):
    source=Path(input_path).resolve();source_key=relative(source);output=Path(output)
    if output.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    value=read(source);validate(value);verify(value['source_hashes'])
    pins=deepcopy(value['source_hashes']);pins[source_key]=digest(source)
    for name in CODE_PATHS:
        current=digest(ROOT/name)
        if name in pins and pins[name]!=current:raise ValueError('CODE_PIN_CONFLICT:'+name)
        pins[name]=current
    registration=dict(schema='CURRENT_TOP1_BOOTSTRAP_V1',input_path=source_key,input_sha256=digest(source),
        source_hashes=pins,decision_date='2026-10-13',initial_cash='20000',maximum_selector_calls=1,
        maximum_quantity_core_calls=0,maximum_book_calls=0,automatic_retry=False,
        role='initial_current_bootstrap',adoption_allowed=False,limitations=LIMITATIONS)
    output.mkdir(parents=True);save(output/'registration.json',registration)
    return dict(registration_sha256=digest(output/'registration.json'))

def run(output,registration_sha):
    output=Path(output);registration_path=output/'registration.json'
    if digest(registration_path)!=registration_sha:raise ValueError('REGISTRATION_CHANGED')
    if {p.name for p in output.iterdir()}!={'registration.json'}:raise ValueError('ALREADY_STARTED_NO_RETRY')
    registration=read(registration_path);verify(registration['source_hashes'])
    if registration['maximum_selector_calls']!=1 or registration['maximum_quantity_core_calls']!=0 or registration['maximum_book_calls']!=0:
        raise ValueError('INVALID_CALL_BUDGET')
    source=ROOT/registration['input_path']
    if digest(source)!=registration['input_sha256']:raise ValueError('INPUT_CHANGED')
    value=read(source);validate(value)
    save(output/'started.json',dict(registration_sha256=registration_sha,maximum_selector_calls=1,automatic_retry=False))
    try:
        selected=select_top1_quantities(**deepcopy(value['search_arguments']))
        if selected.get('status')!='SELECTOR_COMPLETE' or selected.get('selector_calls')!=1 or selected.get('core_calls')!=0:raise ValueError('SELECTOR_NOT_COMPLETE')
        args=value['search_arguments'];stocks=[]
        for sid,q in selected['selected']['quantities'].items():
            stocks.append(dict(security_id=sid,**args['metadata'][sid],units=q,close=args['prices'][sid],
                notional=str(q*Fraction(args['prices'][sid])),target_weight=selected['selected']['actual_weights'][sid]))
        result=dict(schema='CURRENT_TOP1_RESEARCH_SNAPSHOT_V1',status='COMPLETE',selector_result=selected,
            stocks=stocks,metadata=deepcopy(args['metadata']),as_of=args['decision_date'],method=selected['method'],
            budget=selected['entered_cash'],invested=selected['selected']['notional'],fees=selected['selected']['fees'],cash=selected['selected']['residual_cash'],
            source_hashes=registration['source_hashes'],registration_sha256=registration_sha,
            research_id=registration_sha[:24],role='initial_current_bootstrap',research_only=True,execution_blocked=True,
            selector_calls=1,quantity_core_calls=0,book_calls=0,global_optimum_established=False,forecast_return=None,
            coordinate_semantics=value.get('coordinate_semantics'),limitations=LIMITATIONS,adoption_allowed=False)
        save(output/'result.json',result)
        return result
    except Exception as exc:
        save(output/'failure.json',dict(status='FAILED_NO_RETRY',exception_type=type(exc).__name__,detail=str(exc),selector_attempts=1))
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--input');parser.add_argument('--output',required=True);parser.add_argument('--registration-sha')
    a=parser.parse_args()
    if a.prepare:
        if not a.input:parser.error('--input required')
        print(json.dumps(prepare(a.input,a.output)))
    else:
        if not a.registration_sha:parser.error('--registration-sha required')
        result=run(a.output,a.registration_sha);print(json.dumps(dict(status=result['status'],selector_calls=result['selector_calls'])))
