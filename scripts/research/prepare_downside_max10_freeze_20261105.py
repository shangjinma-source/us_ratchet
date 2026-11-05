"""Read-only dependency freeze preparation. Does not execute account runner."""
from pathlib import Path
import ast,json
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]
ROOTS=['scripts/research/run_downside_account_candidate_20261105.py','docs/candidates/qqq_risk_budget_account_runner.py','docs/candidates/downside_account_selection_20261105.py','docs/candidates/downside_bounded_execution_supplement_20261105.py','scripts/run_recent_continuous_probe.py','scripts/run_old_continuous_probe_v4.py','scripts/assemble_old_continuous_inputs_v1.py','tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py']


def dependency_closure(roots):
    visited=set();pending=list(roots)
    while pending:
        name=pending.pop()
        if name in visited:continue
        path=ROOT/name
        if not path.is_file():raise ValueError('MISSING_LOCAL_MODULE:'+name)
        visited.add(name);tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            modules=[]
            if isinstance(node,ast.Import):modules=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom):
                base=node.module or ''
                if node.level:
                    parent=Path(name).parent.parts
                    base='.'.join((*parent[:len(parent)-node.level+1],*base.split('.'))).strip('.')
                modules=[base]+[base+'.'+a.name for a in node.names if a.name!='*']
            for module in modules:
                for candidate in (module.replace('.','/')+'.py',module.replace('.','/')+'/__init__.py'):
                    if (ROOT/candidate).is_file() and candidate not in visited:pending.append(candidate)
    return visited


def main():
    out=ROOT/'research_contracts/downside_max10_20261105';out.mkdir(exist_ok=False,parents=True)
    prior=json.loads((ROOT/'tmp/downside_frontier_preflight_20261105/result.json').read_bytes())
    pins={}
    def add(name,expected=None):
        h=sha256((ROOT/name).read_bytes()).hexdigest()
        if expected is not None and h!=expected:raise ValueError('PRIOR_PIN_CHANGED:'+name)
        if name in pins and pins[name]!=h:raise ValueError('CONFLICTING_PIN:'+name)
        pins[name]=h
    for name,h in prior['source_hashes'].items():add(name,h)
    for name in dependency_closure(ROOTS):add(name)
    for window,base,price in [('2021_2023','recent_continuous_baseline_20261026_v7','recent_execution_prices_20261026'),('2024_2026','old_continuous_baseline_20261026_v9','old_window_execution_prices_20261026')]:
        for name in ('tmp/'+base+'/execution_inputs.json','tmp/'+base+'/book.json','tmp/'+price+'/execution_prices_v1.json','tmp/trend_'+window+'_20261026_v1/execution_inputs.json'):add(name)
    for name in ('tmp/equal_four_20261105/source_review/admitted_supplement.json','tmp/risk_budget_64d_inventory_20261105/bounded_supplement.json'):
        document=json.loads((ROOT/name).read_bytes());add(name)
        for source,h in document['source_hashes'].items():add(source,h)
    for name in ('docs/candidates/downside_account_execution_contract_20261105.md','scripts/research/prepare_downside_max10_freeze_20261105.py'):add(name)
    (out/'freeze.json').write_text(json.dumps(dict(schema='DOWNSIDE_MAX10_EXECUTION_V1',status='READY_FOR_FIXED_MAX10_EXECUTION',max_holdings=10,windows={'2021_2023':36,'2024_2026':31},seconds_per_window=10800,seconds_per_month=600,source_hashes=pins,local_import_closure=sorted(dependency_closure(ROOTS)),dynamic_import_roots=ROOTS,limitation='Freeze is code/input integrity, not proof of economic fitness or complete external action evidence.'),indent=2),encoding='utf-8')
    print(len(pins))

if __name__=='__main__':main()
