"""Read-only bound inventory. Prints report; never creates worker namespace."""
import ast,hashlib,json,shutil
from pathlib import Path
from backtest import ndx_double_replacement_resource_bounds_research as bounds
from backtest import ndx_double_replacement_domain_research as domain
from backtest import ndx_double_replacement_cached_evaluation_research as evaluator
ROOT=Path(__file__).resolve().parents[1]
def run():
    pins={'backtest/ndx_double_replacement_cached_evaluation_research.py':'93da67c1f0011dc8b183a3085ccf96b114c6d9b14357a1cfeb292e0f3609ebfa','backtest/ndx_double_replacement_domain_research.py':'334af655e4d30a928af9d965b1c63bfe664c5c9a633dca3591bfac7f8130d4b6','backtest/ndx_two_positive_integer_budget_domain_research.py':'081a1d3a72c78c3e4637fa25b3845853a610c33608bfd5b4b2ee8ccdca2dc5e1'}
    worker=ROOT/'scripts/ndx_double_replacement_compressed_worker_20261008.py';worker_raw=worker.read_bytes()
    assert hashlib.sha256(worker_raw).hexdigest()=='60620b656ad14e31899aa5b1b64652a0b29983f9b8e97b75f7d5a685c183a92d'
    declaration=next(n for n in ast.parse(worker_raw).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BOUND' for t in n.targets))
    pins.update({p:h for p,h in ast.literal_eval(declaration.value).values()});pins[str(worker.relative_to(ROOT))]=hashlib.sha256(worker_raw).hexdigest()
    for own in (Path(__file__),Path(bounds.__file__)):pins[str(own.resolve().relative_to(ROOT))]=hashlib.sha256(own.read_bytes()).hexdigest()
    for name,digest in pins.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
    path=ROOT/'data/cache/research/double_replacement_preparation_20261003_v1/preparation.json';raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='fca04682cbda564a2f22d315894e7300c70d2f5d94d661adb16150cf5318c3f0'
    prepared=json.loads(raw)['preparation'];d=prepared['document']
    assert domain.digest(d)==prepared['content_sha256']=='11ae1bc652249682337a67b18d1cc2fecbdebee1c31b341f5565ee6c4430d819'
    # Evaluate only the outer return-constructor AST, never the function body or point helper.
    source=Path(evaluator.__file__);tree=ast.parse(source.read_bytes())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='evaluate_explicit_double_replacement_plans_cached')
    expression=ast.Expression(function.body[-1].value)
    env=dict(evaluator.__dict__);env.update(d=d,validated_content_sha256=prepared['content_sha256'],supplied=[],results=[],counts=dict.fromkeys(('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','NOT_EVALUATED_BUDGET','NOT_EVALUATED_TECHNICAL_STOP'),10000),caches={},cache_hits=10000,max_evaluations=10000,stopped=False)
    header=eval(compile(expression,str(source),'eval'),env)
    for key in ('pair_cache_count','pair_cache_hit_count','supplied_plan_count','max_evaluations','completed_evaluation_count'):header[key]=10000
    header['unsupplied_integer_count']=d['integer_count'];header['status']='ALL_SUPPLIED_EVALUATED'
    header_bytes=len(bounds.encode(header))
    rows=[bounds.pair_bound(c,p,rule=domain.RULE,flags=domain.FLAGS,checks=evaluator.CHECKS,full_count=d['integer_count']) for c in d['cases'] for p in c['pairs'] if p['enumerable_integer_count']]
    assert sum(r['count'] for r in rows)==52406569
    for name,digest in pins.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
    return dict(source_hashes=pins,schema='DOUBLE_NORMAL_RETURN_RESOURCE_BOUND_RESEARCH_V1',preparation_sha256=hashlib.sha256(raw).hexdigest(),prepared_bytes=len(raw),prepared_content_sha256=prepared['content_sha256'],header_bytes_upper=header_bytes,enumerable_pairs=len(rows),maxima={k:max(r[k] for r in rows) for k in ('row_bytes','quantity_max','money_chars','weight_chars','effective_chars','l1_chars','task_bytes')},configurations=[bounds.aggregate(rows,header_bytes,n) for n in (512,1000,5000,10000)],disk_free_bytes={drive:shutil.disk_usage(drive+':/').free for drive in ('D','E')},evaluator_point_calls=0,inspector_point_calls=0,metadata_disk_bytes_proved=False,memory_bytes_proved=False,dispatch_authorized=False)
if __name__=='__main__':print(json.dumps(run(),indent=2))
