"""Create-only conditional original-weight registration and one-book entry point."""
import ast
from contextlib import contextmanager
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNNER = 'scripts/return_priority_original_weight_control_registered.py'
LOADED_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
COMPONENT = 'scripts/return_priority_original_weight_control_run.py'
PROPOSAL = 'tmp/next12_original_weight_control_inputs_proposal_20261015_v1.json'
BINDING = 'tmp/next12_original_weight_control_binding_20261015_v1.json'
PROTECTED = ('data/broker_positions.json','data/state.json','config/config.yaml',
 'data/research_paper/research_paper.sqlite3','backtest/return_priority_fresh_cash_quantity_search.py',
 'data/current_research_limit_plan.py','data/current_research_fill_ledger.py')

def require(ok, message):
    if not ok: raise ValueError(message)

def path(name):
    p=Path(name)
    return p if p.is_absolute() else ROOT/p

def digest(name): return hashlib.sha256(path(name).read_bytes()).hexdigest()

def load(name, expected):
    raw=path(name).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected, 'PIN_CHANGED:'+str(name))
    return json.loads(raw)

def save(name, value):
    with Path(name).open('x',encoding='utf-8') as f: json.dump(value,f,indent=2,allow_nan=False)

def put(pins, name, sha):
    # Normalize Windows slash aliases without permitting conflicting hashes.
    name=str(name).replace('\\','/')
    require(name not in pins or pins[name]==sha, 'CONFLICTING_PIN:'+name)
    pins[name]=sha

def verify(pins):
    for name,sha in pins.items(): require(digest(name)==sha,'PIN_CHANGED:'+name)

def method_bytes():
    """Discover local Python imports from captured bytes, including lazy imports."""
    found={}
    def visit(name):
        if name in found:return
        raw=path(name).read_bytes(); found[name]=raw
        tree=ast.parse(raw,filename=name)
        for node in ast.walk(tree):
            modules=([node.module] if isinstance(node,ast.ImportFrom) and node.module else
                     [x.name for x in node.names] if isinstance(node,ast.Import) else [])
            for mod in modules:
                candidate=mod.replace('.','/')+'.py'
                if mod.split('.')[0] in ('backtest','data','scripts') and path(candidate).is_file():visit(candidate)
    visit(COMPONENT)
    for package in ('scripts','backtest','data'):
        name=package+'/__init__.py'
        raw=path(name).read_bytes() if path(name).exists() else b''
        require(not raw.strip(), 'NONEMPTY_PACKAGE_INITIALIZER:'+package)
        if path(name).exists(): found[name]=raw
    return found

def scope(draft, proposal, binding):
    a=proposal['proposed_account']; b=binding['provider_arguments']; dates=proposal['session_dates']
    require(draft['maximum_book_calls']==1 and draft['maximum_search_calls']==0 and draft['automatic_retry'] is False,'BUDGET')
    require(draft['price_only'] is True and draft['independent_oos'] is False and draft['adoption_allowed'] is False,'LIMITATIONS')
    require(dates==draft['session_dates']==b['session_dates'] and len(dates)==251 and dates==sorted(set(dates))
            and dates[0]=='2025-07-31' and dates[-1]=='2026-07-30','CALENDAR')
    monthly=a['monthly_decision_dates']
    require(monthly==draft['monthly_decisions']==[v['decision_date'] for v in b['monthly_inputs']] and len(monthly)==12,'MONTHLY')
    require(len({dates[dates.index(d)+1][:7] for d in monthly})==12,'ACTIVE_MONTHS')
    require(a['initial_cash']==draft['initial_cash']=='20000' and a['initial_shares']==draft['initial_shares']=={}
            and a['commission_bps']==draft['commission_bps']=='0' and a['minimum_cash_buffer']==draft['minimum_cash_buffer']=='0','CAPITAL')
    require(len(proposal['metadata'])==8 and set(proposal['metadata'])==set(proposal['target_weights'])==set(proposal['ohlc'])
            and proposal['target_weights']==b['weights'] and b['actions']==[],'DOMAIN')
    require(b['close_prices']=={sid:{d:v['close'] for d,v in bars.items()} for sid,bars in proposal['ohlc'].items()},'CLOSE_COORDINATE')
    for m in b['monthly_inputs']:
        require(m['search_arguments']=={'fee_bps':'0','minimum_cash_buffer':'0'},'NO_SEARCH_PARAMETERS')
        require({q['security_id']:q['price'] for q in m['valuation_quotes']}==
                {sid:b['close_prices'][sid][m['decision_date']] for sid in b['weights']},'MONTHLY_QUOTES')

@contextmanager
def isolated(captured):
    names={(p[:-12] if p.endswith('/__init__.py') else p[:-3]).replace('/','.'):raw for p,raw in captured.items()}
    packages={p[:-12].replace('/','.') for p in captured if p.endswith('/__init__.py')}
    cached_packages={n for n in packages if n in sys.modules}
    require(not any(n in sys.modules for n in names if n not in packages),'CACHED_METHOD_REFUSED')
    class Loader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            return importlib.util.spec_from_loader(fullname,self,is_package=fullname in packages) if fullname in names else None
        def create_module(self,spec): return None
        def exec_module(self,module):
            filename=str(ROOT/(module.__name__.replace('.','/')+'.py'))
            module.__file__=filename
            exec(compile(names[module.__name__],filename,'exec'),module.__dict__)
    loader=Loader(); sys.meta_path.insert(0,loader)
    parents={}
    for n in names:
        parent,_,child=n.rpartition('.')
        if parent in sys.modules: parents[(parent,child)]=getattr(sys.modules[parent],child,None)
    try:
        yield importlib.import_module(COMPONENT[:-3].replace('/','.'))
    finally:
        sys.meta_path.remove(loader)
        for n in names:
            if n in cached_packages: continue
            sys.modules.pop(n,None)
            parent,_,child=n.rpartition('.')
            if parent in sys.modules and hasattr(sys.modules[parent],child):
                old=parents.get((parent,child))
                if old is None:delattr(sys.modules[parent],child)
                else:setattr(sys.modules[parent],child,old)

def register(*,draft_path,review_path,runner_review_path,output):
    entries={str(x):digest(x) for x in (draft_path,review_path,runner_review_path)}
    draft,review,gate=[load(x,entries[str(x)]) for x in (draft_path,review_path,runner_review_path)]
    require(review.get('status')=='PASS_CONDITIONAL_INPUT_AND_SYNTHETIC_MECHANICS_REQUIRES_SEPARATE_RUN_REGISTRATION'
            and review.get('independent_review') is True,'INDEPENDENT_REVIEW_REQUIRED')
    require(gate.get('status')=='PASS' and gate.get('root_checked') is True
            and gate.get('reviewed_source_hashes',{}).get(RUNNER)==LOADED_SHA,'RUNNER_REVIEW_REQUIRED')
    pins={}
    for n,h in draft['source_hashes'].items():put(pins,n,h)
    for n,h in pins.items():require(review['reviewed_source_hashes'].get(n,review['reviewed_source_hashes'].get(n.replace('/','\\')))==h,'REVIEW_PIN:'+n)
    require(review['reviewed_source_hashes'].get(str(draft_path))==entries[str(draft_path)],'DRAFT_REVIEW_PIN')
    for n,h in entries.items():put(pins,n,h)
    put(pins,RUNNER,LOADED_SHA)
    captured=method_bytes(); methods={n:hashlib.sha256(raw).hexdigest() for n,raw in captured.items()}
    for n,h in methods.items():
        require(review['reviewed_source_hashes'].get(n)==h or gate.get('reviewed_source_hashes',{}).get(n)==h,'METHOD_REVIEW_PIN:'+n)
        put(pins,n,h)
    for n,h in draft['protected_before'].items():put(pins,n,h)
    require(set(draft['protected_before'])==set(PROTECTED),'PROTECTED_SCOPE')
    verify(pins)
    scope(draft,load(PROPOSAL,pins[PROPOSAL]),load(BINDING,pins[BINDING]))
    directory=path(output);directory.mkdir()
    save(directory/'registration.json',dict(schema='ORIGINAL_WEIGHT_CONTROL_SINGLE_RUN_V1',source_hashes=pins,
        method_hashes=methods,draft_path=str(draft_path),review_path=str(review_path),runner_review_path=str(runner_review_path),
        protected_before=draft['protected_before'],maximum_book_calls=1,maximum_search_calls=0,automatic_retry=False))

def run(*,directory,registration_sha256):
    directory=path(directory)
    reg=load(directory/'registration.json',registration_sha256)
    require(set(p.name for p in directory.iterdir())=={'registration.json'},'ALREADY_STARTED_OR_UNEXPECTED_OUTPUT')
    pins=reg['source_hashes'];verify(pins)
    require(pins[RUNNER]==LOADED_SHA==digest(RUNNER),'RUNNER_CHANGED')
    require(reg['schema']=='ORIGINAL_WEIGHT_CONTROL_SINGLE_RUN_V1' and reg['maximum_book_calls']==1
            and reg['maximum_search_calls']==0 and reg['automatic_retry'] is False,'REGISTRATION_SCOPE')
    require(set(reg['protected_before'])==set(PROTECTED),'PROTECTED_SCOPE')
    for n,h in reg['protected_before'].items():require(pins[n]==h,'PROTECTED_BINDING')
    draft=load(reg['draft_path'],pins[reg['draft_path']]);proposal=load(PROPOSAL,pins[PROPOSAL]);binding=load(BINDING,pins[BINDING])
    review=load(reg['review_path'],pins[reg['review_path']]); gate=load(reg['runner_review_path'],pins[reg['runner_review_path']])
    require(review.get('status')=='PASS_CONDITIONAL_INPUT_AND_SYNTHETIC_MECHANICS_REQUIRES_SEPARATE_RUN_REGISTRATION' and review.get('independent_review') is True and review.get('reviewed_source_hashes',{}).get(reg['draft_path'])==pins[reg['draft_path']], 'REVIEW_BINDING')
    require(gate.get('status')=='PASS' and gate.get('root_checked') is True and gate.get('reviewed_source_hashes',{}).get(RUNNER)==LOADED_SHA,'RUNNER_GATE')
    scope(draft,proposal,binding)
    captured=method_bytes()
    require({n:hashlib.sha256(raw).hexdigest() for n,raw in captured.items()}==reg['method_hashes'],'METHOD_CLOSURE_CHANGED')
    require(all(pins[n]==h for n,h in reg['method_hashes'].items()),'METHOD_PIN_MISMATCH')
    # Refuse stale imports before any book intent; execute exactly the verified captured bytes.
    require(not any(n[:-3].replace('/','.') in sys.modules for n in captured),'CACHED_METHOD_REFUSED')
    save(directory/'started.json',dict(registration_sha256=registration_sha256,maximum_book_calls=1,search_calls=0,automatic_retry=False))
    try:
        with isolated(captured) as module:
            result=module.execute_control(proposal=proposal,binding=binding,directory=directory/'book')
        verify(pins)
        save(directory/'result.json',dict(result=result,book_calls=1,search_calls=0,price_only=True,independent_oos=False,adoption_allowed=False))
        return result
    except BaseException as error:
        save(directory/'failure.json',dict(type=type(error).__name__,message=str(error),automatic_retry=False))
        raise
    finally:
        after={n:digest(n) if path(n).exists() else None for n in PROTECTED}
        save(directory/'protected_after.json',dict(hashes=after,unchanged=after==reg['protected_before']))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('register')
    for name in ('draft-path','review-path','runner-review-path','output'):a.add_argument('--'+name,required=True)
    a=sub.add_parser('run');a.add_argument('--directory',required=True);a.add_argument('--registration-sha256',required=True)
    args=vars(p.parse_args());mode=args.pop('mode');globals()[mode](**args)
